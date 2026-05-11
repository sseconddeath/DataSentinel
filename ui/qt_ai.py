"""Страница «AI Помощник»: чат с Groq/Ollama, стриминг ответов."""
from __future__ import annotations

import os
import re
import threading
import webbrowser
import subprocess

from PySide6.QtCore import Qt, Signal, QObject, QMetaObject, Q_ARG
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QTextEdit, QSizePolicy, QProgressBar,
    QButtonGroup,
)

import core.config as cfg

try:
    import services.ai_assistant as ai_mod
    AI_OK = True
except Exception:
    AI_OK = False
    ai_mod = None

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

def _input(placeholder: str = "", parent: QWidget | None = None) -> QLineEdit:
    e = QLineEdit(parent)
    e.setPlaceholderText(placeholder)
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
        QLineEdit:focus {{ border: 1px solid {cfg.ACCENT}; }}
        QLineEdit:disabled {{
            background: {cfg.BG_ELEVATED}; color: {cfg.TEXT_MUTED};
        }}
    """)
    return e

def _btn_primary(text: str, parent: QWidget | None = None,
                 height: int = 38) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(height)
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
        QPushButton:disabled {{ background: {cfg.BG_ELEVATED}; color: {cfg.TEXT_MUTED}; }}
    """)
    return b

def _btn_secondary(text: str, parent: QWidget | None = None,
                   height: int = 36) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(height)
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

def _btn_provider(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCheckable(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(40)
    b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.BG_APP};
            color: {cfg.TEXT_SECONDARY};
            border: 1px solid {cfg.BORDER};
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            padding: 0 14px;
        }}
        QPushButton:hover {{
            background: {cfg.BG_ELEVATED};
            border: 1px solid {cfg.BORDER_HOVER};
        }}
        QPushButton:checked {{
            background: {cfg.ACCENT};
            color: white;
            border: 1px solid {cfg.ACCENT};
            font-weight: 700;
        }}
    """)
    return b

def _btn_quick(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(36)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.ACCENT_MUTED};
            color: {cfg.ACCENT_TEXT};
            border: none;
            border-radius: 6px;
            padding: 0 12px;
            font-size: 13px;
            font-weight: 600;
            text-align: left;
        }}
        QPushButton:hover {{
            background: {cfg.ACCENT};
            color: white;
        }}
    """)
    return b

class AIPage(QWidget):
    # Сигналы для обновлений из фоновых потоков
    statusChanged = Signal(str, str)     # dot_color, status_text
    installState = Signal(str, str, str)  # install_text|"", download("show"/"hide"), install("show"/"hide")
    appendMessage = Signal(str, str)     # sender, text
    streamLine = Signal(str)
    streamDone = Signal()
    progressUpdate = Signal(str, float)

    QUICK = [
        ("Насколько я защищён?",
         "Оцени мой уровень защиты на основе найденных утечек. Что самое опасное?"),
        ("План защиты",
         "Составь пошаговый план что нужно сделать для защиты данных. По приоритетам."),
        ("Объясни угрозы",
         "Объясни простым языком какие конкретные угрозы несут найденные утечки."),
        ("Советы по паролям",
         "Дай конкретные советы по паролям с учётом моих утечек."),
        ("Что такое Dark Web?",
         "Объясни что такое Dark Web и почему мои данные там опасны."),
        ("Защита email",
         "Мой email найден в утечках. Что мне грозит и как защитить почту?"),
    ]

    def __init__(self, db, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.setStyleSheet(f"background:{cfg.BG_APP};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        title = QLabel("AI Помощник", self)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;"
        )
        outer.addWidget(title)
        subtitle = QLabel("Анализ безопасности с искусственным интеллектом", self)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:14px; background:transparent;"
        )
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 4)
        grid.setColumnStretch(1, 6)
        grid.setRowStretch(0, 1)
        outer.addLayout(grid, 1)

        left = QVBoxLayout()
        left.setSpacing(12)
        grid.addLayout(left, 0, 0)

        self._build_provider_card(left)
        self._build_quick_card(left)

        right = QVBoxLayout()
        right.setSpacing(12)
        grid.addLayout(right, 0, 1)

        self._build_chat_card(right)

        self.statusChanged.connect(self._on_status_changed)
        self.installState.connect(self._on_install_state)
        self.appendMessage.connect(self._ai_append)
        self.streamLine.connect(self._ai_stream_line)
        self.streamDone.connect(self._on_stream_done)
        self.progressUpdate.connect(self._on_progress)

        # Чтобы пропускать пустую строку сразу после заголовка:
        # AI обычно ставит \n после ##, а нам нужен компактный отступ.
        self._last_was_heading = False

        # История чата (sender, text) — для replay'я при смене темы.
        # Цвета QTextCharFormat запекаются в момент вставки, чтобы они
        # обновились — приходится перерисовать весь документ.
        self._chat_log: list[tuple[str, str]] = []

        saved_prov = self.db.get_setting("ai_provider", "groq")
        self._set_provider_ui(saved_prov)
        self._ai_append(
            "Скиппи",
            "Привет! Я Скиппи — твой AI-помощник по кибербезопасности.\n"
            "Отвечаю на основе реальных данных из вашего журнала утечек.\n\n"
            "Выберите провайдера слева, введите ключ и задайте вопрос.\n"
            "Groq — бесплатно и быстро, Ollama — локально без интернета."
        )
        threading.Thread(target=self._check_status, daemon=True).start()

    def _build_provider_card(self, parent_lay: QVBoxLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        lay.addWidget(_muted("AI ПРОВАЙДЕР", 11, card))

        prov_bar = QWidget(card)
        prov_bar.setStyleSheet("background:transparent;")
        pbl = QHBoxLayout(prov_bar)
        pbl.setContentsMargins(0, 0, 0, 0)
        pbl.setSpacing(8)

        self._prov_group = QButtonGroup(self)
        self._prov_group.setExclusive(True)
        self._prov_btns: dict[str, QPushButton] = {}
        for prov, label in [("groq", "Groq"), ("ollama", "Ollama")]:
            b = _btn_provider(label, prov_bar)
            b.clicked.connect(lambda _=False, p=prov: self._set_provider(p))
            pbl.addWidget(b, 1)
            self._prov_group.addButton(b)
            self._prov_btns[prov] = b
        lay.addWidget(prov_bar)

        # API-ключ для Groq встроен в приложение (см. ai_assistant._builtin_groq).
        # Ollama работает локально — ключ ей не нужен. Поле ввода ключа в UI больше нет.

        # Статус
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._status_dot = QLabel("●", card)
        self._status_dot.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:12px; background:transparent;"
        )
        status_row.addWidget(self._status_dot)
        self._status_lbl = QLabel("Не проверено", card)
        self._status_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:12px; background:transparent;"
        )
        status_row.addWidget(self._status_lbl)
        status_row.addStretch(1)
        lay.addSpacing(4)
        lay.addLayout(status_row)

        # Кнопки установки / скачивания модели
        self._install_btn = _btn_primary("Установить Ollama", card, height=32)
        self._install_btn.clicked.connect(self._install_ollama)
        self._install_btn.hide()
        lay.addWidget(self._install_btn)

        self._download_btn = _btn_primary("\u2193  Скачать модель (5GB)", card, height=32)
        self._download_btn.clicked.connect(self._download_model)
        self._download_btn.hide()
        lay.addWidget(self._download_btn)

        self._progress_lbl = QLabel("", card)
        self._progress_lbl.setWordWrap(True)
        self._progress_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:11px; background:transparent;"
        )
        lay.addWidget(self._progress_lbl)

        self._progress_bar = QProgressBar(card)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {cfg.BORDER};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {cfg.ACCENT};
                border-radius: 3px;
            }}
        """)
        self._progress_bar.hide()
        lay.addWidget(self._progress_bar)

        parent_lay.addWidget(card)

    def _build_quick_card(self, parent_lay: QVBoxLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        lay.addWidget(_muted("БЫСТРЫЕ ВОПРОСЫ", 11, card))
        lay.addSpacing(4)
        for label, prompt in self.QUICK:
            b = _btn_quick(label, card)
            b.clicked.connect(lambda _=False, p=prompt: self._quick_ask(p))
            lay.addWidget(b)
        lay.addStretch(1)
        parent_lay.addWidget(card, 1)

    def _build_chat_card(self, parent_lay: QVBoxLayout):
        card = _card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        self.chat = QTextEdit(card)
        self.chat.setReadOnly(True)
        self.chat.setStyleSheet(f"""
            QTextEdit {{
                background: {cfg.BG_APP};
                color: {cfg.TEXT_PRIMARY};
                border: 1px solid {cfg.BORDER};
                border-radius: 8px;
                font-family: 'Geist';
                font-size: 13px;
                padding: 14px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 6px 2px 6px 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {cfg.BORDER_HOVER};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {cfg.TEXT_MUTED}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; background: transparent; border: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)
        doc = self.chat.document()
        doc.setDocumentMargin(4)
        lay.addWidget(self.chat, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input = _input("Задайте вопрос о вашей безопасности...", parent=card)
        self.input.setFixedHeight(40)
        self.input.returnPressed.connect(self._send)
        input_row.addWidget(self.input, 1)
        self.send_btn = _btn_primary("→", card, height=40)
        self.send_btn.setFixedWidth(46)
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.send_btn)
        lay.addLayout(input_row)

        parent_lay.addWidget(card, 1)

    def _set_provider(self, prov: str):
        self.db.set_setting("ai_provider", prov)
        self._set_provider_ui(prov)
        self._status_dot.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:12px; background:transparent;"
        )
        self._status_lbl.setText("Проверка...")
        threading.Thread(target=self._check_status, daemon=True).start()

    def _set_provider_ui(self, prov: str):
        for p, b in self._prov_btns.items():
            b.setChecked(p == prov)
        self._install_btn.hide()
        self._download_btn.hide()
        self._progress_bar.hide()
        self._progress_lbl.clear()

    def _check_status(self):
        if not AI_OK:
            self.statusChanged.emit(cfg.DANGER_COLOR, "ai_assistant.py не найден")
            return
        prov = self.db.get_setting("ai_provider", "groq")

        def emit_status(color: str, text: str):
            # Защита от гонок: если пользователь успел переключить провайдера,
            # игнорируем устаревший результат фоновой проверки.
            if self.db.get_setting("ai_provider", "groq") != prov:
                return
            self.statusChanged.emit(color, text)

        def emit_install(*args):
            if self.db.get_setting("ai_provider", "groq") != prov:
                return
            self.installState.emit(*args)

        if prov == "ollama":
            if not ai_mod.OllamaAssistant.is_on_disk():
                emit_status(cfg.DANGER_COLOR, "Ollama не установлена")
                emit_install("Установить Ollama", "hide", "show")
                return
            if not ai_mod.OllamaAssistant.is_running():
                emit_status(cfg.WARNING_COLOR, "Ollama не запущена")
                emit_install("▶  Открыть Ollama", "hide", "show")
                return
            if not ai_mod.OllamaAssistant.is_available():
                emit_status(cfg.WARNING_COLOR, "Модель не скачана")
                emit_install("", "show", "hide")
                return
            emit_status(cfg.SAFE_COLOR, "Готово · llama3.1:8b")
            emit_install("", "hide", "hide")
        else:
            # Groq: ключ встроен в приложение, всегда готово.
            names = {"groq": "Groq · Llama 3.3 70B"}
            emit_status(cfg.SAFE_COLOR, f"Готово · {names.get(prov, prov)}")

    def _on_status_changed(self, color: str, text: str):
        self._status_dot.setStyleSheet(
            f"font-family:'Geist'; color:{color};"
            f"font-size:12px; background:transparent;"
        )
        self._status_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{color};"
            f"font-size:12px; background:transparent;"
        )
        self._status_lbl.setText(text)

    def _on_install_state(self, install_text: str, download: str, install: str):
        if install_text:
            self._install_btn.setText(install_text)
        if install == "show":
            self._install_btn.setEnabled(True)
            self._install_btn.show()
        elif install == "hide":
            self._install_btn.hide()
        if download == "show":
            self._download_btn.setEnabled(True)
            self._download_btn.show()
        elif download == "hide":
            self._download_btn.hide()
            self._progress_bar.hide()

    def _install_ollama(self):
        self._install_btn.setEnabled(False)
        if "Открыть" in self._install_btn.text():
            self._install_btn.setText("Запускаем...")
            self._ai_append("Система", "Запускаю Ollama... подождите 5 секунд.")
            try:
                subprocess.Popen(
                    ["ollama", "serve"],
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
            except Exception:
                path = os.path.expandvars(
                    r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
                if os.path.exists(path):
                    subprocess.Popen([path])
                else:
                    self._ai_append("Система",
                                    "Откройте Ollama вручную через меню Пуск.")
                    self._install_btn.setEnabled(True)
                    return

            def _later():
                self._install_btn.setEnabled(True)
                threading.Thread(target=self._check_status, daemon=True).start()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(5000, _later)
            return

        self._install_btn.setText("Устанавливаем...")
        self._ai_append("Система",
                        "Запускаю установку Ollama...\nПосле — перезапустите приложение.")

        def _do():
            ok, msg = ai_mod.OllamaAssistant.install_windows()
            self.appendMessage.emit("Система", msg)
        threading.Thread(target=_do, daemon=True).start()

    def _download_model(self):
        self._download_btn.setEnabled(False)
        self._download_btn.setText("Скачиваем...")
        self._progress_bar.show()
        self._progress_bar.setValue(0)
        self._ai_append("Система", "Скачиваю llama3.1:8b (~5GB)...")

        def _progress(text, pct):
            self.progressUpdate.emit(text or "", float(pct) if pct is not None else 0.0)

        def _do():
            ok, msg = ai_mod.OllamaAssistant.pull_model(progress_callback=_progress)
            self.appendMessage.emit("Система", msg)
            threading.Thread(target=self._check_status, daemon=True).start()
        threading.Thread(target=_do, daemon=True).start()

    def _on_progress(self, text: str, pct: float):
        self._progress_lbl.setText(text)
        self._progress_bar.setValue(int(pct * 100 if pct <= 1 else pct))

    def _quick_ask(self, prompt: str):
        self.input.setText(prompt)
        self._send()

    def _send(self):
        q = self.input.text().strip()
        if not q:
            return
        self.input.clear()
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")
        self._ai_append("Вы", q)

        self._append_sender("Скиппи", "ai")
        buf = [""]

        def _chunk(chunk: str):
            buf[0] += chunk
            if "\n" in buf[0]:
                lines = buf[0].split("\n")
                for line in lines[:-1]:
                    self.streamLine.emit(line)
                buf[0] = lines[-1]

        def _do():
            if not AI_OK:
                self.streamLine.emit("Положите ai_assistant.py рядом с main_qt.py")
                self.streamDone.emit()
                return
            try:
                prov = self.db.get_setting("ai_provider", "groq")
                api_key = self.db.get_setting(f"ai_key_{prov}", "")
                context = ai_mod.AIAssistant.build_context(self.db)
                ai_mod.AIAssistant.ask(prov, api_key, q, context,
                                       stream_callback=_chunk)
            except Exception as e:
                self.streamLine.emit(f"Ошибка: {e}")
            if buf[0]:
                self.streamLine.emit(buf[0])
                buf[0] = ""
            self.streamDone.emit()

        threading.Thread(target=_do, daemon=True).start()

    def _on_stream_done(self):
        cur = self.chat.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText("\n")
        self.chat.setTextCursor(cur)
        self.chat.ensureCursorVisible()
        self.send_btn.setEnabled(True)
        self.send_btn.setText("→")

    def _append_sender(self, sender: str, kind: str):
        cur = self.chat.textCursor()
        cur.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        color = {
            "ai": cfg.ACCENT_TEXT,
            "user": cfg.TEXT_MUTED,
            "sys": cfg.WARNING_COLOR,
        }.get(kind, cfg.ACCENT_TEXT)
        fmt.setForeground(QColor(color))
        fmt.setFontPointSize(13)
        fmt.setFontWeight(QFont.Bold)
        cur.insertText("\n", QTextCharFormat())
        cur.insertText(f"{sender}\n", fmt)
        self.chat.setTextCursor(cur)
        self.chat.ensureCursorVisible()

    def _ai_append(self, sender: str, text: str):
        # Записываем в лог ДО рендера, чтобы apply_theme() мог восстановить.
        try:
            self._chat_log.append((sender, text))
        except AttributeError:
            self._chat_log = [(sender, text)]
        kind = "user" if sender == "Вы" else (
            "sys" if sender == "Система" else "ai")
        self._append_sender(sender, kind)
        for line in text.split("\n"):
            self._render_line(line)
        cur = self.chat.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText("\n")
        self.chat.setTextCursor(cur)
        self.chat.ensureCursorVisible()

    def apply_theme(self):
        """Цвета QTextCharFormat запекаются в документ при вставке —
        чтобы они обновились после смены темы, чистим документ и
        проигрываем _chat_log заново с текущими cfg-цветами."""
        log = list(getattr(self, "_chat_log", []))
        self.chat.clear()
        self._chat_log = []
        for sender, text in log:
            self._ai_append(sender, text)

    def _ai_stream_line(self, line: str):
        self._render_line(line)
        self.chat.ensureCursorVisible()

    def _render_line(self, line: str):
        cur = self.chat.textCursor()
        cur.movePosition(QTextCursor.End)

        plain = QTextCharFormat()
        plain.setForeground(QColor(cfg.TEXT_PRIMARY))
        plain.setFontPointSize(11)
        plain.setFontWeight(QFont.Normal)

        heading = QTextCharFormat()
        heading.setFontWeight(QFont.Bold)
        heading.setForeground(QColor(cfg.ACCENT_TEXT))
        heading.setFontPointSize(15)

        def _strip_md(t: str) -> str:
            t = re.sub(r'\*\*([^*\n]+)\*\*', r'\1', t)
            t = re.sub(r'\*([^*\n]+)\*', r'\1', t)
            t = re.sub(r'`([^`\n]+)`', r'\1', t)
            # Снимаем непарные ведущие/хвостовые звёздочки (***x** / **x*** и т.п.)
            t = t.strip().strip("*").strip()
            return t

        # Пропустить пустую строку сразу после заголовка — компактнее отступ.
        if not line.strip() and self._last_was_heading:
            self._last_was_heading = False
            return

        # Заголовок (markdown # / ## / ###)
        m = re.match(r'^#{1,3}\s+(.*)', line)
        if m:
            cur.insertText(_strip_md(m.group(1)) + "\n", heading)
            self.chat.setTextCursor(cur)
            self._last_was_heading = True
            return

        # Строка целиком в **...** (или ***...**, **...***) — заголовок.
        # \*{2,} с обеих сторон — толерантно к опечаткам LLM.
        stripped = line.strip()
        m = re.match(r'^\*{2,}\s*(.+?)\s*\*{2,}$', stripped)
        if m:
            cur.insertText(_strip_md(m.group(1)) + "\n", heading)
            self.chat.setTextCursor(cur)
            self._last_was_heading = True
            return

        # Строка-подзаголовок (короткая, заканчивается ":")
        if stripped and stripped.endswith(":") and len(stripped) < 50 and " " in stripped:
            sub_heading = QTextCharFormat()
            sub_heading.setFontWeight(QFont.Bold)
            sub_heading.setForeground(QColor(cfg.TEXT_PRIMARY))
            sub_heading.setFontPointSize(13)
            cur.insertText(_strip_md(stripped) + "\n", sub_heading)
            self.chat.setTextCursor(cur)
            self._last_was_heading = True
            return

        self._last_was_heading = False

        # Нумерованный список
        m = re.match(r'^\s*(\d+\.)\s+(.*)', line)
        if m:
            bold = QTextCharFormat()
            bold.setFontWeight(QFont.Bold)
            bold.setForeground(QColor(cfg.ACCENT_TEXT))
            bold.setFontPointSize(11)
            cur.insertText(f"  {m.group(1)} ", bold)
            self._insert_inline(cur, m.group(2))
            cur.insertText("\n", plain)
            self.chat.setTextCursor(cur)
            return

        # Маркированный список
        m = re.match(r'^\s*[-•*]\s+(.*)', line)
        if m:
            bold = QTextCharFormat()
            bold.setFontWeight(QFont.Bold)
            bold.setForeground(QColor(cfg.ACCENT_TEXT))
            bold.setFontPointSize(11)
            cur.insertText("  •  ", bold)
            self._insert_inline(cur, m.group(1))
            cur.insertText("\n", plain)
            self.chat.setTextCursor(cur)
            return

        # Одинокая `*` (артефакт стрима/markdown) — выкидываем.
        if stripped == "*":
            return

        self._insert_inline(cur, line)
        cur.insertText("\n", plain)
        self.chat.setTextCursor(cur)

    def _insert_inline(self, cur: QTextCursor, text: str):
        plain = QTextCharFormat()
        plain.setForeground(QColor(cfg.TEXT_PRIMARY))
        plain.setFontPointSize(11)
        plain.setFontWeight(QFont.Normal)
        bold = QTextCharFormat()
        bold.setFontWeight(QFont.Bold)
        bold.setForeground(QColor(cfg.TEXT_PRIMARY))
        bold.setFontPointSize(11)
        code = QTextCharFormat()
        code.setFontFamily("Consolas")
        code.setForeground(QColor(cfg.SAFE_COLOR))
        code.setBackground(QColor(cfg.BG_ELEVATED))
        code.setFontPointSize(11)

        parts = re.split(r'(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)', text)
        for part in parts:
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                cur.insertText(part[2:-2], bold)
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                cur.insertText(part[1:-1], bold)
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                cur.insertText(part[1:-1], code)
            else:
                cur.insertText(part, plain)
