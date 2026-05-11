# config.py — Design System для Data Leak Sentinel
import os, sys

APP_TITLE = "DataSentinel"
WIDTH     = 1300
HEIGHT    = 820

# Сколько секунд утечка остаётся «новой» (красная) после первого обнаружения.
# Для отладки aging — 120 (2 мин); продакшн — 1*24*3600 (1 день).
NEW_AGING_SECONDS = 1 * 24 * 3600
# Отдельный порог для верхней (parent) строки журнала: плашка «NEW»
# и красная заливка снимаются быстрее, чтобы видно было что свежо
# именно сейчас. Дочерние источники остаются красными NEW_AGING_SECONDS.
NEW_AGING_PARENT_SECONDS = 30 * 60

FONT_MONO    = "Cascadia Code"
FONT_SIZE_XL = 36
FONT_SIZE_LG = 20
FONT_SIZE_MD = 14
FONT_SIZE_SM = 13
FONT_SIZE_XS = 12

ACCENT       = "#7c6ef7"
ACCENT_HOVER = "#6c5ee7"

SAFE_COLOR    = "#3dba7a"
WARNING_COLOR = "#d4882a"
DANGER_COLOR  = "#e05555"

RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_XL = 16

COL_WIDTHS = {"num": 36, "obj": 220, "src": 170, "stat": 260, "rec": 380}
BACKGROUND_CHECK_INTERVAL = 12 * 60 * 60

def _load_geist() -> str:
    """
    Загружает Geist-Regular.ttf и Geist-Bold.ttf из папки fonts/
    рядом с исполняемым файлом (работает и в .py и в .exe).
    Возвращает имя шрифта если загрузка успешна, иначе fallback.
    """
    try:
        import tkinter.font as tkfont  # noqa: F401

        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
        fonts_dir = os.path.join(base, "fonts")

        regular   = os.path.join(fonts_dir, "Geist-Regular.ttf")
        semibold  = os.path.join(fonts_dir, "Geist-SemiBold.ttf")
        bold      = os.path.join(fonts_dir, "Geist-Bold.ttf")

        loaded = False
        # pyglet — самый надёжный способ загрузить кастомный шрифт в tkinter
        try:
            import pyglet
            if os.path.exists(regular):
                pyglet.font.add_file(regular)
                loaded = True
            if os.path.exists(semibold):
                pyglet.font.add_file(semibold)
            if os.path.exists(bold):
                pyglet.font.add_file(bold)
        except ImportError:
            pass

        # Fallback: ctypes на Windows
        if not loaded:
            try:
                import ctypes
                FR_PRIVATE = 0x10
                gdi = ctypes.windll.gdi32
                if os.path.exists(regular):
                    gdi.AddFontResourceExW(regular, FR_PRIVATE, 0)
                    loaded = True
                if os.path.exists(semibold):
                    gdi.AddFontResourceExW(semibold, FR_PRIVATE, 0)
                if os.path.exists(bold):
                    gdi.AddFontResourceExW(bold, FR_PRIVATE, 0)
            except Exception:
                pass

        if loaded and os.path.exists(semibold):
            return "Geist SemiBold"
        if loaded and os.path.exists(regular):
            return "Geist"

    except Exception:
        pass

    # Системный fallback
    return "Segoe UI Variable Text"

FONT_FAMILY = _load_geist()

_THEMES = {
    "dark": {
        "BG_APP":        "#0f0f13",
        "BG_SURFACE":    "#13131a",
        "BG_ELEVATED":   "#1a1a24",
        "BG_INPUT":      "#0d0d12",
        "BG_NAV":        "#0a0a0d",
        "TEXT_PRIMARY":  "#e8e8f0",
        "TEXT_SECONDARY":"#9090a8",
        "TEXT_MUTED":    "#44445a",
        "TEXT_LINK":     "#7c9ef8",
        "BORDER":        "#1e1e2a",
        "BORDER_HOVER":  "#2e2e3e",
        "SAFE_BG":       "#0e2218",
        "WARNING_BG":    "#261a08",
        "DANGER_BG":     "#2a1010",
        "ACCENT_MUTED":  "#1e1a3a",
        "ACCENT_TEXT":   "#a99ff8",
    },
    "light": {
        "BG_APP":        "#eaeaf4",
        "BG_SURFACE":    "#f2f2f8",
        # BG_ELEVATED и BG_INPUT не делаем буквальным #ffffff: иначе они
        # совпадают с хардкодом `color:#ffffff` в коде (текст на ACCENT),
        # и live-theme-swap по hex-замене пере-переключает значения местами.
        # Визуально неотличимо.
        "BG_ELEVATED":   "#fefefe",
        "BG_INPUT":      "#fcfcfc",
        "BG_NAV":        "#c8c8e0",
        "TEXT_PRIMARY":  "#0e0e20",
        "TEXT_SECONDARY":"#2a2a45",
        "TEXT_MUTED":    "#7070a0",
        "TEXT_LINK":     "#3a5ee8",
        "BORDER":        "#c0c0d8",
        "BORDER_HOVER":  "#a0a0c0",
        "SAFE_BG":       "#d0f0e0",
        "WARNING_BG":    "#fde8c0",
        "DANGER_BG":     "#fdd8d8",
        "ACCENT_MUTED":  "#e0dcff",
        "ACCENT_TEXT":   "#4a3db8",
    },
}

# Глобальные переменные (переключаются через apply_theme)
BG_APP = BG_SURFACE = BG_ELEVATED = BG_INPUT = BG_NAV = ""
TEXT_PRIMARY = TEXT_SECONDARY = TEXT_MUTED = TEXT_LINK = ""
BORDER = BORDER_HOVER = ""
SAFE_BG = WARNING_BG = DANGER_BG = ACCENT_MUTED = ACCENT_TEXT = ""

def apply_theme(mode: str):
    global BG_APP, BG_SURFACE, BG_ELEVATED, BG_INPUT, BG_NAV
    global TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, TEXT_LINK
    global BORDER, BORDER_HOVER, SAFE_BG, WARNING_BG, DANGER_BG
    global ACCENT_MUTED, ACCENT_TEXT

    if mode == "system":
        try:
            import darkdetect
            mode = "light" if darkdetect.isLight() else "dark"
        except Exception:
            mode = "dark"

    t = _THEMES.get(mode, _THEMES["dark"])
    BG_APP         = t["BG_APP"]
    BG_SURFACE     = t["BG_SURFACE"]
    BG_ELEVATED    = t["BG_ELEVATED"]
    BG_INPUT       = t["BG_INPUT"]
    BG_NAV         = t["BG_NAV"]
    TEXT_PRIMARY   = t["TEXT_PRIMARY"]
    TEXT_SECONDARY = t["TEXT_SECONDARY"]
    TEXT_MUTED     = t["TEXT_MUTED"]
    TEXT_LINK      = t["TEXT_LINK"]
    BORDER         = t["BORDER"]
    BORDER_HOVER   = t["BORDER_HOVER"]
    SAFE_BG        = t["SAFE_BG"]
    WARNING_BG     = t["WARNING_BG"]
    DANGER_BG      = t["DANGER_BG"]
    ACCENT_MUTED   = t["ACCENT_MUTED"]
    ACCENT_TEXT    = t["ACCENT_TEXT"]

apply_theme("dark")
