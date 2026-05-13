"""Knox — Qt-версия (PySide6). Точка входа приложения."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import (
    Qt, QPoint, QRect, QSize, QPropertyAnimation, QEasingCurve, Property, QEvent, QTimer, Signal, QObject,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QFontDatabase, QMouseEvent,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QStackedWidget, QSizePolicy, QSpacerItem,
    QGraphicsDropShadowEffect, QMessageBox, QDialog, QProgressBar,
)

import ctypes
import ctypes.wintypes

import core.config as cfg
from core.database import DBManager
from core.version import VERSION as APP_VERSION
try:
    from services import updater
    UPDATER_OK = True
except Exception:
    UPDATER_OK = False
from ui.qt_dashboard import DashboardPage
from ui.qt_manager import ManagerPage
from ui.qt_journal import JournalPage
from ui.qt_tools import ToolsPage
from ui.qt_settings import SettingsPage
from ui.qt_ai import AIPage
from ui.qt_scan import ScanWorker
from core.engine import LeakEngine
try:
    from services.pdf_export import export_pdf_report, export_pdf_for_target
    PDF_OK = True
except Exception:
    PDF_OK = False

try:
    import pystray
    from pystray import MenuItem as TrayItem
    from PIL import Image as PILImage
    TRAY_OK = True
except ImportError:
    TRAY_OK = False

try:
    from winotify import Notification
    TOAST_OK = True
except ImportError:
    TOAST_OK = False
from PySide6.QtCore import QThread
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray
from PySide6.QtNetwork import QLocalServer, QLocalSocket

TITLEBAR_H = 52
SIDEBAR_W_OPEN = 220
SIDEBAR_W_COLLAPSED = 64
WINDOW_BTN_W = 50
BURGER_SIZE = 26
RESIZE_BORDER = 4

# Имя именованного канала (Win32 named pipe) для single-instance IPC.
SINGLE_INSTANCE_KEY = "Knox.SingleInstance.LocalServer"
# Файл с одноразовым токеном — отбивает случайные процессы, которые могли бы
# слать "show" на канал. Файл лежит в user-only data/, перегенерируется на старте.
IPC_TOKEN_FILE = "data/.ipc_token"
# Лимит входящего сообщения, чтобы локальный процесс не съел память бесконечным потоком.
IPC_MAX_MSG = 256
# AppUserModelID — должен совпадать в SetCurrentProcessExplicitAppUserModelID
# и в winotify.Notification(app_id=...), иначе Windows не показывает toasts.
APP_AUMID = "Knox.App"

_NAV_SVG: dict[str, str] = {
    "дашборд": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>',
    "менеджер": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    "журнал": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>',
    "инструменты": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
    "ai": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M12 7V3"/><circle cx="12" cy="3" r="1"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/><path d="M9 17h6"/></svg>',
    "новости": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8z"/></svg>',
    "настройки": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    "github": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>',
}

NAV_ITEMS = [
    ("дашборд",     "Дашборд"),
    ("менеджер",    "Менеджер данных"),
    ("журнал",      "Журнал"),
    ("новости",     "Новости"),
    ("инструменты", "Инструменты"),
    ("ai",          "AI Помощник"),
    ("настройки",   "Настройки"),
]

_nav_icon_cache: dict = {}

def make_nav_icon(page_id: str, color: str, size: int = 20) -> QIcon:
    key = (page_id, color, size)
    cached = _nav_icon_cache.get(key)
    if cached is not None:
        return cached
    svg = _NAV_SVG.get(page_id, "").format(c=color)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    if svg:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(p)
        p.end()
    ico = QIcon(pm)
    _nav_icon_cache[key] = ico
    return ico

def _resource_path(name: str) -> str:
    """Путь к bundled-ресурсу. В исходниках — рядом с main_qt.py;
    после PyInstaller-сборки — внутри _internal/ через sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)

def _load_geist_qt() -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(base, "fonts")
    files = ["Geist-Regular.ttf", "Geist-SemiBold.ttf", "Geist-Bold.ttf"]
    loaded_family = None
    for f in files:
        path = os.path.join(fonts_dir, f)
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid != -1 and loaded_family is None:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    loaded_family = fams[0]
    return loaded_family or "Segoe UI"

class BurgerButton(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 36)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self._on_click = None

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.LeftButton and self._on_click:
            self._on_click()

    def paintEvent(self, _e):
        from PySide6.QtGui import QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        side = 30
        cx_w = self.width() // 2
        cy_w = self.height() // 2
        r = QRect(cx_w - side // 2, cy_w - side // 2, side, side)
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(cfg.BG_ELEVATED))
            p.drawRoundedRect(r, 8, 8)
            pen = QPen(QColor(cfg.BORDER_HOVER))
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 8, 8)
        # Три полоски
        pen = QPen(QColor(cfg.TEXT_PRIMARY))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx = self.width() // 2
        x1, x2 = cx - 7, cx + 7
        cy = self.height() // 2
        for dy in (-5, 0, 5):
            p.drawLine(x1, cy + dy, x2, cy + dy)
        p.end()

class TitleBar(QFrame):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self._win = window
        self.setFixedHeight(TITLEBAR_H)
        self.setStyleSheet(f"background:{cfg.BG_SURFACE};")
        self._is_max = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        burger_wrap = QWidget(self)
        burger_wrap.setFixedWidth(SIDEBAR_W_COLLAPSED)
        bw_lay = QHBoxLayout(burger_wrap)
        bw_lay.setContentsMargins(0, 0, 0, 0)
        bw_lay.setSpacing(0)
        bw_lay.setAlignment(Qt.AlignCenter)
        self.burger = BurgerButton(burger_wrap)
        self.burger._on_click = window.toggle_sidebar
        bw_lay.addWidget(self.burger, 0, Qt.AlignCenter)
        lay.addWidget(burger_wrap)

        lay.addSpacing(6)

        # Логотип (icon.ico) — если нет, пропускаем.
        ico_path = _resource_path("icon.ico")
        if os.path.exists(ico_path):
            logo = QLabel(self)
            # Берём наибольшее доступное разрешение из multi-ICO (256×256)
            # и smooth-скейлим один раз вниз — даёт чёткий рендер при любом
            # DPI без блюра от двойного скейла. Раньше Qt брал ближайший
            # 24/32 и тянул вверх до 28 → выглядело размыто на VM/ноутбуках.
            dpr = self.devicePixelRatioF() or 1.0
            target_px = int(round(28 * dpr))
            pm = QIcon(ico_path).pixmap(QSize(256, 256))
            if pm.width() != target_px or pm.height() != target_px:
                pm = pm.scaled(target_px, target_px,
                                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            logo.setPixmap(pm)
            logo.setFixedSize(28, 28)
            lay.addWidget(logo)
            lay.addSpacing(10)

        self._title_lbl = QLabel(cfg.APP_TITLE, self)
        self._title_lbl.setStyleSheet(self._title_qss())
        lay.addWidget(self._title_lbl)

        lay.addStretch(1)

        # Кнопки окна: Segoe MDL2 Assets (ровные глифы min/max/close на Windows)
        self.btn_min = self._make_win_btn("\uE921", self._minimize)
        self.btn_max = self._make_win_btn("\uE922", self._toggle_max)
        self.btn_close = self._make_win_btn("\uE8BB", window.close,
                                            hover="#e81123")
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    def _title_qss(self) -> str:
        return (f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY};"
                f" font-size:16px; font-weight:700; background:transparent;")

    def _btn_qss(self, hover: str | None) -> str:
        hover_bg = hover or cfg.BG_ELEVATED
        text_color = "#ffffff" if hover else cfg.TEXT_PRIMARY
        return f"""
            QPushButton {{
                background: transparent;
                color: {cfg.TEXT_PRIMARY};
                border: none;
                font-size: 11px;
                font-family: "Segoe MDL2 Assets";
            }}
            QPushButton:hover {{
                background: {hover_bg};
                color: {text_color};
            }}
        """

    def _make_win_btn(self, text: str, slot, hover: str | None = None) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setFixedSize(WINDOW_BTN_W, TITLEBAR_H)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(self._btn_qss(hover))
        btn.clicked.connect(slot)
        return btn

    def _minimize(self):
        self._win.showMinimized()

    def _toggle_max(self):
        if self._is_max:
            self._win.showNormal()
            self._is_max = False
        else:
            self._win.showMaximized()
            self._is_max = True
        self.btn_max.setText("\uE923" if self._is_max else "\uE922")

    # Drag и double-click обрабатываются нативно через WM_NCHITTEST → HTCAPTION.
    # Ручной drag не нужен — Windows сама управляет перетаскиванием и snap.

class NavButton(QPushButton):
    def __init__(self, page_id: str, label: str, parent=None):
        super().__init__(parent)
        self.page_id = page_id
        self._label = label
        self._active = False
        self._is_collapsed = False
        self._sunk = False
        self._sunk_pm: QPixmap | None = None
        self._grabbing = False
        self._scale = 1.0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setText("  " + label)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setMinimumHeight(46)
        self.setIconSize(QSize(20, 20))
        self._refresh_icon()
        self.setStyleSheet(self._qss(active=False))

        self._press_anim = QPropertyAnimation(self, b"scaleProp", self)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._press_anim.setDuration(180)

    def _get_scale(self) -> float:
        return self._scale

    def _set_scale(self, v: float):
        self._scale = v
        self.update()

    scaleProp = Property(float, _get_scale, _set_scale)

    def _paint_bg(self, color: str):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        inset_v = 6
        r = self.rect().adjusted(0, inset_v, 0, -inset_v)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(r, 9, 9)
        p.end()

    def paintEvent(self, ev):
        if self._sunk and not self._grabbing and self._sunk_pm is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            sw = int(self.width() * self._scale)
            sh = int(self.height() * self._scale)
            x = (self.width() - sw) // 2
            y = (self.height() - sh) // 2
            p.drawPixmap(x, y, sw, sh, self._sunk_pm)
            p.end()
            return
        if self._active:
            self._paint_bg(cfg.ACCENT_MUTED)
        elif self.underMouse():
            self._paint_bg(cfg.BG_ELEVATED)
        super().paintEvent(ev)

    def _start_press_anim(self, target: float, on_finish=None):
        try:
            self._press_anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._press_anim.stop()
        self._press_anim.setStartValue(self._scale)
        self._press_anim.setEndValue(target)
        if on_finish is not None:
            self._press_anim.finished.connect(on_finish)
        self._press_anim.start()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._grabbing = True
            self._sunk_pm = self.grab()
            self._grabbing = False
            self._sunk = True
            self._scale = 1.0
            self._start_press_anim(0.92)
        super().mousePressEvent(e)

    def _end_sunk(self):
        self._sunk = False
        self._sunk_pm = None
        self._scale = 1.0
        self.update()

    def mouseReleaseEvent(self, e):
        if self._sunk:
            self._start_press_anim(1.0, on_finish=self._end_sunk)
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._sunk:
            self._start_press_anim(1.0, on_finish=self._end_sunk)
        self.update()
        super().leaveEvent(e)

    def _refresh_icon(self):
        color = cfg.ACCENT_TEXT if self._active else cfg.TEXT_SECONDARY
        self.setIcon(make_nav_icon(self.page_id, color, 20))

    def _qss(self, active: bool) -> str:
        bg = "transparent"
        fg = cfg.ACCENT_TEXT if active else cfg.TEXT_SECONDARY
        if self._is_collapsed:
            padding = "0"
            align = "center"
        else:
            padding = "0 12px"
            align = "left"
        return f"""
            QPushButton {{
                font-family: 'Geist';
                background: {bg};
                color: {fg};
                border: none;
                border-radius: 10px;
                padding: {padding};
                text-align: {align};
                font-size: 13px;
                font-weight: {700 if active else 600};
            }}
            QPushButton:hover {{
                background: transparent;
            }}
        """

    def set_active(self, active: bool):
        self._active = active
        self.setChecked(active)
        self._refresh_icon()
        self.setStyleSheet(self._qss(active))
        if self._sunk:
            self._grabbing = True
            self.ensurePolished()
            self._sunk_pm = self.grab()
            self._grabbing = False
            self.update()

    def set_collapsed(self, collapsed: bool):
        self._is_collapsed = collapsed
        if collapsed:
            self.setText("")
        else:
            self.setText("  " + self._label)
        self.setMinimumHeight(46)
        self.setMaximumHeight(46)
        self.setStyleSheet(self._qss(self._active))

class Sidebar(QFrame):
    def __init__(self, parent, on_nav):
        super().__init__(parent)
        self.setStyleSheet(f"background:{cfg.BG_SURFACE};")
        self.setFixedWidth(SIDEBAR_W_OPEN)
        self._on_nav = on_nav
        self._collapsed = False
        self._active_btn: NavButton | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(4)

        self.section_lbl = QLabel("НАВИГАЦИЯ", self)
        self.section_lbl.setFixedHeight(24)
        self.section_lbl.setStyleSheet(self._section_qss())
        lay.addWidget(self.section_lbl)

        self.buttons: dict[str, NavButton] = {}
        for pid, label in NAV_ITEMS:
            btn = NavButton(pid, label, self)
            btn.clicked.connect(lambda _=False, p=pid: self._on_nav(p))
            lay.addWidget(btn)
            self.buttons[pid] = btn

        lay.addStretch(1)

        # Футер: иконка GitHub + текст версии под ней. Клик на иконке
        # открывает страницу релизов — оттуда видно changelog. Влезает
        # и в свёрнутый сайдбар (64px), потому что обе части центрируются.
        self.footer = QWidget(self)
        self.footer.setStyleSheet("background:transparent;")
        footer_lay = QVBoxLayout(self.footer)
        footer_lay.setContentsMargins(0, 6, 0, 2)
        footer_lay.setSpacing(2)
        footer_lay.setAlignment(Qt.AlignHCenter)

        self.github_btn = QPushButton(self.footer)
        self.github_btn.setCursor(Qt.PointingHandCursor)
        self.github_btn.setFixedSize(32, 32)
        self.github_btn.setIconSize(QSize(20, 20))
        self.github_btn.setToolTip("Открыть Knox на GitHub")
        self.github_btn.setStyleSheet(
            "QPushButton { background:transparent; border:none; }"
            f"QPushButton:hover {{ background:{cfg.BG_ELEVATED}; "
            "border-radius:6px; }"
        )
        self.github_btn.setIcon(make_nav_icon("github", cfg.TEXT_MUTED, 20))
        self.github_btn.clicked.connect(self._on_github_click)
        footer_lay.addWidget(self.github_btn, 0, Qt.AlignHCenter)

        self.version_lbl = QLabel(f"v{APP_VERSION}", self.footer)
        self.version_lbl.setAlignment(Qt.AlignCenter)
        self.version_lbl.setCursor(Qt.PointingHandCursor)
        self.version_lbl.setToolTip(
            "Нажми чтобы проверить обновления сейчас")
        self.version_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            " font-size:10px; background:transparent;"
        )
        self.version_lbl.mousePressEvent = self._on_version_click
        footer_lay.addWidget(self.version_lbl)

        lay.addWidget(self.footer)

        # Анимация ширины
        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(480)
        self._anim.setEasingCurve(QEasingCurve.OutQuint)
        self._anim2 = QPropertyAnimation(self, b"minimumWidth")
        self._anim2.setDuration(480)
        self._anim2.setEasingCurve(QEasingCurve.OutQuint)

    def toggle(self):
        self._collapsed = not self._collapsed
        target = SIDEBAR_W_COLLAPSED if self._collapsed else SIDEBAR_W_OPEN
        self._anim.stop(); self._anim2.stop()
        self._anim.setStartValue(self.width())
        self._anim.setEndValue(target)
        self._anim2.setStartValue(self.width())
        self._anim2.setEndValue(target)
        self._anim.start()
        self._anim2.start()
        self.section_lbl.setText("" if self._collapsed else "НАВИГАЦИЯ")
        for btn in self.buttons.values():
            btn.set_collapsed(self._collapsed)

    def set_active(self, page_id: str):
        for pid, btn in self.buttons.items():
            is_active = pid == page_id
            btn.set_active(is_active)
            if is_active:
                self._active_btn = btn
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        btn = self._active_btn
        if btn is None or not btn.isVisible():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(cfg.ACCENT))
        top_left = btn.mapTo(self, QPoint(0, 0))
        h = btn.height()
        bar_h = int(h * 0.55)
        y = top_left.y() + (h - bar_h) // 2
        p.drawRoundedRect(2, y, 3, bar_h, 1.5, 1.5)
        p.end()

    def _section_qss(self) -> str:
        return (f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
                f" font-size:10px; font-weight:700; letter-spacing:1px;"
                f" background:transparent; padding:6px;")

    def _on_github_click(self):
        import webbrowser
        try:
            webbrowser.open_new_tab(
                "https://github.com/sseconddeath/Knox/releases")
        except Exception:
            pass

    def _on_version_click(self, ev):
        # Клик по лейблу версии → ручная проверка обновлений с UI-фидбеком.
        # self.window() возвращает MainWindow (QMainWindow-родитель в
        # дереве виджетов).
        win = self.window()
        if hasattr(win, "_check_for_update_async"):
            try:
                win._check_for_update_async(manual=True)
            except Exception:
                pass

class PagePlaceholder(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 32, 32, 32)
        lbl = QLabel(title, self)
        lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;")
        lay.addWidget(lbl)
        hint = QLabel("Страница будет перенесена из Tk-версии.", self)
        hint.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY}; font-size:14px;"
            f"background:transparent;")
        lay.addWidget(hint)
        lay.addStretch(1)

class UpdateCheckWorker(QObject):
    """Фоновая проверка обновлений на GitHub Releases. Эмитит found(info)
    если найдена более новая версия (см. services.updater.check_for_update),
    иначе done() без аргументов."""
    found = Signal(dict)
    done = Signal()

    def run(self):
        if not UPDATER_OK:
            self.done.emit()
            return
        try:
            info = updater.check_for_update()
        except Exception:
            info = None
        if info:
            self.found.emit(info)
        else:
            self.done.emit()


class UpdateBanner(QFrame):
    """Узкая плашка-уведомление между titlebar и body. По клику на
    «Обновить» открывает UpdateProgressDialog. «Позже» прячет до
    следующего запуска."""
    updateClicked = Signal()
    laterClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setFixedHeight(40)
        self.setStyleSheet(
            f"QFrame#updateBanner {{ background:{cfg.ACCENT};"
            f" border:none; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(10)

        self._msg = QLabel("Доступно обновление", self)
        self._msg.setStyleSheet(
            "font-family:'Geist'; color:white; font-size:13px;"
            " font-weight:600; background:transparent;"
        )
        lay.addWidget(self._msg)
        lay.addStretch(1)

        upd = QPushButton("Обновить", self)
        upd.setCursor(Qt.PointingHandCursor)
        upd.setFixedHeight(26)
        upd.setStyleSheet(
            "QPushButton { font-family:'Geist'; background:white;"
            f" color:{cfg.ACCENT}; border:none; border-radius:4px;"
            " padding:0 14px; font-size:12px; font-weight:700; }"
            " QPushButton:hover { background:#f0f0f0; }"
        )
        upd.clicked.connect(self.updateClicked.emit)
        lay.addWidget(upd)

        later = QPushButton("Позже", self)
        later.setCursor(Qt.PointingHandCursor)
        later.setFixedHeight(26)
        later.setStyleSheet(
            "QPushButton { font-family:'Geist'; background:transparent;"
            " color:white; border:1px solid rgba(255,255,255,0.5);"
            " border-radius:4px; padding:0 12px; font-size:12px;"
            " font-weight:600; }"
            " QPushButton:hover { background:rgba(255,255,255,0.15); }"
        )
        later.clicked.connect(self.laterClicked.emit)
        lay.addWidget(later)

        self.hide()

    def show_for(self, version: str):
        self._msg.setText(f"Доступна новая версия Knox {version}")
        self.show()


class UpdateProgressDialog(QDialog):
    """Модальное окно: качает инсталлятор с прогресс-баром,
    при успехе запускает его и закрывает приложение."""
    progressUpdate = Signal(int, int)
    downloadDone = Signal(str)  # path, "" при ошибке
    downloadFailed = Signal()

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info = info
        self.setWindowTitle(f"Обновление Knox {info.get('version', '')}")
        self.setFixedSize(420, 180)
        self.setStyleSheet(f"background:{cfg.BG_SURFACE};")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)

        title = QLabel(f"Скачиваю Knox {info.get('version', '')}", self)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY};"
            " font-size:16px; font-weight:700; background:transparent;"
        )
        lay.addWidget(title)

        self._status = QLabel("Подключение к GitHub...", self)
        self._status.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            " font-size:12px; background:transparent;"
        )
        lay.addWidget(self._status)

        self._bar = QProgressBar(self)
        self._bar.setFixedHeight(8)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            "QProgressBar {"
            f" background:{cfg.BORDER}; border:none; border-radius:4px; }}"
            "QProgressBar::chunk {"
            f" background:{cfg.ACCENT}; border-radius:4px; }}"
        )
        lay.addWidget(self._bar)
        lay.addStretch(1)

        self._cancel_btn = QPushButton("Отмена", self)
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setFixedHeight(32)
        self._cancel_btn.setStyleSheet(
            "QPushButton { font-family:'Geist';"
            f" background:{cfg.BG_ELEVATED}; color:{cfg.TEXT_PRIMARY};"
            f" border:1px solid {cfg.BORDER}; border-radius:6px;"
            " padding:0 16px; font-size:12px; }"
            f" QPushButton:hover {{ border:1px solid {cfg.BORDER_HOVER}; }}"
        )
        self._cancel_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self._cancel_btn)
        lay.addLayout(btn_row)

        self.progressUpdate.connect(self._on_progress)
        self.downloadDone.connect(self._on_done)
        self.downloadFailed.connect(self._on_failed)

        # Запускаем скачивание в фоне сразу при открытии.
        self._thread = QThread(self)
        self._worker = _DownloadWorker(info["url"], self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_progress(self, received: int, total: int):
        if total > 0:
            pct = int(received / total * 100)
            self._bar.setValue(pct)
            mb_r = received / (1024 * 1024)
            mb_t = total / (1024 * 1024)
            self._status.setText(f"{mb_r:.1f} / {mb_t:.1f} МБ ({pct}%)")
        else:
            self._status.setText(f"{received / (1024 * 1024):.1f} МБ")

    def _on_done(self, path: str):
        self._status.setText("Запускаю установку...")
        self._bar.setValue(100)
        self._cancel_btn.setEnabled(False)
        # Через секунду стартуем инсталлятор и выходим. Inno Setup
        # сам закроет наш процесс через CloseApplications=force.
        QTimer.singleShot(800, lambda: updater.launch_installer_and_quit(path))

    def _on_failed(self):
        self._status.setText("Не удалось скачать обновление. "
                             "Проверьте интернет и попробуйте позже.")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._cancel_btn.setText("Закрыть")


class _DownloadWorker(QObject):
    """Качает инсталлятор и эмитит сигналы в UpdateProgressDialog
    (через self._dlg, который живёт в main thread)."""
    def __init__(self, url: str, dlg: "UpdateProgressDialog"):
        super().__init__()
        self._url = url
        self._dlg = dlg

    def run(self):
        def _on_prog(received, total):
            self._dlg.progressUpdate.emit(received, total)
        path = updater.download_installer(self._url, on_progress=_on_prog) \
            if UPDATER_OK else None
        if path:
            self._dlg.downloadDone.emit(path)
        else:
            self._dlg.downloadFailed.emit()


class MainWindow(QMainWindow):
    _tray_show = Signal()
    _tray_scan = Signal()
    _tray_quit_sig = Signal()

    def __init__(self):
        super().__init__()
        self._tray_show.connect(self._restore_from_tray)
        self._tray_scan.connect(lambda: self._start_scan(is_manual=True))
        self._tray_quit_sig.connect(self._tray_quit)
        self.setWindowTitle(cfg.APP_TITLE)
        # Минимум — чтобы layout не ломался на узких экранах (VM, ноутбуки 1366×768).
        self.setMinimumSize(900, 600)
        # Дефолт = cfg.WIDTH×HEIGHT, но НЕ больше доступной области экрана
        # (минус 40 px на taskbar/margin). Без клампа на VM с 1024×768 окно
        # уходит правым краем за пределы экрана — отсюда «правая сторона
        # не работает», там просто не видно курсора.
        screen = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        target_w = min(cfg.WIDTH, screen.width() - 40) if screen else cfg.WIDTH
        target_h = min(cfg.HEIGHT, screen.height() - 40) if screen else cfg.HEIGHT
        self.resize(max(target_w, 900), max(target_h, 600))
        self._scan_thread = None
        self._scan_worker = None

        # База данных (общая с Tk-версией)
        self.db = DBManager()

        # Тему читаем ДО построения UI: pages берут cfg.BG_*/TEXT_*
        # при конструировании, а apply_theme в config.py хардкодом ставит "dark".
        cfg.apply_theme(self.db.get_setting("theme", "dark"))

        # Frameless + поддержка min/max через системные кнопки
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Возвращаем WS_THICKFRAME (resize) и WS_CAPTION (snap) через Win32 API.
        # WM_NCCALCSIZE в nativeEvent обнуляет non-client area, сохраняя frameless вид.
        if sys.platform == "win32":
            hwnd = int(self.winId())
            GWL_STYLE = -16
            WS_THICKFRAME = 0x00040000
            WS_CAPTION = 0x00C00000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_CAPTION)
            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER)

        ico_path = _resource_path("icon.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

        self._current_page_id = "дашборд"
        self._build_content()
        self.nav_to(self._current_page_id)
        # Стартуем в обычном окне (1300×820 по cfg.WIDTH/HEIGHT, клампится
        # под availableGeometry-40 на маленьких экранах в __init__ выше).
        # Юзер может максимизировать сам через кнопку в titlebar или
        # double-click. На больших мониторах вокруг будет виден desktop —
        # это нормальное поведение Windows-приложения.
        self._open_maximized = False

        # 1s тик — чтобы автоскан стартовал в начало нужной минуты с
        # погрешностью ≤1с. Сама проверка дешёвая (две settings-cache
        # выборки и арифметика).
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._check_auto_scan)
        self._auto_timer.start(1_000)

        # Запускаем каждые 30s, чтобы утечки белели и когда приложение
        # в трее (раньше aging работал только при открытии журнала).
        self._aging_timer = QTimer(self)
        self._aging_timer.timeout.connect(self._tick_aging)
        self._aging_timer.start(30_000)
        # Сразу один раз — состояние корректно с самого старта.
        self.db.age_old_results(seconds=cfg.NEW_AGING_SECONDS)

        # Создаётся лениво при первом сворачивании в трей (closeEvent),
        # чтобы пока окно открыто — приложение было только в таскбаре.
        self._tray_icon = None
        self._force_quit = False

        # Слушаем именованный канал. Второй запуск пишет туда "show:<token>",
        # и мы восстанавливаем окно (даже если оно скрыто в трее).
        # Токен — рандомный per-launch, лежит в user-only файле; чужой процесс
        # без доступа к этому файлу команду провести не сможет.
        import secrets
        self._ipc_token = secrets.token_hex(16)  # 32 hex-символа
        try:
            os.makedirs(os.path.dirname(IPC_TOKEN_FILE) or ".", exist_ok=True)
            with open(IPC_TOKEN_FILE, "w", encoding="ascii") as f:
                f.write(self._ipc_token)
        except OSError:
            pass

        self._ipc_server = QLocalServer(self)
        if not self._ipc_server.listen(SINGLE_INSTANCE_KEY):
            # Сокет занят (либо чужим живым процессом, либо протухший).
            # На Windows named pipe не может быть «протухшим» — если listen
            # упал, значит другой инстанс реально слушает; но в main() уже
            # был probe, так что сюда дойдём только в маловероятной гонке.
            QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
            self._ipc_server.listen(SINGLE_INSTANCE_KEY)
        self._ipc_server.newConnection.connect(self._on_ipc_connection)

        # Авто-проверка обновлений: первая через 5 секунд после старта,
        # потом каждые 20 минут пока окно живёт. Плюс юзер может вручную
        # дёрнуть проверку кликом по лейблу версии в сайдбаре.
        self._update_thread = None
        self._update_worker = None
        self._notified_update_version: str = ""  # последний показанный юзеру
        self._manual_update_check: bool = False  # флаг ручной проверки
        QTimer.singleShot(5_000, self._check_for_update_async)
        self._update_recheck_timer = QTimer(self)
        self._update_recheck_timer.timeout.connect(
            self._check_for_update_async)
        self._update_recheck_timer.start(20 * 60 * 1000)  # каждые 20 минут

    def _check_for_update_async(self, manual: bool = False):
        if not UPDATER_OK:
            if manual:
                self._show_version_status("апдейтер недоступен")
            return
        # Если предыдущая проверка ещё крутится (network тормозит) —
        # не запускаем параллельную, дождёмся текущей.
        if (self._update_thread is not None
                and self._update_thread.isRunning()):
            if manual:
                self._show_version_status("проверяю...")
            return
        if manual:
            self._manual_update_check = True
            self._show_version_status("проверяю...")
        # Сохраняем ссылки на QThread/worker как атрибуты, иначе GC
        # снесёт их до того как сигналы успеют долететь.
        self._update_thread = QThread(self)
        self._update_worker = UpdateCheckWorker()
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.found.connect(self._on_update_found)
        self._update_worker.done.connect(self._on_update_check_done)
        self._update_worker.found.connect(self._update_thread.quit)
        self._update_worker.done.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.start()

    def _on_update_check_done(self):
        # Эмитится воркером когда обновлений НЕТ. Авто-чек молча
        # игнорирует; ручной чек должен дать юзеру понять, что
        # проверка отработала и он на свежей версии.
        if self._manual_update_check:
            self._manual_update_check = False
            self._show_version_status("актуальная версия")

    def _on_update_found(self, info: dict):
        version = info.get("version", "")
        manual = self._manual_update_check
        self._manual_update_check = False
        # Если юзер уже видел плашку про эту версию в этой сессии и
        # нажал «Позже» — на авто-rechek'е не дёргаем повторно. Ручной
        # клик «Проверить» — наоборот, всегда показываем баннер,
        # юзер явно попросил.
        already_notified = (version and
                            version == self._notified_update_version)
        if already_notified and not manual:
            self._pending_update = info
            return
        self._notified_update_version = version
        self._pending_update = info
        self.update_banner.show_for(version)
        if manual:
            # Сбрасываем «проверяю...» обратно на «v1.0.X» — плашку
            # сверху юзер увидит и так.
            self._show_version_status(f"v{APP_VERSION}", revert=False)

    def _show_version_status(self, text: str, revert: bool = True):
        """Меняет текст лейбла версии в сайдбаре. revert=True вернёт
        «v1.0.X» обратно через 3 секунды (для статусов «проверяю»/
        «актуальная»)."""
        sb = getattr(self, "sidebar", None)
        if sb is None or not hasattr(sb, "version_lbl"):
            return
        sb.version_lbl.setText(text)
        if revert:
            QTimer.singleShot(
                3_000,
                lambda: sb.version_lbl.setText(f"v{APP_VERSION}")
                if hasattr(sb, "version_lbl") else None,
            )

    def _start_update(self):
        info = getattr(self, "_pending_update", None)
        if not info:
            return
        dlg = UpdateProgressDialog(info, self)
        dlg.exec()

    def _log(self, msg: str):
        print(f"[app] {msg}", flush=True)
        try:
            self.settings.append_log(msg)
        except Exception:
            pass

    def _toast(self, title: str, message: str):
        if not TOAST_OK:
            print("[toast] winotify не установлен — уведомление пропущено", flush=True)
            return
        try:
            # app_id должен совпадать с AUMID процесса, иначе Windows
            # привяжет toast к python.exe и тихо подавит на части систем.
            t = Notification(app_id=APP_AUMID, title=title,
                             msg=message, duration="long")
            t.show()
        except Exception as e:
            # Раньше exception молча проглатывался — теперь видим причину.
            print(f"[toast] failed: {type(e).__name__}: {e}", flush=True)

    def _tick_aging(self):
        # Пока скан в процессе — не трогаем дашборд. Иначе при добавлении
        # каждой новой строки в БД (is_new=1) ближайший aging-тик пересчитает
        # «свежие» источники и покажет «Обнаружена угроза!» ещё до того, как
        # все источники проверены. Финальный статус выставляет _scan_done.
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        # Дочерние строки белеют по флагу is_new (1 день) — это в БД.
        # Parent-плашка живёт по wall-clock 30 мин и в БД ничего не меняет,
        # поэтому отдельно следим за числом «свежих» целей и перерисовываем
        # журнал/дашборд при пересечении порога.
        changed = self.db.age_old_results(seconds=cfg.NEW_AGING_SECONDS)
        fresh = self._count_fresh_parents()
        if (not changed) and (fresh == getattr(self, "_last_fresh_parents", -1)):
            return
        self._last_fresh_parents = fresh
        try:
            self.journal.load_from_db()
        except Exception:
            pass
        try:
            self.dashboard.refresh_stats()
            self.dashboard.refresh_status()
        except Exception:
            pass

    def _count_fresh_parents(self) -> int:
        """Сколько уникальных целей имеют утечки моложе NEW_AGING_PARENT_SECONDS.
        target в БД зашифрован — COUNT(DISTINCT) на шифротексте даёт ту же
        мощность множества, что и на открытых значениях."""
        try:
            import datetime as _dt
            cutoff = (_dt.datetime.now()
                      - _dt.timedelta(seconds=cfg.NEW_AGING_PARENT_SECONDS)
                      ).strftime("%Y-%m-%d %H:%M:%S")
            row = self.db._conn.execute(
                "SELECT COUNT(DISTINCT target) FROM scan_results "
                "WHERE scanned_at >= ?", (cutoff,)).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _check_auto_scan(self):
        import time
        if self.db.get_setting("auto_scan_enabled", "0") != "1":
            return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        last = self.db.get_last_scan()
        interval_s = float(self.db.get_setting("scan_interval", "12")) * 3600
        now = time.time()
        # Выравнивание следующего запуска по началу минуты: берём минуту
        # last_scan (отбрасываем секунды) и прибавляем интервал. Если
        # last_scan = 17:47:23, scan'ы будут в :47:00 каждый интервал.
        if last <= 0:
            eligible = True  # никогда не сканировали — старт сразу
        else:
            last_minute = int(last) - (int(last) % 60)
            next_at = last_minute + interval_s
            eligible = now >= next_at
        if eligible:
            self._log(f"Автосканирование запущено (интервал {int(interval_s)}s)")
            self._start_scan(is_manual=False)

    def _setup_tray(self):
        if not TRAY_OK or self._tray_icon is not None:
            return
        ico_path = _resource_path("icon.ico")
        try:
            tray_img = PILImage.open(ico_path).resize((64, 64))
        except Exception:
            tray_img = PILImage.new("RGBA", (64, 64), (124, 110, 247, 255))

        def _show(icon, item):
            self._tray_show.emit()

        def _scan(icon, item):
            self._tray_scan.emit()

        def _quit(icon, item):
            self._tray_quit_sig.emit()

        menu = pystray.Menu(
            TrayItem("Открыть Knox", _show, default=True),
            TrayItem("Запустить мониторинг", _scan),
            pystray.Menu.SEPARATOR,
            TrayItem("Выйти", _quit),
        )
        # Tooltip: на Windows pystray default-action срабатывает по double-click
        # (одиночный клик показывает меню). Пишем явно, чтобы юзер не думал
        # что приложение "не открывается".
        self._tray_icon = pystray.Icon("Knox", tray_img,
                                       "Knox — двойной клик чтобы открыть", menu)
        import threading
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _restore_from_tray(self):
        # Через Win32 SW_RESTORE — Qt's showNormal() для frameless+thickframe
        # не возвращает окно, если его HWND был уничтожен на hide().
        # SetForegroundWindow часто блокируется Windows для процессов, которые
        # сами не в фокусе — нужны обходы (topmost-flicker, attach-thread-input).
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                SW_RESTORE = 9
                SW_SHOW    = 5
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.ShowWindow(hwnd, SW_SHOW)
                # Обход блокировки SetForegroundWindow: коротко прикидываемся
                # topmost-окном — Windows тогда принудительно выводит на передний план.
                HWND_TOPMOST    = -1
                HWND_NOTOPMOST  = -2
                SWP_NOSIZE      = 0x0001
                SWP_NOMOVE      = 0x0002
                SWP_SHOWWINDOW  = 0x0040
                user32.SetWindowPos(hwnd, HWND_TOPMOST,   0, 0, 0, 0,
                                    SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                    SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
            except Exception as e:
                print(f"[tray] restore failed: {e}", flush=True)
                self.showNormal()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()
        # Пока окно видно — трей не нужен; иначе приложение «в двух местах».
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None

    def _on_ipc_connection(self):
        client = self._ipc_server.nextPendingConnection()
        if client is None:
            return
        # Чтобы накапливающиеся клиенты не висели дочерними объектами сервера
        # (это могло бы съесть память при спаме коннектов от локального процесса).
        client.disconnected.connect(client.deleteLater)
        client.readyRead.connect(lambda: self._handle_ipc(client))

    def _handle_ipc(self, client):
        # Лимитируем читаемый объём — иначе локальный процесс может пушить
        # бесконечный поток данных в нашу память.
        data = bytes(client.read(IPC_MAX_MSG).data())
        client.disconnectFromServer()
        # Точное сравнение, не substring: иначе любая строка с "show:" внутри
        # сработала бы. compare_digest защищает от тайминг-атак на токен.
        import hmac
        expected = b"show:" + self._ipc_token.encode("ascii")
        if hmac.compare_digest(data.strip(), expected):
            self._tray_show.emit()

    def _tray_quit(self):
        self._force_quit = True
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        self.close()

    _THEME_KEYS = (
        "BG_APP", "BG_SURFACE", "BG_ELEVATED", "BG_INPUT", "BG_NAV",
        "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED", "TEXT_LINK",
        "BORDER", "BORDER_HOVER", "SAFE_BG", "WARNING_BG", "DANGER_BG",
        "ACCENT_MUTED", "ACCENT_TEXT",
    )

    def _snapshot_theme(self) -> dict:
        return {k: getattr(cfg, k) for k in self._THEME_KEYS}

    def _on_theme_changed(self, mode: str):
        # Live-switch без пересоздания виджетов: снимаем snapshot цветов
        # до cfg.apply_theme и после, потом обходим всё дерево и в каждом
        # stylesheet'е свапаем старые hex на новые. Двухэтапный свап через
        # sentinel-токены, чтобы циклические замены (#A→#B, #B→#A) не
        # схлопнулись. Откладываем на следующий тик event-loop'а — клик
        # по кнопке темы должен развернуться полностью.
        old = self._snapshot_theme()
        cfg.apply_theme(mode)
        new = self._snapshot_theme()
        QTimer.singleShot(0, lambda: self._do_theme_apply(old, new))

    def _do_theme_apply(self, old: dict, new: dict):
        try:
            # Все значения в обеих темах уникальны (см. _THEMES в config.py:
            # light BG_ELEVATED/BG_INPUT специально слегка различаются,
            # чтобы не пересечься с хардкодом `color:#ffffff` в коде).
            # Поэтому простая dict-замена работает без коллизий.
            repl = {old[k]: new[k] for k in old if old[k] != new[k]}
            if repl:
                self._swap_styles_in_tree(self, repl)
            # Страницам, где цвета запекаются мимо stylesheet'а (AIPage —
            # QTextCharFormat в документе QTextEdit), даём шанс перерисоваться.
            ai = getattr(self, "ai", None)
            if ai is not None and hasattr(ai, "apply_theme"):
                try:
                    ai.apply_theme()
                except Exception as e:
                    print(f"[theme] ai.apply_theme: {e}", flush=True)
            # Иконки навигации построены через make_nav_icon(color) —
            # из stylesheet их не освежить, нужен явный refresh.
            sb = getattr(self, "sidebar", None)
            if sb is not None and hasattr(sb, "buttons"):
                for btn in sb.buttons.values():
                    try:
                        btn._refresh_icon()
                    except Exception:
                        pass
                # footer-иконка GitHub — тоже из cached pixmap, нужен refresh
                try:
                    sb.github_btn.setIcon(
                        make_nav_icon("github", cfg.TEXT_MUTED, 20))
                except Exception:
                    pass
            # paintEvent-based виджеты (BurgerButton, NavButton paint,
            # делегаты в журнале/новостях) подхватят новые cfg при repaint.
            for w in self.findChildren(QWidget):
                try:
                    w.update()
                except Exception:
                    pass
            self.update()
        except Exception as e:
            import traceback
            print(f"[theme] apply failed: {type(e).__name__}: {e}",
                  flush=True)
            traceback.print_exc()

    @staticmethod
    def _swap_styles_in_tree(root_widget, repl: dict):
        sentinels = {old: f"__THM_{i}__" for i, old in enumerate(repl)}
        for w in [root_widget] + root_widget.findChildren(QWidget):
            try:
                s = w.styleSheet()
                if not s:
                    continue
                # 1) старые значения → уникальные токены
                changed = False
                for old in repl:
                    if old and old in s:
                        s = s.replace(old, sentinels[old])
                        changed = True
                if not changed:
                    continue
                # 2) токены → новые значения
                for old, new in repl.items():
                    s = s.replace(sentinels[old], new)
                w.setStyleSheet(s)
            except Exception:
                pass

    def closeEvent(self, event):
        if self._force_quit or not TRAY_OK:
            self._auto_timer.stop()
            self._aging_timer.stop()
            if self._tray_icon is not None:
                self._tray_icon.stop()
                self._tray_icon = None
            self.db.close()
            event.accept()
            return
        # При обычном закрытии — прячем окно и поднимаем трей-иконку.
        if self._tray_icon is None:
            self._setup_tray()
        event.ignore()
        # Прячем через Win32 (SW_HIDE), а не Qt's hide(): для frameless+thickframe
        # окон Qt уничтожает HWND, и SW_RESTORE из трея не возвращает его.
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.ShowWindow(int(self.winId()), 0)  # SW_HIDE
                return
            except Exception:
                pass
        self.hide()

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))

            WM_NCCALCSIZE = 0x0083
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                # Обнуляем non-client area — окно остаётся frameless,
                # но WS_THICKFRAME/WS_CAPTION уже активны для resize и snap.
                return True, 0

            WM_NCHITTEST = 0x0084
            if msg.message == WM_NCHITTEST:
                # WM_NCHITTEST даёт физические пиксели в lParam, а frameGeometry()
                # — логические (HighDpiScaling в Qt6). На дисплеях с DPI > 100%
                # без масштабирования geo.right() - x уходит в минус и весь
                # правый край ошибочно ловится как resize → клики не доходят
                # до контента. Делим x/y на devicePixelRatio чтобы привести
                # к той же системе координат, что и frameGeometry().
                dpr = self.devicePixelRatioF() or 1.0
                raw_x = ctypes.c_short(msg.lParam & 0xFFFF).value
                raw_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                x = int(raw_x / dpr)
                y = int(raw_y / dpr)
                geo = self.frameGeometry()
                b = RESIZE_BORDER
                HTCLIENT = 1
                HTCAPTION = 2
                HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
                HTTOPLEFT, HTTOPRIGHT = 13, 14
                HTBOTTOMLEFT, HTBOTTOMRIGHT = 16, 17

                left   = x - geo.left() < b
                right  = geo.right() - x < b
                top    = y - geo.top() < b
                bottom = geo.bottom() - y < b

                if top and left:
                    return True, HTTOPLEFT
                if top and right:
                    return True, HTTOPRIGHT
                if bottom and left:
                    return True, HTBOTTOMLEFT
                if bottom and right:
                    return True, HTBOTTOMRIGHT
                if left:
                    return True, HTLEFT
                if right:
                    return True, HTRIGHT
                if top:
                    return True, HTTOP
                if bottom:
                    return True, HTBOTTOM

                # Titlebar — Windows нативно drag + snap.
                # Исключаем кнопки окна (справа 3×50px) и бургер (слева 64px).
                local_x = x - geo.left()
                local_y = y - geo.top()
                if local_y < TITLEBAR_H:
                    buttons_zone = WINDOW_BTN_W * 3
                    if SIDEBAR_W_COLLAPSED < local_x < geo.width() - buttons_zone:
                        return True, HTCAPTION

        return super().nativeEvent(event_type, message)

    def changeEvent(self, event):
        super().changeEvent(event)
        self._apply_dwm_round()

    def toggle_sidebar(self):
        self.sidebar.toggle()

    def _build_content(self):
        """Создаёт центральный виджет, titlebar, sidebar, страницы.
        Вызывается один раз из __init__. Смена темы НЕ пересобирает
        виджеты — apply_theme() переустанавливает stylesheet'ы in-place."""
        root = QWidget(self)
        root.setStyleSheet(f"background:{cfg.BG_ELEVATED};")
        self.setCentralWidget(root)
        self._root_widget = root
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        self.titlebar = TitleBar(self)
        root_lay.addWidget(self.titlebar)

        self.update_banner = UpdateBanner(root)
        self.update_banner.updateClicked.connect(self._start_update)
        self.update_banner.laterClicked.connect(self.update_banner.hide)
        root_lay.addWidget(self.update_banner)

        body = QWidget(root)
        body.setStyleSheet(f"background:{cfg.BG_SURFACE};")
        self._body_widget = body
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        root_lay.addWidget(body, 1)

        self.sidebar = Sidebar(body, self.nav_to)
        body_lay.addWidget(self.sidebar)

        content_wrap = QFrame(body)
        content_wrap.setObjectName("contentWrap")
        content_wrap.setStyleSheet(
            f"QFrame#contentWrap {{ background:{cfg.BG_APP}; border:none;"
            f" border-top-left-radius:14px; }}")
        self._content_wrap = content_wrap
        cwl = QVBoxLayout(content_wrap)
        cwl.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget(content_wrap)
        self.stack.setStyleSheet("background:transparent;")
        cwl.addWidget(self.stack)
        body_lay.addWidget(content_wrap, 1)

        self._pages: dict[str, int] = {}
        for pid, label in NAV_ITEMS:
            if pid == "дашборд":
                page = DashboardPage(
                    self.db,
                    on_scan=self._placeholder_scan,
                    on_export_pdf=self._export_pdf_all,
                    on_goto_journal=lambda: self.nav_to("журнал"),
                )
                self.dashboard = page
            elif pid == "менеджер":
                page = ManagerPage(
                    self.db,
                    on_stats_changed=self._on_targets_changed,
                )
                self.manager = page
            elif pid == "журнал":
                page = JournalPage(
                    self.db,
                    on_export_pdf=self._export_pdf_all,
                    on_export_pdf_for=self._export_pdf_for,
                    on_cleared=self._on_journal_cleared,
                )
                self.journal = page
            elif pid == "инструменты":
                page = ToolsPage()
                self.tools = page
            elif pid == "настройки":
                page = SettingsPage(self.db)
                page.themeChanged.connect(self._on_theme_changed)
                self.settings = page
            elif pid == "ai":
                page = AIPage(self.db)
                self.ai = page
            elif pid == "новости":
                from ui.qt_news import NewsPage
                page = NewsPage(self.db)
                self.news = page
            else:
                page = PagePlaceholder(label)
            idx = self.stack.addWidget(page)
            self._pages[pid] = idx

    def nav_to(self, page_id: str):
        if page_id not in self._pages:
            return
        self._current_page_id = page_id
        self.stack.setCurrentIndex(self._pages[page_id])
        self.sidebar.set_active(page_id)
        # При переходе на журнал перечитываем — aging мог сработать
        # пока юзер был на другой вкладке.
        if page_id == "журнал":
            try:
                self.journal.load_from_db()
            except Exception:
                pass
        # На дашборд — повтор count-up и заполнения баров.
        # ВАЖНО: если идёт скан, replay_intro вызовет refresh_status,
        # который прочитает свежие is_new=1 строки и покажет «Обнаружена
        # угроза!» ещё до завершения проверки. Финальный статус выставит
        # _scan_done, поэтому во время скана replay полностью пропускаем —
        # дашборд останется в текущем состоянии «Идёт проверка...».
        elif page_id == "дашборд":
            if self._scan_thread is not None and self._scan_thread.isRunning():
                pass
            else:
                try:
                    self.dashboard.replay_intro()
                except Exception:
                    pass
        # Универсальный fade-in для любой страницы.
        try:
            self._animate_page_entry(self.stack.currentWidget())
        except Exception as e:
            print(f"[nav] page fade-in failed: {e}", flush=True)

    def _animate_page_entry(self, page):
        """Плавное появление страницы при переключении вкладок.
        На страницах с QScrollArea фейдим страницу целиком (каскад внутри
        scroll-а ломает рендер вложенных виджетов в Qt). На остальных —
        каскадный fade-in карточек (QFrame#card). После завершения снимаем
        QGraphicsOpacityEffect и форсим update всех потомков."""
        from PySide6.QtWidgets import (
            QGraphicsOpacityEffect, QFrame, QScrollArea, QWidget,
        )
        from PySide6.QtCore import (
            QPropertyAnimation, QEasingCurve, QTimer, QAbstractAnimation,
        )

        def cleanup(widget):
            try:
                widget.setGraphicsEffect(None)
                widget.update()
                for ch in widget.findChildren(QWidget):
                    ch.update()
            except Exception:
                pass

        def fade_in(widget, duration, delay=0):
            eff = QGraphicsOpacityEffect(widget)
            eff.setOpacity(0.0)
            widget.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", widget)
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda w=widget: cleanup(w))
            # Страховка: даже если finished не успеет долететь, эффект
            # точно снимется через duration+delay+200мс.
            QTimer.singleShot(duration + delay + 200,
                              lambda w=widget: cleanup(w))
            if delay:
                QTimer.singleShot(delay, anim.start)
            else:
                anim.start(QAbstractAnimation.DeleteWhenStopped)

        # Если страница содержит QScrollArea — каскад по карточкам ломает
        # рендер во вложенных виджетах, фейдим страницу целиком.
        has_scroll = bool(page.findChildren(QScrollArea))
        cards = [f for f in page.findChildren(QFrame)
                 if f.objectName() == "card"]
        if cards and not has_scroll:
            for i, card in enumerate(cards):
                fade_in(card, 320, delay=i * 60)
        else:
            fade_in(page, 280)

    def _on_journal_cleared(self):
        try:
            self.dashboard.refresh_stats()
            self.dashboard.refresh_status()
        except Exception:
            pass

    def _on_targets_changed(self):
        # Обновляем метрики на дашборде, когда на менеджере добавили/удалили объект
        try:
            self.dashboard.refresh_stats()
        except Exception:
            pass

    def _placeholder_scan(self):
        self._start_scan(is_manual=True)

    def _start_scan(self, is_manual: bool = True):
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        # Подхватываем API-ключи из настроек (на случай изменения).
        # Пользовательский ключ имеет приоритет; если его нет — остаётся встроенный
        # (выставленный в LeakEngine.RAPID_API_KEY / INTELX_API_KEY на уровне класса).
        from core.engine import _builtin_rapidapi, _builtin_intelx
        LeakEngine.RAPID_API_KEY  = self.db.get_api_key("rapidapi") or _builtin_rapidapi()
        LeakEngine.INTELX_API_KEY = self.db.get_api_key("intelx")   or _builtin_intelx()

        self._scan_thread = QThread(self)
        self._scan_worker = ScanWorker(self.db, is_manual=is_manual)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)

        self._scan_worker.logMessage.connect(self._scan_log)
        self._scan_worker.statusChanged.connect(self._scan_status)
        self._scan_worker.progress.connect(self._scan_progress)
        self._scan_worker.riskUpdate.connect(self._scan_risk)
        self._scan_worker.finished.connect(self._scan_done)

        def _cleanup():
            self._scan_thread.quit()
            self._scan_thread.wait()
            self._scan_thread = None
            self._scan_worker = None
        self._scan_worker.finished.connect(_cleanup)

        try:
            self.dashboard.start_scan_animation()
            self.dashboard.progress_bar.setValue(0)
        except Exception:
            pass
        if is_manual:
            self._log("Сканирование запущено...")
        else:
            # Toast только при автоскане — пользователь видит, что приложение
            # из трея реально работает. При ручном запуске тост избыточен.
            self._toast("Knox", "Фоновая проверка запущена")
        self._scan_thread.start()

    def _scan_log(self, msg: str):
        print(f"[scan] {msg}", flush=True)
        try:
            self.settings.append_log(msg)
        except Exception:
            pass

    def _scan_status(self, text: str, badge: str, kind: str):
        color_map = {
            "safe":   (cfg.SAFE_COLOR,    cfg.SAFE_BG),
            "warn":   (cfg.WARNING_COLOR, cfg.WARNING_BG),
            "danger": (cfg.DANGER_COLOR, cfg.DANGER_BG),
        }
        color, bg = color_map.get(kind, (cfg.TEXT_PRIMARY, cfg.BG_ELEVATED))
        try:
            self.dashboard.status_label.setText(text)
            self.dashboard.status_label.setStyleSheet(
                f"font-family:'Geist'; color:{color}; font-size:20px;"
                f"font-weight:700; background:transparent; border:none;"
            )
            self.dashboard.status_badge.setText(badge)
            self.dashboard.status_badge.setStyleSheet(
                f"QLabel {{ font-family:'Geist'; background:{bg};"
                f"color:{color}; border-radius:10px; padding:3px 10px;"
                f"font-size:11px; font-weight:700; }}"
            )
        except Exception:
            pass

    def _scan_progress(self, pct: float):
        try:
            self.dashboard.progress_bar.setValue(int(pct * 100))
        except Exception:
            pass

    def _scan_risk(self, sources: list):
        try:
            score, level, color = LeakEngine.calculate_risk_score(sources)
            self.dashboard.set_risk(level, score, color)
        except Exception as e:
            print(f"[scan] risk update failed: {e}", flush=True)

    def _scan_done(self, leaks: int, new_breaches: list):
        try:
            self.dashboard.stop_scan_animation()
            self.dashboard.progress_bar.setValue(0)
            self.dashboard.refresh_stats()
            self.dashboard.refresh_status()
            if new_breaches:
                self.dashboard.update_events(new_breaches)
        except Exception:
            pass
        try:
            self.journal.load_from_db()
        except Exception:
            pass
        try:
            self.settings._refresh_next_scan()
        except Exception:
            pass
        if new_breaches:
            self._toast("Knox — Новые утечки!",
                        f"Найдено {len(new_breaches)} новых утечек "
                        f"(всего подтверждено: {leaks}).")
            self._send_email_notify(new_breaches, leaks)
        elif leaks:
            self._toast("Knox",
                        f"Проверка завершена. Подтверждено утечек: {leaks}, "
                        f"новых нет.")
        else:
            self._toast("Knox", "Проверка завершена. Утечек не найдено.")

    def _send_email_notify(self, new_breaches: list, leaks: int):
        smtp = self.db.get_smtp()
        if not smtp.get("host") or not smtp.get("user") or not smtp.get("recipient"):
            return
        try:
            from core.engine import LeakEngine as LE
            sources = [b[1] for b in new_breaches]
            score, level, color = LE.calculate_risk_score(sources)
        except Exception:
            score, level = 0, "Неизвестно"

        def _do():
            from services.smtp_notify import send_breach_email
            ok, err = send_breach_email(
                smtp_host=smtp["host"], smtp_port=smtp["port"],
                smtp_user=smtp["user"], smtp_pass=smtp["password"],
                recipient=smtp["recipient"], breaches=new_breaches,
                risk_level=level, risk_score=score)
            self._log("Email-уведомление отправлено." if ok
                      else f"Email не отправлен: {err}")

        import threading
        threading.Thread(target=_do, daemon=True).start()

    def _placeholder_pdf(self):
        self._export_pdf_all()

    def _export_pdf_all(self):
        if not PDF_OK:
            QMessageBox.warning(self, "PDF", "Установите reportlab: pip install reportlab")
            return
        logs: list[str] = []
        ok = export_pdf_report(self.db, LeakEngine, log_fn=logs.append)
        if not ok:
            QMessageBox.information(
                self, "PDF",
                "\n".join(logs) if logs else "Нет данных для экспорта.")

    def _export_pdf_for(self, target: str):
        if not PDF_OK:
            QMessageBox.warning(self, "PDF", "Установите reportlab: pip install reportlab")
            return
        logs: list[str] = []
        ok = export_pdf_for_target(self.db, LeakEngine, target, log_fn=logs.append)
        if not ok:
            QMessageBox.information(
                self, "PDF",
                "\n".join(logs) if logs else f"Нет данных для {target}.")

    def _apply_dwm_round(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            dwmapi = ctypes.windll.dwmapi
            # Скруглённые углы (Win11).
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            pref = ctypes.c_int(DWMWCP_ROUND)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(pref), ctypes.sizeof(pref))
            # Убираем 1-px светлую границу, которую Win11 рисует по периметру
            # frameless-окон по умолчанию. На дефолтном размере без неё окно
            # выглядит как монолитный прямоугольник темы (а не «с белой
            # линией по бокам, которую можно двигать»).
            DWMWA_BORDER_COLOR = 34
            DWMWA_COLOR_NONE   = 0xFFFFFFFE
            color = ctypes.c_uint(DWMWA_COLOR_NONE)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_BORDER_COLOR,
                ctypes.byref(color), ctypes.sizeof(color))
        except Exception as e:
            print(f"[qt] dwm style failed: {e}", flush=True)

def _register_aumid_for_toasts():
    """Регистрирует AUMID в HKCU\\Software\\Classes\\AppUserModelId\\<AUMID>.
    Без этой записи современный Windows глушит toast-уведомления
    (даже в Action Center не попадают). Идемпотентно — безопасно вызывать
    при каждом запуске."""
    try:
        import winreg
        key_path = f"Software\\Classes\\AppUserModelId\\{APP_AUMID}"
        ico_path = _resource_path("icon.ico")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "Knox")
            if os.path.exists(ico_path):
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, ico_path)
    except Exception as e:
        print(f"[app] AUMID registration failed: {e}", flush=True)

def main():
    # Сглаживание шрифтов через DirectWrite (убирает пикселизацию тонких штрихов)
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=directwrite")
    # AppUserModelID — иначе Windows группирует процесс под иконкой python.exe,
    # и в таскбаре наша icon.ico не показывается. Должно быть до создания окон.
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                APP_AUMID)
        except Exception:
            pass
        _register_aumid_for_toasts()
    app = QApplication(sys.argv)
    # Single-instance: пробуем подключиться к именованному каналу
    # существующего инстанса. Работает и когда окно скрыто в трее
    # (в отличие от FindWindowW, который не находит unmapped окна).
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_KEY)
    if probe.waitForConnected(500):
        # Токен из файла, чтобы наш show-запрос принял первый инстанс.
        try:
            with open(IPC_TOKEN_FILE, "r", encoding="ascii") as f:
                token = f.read().strip()
        except OSError:
            token = ""
        msg = b"show:" + token.encode("ascii")
        probe.write(msg)
        probe.flush()
        probe.waitForBytesWritten(500)
        probe.disconnectFromServer()
        print("[app] Knox уже запущен — открываю окно.", flush=True)
        return
    _ico = _resource_path("icon.ico")
    if os.path.exists(_ico):
        app.setWindowIcon(QIcon(_ico))
    family = _load_geist_qt()
    cfg.QT_FONT_FAMILY = family

    base = QFont(family, 10)
    base.setWeight(QFont.DemiBold)  # 600 — как в меню, толще обычного
    base.setHintingPreference(QFont.PreferNoHinting)
    base.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(base)
    app.setStyleSheet(
        f'* {{ font-family: "{family}"; font-weight: 600; }}'
    )
    win = MainWindow()
    # Стартуем максимизированным (см. MainWindow.__init__): занимает весь
    # экран, нет видимых resize-границ по бокам и пустоты вокруг окна.
    if getattr(win, "_open_maximized", False):
        win.showMaximized()
    else:
        win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
