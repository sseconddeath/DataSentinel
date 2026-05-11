"""
qt_icons.py — общий рендер SVG-иконок типа объекта (email/phone/other).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

from core.engine import LeakEngine

_TYPE_SVG = {
    "email": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<rect x="2" y="4" width="20" height="16" rx="2"/>'
        '<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>'
        '</svg>'
    ),
    "phone": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 '
        '19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3'
        'a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 '
        '9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 '
        '2.81.7A2 2 0 0 1 22 16.92z"/>'
        '</svg>'
    ),
    # Lucide "at-sign" — узнаваемая иконка username/handle.
    "username": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"/>'
        '</svg>'
    ),
    # Lucide "key-round" — традиционный ключ для пароля.
    "password": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">'
        '<circle cx="7.5" cy="15.5" r="5.5"/>'
        '<path d="m21 2-9.6 9.6"/>'
        '<path d="m15.5 7.5 3 3L22 7l-3-3"/>'
        '</svg>'
    ),
}

_cache: dict[tuple[str, str, int], QPixmap] = {}

def detect_kind(value: str) -> str:
    t = LeakEngine.detect_type(value)
    # detect_type теперь возвращает один из email/phone/username/password
    # — используем его напрямую как ключ иконки.
    if t in _TYPE_SVG:
        return t
    return "username"

def make_type_pixmap(kind: str, color: str, size: int = 18) -> QPixmap:
    key = (kind, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    svg = _TYPE_SVG.get(kind, _TYPE_SVG["username"]).replace("{c}", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(p)
    p.end()
    _cache[key] = pm
    return pm
