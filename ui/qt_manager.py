"""Страница «Менеджер данных»: объекты мониторинга и API-ключи."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QSizePolicy,
)

import core.config as cfg
from core.engine import LeakEngine
from ui.qt_icons import detect_kind, make_type_pixmap

def _card(parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("card")
    f.setStyleSheet(
        f"QFrame#card {{ background:{cfg.BG_SURFACE};"
        f"border:1px solid {cfg.BORDER}; border-radius:12px; }}"
    )
    return f

def _muted(text: str, size: int = 11, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:{size}px;"
        f"font-weight:700; letter-spacing:1px; background:transparent;"
    )
    return lbl

def _label(text: str, size: int = 13, color: str | None = None,
           parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"font-family:'Geist'; color:{color or cfg.TEXT_PRIMARY};"
        f"font-size:{size}px; background:transparent;"
    )
    return lbl

def _input(placeholder: str = "", password: bool = False,
           parent: QWidget | None = None) -> QLineEdit:
    e = QLineEdit(parent)
    e.setPlaceholderText(placeholder)
    if password:
        e.setEchoMode(QLineEdit.Password)
    e.setFixedHeight(38)
    e.setStyleSheet(f"""
        QLineEdit {{
            font-family: 'Geist';
            background: {cfg.BG_INPUT};
            color: {cfg.TEXT_PRIMARY};
            border: 1px solid {cfg.BORDER};
            border-radius: 6px;
            padding: 0 10px;
            font-size: 13px;
            selection-background-color: {cfg.ACCENT};
        }}
        QLineEdit:focus {{
            border: 1px solid {cfg.ACCENT};
        }}
    """)
    return e

def _btn_primary(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(38)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.ACCENT};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 0 18px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {cfg.ACCENT_HOVER}; }}
    """)
    return b

def _btn_secondary(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(36)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.BG_ELEVATED};
            color: {cfg.TEXT_PRIMARY};
            border: 1px solid {cfg.BORDER};
            border-radius: 6px;
            padding: 0 14px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{ border: 1px solid {cfg.BORDER_HOVER}; }}
    """)
    return b

def _btn_icon(text: str, hover_bg: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(32, 32)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: transparent;
            color: {cfg.TEXT_MUTED};
            border: none;
            border-radius: 6px;
            font-size: 14px;
        }}
        QPushButton:hover {{
            background: {hover_bg};
            color: {cfg.TEXT_PRIMARY};
        }}
    """)
    return b

def _badge(text: str, parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setMinimumWidth(28)
    lbl.setFixedHeight(20)
    lbl.setStyleSheet(
        f"QLabel {{ font-family:'Geist'; background:{cfg.ACCENT_MUTED};"
        f"color:{cfg.ACCENT_TEXT}; border-radius:10px; padding:0 8px;"
        f"font-size:11px; font-weight:700; }}"
    )
    return lbl

class TargetRow(QFrame):
    deleted = Signal(int)

    def __init__(self, t_id: int, value: str, parent=None):
        super().__init__(parent)
        self.t_id = t_id
        self.setObjectName("targetRow")
        self.setStyleSheet(
            f"QFrame#targetRow {{ background:{cfg.BG_ELEVATED};"
            f"border-radius:6px; }}"
        )
        self.setFixedHeight(44)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(10)

        kind = detect_kind(value)
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(make_type_pixmap(kind, cfg.ACCENT_TEXT, 18))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent;")
        icon_lbl.setFixedWidth(24)
        lay.addWidget(icon_lbl)

        val_lbl = QLabel(value, self)
        val_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY};"
            f"font-size:13px; background:transparent;"
        )
        val_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(val_lbl, 1)

        del_btn = _btn_icon("\u2715", cfg.DANGER_BG, self)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.t_id))
        lay.addWidget(del_btn)

class ManagerPage(QWidget):
    def __init__(self, db, on_stats_changed=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._on_stats_changed = on_stats_changed
        self.setStyleSheet(f"background:{cfg.BG_APP};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        title = QLabel("Менеджер данных", self)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;"
        )
        outer.addWidget(title)
        subtitle = QLabel("Управление объектами мониторинга", self)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:14px; background:transparent;"
        )
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid, 1)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        grid.addLayout(left_col, 0, 0)

        add_card = _card(self)
        add_lay = QVBoxLayout(add_card)
        add_lay.setContentsMargins(20, 16, 20, 16)
        add_lay.setSpacing(10)
        add_lay.addWidget(_muted("ДОБАВИТЬ ОБЪЕКТ", 11, add_card))

        row = QHBoxLayout()
        row.setSpacing(10)
        self.entry = _input(
            "name@example.com  ·  +79991234567  ·  username  ·  пароль",
            parent=add_card,
        )
        self.entry.returnPressed.connect(self._add)
        row.addWidget(self.entry, 1)
        add_btn = _btn_primary("+  Добавить", add_card)
        add_btn.clicked.connect(self._add)
        row.addWidget(add_btn)
        add_lay.addLayout(row)

        # Подсказка с примерами того, что можно мониторить и какие источники
        # отрабатывают на каком типе объекта.
        hint = QLabel(
            "Можно добавлять:\n"
            "  •  Email — проверка по 8 источникам (HIBP, LeakCheck, XposedOrNot,\n"
            "      ProxyNova, Pastebin, Hudson Rock, EmailRep, BreachDirectory, IntelX)\n"
            "  •  Телефон в любом формате (+7 999 123-45-67) — IntelX, BreachDirectory,\n"
            "      ProxyNova, Pastebin\n"
            "  •  Username / никнейм (Telegram, Discord) — Hudson Rock username\n"
            "  •  Пароль — HIBP Pwned Passwords (хеш k-anonymity, сам пароль не уходит)",
            add_card,
        )
        hint.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:12px;"
            f"background:transparent; line-height:160%;"
        )
        hint.setWordWrap(True)
        add_lay.addWidget(hint)

        left_col.addWidget(add_card)

        list_card = _card(self)
        list_lay = QVBoxLayout(list_card)
        list_lay.setContentsMargins(20, 16, 20, 16)
        list_lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_muted("ОБЪЕКТЫ МОНИТОРИНГА", 11, list_card))
        self.count_badge = _badge("0", list_card)
        hdr.addWidget(self.count_badge)
        hdr.addStretch(1)
        list_lay.addLayout(hdr)

        self.scroll = QScrollArea(list_card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {cfg.BORDER}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {cfg.BORDER_HOVER}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_lay = QVBoxLayout(self.list_container)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(6)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(self.list_container)
        list_lay.addWidget(self.scroll, 1)

        left_col.addWidget(list_card, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        grid.addLayout(right_col, 0, 1)

        keys_card = _card(self)
        keys_lay = QVBoxLayout(keys_card)
        keys_lay.setContentsMargins(20, 16, 20, 16)
        keys_lay.setSpacing(8)
        keys_lay.addWidget(_muted("API КЛЮЧИ", 11, keys_card))
        keys_lay.addSpacing(4)

        self._key_entries: dict[str, QLineEdit] = {}
        for label, svc, hint in [
            ("RapidAPI Key", "rapidapi",
             "BreachDirectory · breachdirectory.p.rapidapi.com"),
            ("IntelX API Key", "intelx",
             "Dark Web · intelx.io → Developer"),
        ]:
            keys_lay.addWidget(_label(label, 13, cfg.TEXT_SECONDARY, keys_card))
            hint_lbl = QLabel(hint, keys_card)
            hint_lbl.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
                f"font-size:11px; background:transparent;"
            )
            keys_lay.addWidget(hint_lbl)

            # Если у пользователя нет своего ключа, но в сборку встроен —
            # подсказываем, что приложение и так работает «из коробки».
            from core.engine import _builtin_rapidapi, _builtin_intelx
            builtin = _builtin_rapidapi() if svc == "rapidapi" else (
                      _builtin_intelx() if svc == "intelx" else "")
            placeholder = ("Встроенный ключ активен — введите свой для приоритета"
                           if builtin else "Вставьте ключ...")

            row = QHBoxLayout()
            row.setSpacing(6)
            entry = _input(placeholder, password=True, parent=keys_card)
            entry.setFixedHeight(36)
            saved = self.db.get_api_key(svc)
            if saved:
                entry.setText(saved)
            row.addWidget(entry, 1)

            save_btn = _btn_secondary("Сохранить", keys_card)
            save_btn.clicked.connect(lambda _=False, s=svc, e=entry: self._save_key(s, e))
            row.addWidget(save_btn)

            clear_btn = _btn_icon("\u2715", cfg.DANGER_BG, keys_card)
            clear_btn.clicked.connect(lambda _=False, s=svc, e=entry: self._clear_key(s, e))
            row.addWidget(clear_btn)

            keys_lay.addLayout(row)
            keys_lay.addSpacing(6)
            self._key_entries[svc] = entry

        keys_lay.addStretch(1)
        right_col.addWidget(keys_card)
        right_col.addStretch(1)

        self.refresh_list()

    def _add(self):
        v = self.entry.text().strip()
        if not v:
            return
        self.db.add_target(v)
        self.entry.clear()
        self.refresh_list()
        if self._on_stats_changed:
            self._on_stats_changed()

    def _delete(self, t_id: int):
        self.db.delete_target(t_id)
        self.refresh_list()
        if self._on_stats_changed:
            self._on_stats_changed()

    def refresh_list(self):

        while self.list_lay.count() > 1:
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        targets = self.db.get_all_targets()
        self.count_badge.setText(str(len(targets)))
        for t_id, val in targets:
            row = TargetRow(t_id, val, self.list_container)
            row.deleted.connect(self._delete)
            self.list_lay.insertWidget(self.list_lay.count() - 1, row)

    def _save_key(self, service: str, entry: QLineEdit):
        key = entry.text().strip()
        if not key:
            return
        self.db.set_api_key(service, key)
        # Обновляем класс-атрибуты LeakEngine
        if service == "rapidapi":
            LeakEngine.RAPID_API_KEY = key
        elif service == "intelx":
            LeakEngine.INTELX_API_KEY = key

    def _clear_key(self, service: str, entry: QLineEdit):
        entry.clear()
        self.db.set_api_key(service, "")
        # При очистке возвращаемся ко встроенному ключу (если есть),
        # иначе источник просто отключится в qt_scan.
        from core.engine import _builtin_rapidapi, _builtin_intelx
        if service == "rapidapi":
            LeakEngine.RAPID_API_KEY = _builtin_rapidapi()
        elif service == "intelx":
            LeakEngine.INTELX_API_KEY = _builtin_intelx()
