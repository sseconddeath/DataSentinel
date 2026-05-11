"""Страница «Настройки»: тема, автоскан, источники, SMTP, трей, лог."""
from __future__ import annotations

import datetime
import threading
from typing import Callable

from PySide6.QtCore import (
    Qt, Signal, QObject, QPropertyAnimation, QEasingCurve, Property, QRectF, QEvent,
)
from PySide6.QtGui import QFont, QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QButtonGroup, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QPlainTextEdit, QSizePolicy, QAbstractButton,
)

import core.config as cfg
from services.smtp_notify import send_breach_email, test_smtp_connection, SMTP_PRESETS

class IOSSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None,
                 width: int = 44, height: int = 24):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(width, height)
        self._margin = 2
        self._radius = height // 2
        self._handle_pos = float(self._margin)
        self._anim = QPropertyAnimation(self, b"handlePos", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animate)

    def _handle_end(self, checked: bool) -> float:
        if checked:
            return float(self.width() - self.height() + self._margin)
        return float(self._margin)

    def _animate(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._handle_pos)
        self._anim.setEndValue(self._handle_end(checked))
        self._anim.start()

    def showEvent(self, e):
        self._handle_pos = self._handle_end(self.isChecked())
        super().showEvent(e)

    def getHandlePos(self) -> float:
        return self._handle_pos

    def setHandlePos(self, v: float):
        self._handle_pos = v
        self.update()

    handlePos = Property(float, getHandlePos, setHandlePos)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Track. Для OFF-состояния используем BORDER_HOVER — он гарантированно
        # контрастирует и с card BG (BG_SURFACE) на светлой теме, и с тёмной
        # картой. BG_ELEVATED в светлой теме = почти белый, был невидим.
        if self.isChecked():
            track = QColor(cfg.ACCENT)
        else:
            track = QColor(cfg.BORDER_HOVER)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()),
                          self._radius, self._radius)
        # Handle
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        d = self.height() - self._margin * 2
        p.drawEllipse(QRectF(self._handle_pos, self._margin, d, d))
        p.end()

    def hitButton(self, _pos) -> bool:
        return True

def _card(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background:{cfg.BG_SURFACE};"
        f"border:1px solid {cfg.BORDER}; border-radius:12px; }}"
    )
    return f

def _muted(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:11px;"
        f"font-weight:700; letter-spacing:1px; background:transparent;"
    )
    return lbl

def _label(text: str, size: int = 13, color: str | None = None,
           parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"font-family:'Geist'; color:{color or cfg.TEXT_PRIMARY};"
        f"font-size:{size}px; font-weight:600; background:transparent;"
    )
    return lbl

def _input(placeholder: str = "", password: bool = False,
           parent: QWidget | None = None) -> QLineEdit:
    e = QLineEdit(parent)
    e.setPlaceholderText(placeholder)
    if password:
        e.setEchoMode(QLineEdit.Password)
    e.setFixedHeight(34)
    e.setStyleSheet(f"""
        QLineEdit {{
            font-family: 'Geist';
            background: {cfg.BG_INPUT};
            color: {cfg.TEXT_PRIMARY};
            border: 1px solid {cfg.BORDER};
            border-radius: 6px;
            padding: 0 10px;
            font-size: 13px;
            font-weight: 600;
            selection-background-color: {cfg.ACCENT};
        }}
        QLineEdit:focus {{ border: 1px solid {cfg.ACCENT}; }}
    """)
    return e

def _btn_primary(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(36)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.ACCENT}; color: white;
            border: none; border-radius: 6px;
            padding: 0 18px; font-size: 14px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {cfg.ACCENT_HOVER}; }}
    """)
    return b

def _btn_secondary(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(34)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.BG_ELEVATED}; color: {cfg.TEXT_PRIMARY};
            border: 1px solid {cfg.BORDER}; border-radius: 6px;
            padding: 0 14px; font-size: 13px; font-weight: 600;
        }}
        QPushButton:hover {{ border: 1px solid {cfg.BORDER_HOVER}; }}
    """)
    return b

def _pill(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(True)
    b.setFixedHeight(32)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: transparent; color: {cfg.TEXT_SECONDARY};
            border: none; border-radius: 4px;
            padding: 0 14px; font-size: 13px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {cfg.BG_ELEVATED}; }}
        QPushButton:checked {{
            background: {cfg.ACCENT}; color: white; font-weight: 700;
        }}
    """)
    return b

def _checkbox(text: str, parent: QWidget | None = None) -> QCheckBox:
    c = QCheckBox(text, parent)
    c.setCursor(Qt.PointingHandCursor)
    c.setStyleSheet(f"""
        QCheckBox {{
            font-family: 'Geist'; color: {cfg.TEXT_PRIMARY};
            font-size: 13px; font-weight: 600;
            background: transparent; spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1px solid {cfg.BORDER};
            border-radius: 3px;
            background: {cfg.BG_INPUT};
        }}
        QCheckBox::indicator:checked {{
            background: {cfg.ACCENT}; border: 1px solid {cfg.ACCENT};
        }}
        QCheckBox::indicator:hover {{ border: 1px solid {cfg.ACCENT}; }}
    """)
    return c

class SettingsPage(QWidget):
    # Сигнал логирования — для вывода в системный журнал
    logMessage = Signal(str)
    themeChanged = Signal(str)

    def eventFilter(self, obj, event):
        # Глобально игнорируем wheel на QComboBox — иначе случайный скролл
        # страницы меняет выбор провайдера/etc. ComboBox остаётся кликабельным.
        if event.type() == QEvent.Wheel and isinstance(obj, QComboBox):
            return True
        return super().eventFilter(obj, event)

    def __init__(self, db, on_rebuild: Callable[[], None] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self._on_rebuild = on_rebuild
        self.setStyleSheet(f"background:{cfg.BG_APP};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet(f"""
            QScrollArea#settingsScroll {{ background: {cfg.BG_APP}; border: none; }}
            QScrollArea#settingsScroll > QWidget > QWidget {{ background: {cfg.BG_APP}; }}
            QScrollArea#settingsScroll QScrollBar:vertical {{
                background: {cfg.BG_APP}; width: 10px; margin: 4px 2px 4px 0;
                border: none;
            }}
            QScrollArea#settingsScroll QScrollBar::handle:vertical {{
                background: {cfg.BORDER}; border-radius: 3px; min-height: 24px;
            }}
            QScrollArea#settingsScroll QScrollBar::handle:vertical:hover {{
                background: {cfg.BORDER_HOVER};
            }}
            QScrollArea#settingsScroll QScrollBar::add-line:vertical,
            QScrollArea#settingsScroll QScrollBar::sub-line:vertical {{
                height: 0; background: transparent; border: none;
            }}
            QScrollArea#settingsScroll QScrollBar::add-page:vertical,
            QScrollArea#settingsScroll QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        root.addWidget(scroll, 1)

        inner = QWidget()
        inner.setStyleSheet(f"background:{cfg.BG_APP};")
        scroll.setWidget(inner)

        outer = QVBoxLayout(inner)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        title = QLabel("Настройки", inner)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;"
        )
        outer.addWidget(title)
        subtitle = QLabel("Конфигурация приложения", inner)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:14px; font-weight:600; background:transparent;"
        )
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)

        self._build_theme_card(grid)
        self._build_autoscan_card(grid)
        self._build_sources_card(grid)
        self._build_smtp_card(grid)
        self._build_tray_card(grid)
        self._build_log_card(grid)

        outer.addStretch(1)

    def _build_theme_card(self, grid: QGridLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(_muted("ОФОРМЛЕНИЕ", card))
        lay.addWidget(_label("Тема интерфейса", 14, cfg.TEXT_SECONDARY, card))

        saved_theme = self.db.get_setting("theme", "dark")
        pills_wrap = QFrame(card)
        pills_wrap.setObjectName("pillsWrap")
        pills_wrap.setStyleSheet(
            f"QFrame#pillsWrap {{ background:{cfg.BG_APP}; border-radius:6px; }}"
        )
        pw = QHBoxLayout(pills_wrap)
        pw.setContentsMargins(4, 4, 4, 4)
        pw.setSpacing(2)

        self._theme_group = QButtonGroup(self)
        self._theme_group.setExclusive(True)
        for mode, label in [("dark", "Тёмная"), ("light", "Светлая"), ("system", "Системная")]:
            b = _pill(label, pills_wrap)
            b.setChecked(mode == saved_theme)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, m=mode: self._set_theme(m))
            self._theme_group.addButton(b)
            pw.addWidget(b, 1)
        lay.addWidget(pills_wrap)
        lay.addStretch(1)

        grid.addWidget(card, 0, 0)

    def _set_theme(self, mode: str):
        self.db.set_setting("theme", mode)
        self.logMessage.emit(f"Тема изменена на '{mode}'. Перезапуск…")
        self.themeChanged.emit(mode)

    def _build_autoscan_card(self, grid: QGridLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(_muted("АВТОСКАНИРОВАНИЕ", card))

        row = QHBoxLayout()
        row.addWidget(_label("Фоновая проверка", 14, cfg.TEXT_SECONDARY, card))
        row.addStretch(1)

        saved_auto = self.db.get_setting("auto_scan_enabled", "1") == "1"
        self._auto_enabled = saved_auto
        self._auto_switch = IOSSwitch(card, width=46, height=26)
        self._auto_switch.setChecked(saved_auto)
        self._auto_switch.toggled.connect(self._on_autoscan_toggle)
        row.addWidget(self._auto_switch)
        lay.addLayout(row)

        lay.addWidget(_muted("ИНТЕРВАЛ ПРОВЕРКИ", card))
        saved_interval = self.db.get_setting("scan_interval", "12")
        pills_wrap = QFrame(card)
        pills_wrap.setObjectName("intervalWrap")
        pills_wrap.setStyleSheet(
            f"QFrame#intervalWrap {{ background:{cfg.BG_APP}; border-radius:6px; }}"
        )
        pw = QHBoxLayout(pills_wrap)
        pw.setContentsMargins(4, 4, 4, 4)
        pw.setSpacing(2)

        self._interval_group = QButtonGroup(self)
        self._interval_group.setExclusive(True)
        self._interval_buttons: list[QPushButton] = []
        for label, val in [("2 мин", "0.033"), ("6 ч", "6"), ("12 ч", "12"),
                           ("24 ч", "24"), ("48 ч", "48")]:
            b = _pill(label, pills_wrap)
            b.setChecked(val == saved_interval)
            b.setProperty("interval_val", val)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, v=val: self._set_interval(v))
            self._interval_group.addButton(b)
            pw.addWidget(b, 1)
            self._interval_buttons.append(b)
        lay.addWidget(pills_wrap)

        self._next_scan_lbl = _label("", 11, cfg.TEXT_MUTED, card)
        lay.addWidget(self._next_scan_lbl)
        lay.addStretch(1)

        self._refresh_next_scan()
        self._apply_interval_enabled()

        grid.addWidget(card, 0, 1)

    def _on_autoscan_toggle(self, checked: bool):
        self._auto_enabled = checked
        self.db.set_setting("auto_scan_enabled", "1" if checked else "0")
        import time
        if checked:
            self.db.set_last_scan(time.time())
        self._apply_interval_enabled()
        self._refresh_next_scan()
        self.logMessage.emit(
            f"Автосканирование {'включено' if checked else 'отключено'}.")

    def _apply_interval_enabled(self):
        for b in self._interval_buttons:
            b.setEnabled(self._auto_enabled)

    def _set_interval(self, val: str):
        self.db.set_setting("scan_interval", val)
        self._refresh_next_scan()
        self.logMessage.emit(f"Интервал сканирования: {val} ч.")

    def _refresh_next_scan(self):
        if not self._auto_enabled:
            self._next_scan_lbl.setText("Автопроверка отключена")
            return
        interval_h = float(self.db.get_setting("scan_interval", "12"))
        last = self.db.get_last_scan()
        if last > 0:
            next_ts = last + interval_h * 3600
            next_str = datetime.datetime.fromtimestamp(next_ts).strftime("%d.%m.%Y %H:%M")
            self._next_scan_lbl.setText(f"Следующая проверка: {next_str}")
        else:
            self._next_scan_lbl.setText(
                "Следующая проверка: после первого ручного запуска")

    def _build_sources_card(self, grid: QGridLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(_muted("ИСТОЧНИКИ ПРОВЕРКИ", card))

        sources = [
            ("hibp",            "HIBP Passwords",            "Бесплатно · без ключа",  cfg.SAFE_COLOR),
            ("leakcheck",       "LeakCheck",                  "Бесплатно · без ключа",  cfg.SAFE_COLOR),
            ("xposedornot",     "XposedOrNot",                "Бесплатно · без ключа",  cfg.SAFE_COLOR),
            ("proxynova",       "ProxyNova COMB",             "Бесплатно · без ключа",  cfg.SAFE_COLOR),
            ("psbdmp",          "Pastebin Dumps",             "Бесплатно · без ключа",  cfg.ACCENT_TEXT),
            ("hudson_rock",     "Hudson Rock Dark Web",       "Бесплатно · без ключа",  cfg.ACCENT_TEXT),
            ("hudson_user",     "Hudson Rock · username",     "Бесплатно · без ключа",  cfg.ACCENT_TEXT),
            ("emailrep",        "EmailRep.io",                "Бесплатно · без ключа",  cfg.SAFE_COLOR),
            ("breachdirectory", "BreachDirectory",            "RapidAPI ключ",          cfg.WARNING_COLOR),
            ("intelx",          "IntelX Dark Web",            "IntelX ключ",            cfg.ACCENT_TEXT),
        ]
        gl = QGridLayout()
        gl.setSpacing(8)
        gl.setColumnStretch(0, 1)
        gl.setColumnStretch(1, 1)
        lay.addLayout(gl)

        for i, (key, name, hint, dot_col) in enumerate(sources):
            row_f = QFrame(card)
            row_f.setObjectName(f"src_{key}")
            row_f.setStyleSheet(
                f"QFrame#src_{key} {{ background:{cfg.BG_APP}; border-radius:8px; }}"
            )
            row_f.setMinimumHeight(52)
            rl = QHBoxLayout(row_f)
            rl.setContentsMargins(14, 10, 14, 10)
            rl.setSpacing(12)
            dot = QLabel("●", row_f)
            dot.setStyleSheet(
                f"color:{dot_col}; font-size:12px; background:transparent;"
            )
            rl.addWidget(dot)

            name_lbl = QLabel(name, row_f)
            name_lbl.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY};"
                f"font-size:14px; font-weight:700; background:transparent;"
            )
            rl.addWidget(name_lbl)

            hl = QLabel(hint, row_f)
            hl.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
                f"font-size:12px; font-weight:600; background:transparent;"
            )
            rl.addWidget(hl, 1, Qt.AlignRight | Qt.AlignVCenter)

            sw = IOSSwitch(row_f, width=42, height=22)
            sw.setChecked(self.db.get_setting(f"src_{key}", "1") == "1")
            sw.toggled.connect(
                lambda checked, k=key: self.db.set_setting(
                    f"src_{k}", "1" if checked else "0")
            )
            rl.addWidget(sw)

            gl.addWidget(row_f, i // 2, i % 2)

        grid.addWidget(card, 1, 0, 1, 2)

    def _build_smtp_card(self, grid: QGridLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(_muted("EMAIL-УВЕДОМЛЕНИЯ", card))

        smtp = self.db.get_smtp()
        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        form.setColumnStretch(1, 1)
        lay.addLayout(form)

        form.addWidget(_label("Провайдер", 13, cfg.TEXT_SECONDARY, card), 0, 0, Qt.AlignLeft)
        self.smtp_provider = QComboBox(card)
        self.smtp_provider.addItems(list(SMTP_PRESETS.keys()))
        self.smtp_provider.setCurrentText(smtp.get("provider", "Gmail"))
        self.smtp_provider.setFixedHeight(34)
        # Игнорируем wheel: иначе скролл страницы меняет провайдера, когда
        # курсор случайно над QComboBox. Также ставим NoFocus, чтобы он не
        # перехватывал клавиатурные события.
        self.smtp_provider.setFocusPolicy(Qt.StrongFocus)
        self.smtp_provider.installEventFilter(self)
        self.smtp_provider.setStyleSheet(f"""
            QComboBox {{
                font-family: 'Geist';
                background: {cfg.BG_INPUT}; color: {cfg.TEXT_PRIMARY};
                border: 1px solid {cfg.BORDER}; border-radius: 6px;
                padding: 0 10px; font-size: 13px; font-weight: 600;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {cfg.BG_ELEVATED}; color: {cfg.TEXT_PRIMARY};
                border: 1px solid {cfg.BORDER}; selection-background-color: {cfg.ACCENT};
            }}
        """)
        self.smtp_provider.currentTextChanged.connect(self._on_provider_change)
        form.addWidget(self.smtp_provider, 0, 1)

        self.smtp_host = _input("smtp.gmail.com", parent=card)
        self.smtp_host.setText(smtp.get("host", ""))
        self.smtp_port = _input("587", parent=card)
        self.smtp_port.setText(str(smtp.get("port", 587)))
        self.smtp_user = _input("user@example.com", parent=card)
        self.smtp_user.setText(smtp.get("user", ""))
        self.smtp_pass = _input("пароль приложения", password=True, parent=card)
        self.smtp_pass.setText(smtp.get("password", ""))
        self.smtp_recv = _input("получатель@example.com", parent=card)
        self.smtp_recv.setText(smtp.get("recipient", ""))

        for r, (lbl, w) in enumerate([
            ("SMTP хост", self.smtp_host),
            ("Порт", self.smtp_port),
            ("Логин", self.smtp_user),
            ("Пароль", self.smtp_pass),
            ("Получатель", self.smtp_recv),
        ], 1):
            form.addWidget(_label(lbl, 13, cfg.TEXT_SECONDARY, card), r, 0, Qt.AlignLeft)
            form.addWidget(w, r, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        save_btn = _btn_primary("Сохранить", card)
        save_btn.clicked.connect(self._save_smtp)
        btn_row.addWidget(save_btn)

        test_btn = QPushButton("Тест подключения", card)
        test_btn.setCursor(Qt.PointingHandCursor)
        test_btn.setFixedHeight(36)
        test_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Geist';
                background: {cfg.SAFE_BG}; color: {cfg.SAFE_COLOR};
                border: 1px solid {cfg.SAFE_BG}; border-radius: 6px;
                padding: 0 16px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #143020; }}
        """)
        test_btn.clicked.connect(self._test_smtp)
        btn_row.addWidget(test_btn)

        self.smtp_status = QLabel("", card)
        self.smtp_status.setStyleSheet(
            f"font-family:'Geist'; font-size:12px; font-weight:600;"
            f"background:transparent;"
        )
        btn_row.addWidget(self.smtp_status, 1)
        lay.addLayout(btn_row)

        hint = QLabel(
            "Gmail: пароль приложения — Аккаунт Google → Безопасность → Пароли приложений",
            card)
        hint.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:12px; font-weight:600; background:transparent;"
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        grid.addWidget(card, 2, 0, 1, 2)

    def _on_provider_change(self, provider: str):
        preset = SMTP_PRESETS.get(provider, {})
        if preset.get("host"):
            self.smtp_host.setText(preset["host"])
            self.smtp_port.setText(str(preset["port"]))

    def _save_smtp(self):
        try:
            port = int(self.smtp_port.text().strip() or 587)
        except ValueError:
            port = 587
        self.db.save_smtp(
            host=self.smtp_host.text().strip(),
            port=port,
            user=self.smtp_user.text().strip(),
            password=self.smtp_pass.text(),
            recipient=self.smtp_recv.text().strip(),
            provider=self.smtp_provider.currentText())
        self.smtp_status.setText("✓ Сохранено")
        self.smtp_status.setStyleSheet(
            f"font-family:'Geist'; font-size:11px;"
            f"color:#2ecc71; background:transparent;"
        )
        self.logMessage.emit("SMTP настройки сохранены.")

    def _test_smtp(self):
        self.smtp_status.setText("Проверка...")
        self.smtp_status.setStyleSheet(
            f"font-family:'Geist'; font-size:11px;"
            f"color:{cfg.TEXT_MUTED}; background:transparent;"
        )
        host = self.smtp_host.text().strip()
        try:
            port = int(self.smtp_port.text().strip() or 587)
        except ValueError:
            port = 587
        user = self.smtp_user.text().strip()
        pwd = self.smtp_pass.text()

        def _do():
            ok, msg = test_smtp_connection(host, port, user, pwd)
            # Обновление UI — через сигнал, безопасно для треда
            color = "#2ecc71" if ok else "#e74c3c"
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(
                self.smtp_status, "setText", Qt.QueuedConnection, Q_ARG(str, msg))
            QMetaObject.invokeMethod(
                self.smtp_status, "setStyleSheet", Qt.QueuedConnection,
                Q_ARG(str, f"font-family:'Geist'; font-size:11px;"
                           f"color:{color}; background:transparent;"))
            self.logMessage.emit(f"SMTP тест: {msg}")

        threading.Thread(target=_do, daemon=True).start()

    def _build_tray_card(self, grid: QGridLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(_muted("СИСТЕМНЫЙ ТРЕЙ", card))

        info = QLabel(
            "При закрытии окно сворачивается в трей — приложение продолжает работать",
            card)
        info.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:13px; font-weight:600; background:transparent;"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        hide_btn = _btn_secondary("\u2193  Свернуть в трей", card)
        hide_btn.clicked.connect(self._hide_to_tray)
        btn_row.addWidget(hide_btn)

        quit_btn = QPushButton("\u2715  Выйти полностью", card)
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setFixedHeight(34)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Geist';
                background: {cfg.DANGER_BG}; color: {cfg.DANGER_COLOR};
                border: 1px solid #3a1515; border-radius: 6px;
                padding: 0 14px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #3a1515; }}
        """)
        quit_btn.clicked.connect(self._quit_app)
        btn_row.addWidget(quit_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        lay.addStretch(1)

        grid.addWidget(card, 3, 0, 1, 2)

    def _hide_to_tray(self):
        win = self.window()
        if win:
            win.hide()

    def _quit_app(self):
        win = self.window()
        if hasattr(win, '_force_quit'):
            win._force_quit = True
        if hasattr(win, '_tray_icon') and win._tray_icon:
            win._tray_icon.stop()
            win._tray_icon = None
        win.close()

    def _build_log_card(self, grid: QGridLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(_muted("СИСТЕМНЫЙ ЖУРНАЛ", card))
        hdr.addStretch(1)
        clear_btn = _btn_secondary("Очистить", card)
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(lambda: self.log_view.clear())
        hdr.addWidget(clear_btn)
        lay.addLayout(hdr)

        self.log_view = QPlainTextEdit(card)
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(150)
        self.log_view.setStyleSheet(f"""
            QPlainTextEdit {{
                font-family: 'Consolas', 'Courier New', monospace;
                background: {cfg.BG_APP}; color: #3dba7a;
                border: 1px solid {cfg.BORDER}; border-radius: 6px;
                font-size: 10px; padding: 6px;
            }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
            QScrollBar::handle:vertical {{
                background: {cfg.BORDER}; border-radius: 4px; min-height: 20px;
            }}
        """)
        lay.addWidget(self.log_view)

        self.logMessage.connect(self.append_log)

        grid.addWidget(card, 4, 0, 1, 2)

    def append_log(self, line: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {line}")
