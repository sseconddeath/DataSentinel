"""
qt_tools.py — страница «Инструменты»: генератор и проверка паролей.

Две колонки:
  • Слева:  генератор (режимы Random / Memorable / PIN) + оценка стойкости
  • Справа: проверка произвольного пароля на надёжность
"""
from __future__ import annotations

from PySide6.QtCore import (
    Qt, Signal, Property, QPropertyAnimation, QEasingCurve, QRect, QByteArray,
)
from PySide6.QtGui import QFont, QGuiApplication, QPainter, QColor, QMouseEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QSlider, QCheckBox, QProgressBar,
    QSizePolicy, QButtonGroup,
)

import core.config as cfg
from core.engine import LeakEngine

_CLOCK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
)

_REFRESH_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/>'
    '<path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>'
)

def _svg_pixmap(svg_tpl: str, color: str, size: int = 14):
    from PySide6.QtGui import QPixmap
    svg = svg_tpl.replace("{c}", color)
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    r.render(p)
    p.end()
    return pm

def _clock_pixmap(color: str, size: int = 14):
    return _svg_pixmap(_CLOCK_SVG, color, size)

def _refresh_pixmap(color: str, size: int = 16):
    return _svg_pixmap(_REFRESH_SVG, color, size)

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

def _btn_primary(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(40)
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

def _pill_btn(text: str, parent: QWidget | None = None) -> QPushButton:
    """Кнопка-таб (переключатель), checkable."""
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(True)
    b.setFixedHeight(34)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: transparent;
            color: {cfg.TEXT_SECONDARY};
            border: none;
            border-radius: 4px;
            padding: 0 14px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {cfg.BG_ELEVATED}; }}
        QPushButton:checked {{
            background: {cfg.ACCENT};
            color: white;
            font-weight: 700;
        }}
    """)
    return b

def _toggle_btn(text: str, color: str, parent: QWidget | None = None) -> QPushButton:
    """Цветной toggle-чип для опций Random (ABC / 123 / !&*)."""
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(True)
    b.setFixedHeight(36)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.BG_APP};
            color: {cfg.TEXT_SECONDARY};
            border: 1px solid {cfg.BORDER};
            border-radius: 6px;
            padding: 0 14px;
            font-size: 13px;
        }}
        QPushButton:checked {{
            background: {color};
            border: 1px solid {color};
            color: white;
            font-weight: 700;
        }}
    """)
    return b

def _slider(minimum: int, maximum: int, value: int,
            parent: QWidget | None = None) -> QSlider:
    s = QSlider(Qt.Horizontal, parent)
    s.setRange(minimum, maximum)
    s.setValue(value)
    s.setSingleStep(1)
    s.setPageStep(1)
    s.setStyleSheet(f"""
        QSlider::groove:horizontal {{
            background: {cfg.BORDER};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {cfg.ACCENT};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {cfg.ACCENT};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {cfg.ACCENT_HOVER};
        }}
    """)
    return s

def _progress(parent: QWidget | None = None) -> QProgressBar:
    p = QProgressBar(parent)
    p.setRange(0, 100)
    p.setValue(0)
    p.setTextVisible(False)
    p.setFixedHeight(4)
    p.setStyleSheet(f"""
        QProgressBar {{
            background: {cfg.BORDER};
            border: none;
            border-radius: 2px;
        }}
        QProgressBar::chunk {{
            background: {cfg.ACCENT};
            border-radius: 2px;
        }}
    """)
    return p

class ToggleSwitch(QWidget):
    """Apple-style toggle с подписью справа. Drop-in замена QCheckBox."""
    toggled = Signal(bool)

    TRACK_W = 36
    TRACK_H = 20
    KNOB_R = 8
    PAD = 2

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._checked = False
        self._knob_x = float(self.PAD)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self._label = QLabel(text, self)
        self._label.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:13px; background:transparent;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(self.TRACK_W + 10, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._label)
        lay.addStretch(1)

        self.setFixedHeight(max(self.TRACK_H, 22))

        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def _get_knob(self) -> float:
        return self._knob_x

    def _set_knob(self, v: float):
        self._knob_x = v
        self.update()

    knobPos = Property(float, _get_knob, _set_knob)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool):
        if self._checked == v:
            return
        self._checked = v
        target = self.TRACK_W - self.TRACK_H + self.PAD if v else self.PAD
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(float(target))
        self._anim.start()
        self.toggled.emit(v)

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        y = (self.height() - self.TRACK_H) // 2
        track = QRect(0, y, self.TRACK_W, self.TRACK_H)
        p.setPen(Qt.NoPen)
        bg = QColor(cfg.ACCENT) if self._checked else QColor(cfg.BG_INPUT)
        p.setBrush(bg)
        p.drawRoundedRect(track, self.TRACK_H // 2, self.TRACK_H // 2)
        if not self._checked:
            from PySide6.QtGui import QPen
            pen = QPen(QColor(cfg.BORDER))
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(track, self.TRACK_H // 2, self.TRACK_H // 2)
            p.setPen(Qt.NoPen)
        knob_d = self.TRACK_H - self.PAD * 2
        kr = QRect(int(self._knob_x), y + self.PAD, knob_d, knob_d)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(kr)
        p.end()

def _checkbox(text: str, parent: QWidget | None = None) -> ToggleSwitch:
    return ToggleSwitch(text, parent)

class ToolsPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{cfg.BG_APP};")

        # Состояние генератора
        self._mode = "Random"
        self._pass_len = 16
        self._use_upper = True
        self._use_digits = True
        self._use_symbols = True
        self._mem_words = 4
        self._mem_sep = "-"
        self._mem_cap = True
        self._mem_num = True
        self._pin_len = 6

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        title = QLabel("Инструменты", self)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;"
        )
        outer.addWidget(title)
        subtitle = QLabel("Генератор и проверка паролей", self)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:14px; background:transparent;"
        )
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        # Две колонки
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 58)
        grid.setColumnStretch(1, 42)
        outer.addLayout(grid, 1)

        gen_card = _card(self)
        gi = QVBoxLayout(gen_card)
        gi.setContentsMargins(20, 16, 20, 16)
        gi.setSpacing(10)
        gi.addWidget(_muted("ГЕНЕРАТОР ПАРОЛЕЙ", 11, gen_card))
        gi.addSpacing(4)

        # Режимы (tab bar)
        mode_bar = QFrame(gen_card)
        mode_bar.setObjectName("modeBar")
        mode_bar.setStyleSheet(
            f"QFrame#modeBar {{ background:{cfg.BG_APP}; border-radius:6px; }}"
        )
        mode_lay = QHBoxLayout(mode_bar)
        mode_lay.setContentsMargins(2, 2, 2, 2)
        mode_lay.setSpacing(2)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_btns: dict[str, QPushButton] = {}
        for m in ["Random", "Memorable", "PIN"]:
            b = _pill_btn(m, mode_bar)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, mode=m: self._set_mode(mode))
            mode_lay.addWidget(b)
            self._mode_btns[m] = b
        self._mode_btns["Random"].setChecked(True)
        gi.addWidget(mode_bar)

        # Результирующий пароль
        pass_frame = QFrame(gen_card)
        pass_frame.setObjectName("passFrame")
        pass_frame.setStyleSheet(
            f"QFrame#passFrame {{ background:{cfg.BG_APP}; border-radius:6px; }}"
        )
        pf_lay = QHBoxLayout(pass_frame)
        pf_lay.setContentsMargins(14, 6, 8, 6)
        pf_lay.setSpacing(8)
        self.gen_result = QLineEdit(pass_frame)
        self.gen_result.setReadOnly(True)
        self.gen_result.setFrame(False)
        self.gen_result.setStyleSheet(
            f"QLineEdit {{ background:transparent; border:none;"
            f"color:{cfg.ACCENT_TEXT};"
            f"font-family:'{cfg.FONT_MONO}'; font-size:16px;"
            f"selection-background-color:{cfg.ACCENT}; }}"
        )
        self.gen_result.setMinimumHeight(40)
        pf_lay.addWidget(self.gen_result, 1)
        copy_btn = _btn_primary("Копировать", pass_frame)
        copy_btn.setFixedHeight(34)
        copy_btn.clicked.connect(self._copy_password)
        pf_lay.addWidget(copy_btn)
        gi.addWidget(pass_frame)

        # Crack-time строка + полоса
        crack_row = QWidget(gen_card)
        crack_row.setStyleSheet("background:transparent;")
        cr_lay = QHBoxLayout(crack_row)
        cr_lay.setContentsMargins(0, 0, 0, 0)
        cr_lay.setSpacing(6)
        self.crack_icon = QLabel(crack_row)
        self.crack_icon.setPixmap(_clock_pixmap(cfg.SAFE_COLOR, 14))
        self.crack_icon.setStyleSheet("background:transparent;")
        self.crack_label = QLabel("", crack_row)
        self.crack_label.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.SAFE_COLOR};"
            f"font-size:12px; font-weight:700; background:transparent;"
        )
        cr_lay.addWidget(self.crack_icon)
        cr_lay.addWidget(self.crack_label)
        cr_lay.addStretch(1)
        gi.addWidget(crack_row)
        self.strength_bar = _progress(gen_card)
        gi.addWidget(self.strength_bar)
        gi.addSpacing(6)

        # Блок опций (перестраивается по режиму)
        self.options_wrap = QWidget(gen_card)
        self.options_wrap.setStyleSheet("background: transparent;")
        self.options_lay = QVBoxLayout(self.options_wrap)
        self.options_lay.setContentsMargins(0, 0, 0, 0)
        self.options_lay.setSpacing(8)
        gi.addWidget(self.options_wrap)

        gi.addSpacing(4)
        from PySide6.QtGui import QIcon
        regen_btn = _btn_primary("  Сгенерировать новый", gen_card)
        regen_btn.setIcon(QIcon(_refresh_pixmap("#ffffff", 16)))
        regen_btn.clicked.connect(self._generate)
        gi.addWidget(regen_btn, 0, Qt.AlignHCenter)

        gi.addStretch(1)
        grid.addWidget(gen_card, 0, 0)

        check_card = _card(self)
        ci = QVBoxLayout(check_card)
        ci.setContentsMargins(20, 16, 20, 16)
        ci.setSpacing(10)
        ci.addWidget(_muted("ПРОВЕРИТЬ ПАРОЛЬ", 11, check_card))
        hint = QLabel("Введите пароль чтобы узнать насколько он надёжен", check_card)
        hint.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:13px; background:transparent;"
        )
        hint.setWordWrap(True)
        ci.addWidget(hint)

        self.check_entry = QLineEdit(check_card)
        self.check_entry.setPlaceholderText("Введите пароль...")
        self.check_entry.setFixedHeight(40)
        self.check_entry.setStyleSheet(f"""
            QLineEdit {{
                font-family: 'Geist';
                background: {cfg.BG_INPUT};
                color: {cfg.TEXT_PRIMARY};
                border: 1px solid {cfg.BORDER};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 13px;
                selection-background-color: {cfg.ACCENT};
            }}
            QLineEdit:focus {{ border: 1px solid {cfg.ACCENT}; }}
        """)
        self.check_entry.textChanged.connect(self._on_check_type)
        ci.addWidget(self.check_entry)

        self.check_result = QLabel("", check_card)
        self.check_result.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:13px; font-weight:700; background:transparent;"
        )
        ci.addWidget(self.check_result)

        self.check_bar = _progress(check_card)
        ci.addWidget(self.check_bar)
        ci.addStretch(1)
        grid.addWidget(check_card, 0, 1)

        # Инициализируем опции и первую генерацию
        self._build_options()
        self._generate()

    def _clear_options(self):
        while self.options_lay.count():
            it = self.options_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            else:
                lay = it.layout()
                if lay is not None:
                    self._clear_layout(lay)

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
            elif it.layout() is not None:
                self._clear_layout(it.layout())

    def _build_options(self):
        self._clear_options()
        if self._mode == "Random":
            self._build_random_options()
        elif self._mode == "Memorable":
            self._build_memorable_options()
        else:
            self._build_pin_options()

    def _build_random_options(self):
        # Длина
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(_label("Длина:", 13, cfg.TEXT_SECONDARY, self.options_wrap))
        self._len_slider = _slider(8, 32, self._pass_len, self.options_wrap)
        self._len_slider.valueChanged.connect(self._on_len_changed)
        row1.addWidget(self._len_slider, 1)
        self._len_lbl = _label(str(self._pass_len), 13, cfg.ACCENT_TEXT, self.options_wrap)
        self._len_lbl.setFixedWidth(30)
        row1.addWidget(self._len_lbl)
        self.options_lay.addLayout(row1)

        # Тип символов
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        configs = [
            ("ABC  Заглавные", "#3B8ED0", "_use_upper"),
            ("123  Цифры",     "#2ECC71", "_use_digits"),
            ("!&*  Символы",   "#E67E22", "_use_symbols"),
        ]
        for label, color, attr in configs:
            b = _toggle_btn(label, color, self.options_wrap)
            b.setChecked(getattr(self, attr))
            b.toggled.connect(lambda checked, a=attr: self._toggle_flag(a, checked))
            row2.addWidget(b, 1)
        self.options_lay.addLayout(row2)

    def _on_len_changed(self, v: int):
        self._pass_len = v
        self._len_lbl.setText(str(v))
        self._generate()

    def _toggle_flag(self, attr: str, checked: bool):
        setattr(self, attr, checked)
        self._generate()

    def _build_memorable_options(self):
        # Количество слов
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(_label("Слов:", 13, cfg.TEXT_SECONDARY, self.options_wrap))
        self._mem_lbl = _label(str(self._mem_words), 13, cfg.ACCENT_TEXT, self.options_wrap)
        self._mem_lbl.setFixedWidth(24)
        row1.addWidget(self._mem_lbl)
        self._words_slider = _slider(2, 8, self._mem_words, self.options_wrap)
        self._words_slider.valueChanged.connect(self._on_words_changed)
        row1.addWidget(self._words_slider, 1)
        self.options_lay.addLayout(row1)

        # Разделитель
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(_label("Разделитель:", 13, cfg.TEXT_SECONDARY, self.options_wrap))
        sep_bar = QFrame(self.options_wrap)
        sep_bar.setObjectName("sepBar")
        sep_bar.setStyleSheet(
            f"QFrame#sepBar {{ background:{cfg.BG_APP}; border-radius:6px; }}"
        )
        sep_lay = QHBoxLayout(sep_bar)
        sep_lay.setContentsMargins(2, 2, 2, 2)
        sep_lay.setSpacing(2)
        self._sep_group = QButtonGroup(self.options_wrap)
        self._sep_group.setExclusive(True)
        for sep, label in [("-", "-"), (".", "."), ("_", "_"), (" ", "Пробел")]:
            b = _pill_btn(label, sep_bar)
            b.setFixedWidth(78 if sep == " " else 44)
            if sep == self._mem_sep:
                b.setChecked(True)
            b.clicked.connect(lambda _=False, s=sep: self._set_sep(s))
            self._sep_group.addButton(b)
            sep_lay.addWidget(b)
        row2.addWidget(sep_bar)
        row2.addStretch(1)
        self.options_lay.addLayout(row2)

        # Чекбоксы
        cap_cb = _checkbox("Заглавные буквы", self.options_wrap)
        cap_cb.setChecked(self._mem_cap)
        cap_cb.toggled.connect(lambda v: (setattr(self, "_mem_cap", v), self._generate()))
        self.options_lay.addWidget(cap_cb)

        num_cb = _checkbox("Добавить цифры", self.options_wrap)
        num_cb.setChecked(self._mem_num)
        num_cb.toggled.connect(lambda v: (setattr(self, "_mem_num", v), self._generate()))
        self.options_lay.addWidget(num_cb)

    def _on_words_changed(self, v: int):
        self._mem_words = v
        self._mem_lbl.setText(str(v))
        self._generate()

    def _set_sep(self, sep: str):
        self._mem_sep = sep
        self._generate()

    def _build_pin_options(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_label("Длина PIN:", 13, cfg.TEXT_SECONDARY, self.options_wrap))
        pin_bar = QFrame(self.options_wrap)
        pin_bar.setObjectName("pinBar")
        pin_bar.setStyleSheet(
            f"QFrame#pinBar {{ background:{cfg.BG_APP}; border-radius:6px; }}"
        )
        pl = QHBoxLayout(pin_bar)
        pl.setContentsMargins(2, 2, 2, 2)
        pl.setSpacing(2)
        self._pin_group = QButtonGroup(self.options_wrap)
        self._pin_group.setExclusive(True)
        for length in [4, 6, 8, 10]:
            b = _pill_btn(str(length), pin_bar)
            b.setFixedWidth(50)
            if length == self._pin_len:
                b.setChecked(True)
            b.clicked.connect(lambda _=False, l=length: self._set_pin_len(l))
            self._pin_group.addButton(b)
            pl.addWidget(b)
        row.addWidget(pin_bar)
        row.addStretch(1)
        self.options_lay.addLayout(row)

    def _set_pin_len(self, length: int):
        self._pin_len = length
        self._generate()

    def _set_mode(self, mode: str):
        self._mode = mode
        for m, b in self._mode_btns.items():
            b.setChecked(m == mode)
        self._build_options()
        self._generate()

    def _generate(self):
        if self._mode == "Random":
            if not (self._use_upper or self._use_digits or self._use_symbols):
                # Минимум строчные — LeakEngine скорее всего сам обработает,
                # но подстрахуемся здесь.
                pwd = LeakEngine.generate_random(
                    length=self._pass_len, upper=False,
                    digits=False, symbols=False)
            else:
                pwd = LeakEngine.generate_random(
                    length=self._pass_len,
                    upper=self._use_upper,
                    digits=self._use_digits,
                    symbols=self._use_symbols)
        elif self._mode == "Memorable":
            pwd = LeakEngine.generate_memorable(
                words=self._mem_words,
                separator=self._mem_sep,
                capitalize=self._mem_cap,
                add_number=self._mem_num)
        else:
            pwd = LeakEngine.generate_pin(self._pin_len)

        self.gen_result.setText(pwd)
        self._update_crack(pwd)

    def _update_crack(self, pwd: str):
        if self._mode == "PIN":
            pin_ratings = {
                4:  (1, "Базовый PIN",   "#e67e22", "Минуты"),
                6:  (3, "Стандартный",   "#f1c40f", "Часы"),
                8:  (4, "Надёжный PIN",  "#2ecc71", "Дни"),
                10: (5, "Очень надёжный","#27ae60", "Месяцы"),
            }
            score, s_label, s_color, crack_label = pin_ratings.get(
                len(pwd), (2, "PIN", "#f1c40f", "Часы"))
            crack_color = s_color
        else:
            crack_label, crack_color = LeakEngine.estimate_crack_time(pwd)
            score, s_label, s_color = LeakEngine.check_password_strength(pwd)

        self.crack_label.setText(
            f"{crack_label} чтобы взломать  ·  Надёжность: {s_label}")
        self.crack_label.setStyleSheet(
            f"font-family:'Geist'; color:{crack_color};"
            f"font-size:12px; font-weight:700; background:transparent;"
        )
        self.crack_icon.setPixmap(_clock_pixmap(crack_color, 14))
        self.strength_bar.setValue(int(score / 5 * 100))
        self.strength_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {cfg.BORDER};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {s_color};
                border-radius: 2px;
            }}
        """)

    def _copy_password(self):
        pwd = self.gen_result.text()
        if pwd:
            QGuiApplication.clipboard().setText(pwd)

    def _on_check_type(self, text: str):
        pwd = text
        if not pwd:
            self.check_result.setText("")
            self.check_bar.setValue(0)
            return
        crack, cc = LeakEngine.estimate_crack_time(pwd)
        score, sl, sc = LeakEngine.check_password_strength(pwd)
        self.check_result.setText(f"{crack}  ·  {sl}")
        self.check_result.setStyleSheet(
            f"font-family:'Geist'; color:{cc};"
            f"font-size:13px; font-weight:700; background:transparent;"
        )
        self.check_bar.setValue(int(score / 5 * 100))
        self.check_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {cfg.BORDER};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {sc};
                border-radius: 2px;
            }}
        """)
