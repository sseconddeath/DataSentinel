import sqlite3, os, sys, datetime, hmac, hashlib, base64
from collections import Counter
from cryptography.fernet import Fernet

if sys.platform == "win32":
    import ctypes, ctypes.wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD),
                     ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _dpapi_protect(data: bytes) -> bytes:
        blob_in = _DATA_BLOB(len(data),
            ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                        ctypes.POINTER(ctypes.c_char)))
        blob_out = _DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
                ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)):
            raise OSError("CryptProtectData failed")
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result

    def _dpapi_unprotect(data: bytes) -> bytes:
        blob_in = _DATA_BLOB(len(data),
            ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                        ctypes.POINTER(ctypes.c_char)))
        blob_out = _DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 0,
                ctypes.byref(blob_out)):
            raise OSError("CryptUnprotectData failed")
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result

class DBManager:
    """
    Оптимизированная БД:
    - Persistent connection вместо открытия на каждый запрос
    - WAL mode для быстрых записей
    - Индексы на часто запрашиваемые поля
    - Кэш настроек в памяти
    """
    def __init__(self, db_dir="data", db_name="storage.db", key_name="secret.key"):
        self.db_path  = os.path.join(db_dir, db_name)
        self.key_path = os.path.join(db_dir, key_name)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        self._init_encryption()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")    # быстрые записи
        self._conn.execute("PRAGMA synchronous=NORMAL")  # баланс скорость/надёжность
        self._conn.execute("PRAGMA cache_size=4000")     # 4MB кэш страниц
        self._conn.execute("PRAGMA temp_store=MEMORY")   # временные данные в RAM
        self._init_db()
        self._settings_cache: dict = {}   # кэш настроек в памяти
        self._migrate_legacy_last_scan()

    def _migrate_legacy_last_scan(self):
        """Старые версии писали 'last_scan' без шифрования. Перезаписываем
        в зашифрованном виде, чтобы убрать warning [db] decrypt failed."""
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key='last_scan'").fetchone()
        if not row or not row[0]:
            return
        raw = row[0]
        # Лимит размера + жёсткие проверки на подозрительные значения:
        # БД на диске может быть подменена локальным процессом, и без проверок
        # мы могли бы записать nan/inf/мусор обратно в settings.
        if len(raw) > 64:
            return
        # Если уже шифрованное — расшифруется без ошибки.
        try:
            self.cipher.decrypt(raw.encode())
            return
        except Exception:
            pass
        # Иначе ожидаем legacy-формат: конечный неотрицательный timestamp.
        try:
            ts = float(raw)
        except (ValueError, OverflowError):
            return
        import math
        # Разумный диапазон (после 2000 года и до 2100), не nan/inf:
        if not math.isfinite(ts) or ts < 946684800.0 or ts > 4102444800.0:
            return
        self.set_setting("last_scan", str(ts))

    def _init_encryption(self):
        if not os.path.exists(self.key_path):
            key_data = Fernet.generate_key()
            self._save_key(key_data)
        else:
            key_data = self._load_key()
        self.cipher = Fernet(key_data)
        self._hmac_key = base64.urlsafe_b64decode(key_data)

    def _save_key(self, key_data: bytes):
        if sys.platform == "win32":
            with open(self.key_path, "wb") as f:
                f.write(_dpapi_protect(key_data))
        else:
            with open(self.key_path, "wb") as f:
                f.write(key_data)

    def _load_key(self) -> bytes:
        with open(self.key_path, "rb") as f:
            raw = f.read()
        if sys.platform == "win32":
            if len(raw) == 44:
                # Миграция: незащищённый ключ → DPAPI
                self._save_key(raw)
                return raw
            return _dpapi_unprotect(raw)
        return raw

    def _hmac_hash(self, *parts: str) -> str:
        data = "\0".join(parts).encode()
        return hmac.new(self._hmac_key, data, hashlib.sha256).hexdigest()

    def encrypt_val(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt_val(self, token: str) -> str:
        try:
            return self.cipher.decrypt(token.encode()).decode()
        except Exception:
            if token:
                print(f"[db] decrypt failed for value (len={len(token)})", flush=True)
            return ""

    def _init_db(self):
        c = self._conn
        c.execute('''CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT, type TEXT DEFAULT "Email")''')
        c.execute('''CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT, source TEXT, breach_name TEXT, detail TEXT,
            url TEXT, scanned_at TEXT, is_new INTEGER DEFAULT 1,
            dedup_hash TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)''')
        # Кэш новостей: ключ — link (URL статьи). Содержимое RSS-фидов
        # публичное, так что без шифрования (и чтобы можно было искать LIKE).
        c.execute('''CREATE TABLE IF NOT EXISTS news_cache (
            link TEXT PRIMARY KEY,
            lang TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            pub_date INTEGER,
            excerpt TEXT,
            image_path TEXT,
            full_html TEXT,
            is_read INTEGER DEFAULT 0,
            fetched_at INTEGER NOT NULL)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_news_lang_date
            ON news_cache(lang, pub_date DESC)''')
        # Миграция: если БД создавалась прошлой версией без full_html.
        news_cols = {r[1] for r in c.execute("PRAGMA table_info(news_cache)")}
        if "full_html" not in news_cols:
            c.execute("ALTER TABLE news_cache ADD COLUMN full_html TEXT")

        cols = {r[1] for r in c.execute("PRAGMA table_info(scan_results)")}
        if "dedup_hash" not in cols:
            c.execute("ALTER TABLE scan_results ADD COLUMN dedup_hash TEXT")

        c.execute("DROP INDEX IF EXISTS idx_results_target")
        c.execute("DROP INDEX IF EXISTS idx_results_dedup")
        c.execute("CREATE INDEX IF NOT EXISTS idx_results_new ON scan_results(is_new)")
        # Старый баг: индекс мог быть создан без UNIQUE, и `CREATE UNIQUE INDEX IF
        # NOT EXISTS` его не пересоздавал. Проверяем явно через PRAGMA и при
        # необходимости дропаем + чистим дубли + создаём заново.
        idx_info = c.execute(
            "SELECT \"unique\" FROM pragma_index_list('scan_results') "
            "WHERE name='idx_results_dedup_hash'").fetchone()
        if idx_info is not None and idx_info[0] == 0:
            c.execute("DROP INDEX idx_results_dedup_hash")
            self._dedup_existing_results()
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_results_dedup_hash "
                  "ON scan_results(dedup_hash)")
        c.commit()
        self._migrate_scan_results()

    def _dedup_existing_results(self):
        """Удаляет дубли в scan_results, оставляя самую раннюю запись на
        каждый dedup_hash. Запускается один раз при миграции старого
        не-UNIQUE индекса."""
        before = self._conn.execute(
            "SELECT COUNT(*) FROM scan_results").fetchone()[0]
        # Оставляем строку с минимальным id (= самая ранняя по времени вставки).
        self._conn.execute(
            "DELETE FROM scan_results WHERE id NOT IN ("
            "  SELECT MIN(id) FROM scan_results "
            "  WHERE dedup_hash IS NOT NULL "
            "  GROUP BY dedup_hash"
            ") AND dedup_hash IS NOT NULL")
        after = self._conn.execute(
            "SELECT COUNT(*) FROM scan_results").fetchone()[0]
        removed = before - after
        if removed:
            print(f"[db] dedup migration: removed {removed} duplicate rows "
                  f"({before} → {after})", flush=True)

    def _migrate_scan_results(self):
        rows = self._conn.execute(
            "SELECT id, target, source, breach_name, detail, url "
            "FROM scan_results WHERE dedup_hash IS NULL").fetchall()
        if not rows:
            return
        for rid, target, source, breach_name, detail, url in rows:
            dedup = self._hmac_hash(target, source, breach_name)
            self._conn.execute(
                "UPDATE scan_results SET target=?, source=?, breach_name=?, "
                "detail=?, url=?, dedup_hash=? WHERE id=?",
                (self.encrypt_val(target), self.encrypt_val(source),
                 self.encrypt_val(breach_name or ""),
                 self.encrypt_val(detail or ""),
                 self.encrypt_val(url or ""), dedup, rid))
        self._conn.commit()
        # VACUUM убирает старые страницы с открытым текстом из файла БД
        self._conn.execute("VACUUM")

    def add_target(self, value: str):
        t_type = "Email" if "@" in value else "Password"
        self._conn.execute("INSERT INTO targets (value, type) VALUES (?, ?)",
                     (self.encrypt_val(value), t_type))
        self._conn.commit()

    def delete_target(self, t_id: int):
        self._conn.execute("DELETE FROM targets WHERE id=?", (t_id,))
        self._conn.commit()

    def get_all_targets(self):
        rows = self._conn.execute("SELECT id, value FROM targets").fetchall()
        return [(r[0], self.decrypt_val(r[1])) for r in rows]

    def save_result(self, target, source, breach_name, detail, url) -> bool:
        """INSERT OR IGNORE: если утечка уже есть в БД (по dedup_hash) —
        ничего не трогаем. Старая запись сохраняет свою дату находки и
        состояние is_new — пере-скан не «освежает» её. Возвращает True
        только при действительно новой записи."""
        dedup = self._hmac_hash(target, source, breach_name)
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO scan_results "
            "(target,source,breach_name,detail,url,scanned_at,is_new,dedup_hash)"
            " VALUES (?,?,?,?,?,?,1,?)",
            (self.encrypt_val(target), self.encrypt_val(source),
             self.encrypt_val(breach_name), self.encrypt_val(detail or ""),
             self.encrypt_val(url or ""),
             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dedup))
        self._conn.commit()
        return cur.rowcount > 0

    def get_results_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]

    def get_all_results(self):
        rows = self._conn.execute(
            "SELECT id,target,source,breach_name,detail,url,scanned_at,is_new "
            "FROM scan_results ORDER BY is_new DESC, scanned_at DESC").fetchall()
        return [(r[0], self.decrypt_val(r[1]), self.decrypt_val(r[2]),
                 self.decrypt_val(r[3]), self.decrypt_val(r[4]),
                 self.decrypt_val(r[5]), r[6], r[7]) for r in rows]

    def get_results_for_chart(self):
        return self._conn.execute(
            "SELECT substr(scanned_at,1,10), COUNT(*) FROM scan_results "
            "GROUP BY substr(scanned_at,1,10) ORDER BY scanned_at").fetchall()

    def get_sources_summary(self):
        rows = self._conn.execute("SELECT source FROM scan_results").fetchall()
        counts = Counter(self.decrypt_val(r[0]) for r in rows)
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)

    def get_fresh_sources(self) -> list:
        """Источники только «свежих» (is_new=1) утечек — для текущего risk-score
        и индикатора «Обнаружена угроза!». Старые утечки в счёт не идут."""
        rows = self._conn.execute(
            "SELECT source FROM scan_results WHERE is_new=1").fetchall()
        return [self.decrypt_val(r[0]) for r in rows]

    def mark_all_seen(self):
        self._conn.execute("UPDATE scan_results SET is_new=0 WHERE is_new=1")
        self._conn.commit()

    def age_old_results(self, seconds: int = 2 * 24 * 3600) -> int:
        """Снимает is_new=1 со старых записей: запись считается «новой»
        N секунд после первого обнаружения. Возвращает число затронутых
        строк — UI может перерисоваться если что-то изменилось."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(seconds=seconds)
                  ).strftime("%Y-%m-%d %H:%M:%S")
        cur = self._conn.execute(
            "UPDATE scan_results SET is_new=0 "
            "WHERE is_new=1 AND scanned_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def clear_results(self):
        self._conn.execute("DELETE FROM scan_results")
        self._conn.commit()

    def set_setting(self, key: str, value: str):
        enc = self.encrypt_val(value)
        self._conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                     (key, enc))
        self._conn.commit()
        self._settings_cache[key] = value   # обновляем кэш

    def delete_setting(self, key: str):
        """Полностью удаляет запись из БД."""
        self._conn.execute("DELETE FROM settings WHERE key=?", (key,))
        self._conn.commit()
        self._settings_cache.pop(key, None)

    def get_setting(self, key: str, default: str = "") -> str:
        if key in self._settings_cache:
            return self._settings_cache[key]
        res = self._conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        val = self.decrypt_val(res[0]) if res else default
        self._settings_cache[key] = val
        return val

    def set_api_key(self, service: str, key: str):
        if key:
            self.set_setting(f"api_key_{service}", key)
        else:
            self.delete_setting(f"api_key_{service}")

    def get_api_key(self, service: str) -> str:
        return self.get_setting(f"api_key_{service}", "")

    def save_smtp(self, host, port, user, password, recipient, provider):
        # Батч-запись за одну транзакцию
        pairs = [
            ("smtp_host",      host),
            ("smtp_port",      str(port)),
            ("smtp_user",      user),
            ("smtp_pass",      password),
            ("smtp_recipient", recipient),
            ("smtp_provider",  provider),
        ]
        for k, v in pairs:
            self._conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                         (k, self.encrypt_val(v)))
            self._settings_cache[k] = v
        self._conn.commit()

    def get_smtp(self) -> dict:
        return {
            "host":      self.get_setting("smtp_host"),
            "port":      int(self.get_setting("smtp_port", "587")),
            "user":      self.get_setting("smtp_user"),
            "password":  self.get_setting("smtp_pass"),
            "recipient": self.get_setting("smtp_recipient"),
            "provider":  self.get_setting("smtp_provider", "Gmail"),
        }

    def set_last_scan(self, ts: float):
        # Шифруем как любую другую настройку — раньше писали plain,
        # из-за чего get_setting() не мог дешифровать (warning + return 0).
        self.set_setting("last_scan", str(ts))

    def get_last_scan(self) -> float:
        val = self.get_setting("last_scan", "0")
        try:
            return float(val)
        except ValueError:
            return 0.0

    def cache_news_items(self, lang: str, items: list) -> int:
        """Upsert: обновляем title/excerpt/date по link, но не сбрасываем
        is_read=1 если статью уже отметили прочитанной. Сохраняем старый
        image_path, если новый — None (картинка не успела докачаться).

        Возвращает количество именно НОВЫХ записей (link не было в БД)."""
        import time as _t
        now = int(_t.time())
        new_count = 0
        for it in items:
            link = (it.get("link") or "").strip()
            if not link:
                continue
            exists = self._conn.execute(
                "SELECT 1 FROM news_cache WHERE link=? LIMIT 1",
                (link,)).fetchone()
            if exists is None:
                new_count += 1
            pub = it.get("date")
            pub_ts = None
            try:
                if pub is not None:
                    if hasattr(pub, "timestamp"):
                        # qt_news._parse_pubdate возвращает naive datetime,
                        # представляющий UTC. Python .timestamp() на naive
                        # datetime трактует его как LOCAL и сдвигает на
                        # tz offset (для UTC+5 даёт -5h). Берём calendar.
                        # timegm — он корректно считает naive как UTC.
                        if pub.tzinfo is None:
                            import calendar
                            pub_ts = calendar.timegm(pub.timetuple())
                        else:
                            pub_ts = int(pub.timestamp())
                    else:
                        pub_ts = int(pub)
            except Exception:
                pub_ts = None
            # Кламп pub_date в будущее: некоторые RSS (DarkReading) изредка
            # отдают timestamp на дни вперёд (внутренние scheduled-публикации
            # или баг на их стороне). Допускаем небольшой запас 1 час
            # на расхождение часов; всё что дальше — приводим к now.
            if pub_ts is not None and pub_ts > now + 3600:
                pub_ts = now
            self._conn.execute(
                """INSERT INTO news_cache
                   (link, lang, source, title, pub_date, excerpt, image_path,
                    full_html, is_read, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                   ON CONFLICT(link) DO UPDATE SET
                     source=excluded.source,
                     title=excluded.title,
                     pub_date=excluded.pub_date,
                     excerpt=excluded.excerpt,
                     image_path=COALESCE(excluded.image_path, news_cache.image_path),
                     full_html=COALESCE(NULLIF(excluded.full_html, ''),
                                         news_cache.full_html),
                     fetched_at=excluded.fetched_at""",
                (link, lang, it.get("source") or "",
                 it.get("title") or "", pub_ts,
                 it.get("excerpt") or "", it.get("image_path"),
                 it.get("full_html") or "", now))
        self._conn.commit()
        return new_count

    def get_cached_news(self, lang: str, limit: int = 30) -> list[dict]:
        """Вернёт топ-N статей по pub_date (свежие сверху)."""
        import datetime as _dt
        rows = self._conn.execute(
            "SELECT link, lang, source, title, pub_date, excerpt, image_path,"
            " full_html, is_read FROM news_cache WHERE lang=? "
            "ORDER BY COALESCE(pub_date, 0) DESC, fetched_at DESC LIMIT ?",
            (lang, limit)).fetchall()
        out = []
        for (link, lng, src, title, pub_ts, excerpt, image_path,
             full_html, is_read) in rows:
            d = None
            if pub_ts:
                try:
                    # pub_ts хранится как UTC Unix timestamp. Конвертим
                    # в локальное время для отображения. Убираем tzinfo
                    # (naive local), потому что delegate/reader делают
                    # обычный strftime без tz-форматирования.
                    d = (_dt.datetime
                          .fromtimestamp(int(pub_ts), tz=_dt.timezone.utc)
                          .astimezone()
                          .replace(tzinfo=None))
                except Exception:
                    d = None
            out.append({
                "link": link, "source": src, "title": title,
                "date": d, "excerpt": excerpt or "",
                "image_path": image_path, "full_html": full_html or "",
                "is_read": bool(is_read),
            })
        return out

    def mark_news_read(self, link: str):
        self._conn.execute(
            "UPDATE news_cache SET is_read=1 WHERE link=?", (link,))
        self._conn.commit()

    def cleanup_old_news(self, days: int = 30):
        """Удаляет записи старше N дней. Картинки в data/news_cache/ не
        трогаем — они шарятся между записями по sha1 от URL."""
        import time as _t
        cutoff = int(_t.time()) - days * 86400
        cur = self._conn.execute(
            "DELETE FROM news_cache WHERE fetched_at < ?", (cutoff,))
        self._conn.commit()
        if cur.rowcount:
            print(f"[db] news_cache: removed {cur.rowcount} rows older "
                  f"than {days}d", flush=True)

    def close(self):
        """Закрыть соединение при выходе."""
        try:
            self._conn.close()
        except Exception:
            pass
