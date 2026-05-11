import hashlib, requests, time, random, string, secrets, math
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Встроенные API-ключи (XOR-обфускация). Подробности — в services/ai_assistant.py.
# В git-репо это пустые stub'ы; build_inject.py inject подставляет реальные значения
# из secrets.local перед PyInstaller'ом и затем восстанавливает stub.
_RA = b''
_RB = b''
_IA = b''
_IB = b''

def _builtin_rapidapi() -> str:
    return bytes(a ^ b for a, b in zip(_RA, _RB)).decode() if _RA and _RB else ""

def _builtin_intelx() -> str:
    return bytes(a ^ b for a, b in zip(_IA, _IB)).decode() if _IA and _IB else ""

# Словарь для memorable-паролей (короткий, встроенный)
WORD_LIST = [
    "apple","brave","cloud","dance","eagle","flame","grace","happy","ivory","joker",
    "karma","lemon","mango","noble","ocean","pearl","quest","river","solar","tiger",
    "ultra","vivid","whale","xenon","yacht","zebra","amber","blaze","crisp","delta",
    "emerald","frost","giant","honey","ideal","jade","knack","lunar","magic","nexus",
    "orbit","piano","quartz","rapid","stone","torch","unity","valor","windy","pixel",
    "cyber","storm","sharp","swift","cedar","birch","maple","cliff","dunes","fjord",
    "grove","haven","inlet","lagoon","marsh","north","oasis","prism","ridge","savoy",
    "thorn","umbra","vault","wagon","xerox","yield","zephyr","acorn","basin","comet",
    "drake","envoy","forge","glint","heron","index","jewel","kiosk","laser","monks",
    "nymph","onyx","plume","queen","raven","sphinx","trout","ulcer","viola","waltz",
    "axiom","baron","cubic","demon","ether","fable","gloom","hazel","ingot","jinx",
    "knave","lyric","metal","nomad","optic","proxy","quota","realm","sigma","talon",
    "unify","vapor","witch","oxide","plank","rocky","siren","tutor","urban","venom",
    "wheat","exile","flint","gnome","hyper","irony","kazoo","llama","moose","naive",
    "otter","panda","quirk","robin","stoic","tepid","usher","viper","walrus","xerus",
    "yodel","zonal","adept","bison","cobra","dingo","eland","finch","gecko","hippo",
    "impel","jaunt","kayak","llano","merlin","newt","okapi","puffin","quail","rhino",
    "skunk","tapir","urial","vixen","wyvern","xebec","yak","zorilla","abbot","brine",
    "chasm","depot","ember","flare","glyph","haste","inbox","japan","karma","lucid",
    "manor","Norse","oboe","perch","quota","relic","scout","tidal","usurp","vigor",
    "wrath","xylem","yeoman","zilch","acrid","brawl","crest","dwarf","epoch","facet",
    "grail","homer","imply","joust","kneel","latch","motif","notch","opaque","pivot",
    "qualm","rivet","scorn","taboo","unwed","verge","whirl","expel","fleck","guile",
    "haunt","infer","jumbo","leech","myrrh","nudge","onset","parch","quirky","rogue",
    "scamp","truce","udder","vouch","whelp","exert","frown","gripe","heist","impede",
    "joker","kudos","leapt","mirth","notch","outdo","prowl","qualm","reach","scald",
    "taint","undue","voila","wager","expat","finesse","gusto","havoc","impish","jamb",
]

class LeakEngine:
    RAPID_API_KEY  = _builtin_rapidapi()
    INTELX_API_KEY = _builtin_intelx()
    INTELX_HOST    = "https://free.intelx.io"

    # Единая сессия с retry и connection pooling
    _retry = Retry(
        total=2,                    # макс 2 повтора
        backoff_factor=0.5,         # пауза между попытками: 0.5, 1.0 сек
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    _adapter = HTTPAdapter(
        max_retries=_retry,
        pool_connections=4,         # пул соединений
        pool_maxsize=8,
    )
    session = requests.Session()
    session.mount("https://", _adapter)
    session.mount("http://",  _adapter)

    # Таймаут по умолчанию (connect, read)
    TIMEOUT = (5, 15)

    @staticmethod
    def get_headers():
        return {"User-Agent": "DataSentinel/1.0", "Accept": "application/json"}

    @staticmethod
    def check_hibp_pass(value: str):
        sha1 = hashlib.sha1(value.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        try:
            res = LeakEngine.session.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers=LeakEngine.get_headers(), timeout=7)
            if res.status_code == 200:
                for line in res.text.splitlines():
                    h, count = line.split(":")
                    if h == suffix:
                        return True, int(count), "https://haveibeenpwned.com/Passwords"
            return False, 0, ""
        except Exception:
            return "CONN_ERR", 0, ""

    @staticmethod
    def check_leak_lookup(email: str):
        try:
            res = LeakEngine.session.get(f"https://leakcheck.io/api/public?check={email}",
                               headers=LeakEngine.get_headers(), timeout=LeakEngine.TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                if data.get("success") and data.get("found", 0) > 0:
                    names = [s.get("name", "Unknown") for s in data.get("sources", [])]
                    return True, names, "https://leakcheck.io/"
            return False, [], ""
        except Exception:
            return "CONN_ERR", [], ""

    @staticmethod
    def check_hudson_rock(email: str):
        try:
            res = LeakEngine.session.get(
                "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email",
                params={"email": email}, headers=LeakEngine.get_headers(), timeout=12)
            if res.status_code == 200:
                stealers = res.json().get("stealers", [])
                if stealers:
                    count   = len(stealers)
                    malware = stealers[0].get("malware_path", "Stealer")
                    return True, f"Найдено в {count} stealer-лог(ах), тип: {malware}", \
                           "https://www.hudsonrock.com/threat-intelligence-cybercrime-tools"
            return False, "", ""
        except Exception:
            return "CONN_ERR", "", ""

    @staticmethod
    def check_breach_directory(email: str):
        if not LeakEngine.RAPID_API_KEY:
            return "NO_KEY", [], ""
        try:
            res = LeakEngine.session.get(
                "https://breachdirectory.p.rapidapi.com/",
                params={"func": "auto", "term": email},
                headers={"X-RapidAPI-Key": LeakEngine.RAPID_API_KEY,
                         "X-RapidAPI-Host": "breachdirectory.p.rapidapi.com"}, timeout=LeakEngine.TIMEOUT)
            if res.status_code == 200:
                data = res.json()
                if data.get("result"):
                    def _first_src(item):
                        s = item.get("sources", "Unknown")
                        if isinstance(s, list):
                            return s[0] if s else "Unknown"
                        return s or "Unknown"
                    sources = [_first_src(item) for item in data["result"][:5]]
                    return True, sources, "https://breachdirectory.tk/"
            return False, [], ""
        except Exception:
            return "CONN_ERR", [], ""

    @staticmethod
    def check_emailrep(email: str):
        try:
            res = LeakEngine.session.get(f"https://emailrep.io/{email}",
                               headers=LeakEngine.get_headers(), timeout=8)
            if res.status_code == 200:
                details = res.json().get("details", {})
                if details.get("data_breach"):
                    count = details.get("breach_count", 1)
                    return True, f"Упоминаний в утечках: {count}", "https://emailrep.io/"
            return False, "", ""
        except Exception:
            return "CONN_ERR", "", ""

    @staticmethod
    def check_xposedornot(email: str):
        """Возвращает список конкретных утечек (LinkedIn, Adobe, Twitter и т.п.)."""
        try:
            res = LeakEngine.session.get(
                f"https://api.xposedornot.com/v1/check-email/{email}",
                headers=LeakEngine.get_headers(), timeout=LeakEngine.TIMEOUT)
            if res.status_code == 404:
                return False, [], ""
            if res.status_code == 200:
                data = res.json()
                # API отдаёт breaches как [["LinkedIn","Adobe",...]] (вложенный список).
                raw = data.get("breaches") or []
                flat: list[str] = []
                for item in raw:
                    if isinstance(item, list):
                        flat.extend(str(x) for x in item if x)
                    elif item:
                        flat.append(str(item))
                if flat:
                    seen, uniq = set(), []
                    for n in flat:
                        if n not in seen:
                            seen.add(n)
                            uniq.append(n)
                    return True, uniq, f"https://xposedornot.com/email-report/?email={email}"
            return False, [], ""
        except Exception:
            return "CONN_ERR", [], ""

    @staticmethod
    def check_proxynova(value: str):
        """Возвращает количество совпадений в публичных combo-листах.
        Пароли НЕ возвращаем (privacy + risk если экран расшарен)."""
        import re
        # Для телефона убираем форматирование, для email — как есть.
        query = re.sub(r"[\s\-\(\)]", "", value.strip())
        try:
            res = LeakEngine.session.get(
                "https://api.proxynova.com/comb",
                params={"query": query, "start": 0, "limit": 15},
                headers=LeakEngine.get_headers(), timeout=LeakEngine.TIMEOUT)
            if res.status_code != 200:
                return False, 0, ""
            data = res.json()
            count = int(data.get("count") or 0)
            # API иногда возвращает count=0, но lines с записями — учтём оба.
            if not count:
                count = len(data.get("lines") or [])
            if count > 0:
                return True, count, "https://www.proxynova.com/tools/comb/"
            return False, 0, ""
        except Exception:
            return "CONN_ERR", 0, ""

    @staticmethod
    def check_pastebin_dumps(value: str):
        """Поиск в архиве Pastebin-дампов (psbdmp.ws). Туда регулярно
        сливают части RockYou/Anti-Public/COMB и прочие credential-листы.
        API нестабильное — таймауты и 5xx считаем «не нашли», не ошибкой."""
        import re
        query = re.sub(r"[\s\-\(\)]", "", value.strip())
        try:
            res = LeakEngine.session.get(
                f"https://psbdmp.ws/api/search/{query}",
                headers=LeakEngine.get_headers(), timeout=10)
            if res.status_code != 200:
                return False, 0, ""
            data = res.json()
            count = 0
            if isinstance(data, dict):
                count = int(data.get("count") or 0)
                if not count:
                    count = len(data.get("data") or [])
            elif isinstance(data, list):
                count = len(data)
            if count > 0:
                return True, count, f"https://psbdmp.ws/search/{query}"
            return False, 0, ""
        except Exception:
            return "CONN_ERR", 0, ""

    @staticmethod
    def check_hudson_rock_username(username: str):
        """Стилер-логи по имени пользователя (Telegram/Discord/прочие ники)."""
        try:
            res = LeakEngine.session.get(
                "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-username",
                params={"username": username}, headers=LeakEngine.get_headers(), timeout=12)
            if res.status_code == 200:
                stealers = res.json().get("stealers", [])
                if stealers:
                    count = len(stealers)
                    malware = stealers[0].get("malware_path", "Stealer")
                    return True, f"Найдено в {count} stealer-лог(ах), тип: {malware}", \
                           "https://www.hudsonrock.com/threat-intelligence-cybercrime-tools"
            return False, "", ""
        except Exception:
            return "CONN_ERR", "", ""

    @staticmethod
    def check_intelx(email: str):
        key, host = LeakEngine.INTELX_API_KEY, LeakEngine.INTELX_HOST
        if not key:
            return "NO_KEY"
        try:
            r1 = LeakEngine.session.post(f"{host}/intelligent/search",
                               headers={**LeakEngine.get_headers(), "x-key": key,
                                        "Content-Type": "application/json"},
                               json={"term": email, "maxresults": 20,
                                     "media": 0, "sort": 4, "terminate": []}, timeout=LeakEngine.TIMEOUT)
            if r1.status_code == 402: return "NO_CREDITS"
            if r1.status_code != 200: return "CONN_ERR"
            sid = r1.json().get("id")
            if not sid: return "NOT_FOUND"
            time.sleep(3)
            r2 = LeakEngine.session.get(f"{host}/intelligent/search/result",
                              params={"id": sid, "limit": 20},
                              headers={**LeakEngine.get_headers(), "x-key": key}, timeout=LeakEngine.TIMEOUT)
            if r2.status_code != 200: return "CONN_ERR"
            records = r2.json().get("records", [])
            if not records: return "NOT_FOUND"
            seen, out = set(), []
            for rec in records:
                name   = rec.get("name", "Архив IntelX")
                bucket = rec.get("bucket", "")
                k      = f"{name}|{bucket}"
                if k not in seen:
                    seen.add(k)
                    out.append((name, bucket, f"https://intelx.io/?s={email}"))
            return out if out else "NOT_FOUND"
        except Exception:
            return "CONN_ERR"

    @staticmethod
    def detect_type(value: str) -> str:
        """Определяет тип объекта: email / phone / username / password.

        username vs password — эвристика: пароли почти всегда содержат
        спецсимволы или очень длинные; usernames обычно alphanumeric +
        точка/подчёркивание/дефис длиной 3–16. Точно разрешить нельзя
        без подсказки от юзера, но эвристика покрывает 90% случаев.
        Старый возвращаемый код 'other' заменён на 'username'/'password'."""
        import re
        value = value.strip()
        if "@" in value and "." in value:
            return "email"
        # Телефон: начинается с + или цифры, содержит 7-15 цифр
        digits = re.sub(r"[\s\-\(\)]", "", value)
        if re.match(r"^\+?\d{7,15}$", digits):
            return "phone"
        # Любая цифра, спецсимвол или длина > 16 — пароль.
        # Юзернеймы у нас = только буквы (+точка/подчёркивание/дефис).
        # Иначе нельзя отличить «abc12345» (пароль) от «user2024» (тоже
        # обычно пароль) — лучше быть консервативным и считать всё с
        # цифрами паролем; чистый текст почти всегда — username.
        if re.search(r"[^a-zA-Z._\-]", value) or len(value) > 16:
            return "password"
        return "username"

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Нормализует номер: убирает пробелы/скобки, добавляет + если нет."""
        import re
        digits = re.sub(r"[\s\-\(\)]", "", phone.strip())
        if not digits.startswith("+"):
            digits = "+" + digits
        return digits

    @staticmethod
    def check_phone_intelx(phone: str):
        """Проверка телефона через IntelX (поддерживает любые строки)."""
        normalized = LeakEngine.normalize_phone(phone)
        return LeakEngine.check_intelx(normalized)

    @staticmethod
    def check_phone_breachdirectory(phone: str):
        """Проверка телефона через BreachDirectory."""
        if not LeakEngine.RAPID_API_KEY:
            return False, [], ""
        import re
        normalized = re.sub(r"[\s\-\(\)\+]", "", phone.strip())
        try:
            res = LeakEngine.session.get(
                "https://breachdirectory.p.rapidapi.com/",
                params={"func": "auto", "term": normalized},
                headers={
                    "X-RapidAPI-Key":  LeakEngine.RAPID_API_KEY,
                    "X-RapidAPI-Host": "breachdirectory.p.rapidapi.com",
                    **LeakEngine.get_headers(),
                }, timeout=LeakEngine.TIMEOUT)
            if res.status_code != 200:
                return False, [], ""
            data = res.json()
            if not data.get("found"):
                return False, [], ""
            def _first_src(r):
                s = r.get("sources", "BreachDirectory")
                if isinstance(s, list):
                    return s[0] if s else "BreachDirectory"
                return s or "BreachDirectory"
            sources = list({_first_src(r) for r in data.get("result", [])})
            return True, sources, f"https://breachdirectory.com/?q={normalized}"
        except Exception:
            return False, [], ""

    @staticmethod
    def get_intelx_credits() -> dict:
        key, host = LeakEngine.INTELX_API_KEY, LeakEngine.INTELX_HOST
        if not key: return {"error": "NO_KEY"}
        try:
            res = LeakEngine.session.get(f"{host}/authenticate/info",
                               headers={**LeakEngine.get_headers(), "x-key": key}, timeout=8)
            if res.status_code == 200:
                info = {"error": None}
                for item in res.json().get("capabilitylist", []):
                    p = item.get("path", "")
                    if p == "/intelligent/search":
                        info["search_credits"] = item.get("credits", "?")
                        info["search_max"]     = item.get("maxcredits", "?")
                    elif p == "/file/preview":
                        info["file_preview"]   = item.get("credits", "?")
                return info
            return {"error": f"HTTP {res.status_code}"}
        except Exception:
            return {"error": "CONN_ERR"}

    @staticmethod
    def calculate_risk_score(sources: list) -> tuple:
        """Считает суммарный риск как:
          1) tier-веса источника по «опасности» утечки (инфостилерные
             пароли > dark-web дамп > HIBP-индекс > reputation-флаг);
          2) diminishing returns на повторы из одного источника
             (10 одинаковых HIBP не должны весить как 10 разных);
          3) soft-cap squash в 0–100 через экспоненту (без стенки).
        Порядок в SEVERITY важен: первый match выигрывает (Hudson Rock
        перед HIBP, чтобы 'Hudson Rock email' не упал в HIBP-tier)."""
        SEVERITY = (
            ("Hudson Rock",     22),  # infostealer creds — активно используются
            ("IntelX",          18),  # dark/deep-web exposure
            ("BreachDirectory", 14),
            ("ProxyNova",       12),  # COMB combo-листы
            ("XposedOrNot",     12),
            ("Pastebin",        10),
            ("LeakCheck",        9),
            ("HIBP",             8),  # хорошо проиндексирован, но обычно старый
            ("EmailRep",         5),  # reputation-флаг, не сама утечка
        )
        if not sources:
            return 0, "ОТСУТСТВУЕТ", "#2ECC71"

        counts: dict = {}
        for src in sources:
            for name, _ in SEVERITY:
                if name in src:
                    counts[name] = counts.get(name, 0) + 1
                    break

        raw = 0.0
        for name, base in SEVERITY:
            n = counts.get(name, 0)
            if n == 0:
                continue
            # n=1 → base*0.5; n=2 → ~base*0.75 + 0.3; n=∞ → base + хвост.
            raw += base * (1 - 0.5 ** n) + 0.3 * max(0, n - 1)

        score = int(round(100 * (1 - math.exp(-raw / 50.0))))
        score = max(0, min(100, score))

        if score >= 80: return score, "КРИТИЧЕСКИЙ", "#E74C3C"
        if score >= 60: return score, "ВЫСОКИЙ",     "#E67E22"
        if score >= 35: return score, "СРЕДНИЙ",     "#E6B422"
        if score >= 15: return score, "НИЗКИЙ",      "#F1C40F"
        if score >  0:  return score, "МИНИМАЛЬНЫЙ", "#A5D02C"
        return 0, "ОТСУТСТВУЕТ", "#2ECC71"

    @staticmethod
    def generate_random(length: int = 16, upper: bool = True,
                        digits: bool = True, symbols: bool = True) -> str:
        pool = string.ascii_lowercase
        mandatory = [secrets.choice(string.ascii_lowercase)]
        if upper:   pool += string.ascii_uppercase;  mandatory.append(secrets.choice(string.ascii_uppercase))
        if digits:  pool += string.digits;            mandatory.append(secrets.choice(string.digits))
        if symbols: pool += "!@#$%^&*()-_=+";        mandatory.append(secrets.choice("!@#$%^&*()-_=+"))
        rest = [secrets.choice(pool) for _ in range(length - len(mandatory))]
        pwd  = mandatory + rest
        secrets.SystemRandom().shuffle(pwd)
        return "".join(pwd)

    @staticmethod
    def generate_memorable(words: int = 4, separator: str = "-",
                           capitalize: bool = True, add_number: bool = True) -> str:
        chosen = [secrets.choice(WORD_LIST) for _ in range(words)]
        if capitalize:
            chosen = [w.capitalize() for w in chosen]
        result = separator.join(chosen)
        if add_number:
            result += separator + str(secrets.randbelow(90) + 10)
        return result

    @staticmethod
    def generate_pin(length: int = 6) -> str:
        return "".join(str(secrets.randbelow(10)) for _ in range(length))

    @staticmethod
    def estimate_crack_time(password: str) -> tuple:
        """
        Оценка времени взлома с учётом реальных атак:
        - словарные атаки
        - паттерны (имя+цифры)
        - GPU brute-force 100 млрд/сек
        """
        import re

        pool = 0
        if any(c.islower()           for c in password): pool += 26
        if any(c.isupper()           for c in password): pool += 26
        if any(c.isdigit()           for c in password): pool += 10
        if any(c in "!@#$%^&*()-_=+" for c in password): pool += 20
        if any(c in string.punctuation and c not in "!@#$%^&*()-_=+"
               for c in password): pool += 12

        if pool == 0:
            return "Мгновенно", "#e74c3c"

        entropy = len(password) * math.log2(pool)

        # Штрафы за предсказуемые паттерны
        # Имя + цифры (Vlad22814, Anna1990 и т.д.)
        if re.match(r'^[A-Za-z]{2,10}\d{2,8}[!@#$%]?$', password):
            entropy *= 0.25   # очень предсказуемо — режем энтропию на 75%

        # Только буквы + цифры без спецсимволов — слабее
        if not any(c in "!@#$%^&*()-_=+" for c in password):
            entropy *= 0.6

        # Повторяющиеся символы (aaa, 111)
        if re.search(r'(.)\1{2,}', password):
            entropy *= 0.5

        # Последовательности (123, abc, qwerty)
        sequences = ['0123456789', 'abcdefghijklmnopqrstuvwxyz', 'qwertyuiop', 'asdfghjkl']
        pwd_lower = password.lower()
        for seq in sequences:
            for i in range(len(seq) - 2):
                if seq[i:i+3] in pwd_lower:
                    entropy *= 0.7
                    break

        # Короткий пароль (< 10 символов) — дополнительный штраф
        if len(password) < 10:
            entropy *= 0.4

        # GPU-атака: 100 млрд попыток/сек
        seconds = (2 ** max(entropy, 1)) / 100_000_000_000

        thresholds = [
            (1,               "Мгновенно",    "#e74c3c"),
            (60,              "Секунды",      "#e74c3c"),
            (3_600,           "Минуты",       "#e74c3c"),
            (86_400,          "Часы",         "#e67e22"),
            (2_592_000,       "Дни",          "#e67e22"),
            (31_536_000,      "Месяцы",       "#f1c40f"),
            (315_360_000,     "Годы",         "#f1c40f"),
            (3_153_600_000,   "Десятилетия",  "#2ecc71"),
            (float("inf"),    "Тысячелетия",  "#27ae60"),
        ]
        for limit, label, color in thresholds:
            if seconds < limit:
                return label, color
        return "Тысячелетия", "#27ae60"

    @staticmethod
    def check_password_strength(password: str) -> tuple:
        """
        Реалистичная оценка (0-5, label, color).
        Vlad22814! = Слабый, T#9kPx!mQ2 = Сильный
        """
        import re
        score = 0

        # Длина
        if len(password) >= 10: score += 1
        if len(password) >= 14: score += 1

        # Разнообразие символов
        has_upper   = any(c.isupper() for c in password)
        has_lower   = any(c.islower() for c in password)
        has_digit   = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password)

        if has_upper and has_lower: score += 1
        if has_digit:               score += 1
        if has_special:             score += 1

        # Штрафы — снижаем оценку
        # Паттерн "имя + цифры"
        if re.match(r'^[A-Za-z]{2,10}\d+[!@#$%]?$', password):
            score = max(0, score - 2)

        # Нет спецсимволов
        if not has_special:
            score = max(0, score - 1)

        # Короткий
        if len(password) < 8:
            score = 0

        score = min(score, 5)

        labels = {
            0: ("Очень слабый", "#e74c3c"),
            1: ("Слабый",       "#e74c3c"),
            2: ("Средний",      "#e67e22"),
            3: ("Хороший",      "#f1c40f"),
            4: ("Сильный",      "#2ecc71"),
            5: ("Очень сильный","#27ae60"),
        }
        label, color = labels[score]
        return score, label, color
