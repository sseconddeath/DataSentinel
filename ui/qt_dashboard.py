"""Страница «Дашборд»: статус, метрики, активность по источникам."""
from __future__ import annotations

import datetime
from typing import Callable

from PySide6.QtCore import (
    Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve, Property, QObject,
    QVariantAnimation, QAbstractAnimation,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QProgressBar, QSizePolicy, QGraphicsOpacityEffect,
)

import core.config as cfg

def _animate_int(label: QLabel, target: int, duration_ms: int = 900):
    """Count-up анимация для QLabel: текст плавно меняется от текущего числа
    к target. Если число изменилось мало (<= 1) — обновляем без анимации."""
    try:
        current = int(label.text() or "0")
    except (ValueError, TypeError):
        current = 0
    if current == target or abs(target - current) <= 1:
        label.setText(str(target))
        return
    steps = max(8, min(40, abs(target - current)))
    interval = max(20, duration_ms // steps)
    delta = (target - current) / steps
    state = {"i": 0, "val": float(current)}
    timer = QTimer(label)

    def tick():
        state["i"] += 1
        state["val"] += delta
        if state["i"] >= steps:
            label.setText(str(target))
            timer.stop()
            timer.deleteLater()
        else:
            label.setText(str(int(state["val"])))
    timer.timeout.connect(tick)
    timer.start(interval)

class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(f"""
            QFrame#card {{
                background: {cfg.BG_SURFACE};
                border: 1px solid {cfg.BORDER};
                border-radius: 12px;
            }}
        """)

def _muted_label(text: str, size: int = cfg.FONT_SIZE_XS,
                 parent: QWidget | None = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:{size}px; "
        f"background:transparent; border:none; text-transform:uppercase;"
        f"letter-spacing:1px;")
    return lbl

def _badge(text: str, color: str, bg: str, parent=None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(f"""
        QLabel {{
            font-family: 'Geist';
            color: {color};
            background: {bg};
            border-radius: 10px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
    """)
    return lbl

class DashboardPage(QWidget):
    def __init__(self, db, on_scan: Callable[[], None] | None = None,
                 on_export_pdf: Callable[[], None] | None = None,
                 on_goto_journal: Callable[[], None] | None = None,
                 parent=None):
        super().__init__(parent)
        self.db = db
        self._on_scan = on_scan
        self._on_export_pdf = on_export_pdf
        self._on_goto_journal = on_goto_journal

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)

        self._build_header(outer)

        self._build_status_card(outer)

        self._build_grid(outer)

        self.refresh_stats()
        self.refresh_status()
        self._build_source_status()

        # Каскадный fade-in карточек — теперь играет каждый раз при возврате
        # на дашборд (вызывается из MainWindow.nav_to через replay_intro).

    def _build_header(self, parent_lay: QVBoxLayout):
        header = QWidget(self)
        h = QVBoxLayout(header)
        h.setContentsMargins(0, 0, 0, 4)
        h.setSpacing(2)

        title = QLabel("Дашборд", header)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px; font-weight:700;"
            f"background:transparent;")
        h.addWidget(title)

        subtitle = QLabel("Мониторинг безопасности", header)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY}; font-size:13px; background:transparent;")
        h.addWidget(subtitle)

        parent_lay.addWidget(header)

    def _build_status_card(self, parent_lay: QVBoxLayout):
        card = Card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.pulse_dot = QLabel("●", card)
        self.pulse_dot.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.SAFE_COLOR}; font-size:18px; background:transparent;"
            f"border:none;")
        top.addWidget(self.pulse_dot)

        self.status_label = QLabel("Система готова", card)
        self.status_label.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:26px; font-weight:700;"
            f"background:transparent; border:none;")
        top.addWidget(self.status_label)

        self.status_badge = _badge("  Активна  ", cfg.SAFE_COLOR, cfg.SAFE_BG, card)
        top.addWidget(self.status_badge)

        top.addStretch(1)

        self.stats_label = QLabel("Объектов: 0  ·  Скан: никогда", card)
        self.stats_label.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:13px; background:transparent;"
            f"border:none;")
        top.addWidget(self.stats_label)

        lay.addLayout(top)

        self.progress_bar = QProgressBar(card)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {cfg.BORDER};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {cfg.ACCENT};
                border-radius: 4px;
            }}
        """)
        lay.addWidget(self.progress_bar)

        parent_lay.addWidget(card)

    def _build_grid(self, parent_lay: QVBoxLayout):
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        risk = self._build_risk_card()
        obj = self._build_metric_card("Объектов", "на мониторинге", "obj")
        self._leak_card = self._build_metric_card(
            "Утечек найдено", "всего в журнале", "leak")
        actions = self._build_actions_card()
        activity = self._build_activity_card()

        grid.addWidget(risk, 0, 0)
        grid.addWidget(obj, 0, 1)
        grid.addWidget(self._leak_card, 0, 2)
        grid.addWidget(actions, 1, 0)
        grid.addWidget(activity, 1, 1, 1, 2)

        # Запоминаем порядок для каскадного fade-in.
        self._cards_for_intro = [risk, obj, self._leak_card, actions, activity]

        parent_lay.addLayout(grid, 1)

    def _build_risk_card(self) -> Card:
        card = Card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)

        lay.addWidget(_muted_label("Уровень угрозы", parent=card))

        self.risk_label = QLabel("—", card)
        self.risk_label.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:42px; font-weight:700;"
            f"background:transparent; border:none;")
        lay.addWidget(self.risk_label)

        self.risk_score_label = QLabel("Нет данных", card)
        self.risk_score_label.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:13px; background:transparent;"
            f"border:none;")
        lay.addWidget(self.risk_score_label)

        lay.addStretch(1)
        return card

    def _build_metric_card(self, title: str, sub: str, kind: str) -> Card:
        card = Card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)

        lay.addWidget(_muted_label(title, parent=card))

        big = QLabel("0", card)
        big.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:36px; font-weight:700;"
            f"background:transparent; border:none;")
        lay.addWidget(big)

        lay.addWidget(_muted_label(sub, parent=card))
        lay.addStretch(1)

        if kind == "obj":
            self.obj_count_label = big
        else:
            self.leak_count_label = big
        return card

    def _build_actions_card(self) -> Card:
        card = Card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        lay.addWidget(_muted_label("Действия", parent=card))

        # Угол текущего кадра спиннера (0..359). На каждом тике увеличивается.
        # Рисуем дугу по окружности — визуально это вращающаяся «стрелка».
        self._spin_angle = 0
        self._spin_timer: QTimer | None = None

        self.scan_button = QPushButton("▶   Запустить мониторинг", card)
        self.scan_button.setFixedHeight(64)
        self.scan_button.setCursor(Qt.PointingHandCursor)
        self.scan_button.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Geist';
                background: {cfg.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 17px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover {{ background: {cfg.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background: {cfg.ACCENT}; }}
            QPushButton:disabled {{ background: {cfg.BG_ELEVATED}; color: {cfg.TEXT_MUTED}; }}
        """)
        if self._on_scan:
            self.scan_button.clicked.connect(self._on_scan)
        lay.addWidget(self.scan_button)

        sec_row = QHBoxLayout()
        sec_row.setSpacing(6)
        btn_pdf = self._secondary_btn("↓  PDF отчёт", card)
        if self._on_export_pdf:
            btn_pdf.clicked.connect(self._on_export_pdf)
        sec_row.addWidget(btn_pdf)
        btn_journal = self._secondary_btn("→  Журнал", card)
        if self._on_goto_journal:
            btn_journal.clicked.connect(self._on_goto_journal)
        sec_row.addWidget(btn_journal)
        lay.addLayout(sec_row)

        # Разделитель
        sep = QFrame(card)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{cfg.BORDER}; border:none;")
        lay.addWidget(sep)

        lay.addWidget(_muted_label("Источники", parent=card))
        self.src_container = QWidget(card)
        self.src_container_lay = QVBoxLayout(self.src_container)
        self.src_container_lay.setContentsMargins(0, 0, 0, 0)
        self.src_container_lay.setSpacing(2)
        lay.addWidget(self.src_container)

        lay.addStretch(1)
        return card

    def _secondary_btn(self, text: str, parent) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Geist';
                background: {cfg.BG_ELEVATED};
                color: {cfg.TEXT_PRIMARY};
                border: 1px solid {cfg.BORDER};
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {cfg.ACCENT_MUTED};
                color: {cfg.ACCENT_TEXT};
                border-color: {cfg.ACCENT};
            }}
        """)
        return btn

    # Activity card — горизонтальные бары распределения утечек по источникам.
    def _build_activity_card(self) -> Card:
        card = Card(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        lay.addWidget(_muted_label("Активность по источникам", parent=card))

        self.activity_container = QWidget(card)
        self.activity_lay = QVBoxLayout(self.activity_container)
        self.activity_lay.setContentsMargins(0, 6, 0, 0)
        self.activity_lay.setSpacing(10)
        lay.addWidget(self.activity_container)

        self.activity_empty = QLabel("Запустите сканирование...", card)
        self.activity_empty.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:13px;"
            f"background:transparent; border:none;")
        self.activity_lay.addWidget(self.activity_empty)

        lay.addStretch(1)
        return card

    def _refresh_activity(self):
        """Перерисовка горизонтальных баров: для каждого источника — линия,
        длина пропорциональна доле утечек этого источника от максимума."""

        while self.activity_lay.count():
            it = self.activity_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        try:
            summary = self.db.get_sources_summary()  # [(source, count), ...]
        except Exception:
            summary = []
        if not summary:
            self.activity_empty = QLabel("Запустите сканирование...", self.activity_container)
            self.activity_empty.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:13px;"
                f"background:transparent; border:none;")
            self.activity_lay.addWidget(self.activity_empty)
            return
        max_count = max(c for _, c in summary)
        # Цвет по «весу» источника (Hudson/IntelX опаснее, HIBP/EmailRep слабее).
        weights = {"Hudson Rock": 35, "IntelX": 30, "BreachDirectory": 20,
                   "XposedOrNot": 20, "LeakCheck": 15, "ProxyNova": 15,
                   "Pastebin": 12, "EmailRep": 10, "HIBP": 10}
        for i, (src, cnt) in enumerate(summary):
            row = self._build_activity_row(src, cnt, max_count, weights,
                                           index=i)
            self.activity_lay.addWidget(row)

    def _build_activity_row(self, src: str, cnt: int, max_count: int,
                             weights: dict, index: int = 0) -> QWidget:
        # Цвет линии = опасность источника
        w = next((v for k, v in weights.items() if k in src), 10)
        if w >= 30:
            color = cfg.DANGER_COLOR
        elif w >= 15:
            color = cfg.WARNING_COLOR
        else:
            color = cfg.ACCENT
        row = QWidget(self.activity_container)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        # Верхняя строка: имя источника слева + число справа.
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        name = QLabel(src, row)
        name.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:13px;"
            f"font-weight:600; background:transparent; border:none;")
        head.addWidget(name)
        head.addStretch(1)
        num = QLabel(str(cnt), row)
        num.setStyleSheet(
            f"font-family:'Geist'; color:{color}; font-size:13px; font-weight:700;"
            f"background:transparent; border:none;")
        head.addWidget(num)
        rl.addLayout(head)

        # Бар. Масштабируем range ×100, чтобы анимация для маленьких
        # значений (LeakCheck=2, XposedOrNot=3) была плавной — иначе у
        # int-property всего 2-3 видимых шага и выглядит как «прыжок».
        SCALE = 100
        bar = QProgressBar(row)
        bar.setFixedHeight(8)
        bar.setRange(0, (max_count if max_count > 0 else 1) * SCALE)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background: {cfg.BG_ELEVATED};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 4px;
            }}
        """)
        rl.addWidget(bar)

        # Каскадное заполнение: первый бар через 350мс, каждый следующий
        # на 160мс позже. OutCubic мягче OutQuart — нет жёсткой остановки
        # к концу. Длительность 1500мс — спокойнее воспринимается глазом.
        anim = QPropertyAnimation(bar, b"value", row)
        anim.setStartValue(0)
        anim.setEndValue(cnt * SCALE)
        anim.setDuration(1500)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        delay = 350 + index * 160
        QTimer.singleShot(delay, anim.start)
        return row

    def refresh_stats(self):
        try:
            last = self.db.get_last_scan()
            t_str = (datetime.datetime.fromtimestamp(last).strftime("%d.%m.%Y %H:%M")
                     if last > 0 else "никогда")
            n_obj = len(self.db.get_all_targets())
            n_leak = self.db._conn.execute(
                "SELECT COUNT(*) FROM scan_results").fetchone()[0]
            self.stats_label.setText(f"Объектов: {n_obj}  ·  Скан: {t_str}")
            _animate_int(self.obj_count_label, n_obj)
            color = cfg.DANGER_COLOR if n_leak > 0 else cfg.TEXT_PRIMARY
            _animate_int(self.leak_count_label, n_leak)
            self.leak_count_label.setStyleSheet(
                f"font-family:'Geist'; color:{color}; font-size:36px; font-weight:700;"
                f"background:transparent; border:none;")
            self._refresh_activity()
        except Exception as e:
            print(f"[dashboard] refresh_stats failed: {e}", flush=True)

    def set_risk(self, level: str, score: int, color: str):
        self.risk_label.setText(level)
        self.risk_label.setStyleSheet(
            f"font-family:'Geist'; color:{color}; font-size:42px; font-weight:700;"
            f"background:transparent; border:none;")
        self.risk_score_label.setText(f"Score: {score}/100")
        self.risk_score_label.setStyleSheet(
            f"font-family:'Geist'; color:{color}; font-size:13px; background:transparent; border:none;")

    def refresh_status(self):
        """Перечитывает только свежие (is_new=1) утечки и пересчитывает
        статус-индикатор + уровень угрозы. Старые утечки уже не «активная»
        угроза — индикатор должен затихать вместе с aging."""
        try:
            from core.engine import LeakEngine
            fresh = self.db.get_fresh_sources()
            score, level, color = LeakEngine.calculate_risk_score(fresh)
            self.set_risk(level, score, color)
            if fresh:
                self.status_label.setText("Обнаружена угроза!")
                self._animate_status_color(cfg.DANGER_COLOR)
                self.status_badge.setText("  Угроза!  ")
                self.status_badge.setStyleSheet(
                    f"QLabel {{ font-family:'Geist'; background:{cfg.DANGER_BG};"
                    f"color:{cfg.DANGER_COLOR}; border-radius:10px; padding:3px 10px;"
                    f"font-size:11px; font-weight:700; }}")
                self.pulse_dot.setStyleSheet(
                    f"font-family:'Geist'; color:{cfg.DANGER_COLOR}; font-size:18px;"
                    f"background:transparent; border:none;")
                self._start_pulse()
            else:
                self.status_label.setText("Нет активных угроз")
                self._animate_status_color(cfg.SAFE_COLOR)
                self.status_badge.setText("  ОК  ")
                self.status_badge.setStyleSheet(
                    f"QLabel {{ font-family:'Geist'; background:{cfg.SAFE_BG};"
                    f"color:{cfg.SAFE_COLOR}; border-radius:10px; padding:3px 10px;"
                    f"font-size:11px; font-weight:700; }}")
                self.pulse_dot.setStyleSheet(
                    f"font-family:'Geist'; color:{cfg.SAFE_COLOR}; font-size:18px;"
                    f"background:transparent; border:none;")
                self._stop_pulse()
        except Exception as e:
            print(f"[dashboard] refresh_status failed: {e}", flush=True)

    def _animate_status_color(self, target_hex: str):
        """Плавный переход цвета status_label из текущего в target_hex
        через QVariantAnimation<QColor>. Если текущий совпадает — мгновенно."""
        target = QColor(target_hex)
        # Извлекаем текущий цвет из stylesheet (грубо).
        cur = getattr(self, "_status_color", None) or QColor(cfg.TEXT_PRIMARY)
        if cur.name().lower() == target.name().lower():
            return
        anim = QVariantAnimation(self.status_label)
        anim.setDuration(450)
        anim.setStartValue(cur)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def apply(c: QColor):
            self.status_label.setStyleSheet(
                f"font-family:'Geist'; color:{c.name()};"
                f"font-size:20px; font-weight:700; background:transparent; border:none;")
            self._status_color = c
        anim.valueChanged.connect(apply)
        anim.start(QAbstractAnimation.DeleteWhenStopped)
        self._status_color = target

    def start_scan_animation(self):
        """Круглый QPainter-спиннер на кнопке + блокировка во время скана.
        Угол дуги вращается по часовой каждые 40мс — выглядит как обычная
        иконка загрузки в браузере/системе."""
        self.scan_button.setEnabled(False)
        self.scan_button.setText("   Сканирование...")
        self.scan_button.setIconSize(QSize(22, 22))
        self._spin_angle = 0
        self._render_spinner_icon()
        if self._spin_timer is None:
            self._spin_timer = QTimer(self)
            self._spin_timer.timeout.connect(self._tick_spinner)
        self._spin_timer.start(40)

    def _tick_spinner(self):
        self._spin_angle = (self._spin_angle + 18) % 360
        self._render_spinner_icon()

    def _render_spinner_icon(self):
        """Рисует pixmap-кадр: тонкое кольцо-фон + яркая дуга 110° на текущем
        угле. Передаём как icon кнопке — никаких глифов из шрифта."""
        size = 22
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        rect = pm.rect().adjusted(2, 2, -2, -2)
        # Фон кольца — полупрозрачный белый.
        bg_pen = QPen(QColor(255, 255, 255, 60))
        bg_pen.setWidth(2)
        p.setPen(bg_pen)
        p.drawArc(rect, 0, 360 * 16)
        # Активная дуга — яркая, с round-cap (выглядит как «стрелка»).
        fg_pen = QPen(QColor("#ffffff"))
        fg_pen.setWidth(3)
        fg_pen.setCapStyle(Qt.RoundCap)
        p.setPen(fg_pen)
        # Qt отсчитывает углы против часовой; делаем -angle чтобы крутилось
        # по часовой стрелке. 110° длина дуги.
        p.drawArc(rect, -self._spin_angle * 16, 110 * 16)
        p.end()
        self.scan_button.setIcon(QIcon(pm))

    def stop_scan_animation(self):
        if self._spin_timer is not None:
            self._spin_timer.stop()
        self.scan_button.setEnabled(True)
        self.scan_button.setIcon(QIcon())  # убираем icon, возвращаем ▶ в тексте
        self.scan_button.setText("▶   Запустить мониторинг")

    def replay_intro(self):
        """Сбрасывает числа в 0 и вызывает refresh_stats() — count-up
        анимация и заполнение баров проигрываются заново. Дёргается из
        MainWindow.nav_to при возврате на дашборд."""
        try:
            self.obj_count_label.setText("0")
            self.leak_count_label.setText("0")
            # risk_score_label тоже count-up'нется через replay set_risk
            self.risk_score_label.setText("Score: 0/100")
            self.refresh_stats()
            self.refresh_status()
        except Exception as e:
            print(f"[dashboard] replay_intro failed: {e}", flush=True)

    def _start_pulse(self):
        """Зацикленная анимация opacity 1.0 → 0.35 → 1.0 на dot-индикаторе.
        Привлекает внимание когда есть активная угроза."""
        if getattr(self, "_pulse_anim", None) is not None:
            return  # уже работает
        eff = QGraphicsOpacityEffect(self.pulse_dot)
        eff.setOpacity(1.0)
        self.pulse_dot.setGraphicsEffect(eff)
        self._pulse_effect = eff
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(900)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.35)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._pulse_anim = anim

    def _stop_pulse(self):
        anim = getattr(self, "_pulse_anim", None)
        if anim is not None:
            anim.stop()
            self._pulse_anim = None
        self.pulse_dot.setGraphicsEffect(None)

    def update_events(self, new_breaches: list):
        """Карточка «Последние события» убрана; данные о свежих утечках видны
        в журнале и в активности по источникам. На каждый раз когда найдены
        новые утечки — короткая красная вспышка карточки «Утечек найдено»."""
        if new_breaches:
            self.flash_leak_card()

    def flash_leak_card(self):
        """Короткая вспышка фона карточки «Утечек найдено»: BG_SURFACE → DANGER_BG
        и обратно за 800мс. Привлекает внимание когда нашлись новые утечки."""
        card = getattr(self, "_leak_card", None)
        if card is None:
            return
        anim = QVariantAnimation(card)
        anim.setDuration(900)
        bg_normal = QColor(cfg.BG_SURFACE)
        bg_flash = QColor(cfg.DANGER_BG)
        anim.setStartValue(bg_normal)
        anim.setKeyValueAt(0.25, bg_flash)
        anim.setKeyValueAt(0.55, bg_flash)
        anim.setEndValue(bg_normal)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def apply(c: QColor):
            card.setStyleSheet(
                f"QFrame#card {{ background:{c.name()}; "
                f"border:1px solid {cfg.BORDER}; border-radius:12px; }}")
        anim.valueChanged.connect(apply)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def _build_source_status(self):
        """Мини-список активных источников в карточке Действия — 2 колонки."""
        # Очистить
        while self.src_container_lay.count():
            item = self.src_container_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        sources = [
            ("HIBP", "hibp"),
            ("LeakCheck", "leakcheck"),
            ("XposedOrNot", "xposedornot"),
            ("ProxyNova", "proxynova"),
            ("Pastebin", "psbdmp"),
            ("Hudson Rock", "hudson_rock"),
            ("Hudson · username", "hudson_user"),
            ("EmailRep", "emailrep"),
            ("BreachDirectory", "breachdirectory"),
            ("IntelX", "intelx"),
        ]

        # Раскладываем по строкам: 5 левых, 5 правых.
        half = (len(sources) + 1) // 2
        left, right = sources[:half], sources[half:]

        for i in range(max(len(left), len(right))):
            row = QWidget(self)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(12)

            for col_sources in (left, right):
                if i < len(col_sources):
                    name, key = col_sources[i]
                    rl.addWidget(self._make_source_item(name, key, row), 1)
                else:
                    rl.addStretch(1)

            self.src_container_lay.addWidget(row)

    def _make_source_item(self, name: str, key: str, parent: QWidget) -> QWidget:
        enabled = self.db.get_setting(f"src_{key}", "1") == "1"
        # Эффективный ключ = пользовательский (если есть) ИЛИ встроенный в сборку.
        # Проверяем LeakEngine.*_API_KEY (там уже учтён builtin), а не только БД.
        from core.engine import LeakEngine
        has_key = True
        if key == "breachdirectory":
            has_key = bool(self.db.get_api_key("rapidapi")) or bool(LeakEngine.RAPID_API_KEY)
        elif key == "intelx":
            has_key = bool(self.db.get_api_key("intelx")) or bool(LeakEngine.INTELX_API_KEY)

        item = QWidget(parent)
        il = QHBoxLayout(item)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(6)

        dot_color = cfg.SAFE_COLOR if (enabled and has_key) else (
            cfg.WARNING_COLOR if (enabled and not has_key) else cfg.TEXT_MUTED)
        dot = QLabel("●", item)
        dot.setStyleSheet(
            f"font-family:'Geist'; color:{dot_color}; font-size:10px;"
            f"background:transparent; border:none;")
        il.addWidget(dot)

        name_lbl = QLabel(name, item)
        name_lbl.setStyleSheet(
            f"font-family:'Geist';"
            f"color:{cfg.TEXT_SECONDARY if enabled else cfg.TEXT_MUTED};"
            f"font-size:12px; background:transparent; border:none;")
        il.addWidget(name_lbl)
        il.addStretch(1)

        if not has_key and enabled:
            warn = QLabel("нет ключа", item)
            warn.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.WARNING_COLOR}; font-size:10px;"
                f"background:transparent; border:none;")
            il.addWidget(warn)

        return item
