"""
qt_journal.py — страница «Журнал инцидентов» на PySide6.

Двухуровневое дерево:
  • Parent-строка  — объект мониторинга (email/phone/username)
  • Child-строки   — найденные утечки по этому объекту

Использует QTreeView + QStandardItemModel. Кликабельные source-ячейки
для открытия URL утечки в браузере.
"""
from __future__ import annotations

import datetime
import webbrowser
from collections import OrderedDict
from typing import Callable

from PySide6.QtCore import Qt, QModelIndex, QSize, QRect, QTimer
from PySide6.QtGui import (
    QColor, QStandardItem, QStandardItemModel, QBrush, QFont, QPainter, QPen,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QTreeView, QHeaderView, QAbstractItemView, QMessageBox, QSizePolicy,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)

import core.config as cfg
from core.engine import LeakEngine

COLUMNS = ["#", "Источник", "Название утечки", "Рекомендация", "Дата"]
COL_NUM, COL_SRC, COL_BREACH, COL_REC, COL_DATE = range(5)

ROLE_URL = Qt.UserRole + 1
ROLE_TARGET = Qt.UserRole + 2

def _rec(source: str) -> str:
    for k, v in [
        ("HIBP",            "Смените пароль немедленно!"),
        ("LeakCheck",       "Включите 2FA на аккаунте"),
        ("Hudson Rock",     "Проверьте устройство на вирусы!"),
        ("BreachDirectory", "Смените пароль и включите 2FA"),
        ("EmailRep",        "Смените пароль, проверьте аккаунты"),
        ("IntelX",          "Данные в Dark Web — смените почту"),
    ]:
        if k in source:
            return v
    return "Проверьте безопасность аккаунта"

def _is_danger(breach_name: str) -> bool:
    low = breach_name.lower()
    return any(w in low for w in
               ["слито", "dehashed", "mailpass", "database", "dump", "leak", "mix"])

def _btn_secondary(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(32)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.BG_ELEVATED};
            color: {cfg.TEXT_PRIMARY};
            border: 1px solid {cfg.BORDER};
            border-radius: 6px;
            padding: 0 14px;
            font-size: 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{ border: 1px solid {cfg.BORDER_HOVER}; }}
    """)
    return b

def _btn_danger(text: str, parent: QWidget | None = None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(32)
    b.setStyleSheet(f"""
        QPushButton {{
            font-family: 'Geist';
            background: {cfg.DANGER_BG};
            color: {cfg.DANGER_COLOR};
            border: 1px solid #3a1515;
            border-radius: 6px;
            padding: 0 14px;
            font-size: 12px;
            font-weight: 500;
        }}
        QPushButton:hover {{ background: #3a1515; }}
    """)
    return b

ROLE_COUNT = Qt.UserRole + 4
ROLE_ICON  = Qt.UserRole + 5

class _JournalTree(QTreeView):
    """Отключает штатную отрисовку стрелок/hover у детей;
    parent-hover ведём вручную через mouseMoveEvent → hovered_row."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_row = -1
        self._on_pdf_click = None  # callable(target: str)
        self.viewport().setAttribute(Qt.WA_Hover, False)
        self.setMouseTracking(True)

    def drawBranches(self, painter, rect, index):
        return

    def drawRow(self, painter, options, index):
        opt = QStyleOptionViewItem(options)
        opt.state &= ~QStyle.State_MouseOver
        opt.state &= ~QStyle.State_Selected
        opt.state &= ~QStyle.State_HasFocus
        is_parent = bool(index.data(Qt.UserRole + 3))
        if is_parent and index.row() == self._hover_row and not index.parent().isValid():
            opt.state |= QStyle.State_MouseOver
        # Полностью заливаем ряд фоном приложения — перекрывает любой
        # остаточный hover/current/focus-прямоугольник, который рисует стиль.
        full = QRect(0, options.rect.top(),
                     self.viewport().width(), options.rect.height())
        painter.fillRect(full, QColor(cfg.BG_APP))
        super().drawRow(painter, opt, index)

    def mouseMoveEvent(self, ev):
        idx = self.indexAt(ev.pos())
        row = idx.row() if (idx.isValid() and not idx.parent().isValid()
                            and bool(idx.data(Qt.UserRole + 3))) else -1
        if row != self._hover_row:
            self._hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(ev)

    def _pdf_hit(self, pos, idx) -> bool:
        if not (idx.isValid() and not idx.parent().isValid()
                and bool(idx.data(Qt.UserRole + 3))):
            return False
        row_rect = self.visualRect(idx.sibling(idx.row(), 0))
        full_right = self.viewport().width() - 2
        btn_w, btn_h = 80, 26
        bx = full_right - btn_w - 12
        by = row_rect.center().y() - btn_h // 2
        return bx <= pos.x() <= bx + btn_w and by <= pos.y() <= by + btn_h

    def mousePressEvent(self, ev):
        idx = self.indexAt(ev.pos())
        if self._pdf_hit(ev.pos(), idx):
            self._pdf_pressed = True
            ev.accept()
            return
        self._pdf_pressed = False
        super().mousePressEvent(ev)
        self.setCurrentIndex(QModelIndex())

    def mouseReleaseEvent(self, ev):
        if getattr(self, "_pdf_pressed", False):
            self._pdf_pressed = False
            idx = self.indexAt(ev.pos())
            if self._pdf_hit(ev.pos(), idx):
                target = idx.data(ROLE_TARGET) or idx.data(Qt.DisplayRole)
                if self._on_pdf_click and target:
                    self._on_pdf_click(str(target))
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def leaveEvent(self, ev):
        if self._hover_row != -1:
            self._hover_row = -1
            self.viewport().update()
        super().leaveEvent(ev)

class ParentRowDelegate(QStyledItemDelegate):
    """Рисует скруглённый фон + бейдж счётчика для parent-строк."""
    def __init__(self, tree: QTreeView):
        super().__init__(tree)
        self._tree = tree

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        is_parent = bool(index.data(Qt.UserRole + 3))
        if not is_parent:
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.State_MouseOver
            opt.state &= ~QStyle.State_Selected
            opt.state &= ~QStyle.State_HasFocus
            if index.column() == 0:
                opt.rect = opt.rect.adjusted(18, 0, 0, 0)
            super().paint(painter, opt, index)
            return

        has_new = bool(index.sibling(index.row(), 0).data(Qt.UserRole))
        hover = bool(option.state & QStyle.State_MouseOver)
        selected = bool(option.state & QStyle.State_Selected)

        if has_new:
            bg = QColor(cfg.DANGER_BG)
        elif hover:
            bg = QColor(cfg.BORDER)
        else:
            bg = QColor(cfg.BG_ELEVATED)
        _ = selected  # selection не рисуем, чтобы не было синей плашки

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        indent = self._tree.indentation() * 1  # depth 1 parent
        rect = option.rect.adjusted(-indent + 2, 2, -2, -2)
        painter.drawRoundedRect(rect, 8, 8)

        # Ручная отрисовка стрелки-шеврона в зоне indent (её затёр наш фон)
        if index.column() == 0:
            expanded = self._tree.isExpanded(index)
            cx = rect.left() + 14
            cy = rect.center().y()
            arrow_color = QColor(cfg.TEXT_MUTED)
            painter.setPen(QPen(arrow_color, 1.6))
            painter.setBrush(Qt.NoBrush)
            from PySide6.QtCore import QPointF
            if expanded:
                # ▼
                pts = [QPointF(cx - 4, cy - 2),
                       QPointF(cx,     cy + 3),
                       QPointF(cx + 4, cy - 2)]
            else:
                # ▶
                pts = [QPointF(cx - 2, cy - 4),
                       QPointF(cx + 3, cy),
                       QPointF(cx - 2, cy + 4)]
            painter.drawPolyline(pts)

        # Содержимое рисуем только в первой колонке (spanned row)
        if index.column() == 0:
            target = index.data(Qt.DisplayRole) or ""
            ic     = index.data(ROLE_ICON) or ""
            count  = index.data(ROLE_COUNT) or 0
            text_color = QColor(cfg.DANGER_COLOR if has_new else cfg.TEXT_PRIMARY)

            font = QFont(cfg.QT_FONT_FAMILY if hasattr(cfg, 'QT_FONT_FAMILY') else "Geist")
            font.setPixelSize(14)
            font.setWeight(QFont.DemiBold)
            font.setHintingPreference(QFont.PreferNoHinting)
            font.setStyleStrategy(QFont.PreferAntialias)
            painter.setFont(font)
            painter.setPen(QPen(text_color))

            x = rect.left() + 32
            y = rect.center().y()
            fm = painter.fontMetrics()

            from ui.qt_icons import make_type_pixmap
            pm = make_type_pixmap(
                ic,
                cfg.DANGER_COLOR if has_new else cfg.TEXT_PRIMARY,
                18,
            )
            pm_y = y - 9
            painter.drawPixmap(x, pm_y, pm)
            x += 26

            tw = fm.horizontalAdvance(target)
            painter.drawText(QRect(x, rect.top(), tw + 4, rect.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, target)
            x += tw + 14

            # Бейдж со счётчиком
            badge_font = QFont(font)
            badge_font.setPixelSize(12)
            badge_font.setWeight(QFont.DemiBold)
            painter.setFont(badge_font)
            bfm = painter.fontMetrics()
            badge_txt = f"{count} утечек"
            bw = bfm.horizontalAdvance(badge_txt) + 20
            bh = 22
            badge_rect = QRect(x, y - bh // 2, bw, bh)
            badge_bg = QColor(cfg.DANGER_COLOR if has_new else cfg.ACCENT_MUTED)
            painter.setBrush(badge_bg)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_rect, 6, 6)
            painter.setPen(QPen(QColor("#ffffff" if has_new else cfg.TEXT_PRIMARY)))
            painter.drawText(badge_rect, Qt.AlignCenter, badge_txt)

            # Кнопка "↓ PDF" справа — отчёт по конкретной утечке
            btn_txt = "\u2193 PDF"
            btn_font = QFont(font)
            btn_font.setPixelSize(12)
            btn_font.setWeight(QFont.DemiBold)
            painter.setFont(btn_font)
            btfm = painter.fontMetrics()
            btw = btfm.horizontalAdvance(btn_txt) + 22
            bth = 26
            bt_rect = QRect(rect.right() - btw - 12, y - bth // 2, btw, bth)
            painter.setBrush(QColor(cfg.BG_APP))
            painter.setPen(QPen(QColor(cfg.BORDER), 1))
            painter.drawRoundedRect(bt_rect, 6, 6)
            painter.setPen(QPen(QColor(cfg.TEXT_PRIMARY)))
            painter.drawText(bt_rect, Qt.AlignCenter, btn_txt)

            if has_new:
                x += bw + 10
                painter.setFont(font)
                painter.setPen(QPen(QColor(cfg.DANGER_COLOR)))
                painter.drawText(QRect(x, rect.top(), 80, rect.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, "\u2726 NEW")

        painter.restore()

class JournalPage(QWidget):
    def __init__(self, db,
                 on_export_pdf: Callable[[], None] | None = None,
                 on_export_pdf_for: Callable[[str], None] | None = None,
                 on_cleared: Callable[[], None] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self._on_export_pdf = on_export_pdf
        self._on_export_pdf_for = on_export_pdf_for
        self._on_cleared = on_cleared
        self.setStyleSheet(f"background:{cfg.BG_APP};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(12)

        title = QLabel("Журнал инцидентов", self)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;"
        )
        outer.addWidget(title)
        subtitle = QLabel("История найденных утечек", self)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:14px; background:transparent;"
        )
        outer.addWidget(subtitle)
        outer.addSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        # Легенда
        for dot_color, label in [
            (cfg.DANGER_COLOR, "Новые"),
            (cfg.ACCENT_TEXT, "Ранее известные"),
        ]:
            dot = QLabel("●", self)
            dot.setStyleSheet(
                f"font-family:'Geist'; color:{dot_color};"
                f"font-size:12px; background:transparent;"
            )
            top.addWidget(dot)
            lbl = QLabel(label, self)
            lbl.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
                f"font-size:11px; background:transparent; padding-right:8px;"
            )
            top.addWidget(lbl)

        top.addStretch(1)

        btn_pdf = _btn_secondary("\u2193  PDF", self)
        btn_pdf.clicked.connect(self._export_all)
        top.addWidget(btn_pdf)

        btn_expand = _btn_secondary("\u25BC  Все", self)
        btn_expand.clicked.connect(self._expand_all)
        top.addWidget(btn_expand)

        btn_collapse = _btn_secondary("\u25B6  Свернуть", self)
        btn_collapse.clicked.connect(self._collapse_all)
        top.addWidget(btn_collapse)

        btn_clear = _btn_danger("\u2715  Очистить", self)
        btn_clear.clicked.connect(self._clear)
        top.addWidget(btn_clear)

        outer.addLayout(top)

        self.tree = _JournalTree(self)
        self.tree.setObjectName("journalTree")
        self.tree.setAlternatingRowColors(False)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAnimated(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setMouseTracking(True)
        self.tree.setFocusPolicy(Qt.NoFocus)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.clicked.connect(self._on_clicked)
        self.tree._on_pdf_click = self._export_group_pdf

        self.tree.setStyleSheet(f"""
            QTreeView#journalTree {{
                background: {cfg.BG_APP};
                border: 1px solid {cfg.BORDER};
                border-radius: 12px;
                color: {cfg.TEXT_PRIMARY};
                font-family: 'Geist';
                font-size: 12px;
                outline: none;
                padding: 6px;
                selection-background-color: transparent;
                selection-color: {cfg.TEXT_PRIMARY};
            }}
            QTreeView#journalTree::item {{
                padding: 8px 4px;
                border: none;
            }}
            QTreeView#journalTree::item:hover {{
                background: transparent;
            }}
            QTreeView#journalTree::item:selected {{
                background: transparent;
                color: {cfg.TEXT_PRIMARY};
            }}
            QTreeView#journalTree::branch {{
                background: transparent;
                border: none;
                image: none;
                border-image: none;
            }}
            QTreeView#journalTree::branch:hover,
            QTreeView#journalTree::branch:selected {{
                background: transparent;
            }}
            QHeaderView {{
                background: {cfg.BG_APP};
            }}
            QHeaderView::section {{
                background: {cfg.BG_APP};
                color: {cfg.TEXT_MUTED};
                border: none;
                border-bottom: 1px solid {cfg.BORDER};
                padding: 10px 12px;
                font-family: 'Geist';
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
            }}
            QTreeView#journalTree QScrollBar:vertical {{
                background: transparent; width: 12px;
                margin: 0; border: none; padding: 2px;
            }}
            QTreeView#journalTree QScrollBar::handle:vertical {{
                background: {cfg.BORDER}; border-radius: 4px; min-height: 30px;
            }}
            QTreeView#journalTree QScrollBar::handle:vertical:hover {{
                background: {cfg.BORDER_HOVER};
            }}
            QTreeView#journalTree QScrollBar::add-line:vertical,
            QTreeView#journalTree QScrollBar::sub-line:vertical {{
                height: 0; background: transparent; border: none;
            }}
            QTreeView#journalTree QScrollBar::add-page:vertical,
            QTreeView#journalTree QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(COLUMNS)
        self.tree.setModel(self.model)
        self.tree.setItemDelegate(ParentRowDelegate(self.tree))

        hdr = self.tree.header()
        hdr.hide()
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setSectionResizeMode(COL_NUM, QHeaderView.Fixed)
        hdr.resizeSection(COL_NUM, 70)
        hdr.setSectionResizeMode(COL_SRC, QHeaderView.Interactive)
        hdr.resizeSection(COL_SRC, 180)
        hdr.setSectionResizeMode(COL_BREACH, QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_REC, QHeaderView.Interactive)
        hdr.resizeSection(COL_REC, 280)
        hdr.setSectionResizeMode(COL_DATE, QHeaderView.Interactive)
        hdr.resizeSection(COL_DATE, 140)
        hdr.setStretchLastSection(False)

        outer.addWidget(self.tree, 1)

        self.empty_lbl = QLabel("Нет записей — запустите сканирование", self)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED};"
            f"font-size:14px; background:transparent;"
        )
        outer.addWidget(self.empty_lbl, 1)

        self.load_from_db()

    def load_from_db(self):
        # Старить ДО чтения, иначе строки рендерятся со «свежим» is_new,
        # а UPDATE в БД случается слишком поздно — UI показывает неправду.
        self.db.age_old_results(seconds=cfg.NEW_AGING_SECONDS)

        self.model.removeRows(0, self.model.rowCount())
        results = self.db.get_all_results()

        if not results:
            self.tree.hide()
            self.empty_lbl.show()
            return
        self.empty_lbl.hide()
        self.tree.show()

        # Группировка по target
        grouped: "OrderedDict[str, list]" = OrderedDict()
        for row in results:
            _, target, source, breach_name, detail, url, scanned_at, is_new = row
            grouped.setdefault(target, []).append(
                (source, breach_name or detail or "—", url or "",
                 scanned_at, bool(is_new))
            )

        # Свежесть parent-строки определяем по времени scanned_at:
        # «совсем свежие» (≤ NEW_AGING_PARENT_SECONDS) — красная заливка и
        # плашка «NEW». Дочерние источники остаются красными ещё на
        # NEW_AGING_SECONDS, чтобы внутри карточки видно было что нашлось.
        parent_cutoff = (
            datetime.datetime.now()
            - datetime.timedelta(seconds=cfg.NEW_AGING_PARENT_SECONDS)
        )
        has_new_any = False
        for target, items in grouped.items():
            has_new = False
            for _src, _name, _url, scanned_at, _isnew in items:
                try:
                    ts = datetime.datetime.strptime(
                        scanned_at, "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    continue
                if ts >= parent_cutoff:
                    has_new = True
                    break
            has_new_any = has_new_any or has_new
            self._add_group(target, items, has_new)

        # Parent-строки растягиваем на всю ширину. Группы оставляем СВЁРНУТЫМИ —
        # пользователь сам решит какую развернуть. Раньше авто-открытие шумело,
        # когда было много адресов с новыми утечками.
        for r in range(self.model.rowCount()):
            self.tree.setFirstColumnSpanned(r, QModelIndex(), True)
        # Принудительная перерисовка вьюпорта — иначе после _scan_done иногда
        # требуется переключение вкладки чтобы увидеть новые строки.
        self.tree.viewport().update()

    def _add_group(self, target: str, items: list, has_new: bool):
        from ui.qt_icons import detect_kind
        ic = detect_kind(target)

        count = len(items)

        parent_item = QStandardItem(target)
        parent_item.setData(has_new, Qt.UserRole)
        parent_item.setData(target, ROLE_TARGET)
        parent_item.setData(True, Qt.UserRole + 3)  # marker: parent row
        parent_item.setData(count, ROLE_COUNT)
        parent_item.setData(ic, ROLE_ICON)
        parent_item.setEditable(False)
        parent_item.setSizeHint(QSize(0, 46))

        row_items = [parent_item]
        for col in range(1, len(COLUMNS)):
            it = QStandardItem("")
            it.setEditable(False)
            it.setData(True, Qt.UserRole + 3)
            row_items.append(it)

        self.model.appendRow(row_items)

        self._add_header_row(parent_item)
        for n, (source, breach_name, url, scanned_at, is_new) in enumerate(items, 1):
            self._add_child(parent_item, n, source, breach_name, url,
                            scanned_at, is_new)

    def _add_header_row(self, parent_item: QStandardItem):
        headers = ["#", "Источник", "Название утечки", "Рекомендация", "Дата"]
        row = []
        hfont = QFont(cfg.QT_FONT_FAMILY if hasattr(cfg, 'QT_FONT_FAMILY') else "Geist")
        hfont.setPixelSize(11)
        hfont.setWeight(QFont.DemiBold)
        for txt in headers:
            it = QStandardItem(txt)
            it.setEditable(False)
            it.setSelectable(False)
            it.setFont(hfont)
            it.setForeground(QBrush(QColor(cfg.TEXT_MUTED)))
            it.setBackground(QBrush(QColor(cfg.BG_APP)))
            it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            row.append(it)
        parent_item.appendRow(row)

    def _add_child(self, parent_item: QStandardItem, n: int,
                   source: str, breach_name: str, url: str,
                   scanned_at: str, is_new: bool):
        num = QStandardItem(str(n))
        num.setEditable(False)
        num.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        num.setForeground(QBrush(QColor(cfg.TEXT_SECONDARY)))

        src = QStandardItem(source)
        src.setEditable(False)
        src.setData(url, ROLE_URL)
        src.setForeground(QBrush(QColor(
            cfg.TEXT_LINK if url else cfg.ACCENT_TEXT)))
        if url:
            src.setToolTip(f"Открыть: {url}")

        breach = QStandardItem(breach_name)
        breach.setEditable(False)
        # Красный — только для is_new (последние 2 дня), легенда «● Новые».
        # _is_danger даёт лишь жирный шрифт (визуальный акцент без конфликта
        # с семантикой «новый» в легенде).
        breach.setForeground(QBrush(QColor(
            cfg.DANGER_COLOR if is_new else cfg.TEXT_PRIMARY)))
        bf = QFont(cfg.QT_FONT_FAMILY if hasattr(cfg, 'QT_FONT_FAMILY') else "Geist")
        bf.setPixelSize(13)
        bf.setWeight(QFont.Bold if _is_danger(breach_name) else QFont.DemiBold)
        breach.setFont(bf)
        breach.setToolTip(breach_name)

        rec = QStandardItem(_rec(source))
        rec.setEditable(False)
        rec.setForeground(QBrush(QColor(cfg.TEXT_SECONDARY)))

        # Журнал хранит ISO ("YYYY-MM-DD HH:MM:SS") — для UI переводим в DD.MM.YYYY.
        iso = (scanned_at or "")[:10]
        try:
            y, m, d = iso.split("-")
            date_str = f"{d}.{m}.{y}"
        except Exception:
            date_str = iso
        date = QStandardItem(date_str)
        date.setEditable(False)
        date.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        date.setForeground(QBrush(QColor(cfg.TEXT_MUTED)))

        row = [num, src, breach, rec, date]
        if is_new:
            for it in row:
                it.setBackground(QBrush(QColor(cfg.DANGER_BG)))

        parent_item.appendRow(row)

    def _on_clicked(self, idx: QModelIndex):
        # Клик по parent-строке → раскрыть/свернуть группу одним нажатием
        if idx.data(Qt.UserRole + 3):
            root = idx.sibling(idx.row(), 0)
            if self.tree.isExpanded(root):
                self.tree.collapse(root)
            else:
                self.tree.expand(root)
            return
        # Клик по source-ячейке с URL → открываем браузер
        if idx.column() != COL_SRC:
            return
        url = idx.data(ROLE_URL)
        if url:
            try:
                webbrowser.open_new_tab(url)
            except Exception:
                pass

    def _export_group_pdf(self, target: str):
        if self._on_export_pdf_for:
            self._on_export_pdf_for(target)

    def _expand_all(self):
        self._animate_toggle(expand=True)

    def _collapse_all(self):
        self._animate_toggle(expand=False)

    def _animate_toggle(self, expand: bool):
        # Раскрываем/сворачиваем группы по очереди с небольшой задержкой —
        # встроенная анимация QTreeView при bulk-expand выглядит рывками,
        # а каскад делает переход плавным.
        rows = [self.model.index(r, 0) for r in range(self.model.rowCount())]
        if not expand:
            rows = list(reversed(rows))
        step = 120 if expand else 50  # мс между соседними группами
        for i, idx in enumerate(rows):
            QTimer.singleShot(
                i * step,
                (lambda ix=idx: self.tree.expand(ix)) if expand
                else (lambda ix=idx: self.tree.collapse(ix)))

    def _export_all(self):
        if self._on_export_pdf:
            self._on_export_pdf()

    def _clear(self):
        box = QMessageBox(self)
        box.setWindowTitle("Очистить журнал")
        box.setText("Удалить все записи из журнала?")
        box.setIcon(QMessageBox.Question)
        # Кастомные кнопки на русском (Qt по умолчанию ставит Yes/No на языке ОС).
        yes_btn = box.addButton("Да", QMessageBox.YesRole)
        no_btn = box.addButton("Нет", QMessageBox.NoRole)
        box.setDefaultButton(no_btn)
        box.exec()
        if box.clickedButton() is not yes_btn:
            return
        self.db.clear_results()
        self.model.removeRows(0, self.model.rowCount())
        self.tree.hide()
        self.empty_lbl.show()
        if self._on_cleared:
            self._on_cleared()
