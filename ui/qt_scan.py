"""
qt_scan.py — фоновое сканирование для Qt UI.

ScanWorker запускается в QThread и эмитит сигналы о прогрессе, строках,
новых утечках и завершении.
"""
from __future__ import annotations

import time
import threading

from PySide6.QtCore import QObject, QThread, Signal

from core.engine import LeakEngine

def _mask(val: str) -> str:
    """Скрывает PII в логах: email → u***@domain, phone → +7***last3, other → s****t.
    Лог попадает в UI и stdout — открытое значение свело бы на нет
    шифрование таблицы `targets`."""
    if not val:
        return val
    if "@" in val:
        local, _, domain = val.partition("@")
        head = local[0] if local else "?"
        return f"{head}***@{domain}"
    if val.startswith("+") or (val[:1].isdigit() and len(val) >= 7):
        # Телефон: оставляем код страны (до 3 символов) и последние 3 цифры.
        return f"{val[:3]}***{val[-3:]}"
    if len(val) <= 2:
        return "***"
    return f"{val[0]}***{val[-1]}"

class ScanWorker(QObject):
    # Сигналы к UI
    logMessage = Signal(str)
    rowAdded = Signal(dict)                # {n, target, source, name, rec, url, is_new}
    progress = Signal(float)               # 0..1
    statusChanged = Signal(str, str, str)  # text, badge, color_name ("safe"/"warn"/"danger")
    riskUpdate = Signal(list)              # all_sources (для recompute)
    finished = Signal(int, list)           # leaks, new_breaches [(target,source,breach),...]

    def __init__(self, db, is_manual: bool):
        super().__init__()
        self.db = db
        self.is_manual = is_manual
        self._stop = False

    def stop(self):
        self._stop = True

    def _src(self, key: str) -> bool:
        return self.db.get_setting(f"src_{key}", "1") == "1"

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.logMessage.emit(f"Ошибка сканирования: {e}")
            self.finished.emit(0, [])

    def _run(self):
        targets = self.db.get_all_targets()
        if not targets:
            self.logMessage.emit("Нет объектов.")
            self.finished.emit(0, [])
            return

        if self.is_manual:
            self.statusChanged.emit("Идёт проверка...", "  Сканирование  ", "warn")
            self.progress.emit(0.0)

        leaks = 0
        row_num = 1
        new_breaches: list[tuple[str, str, str]] = []
        all_sources: list[str] = []

        def _add(val, src, name, url, rec, is_new):
            nonlocal leaks, row_num
            leaks += 1
            all_sources.append(src)
            self.rowAdded.emit({
                "n": row_num, "target": val, "source": src,
                "name": name, "rec": rec, "url": url, "is_new": is_new,
            })
            row_num += 1

        for i, (t_id, val) in enumerate(targets):
            if self._stop:
                break
            self.logMessage.emit(f"Анализ: {_mask(val)}")
            obj_type = LeakEngine.detect_type(val)

            if obj_type == "email":
                if self._src("hibp"):
                    res, count, url = LeakEngine.check_hibp_pass(val)
                    if res is True:
                        label = f"Слито {count:,} раз"
                        isnew = self.db.save_result(val, "HIBP Passwords", label, "", url)
                        if isnew: new_breaches.append((val, "HIBP Passwords", label))
                        _add(val, "HIBP Passwords", label, url, "Смените пароль!", isnew)
                    self.logMessage.emit(f"  HIBP: {res}")

                if self._src("leakcheck"):
                    time.sleep(0.5)
                    res, names, url = LeakEngine.check_leak_lookup(val)
                    if res is True:
                        for b in names:
                            isnew = self.db.save_result(val, "LeakCheck", b, "", url)
                            if isnew: new_breaches.append((val, "LeakCheck", b))
                            _add(val, "LeakCheck", b, url, "Включите 2FA!", isnew)
                    self.logMessage.emit(f"  LeakCheck: {res}")

                if self._src("hudson_rock"):
                    time.sleep(0.3)
                    res, detail, url = LeakEngine.check_hudson_rock(val)
                    if res is True:
                        isnew = self.db.save_result(val, "Hudson Rock (Dark Web)", detail, detail, url)
                        if isnew: new_breaches.append((val, "Hudson Rock", detail))
                        _add(val, "Dark Web (Hudson Rock)", detail, url,
                             "Проверьте устройство на вирусы!", isnew)
                    self.logMessage.emit(f"  Hudson Rock: {res}")

                if self._src("breachdirectory"):
                    time.sleep(0.5)
                    res, sources, url = LeakEngine.check_breach_directory(val)
                    if res is True:
                        for b in sources:
                            isnew = self.db.save_result(val, "BreachDirectory", b, "", url)
                            if isnew: new_breaches.append((val, "BreachDirectory", b))
                            _add(val, "BreachDirectory", b, url,
                                 "Смените пароль и включите 2FA", isnew)
                    self.logMessage.emit(f"  BreachDirectory: {res}")

                if self._src("emailrep"):
                    time.sleep(0.3)
                    res, detail, url = LeakEngine.check_emailrep(val)
                    if res is True:
                        isnew = self.db.save_result(val, "EmailRep", detail, detail, url)
                        if isnew: new_breaches.append((val, "EmailRep", detail))
                        _add(val, "EmailRep", detail, url,
                             "Смените пароль, проверьте аккаунты", isnew)
                    self.logMessage.emit(f"  EmailRep: {res}")

                if self._src("xposedornot"):
                    time.sleep(0.3)
                    res, names, url = LeakEngine.check_xposedornot(val)
                    if res is True:
                        for b in names:
                            isnew = self.db.save_result(val, "XposedOrNot", b, "", url)
                            if isnew: new_breaches.append((val, "XposedOrNot", b))
                            _add(val, "XposedOrNot", b, url,
                                 "Смените пароль на этом сайте", isnew)
                    self.logMessage.emit(f"  XposedOrNot: {res}")

                if self._src("proxynova"):
                    time.sleep(0.3)
                    res, count, url = LeakEngine.check_proxynova(val)
                    if res is True:
                        label = f"Combo-листы: {count} совпадений"
                        isnew = self.db.save_result(val, "ProxyNova COMB", label, "", url)
                        if isnew: new_breaches.append((val, "ProxyNova", label))
                        _add(val, "ProxyNova COMB", label, url,
                             "Пароль попал в combo-лист — смените везде, где использовали",
                             isnew)
                    self.logMessage.emit(f"  ProxyNova: {res}")

                if self._src("hudson_user"):
                    time.sleep(0.3)
                    local = val.split("@", 1)[0]
                    res, detail, url = LeakEngine.check_hudson_rock_username(local)
                    if res is True:
                        isnew = self.db.save_result(val, "Hudson Rock (username)", detail, detail, url)
                        if isnew: new_breaches.append((val, "Hudson Rock", detail))
                        _add(val, "Dark Web (Hudson Rock · username)", detail, url,
                             "Проверьте устройство на вирусы, смените пароли", isnew)
                    self.logMessage.emit(f"  Hudson Rock username: {res}")

                if self._src("psbdmp"):
                    time.sleep(0.3)
                    res, count, url = LeakEngine.check_pastebin_dumps(val)
                    if res is True:
                        label = f"Pastebin dumps: {count} paste-ов"
                        isnew = self.db.save_result(val, "Pastebin Dumps", label, "", url)
                        if isnew: new_breaches.append((val, "Pastebin", label))
                        _add(val, "Pastebin Dumps", label, url,
                             "Email засветился в публичном дампе — смените пароли", isnew)
                    self.logMessage.emit(f"  PSBDMP: {res}")

                if self._src("intelx") and LeakEngine.INTELX_API_KEY:
                    ix = LeakEngine.check_intelx(val)
                    if ix == "NO_CREDITS":
                        self.logMessage.emit("  IntelX: кредиты исчерпаны!")
                    elif isinstance(ix, list):
                        for name, bucket, url in ix:
                            label = f"{name} [{bucket}]" if bucket else name
                            isnew = self.db.save_result(val, "IntelX (Dark Web)", label, "", url)
                            if isnew: new_breaches.append((val, "IntelX", label))
                            _add(val, "IntelX (Dark Web)", label, url,
                                 "Данные в Dark Web — смените почту!", isnew)
                        self.logMessage.emit(f"  IntelX: {len(ix)} записей")
                    else:
                        self.logMessage.emit(f"  IntelX: {ix}")

            elif obj_type == "phone":
                normalized = LeakEngine.normalize_phone(val)
                self.logMessage.emit(f"  Тип: телефон ({_mask(normalized)})")

                if self._src("intelx") and LeakEngine.INTELX_API_KEY:
                    ix = LeakEngine.check_phone_intelx(val)
                    if ix == "NO_CREDITS":
                        self.logMessage.emit("  IntelX: кредиты исчерпаны!")
                    elif isinstance(ix, list):
                        for name, bucket, url in ix:
                            label = f"{name} [{bucket}]" if bucket else name
                            isnew = self.db.save_result(normalized, "IntelX (Dark Web)", label, "", url)
                            if isnew: new_breaches.append((normalized, "IntelX", label))
                            _add(normalized, "IntelX (Dark Web)", label, url,
                                 "Номер найден в Dark Web!", isnew)
                        self.logMessage.emit(f"  IntelX телефон: {len(ix)} записей")

                if self._src("breachdirectory"):
                    time.sleep(0.5)
                    res, sources, url = LeakEngine.check_phone_breachdirectory(val)
                    if res is True:
                        for b in sources:
                            isnew = self.db.save_result(normalized, "BreachDirectory", b, "", url)
                            if isnew: new_breaches.append((normalized, "BreachDirectory", b))
                            _add(normalized, "BreachDirectory", b, url,
                                 "Номер в базе утечек!", isnew)
                    self.logMessage.emit(f"  BreachDirectory телефон: {res}")

                if self._src("proxynova"):
                    time.sleep(0.3)
                    res, count, url = LeakEngine.check_proxynova(normalized)
                    if res is True:
                        label = f"Combo-листы: {count} совпадений"
                        isnew = self.db.save_result(normalized, "ProxyNova COMB", label, "", url)
                        if isnew: new_breaches.append((normalized, "ProxyNova", label))
                        _add(normalized, "ProxyNova COMB", label, url,
                             "Номер в публичных combo-листах", isnew)
                    self.logMessage.emit(f"  ProxyNova телефон: {res}")

                if self._src("psbdmp"):
                    time.sleep(0.3)
                    res, count, url = LeakEngine.check_pastebin_dumps(normalized)
                    if res is True:
                        label = f"Pastebin dumps: {count} paste-ов"
                        isnew = self.db.save_result(normalized, "Pastebin Dumps", label, "", url)
                        if isnew: new_breaches.append((normalized, "Pastebin", label))
                        _add(normalized, "Pastebin Dumps", label, url,
                             "Номер засветился в публичном дампе", isnew)
                    self.logMessage.emit(f"  PSBDMP телефон: {res}")

            elif obj_type == "password":
                # Пароль: HIBP Pwned Passwords (k-anonymity, сам пароль не уходит).
                if self._src("hibp"):
                    res, count, url = LeakEngine.check_hibp_pass(val)
                    if res is True:
                        label = f"Слито {count:,} раз"
                        isnew = self.db.save_result(val, "HIBP Passwords", label, "", url)
                        if isnew: new_breaches.append((val, "HIBP Passwords", label))
                        _add(val, "HIBP Passwords", label, url, "Смените пароль!", isnew)
                    self.logMessage.emit(f"  HIBP: {res}")

            else:  # username
                # Username: только Hudson Rock username — HIBP password
                # неуместен (он чек'ит хеш ПАРОЛЯ, не имя).
                if self._src("hudson_user"):
                    time.sleep(0.3)
                    res, detail, url = LeakEngine.check_hudson_rock_username(val)
                    if res is True:
                        isnew = self.db.save_result(val, "Hudson Rock (username)", detail, detail, url)
                        if isnew: new_breaches.append((val, "Hudson Rock", detail))
                        _add(val, "Dark Web (Hudson Rock · username)", detail, url,
                             "Проверьте устройство на вирусы, смените пароли", isnew)
                    self.logMessage.emit(f"  Hudson Rock username: {res}")

            if self.is_manual:
                self.progress.emit((i + 1) / len(targets))

        if all_sources:
            self.riskUpdate.emit(all_sources)

        self.db.set_last_scan(time.time())

        if self.is_manual:
            if leaks == 0:
                self.statusChanged.emit("Система защищена", "  Защищена  ", "safe")
            else:
                self.statusChanged.emit("Обнаружена угроза!", "  Угроза!  ", "danger")

        self.logMessage.emit(f"Готово. Утечек: {leaks}, новых: {len(new_breaches)}")
        self.finished.emit(leaks, new_breaches)
