"""Экспорт отчётов в PDF (ReportLab) с автоопределением кириллического шрифта."""

import os, re, sys, datetime, webbrowser
from xml.sax.saxutils import escape as _xml_escape

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

def _safe_para(text, style):
    """Paragraph с экранированием — иначе ReportLab парсит мини-HTML
    (`<b>`, `<font>`, `<onDraw>`) во внешних данных (имена брешей, email)."""
    return Paragraph(_xml_escape(str(text)), style)

def get_app_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _register_cyrillic_font() -> str:
    """
    Регистрирует TTF-шрифт с поддержкой кириллицы в ReportLab.
    Возвращает имя зарегистрированного шрифта.
    """
    font_name = "CyrillicFont"

    # 1. Arial — стандартный шрифт Windows
    arial_paths = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        "/Library/Fonts/Arial.ttf",           # macOS
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",  # Linux
    ]
    for path in arial_paths:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont(font_name, path))
            return font_name

    # 2. DejaVuSans — берём из matplotlib (он почти всегда установлен)
    try:
        import matplotlib
        mpl_data = matplotlib.get_data_path()
        dejavu   = os.path.join(mpl_data, "fonts", "ttf", "DejaVuSans.ttf")
        if os.path.exists(dejavu):
            pdfmetrics.registerFont(TTFont(font_name, dejavu))
            return font_name
    except Exception:
        pass

    # 3. Ищем любой TTF с поддержкой кириллицы в системных папках
    search_dirs = [
        r"C:\Windows\Fonts",
        "/usr/share/fonts/truetype",
        "/usr/share/fonts",
        os.path.join(get_app_path(), "fonts"),
    ]
    cyrillic_fonts = ["arial.ttf", "verdana.ttf", "tahoma.ttf",
                      "DejaVuSans.ttf", "FreeSans.ttf", "LiberationSans-Regular.ttf"]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if fname.lower() in [f.lower() for f in cyrillic_fonts]:
                full = os.path.join(d, fname)
                try:
                    pdfmetrics.registerFont(TTFont(font_name, full))
                    return font_name
                except Exception:
                    continue

    # Fallback — Helvetica (кириллицы нет, но хоть не упадёт)
    return "Helvetica"

def export_pdf_report(db, engine_cls, log_fn=None) -> bool:
    """
    Генерирует PDF-отчёт об утечках.
    db         — экземпляр DBManager
    engine_cls — класс LeakEngine (для calculate_risk_score)
    log_fn     — функция логирования (опционально)
    Возвращает True при успехе.
    """
    if not REPORTLAB_OK:
        if log_fn: log_fn("Установите reportlab: pip install reportlab")
        return False

    results = db.get_all_results()
    if not results:
        if log_fn: log_fn("Нет данных для экспорта.")
        return False

    font = _register_cyrillic_font()
    font_bold = font  # для bold используем тот же шрифт (TTF bold отдельно не нужен)

    reports_dir = os.path.join(get_app_path(), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    path = os.path.join(
        reports_dir,
        f"report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm
    )

    normal  = ParagraphStyle("normal_cyr",  fontName=font,      fontSize=10, leading=14)
    heading = ParagraphStyle("heading_cyr", fontName=font,      fontSize=14, leading=18, spaceAfter=6)
    title_s = ParagraphStyle("title_cyr",   fontName=font,      fontSize=18, leading=22, spaceAfter=10)
    small_s = ParagraphStyle("small_cyr",   fontName=font,      fontSize=8,  leading=11)

    story = []

    # Заголовок
    story.append(Paragraph("Data Leak Sentinel — Отчёт об утечках", title_s))
    story.append(Paragraph(
        f"Сгенерирован: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}",
        normal))
    story.append(Spacer(1, 0.5*cm))

    # Risk Score
    srcs = [r[2] for r in results]
    score, level, _ = engine_cls.calculate_risk_score(srcs)
    story.append(Paragraph(f"Уровень угрозы: {level} ({score}/100)", heading))
    story.append(Paragraph(f"Всего записей в журнале: {len(results)}", normal))
    story.append(Spacer(1, 0.5*cm))

    # Разбивка по источникам
    from collections import Counter
    src_counts = Counter(r[2] for r in results)
    src_text   = "  |  ".join(f"{k}: {v}" for k, v in src_counts.most_common())
    story.append(_safe_para(f"Источники: {src_text}", small_s))
    story.append(Spacer(1, 0.4*cm))

    # Таблица утечек
    col_widths = [0.8*cm, 4*cm, 3.5*cm, 5*cm, 2.7*cm]
    header     = ["#", "Объект", "Источник", "Утечка / Детали", "Дата"]

    def wrap(text, limit=35):
        """Обрезает длинный текст для ячейки таблицы."""
        return text[:limit] + "…" if len(text) > limit else text

    rows = [header]
    for i, row in enumerate(results, 1):
        _, target, source, breach_name, detail, url, scanned_at, is_new = row
        cell_text = breach_name or detail or "—"
        rows.append([
            str(i),
            wrap(target, 28),
            wrap(source, 22),
            wrap(cell_text, 35),
            scanned_at[:10]
        ])

    # Создаём ячейки как Paragraph для корректного переноса кириллицы
    cell_style = ParagraphStyle("cell", fontName=font, fontSize=8, leading=11)
    hdr_style  = ParagraphStyle("hdr",  fontName=font, fontSize=9, leading=12,
                                 textColor=colors.white)

    para_rows = []
    for r_idx, row in enumerate(rows):
        if r_idx == 0:
            para_rows.append([_safe_para(cell, hdr_style) for cell in row])
        else:
            para_rows.append([_safe_para(cell, cell_style) for cell in row])

    table = Table(para_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # Заголовок
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1e3a6e")),
        ("TOPPADDING",    (0, 0), (-1, 0),  6),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
        # Строки
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),
         [colors.HexColor("#f8f8f8"), colors.HexColor("#eef2f8")]),
        ("TEXTCOLOR",     (0, 1), (-1, -1), colors.HexColor("#222222")),
        ("TOPPADDING",    (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        # Сетка
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # Колонка # — по центру
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.6*cm))

    # Рекомендации
    story.append(Paragraph("Рекомендации:", heading))
    recs = [
        "• Немедленно смените пароли на всех сервисах, упомянутых в отчёте.",
        "• Включите двухфакторную аутентификацию (2FA) на всех важных аккаунтах.",
        "• Если email найден в stealer-логах — проверьте устройство на вирусы.",
        "• Используйте уникальный пароль для каждого сервиса.",
        "• Регулярно проверяйте свои данные в базах утечек.",
    ]
    for rec in recs:
        story.append(Paragraph(rec, normal))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"Отчёт сгенерирован автоматически системой Data Leak Sentinel · "
        f"{datetime.datetime.now().strftime('%d.%m.%Y')}",
        ParagraphStyle("footer", fontName=font, fontSize=8,
                       textColor=colors.HexColor("#888888"))))

    doc.build(story)
    if log_fn: log_fn(f"PDF сохранён: {path}")
    webbrowser.open(path)
    return True

def export_pdf_for_target(db, engine_cls, target_email: str, log_fn=None) -> bool:
    """PDF только для одного email."""
    if not REPORTLAB_OK:
        if log_fn: log_fn("Установите reportlab: pip install reportlab")
        return False

    all_results = db.get_all_results()
    results = [r for r in all_results if r[1] == target_email]

    if not results:
        if log_fn: log_fn(f"Нет данных для {target_email}")
        return False

    font = _register_cyrillic_font()

    reports_dir = os.path.join(get_app_path(), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    # Жёсткая фильтрация: только alphanumeric/underscore/dash. Email с
    # path-разделителями (a/../b@x.com) или whitespace больше не пролезет.
    safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', target_email)[:80] or "target"
    path = os.path.join(
        reports_dir,
        f"report_{safe_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    normal  = ParagraphStyle("normal_cyr",  fontName=font, fontSize=10, leading=14)
    heading = ParagraphStyle("heading_cyr", fontName=font, fontSize=14, leading=18, spaceAfter=6)
    title_s = ParagraphStyle("title_cyr",   fontName=font, fontSize=18, leading=22, spaceAfter=10)
    small_s = ParagraphStyle("small_cyr",   fontName=font, fontSize=8,  leading=11)

    story = []

    story.append(Paragraph("DataSentinel — Отчёт об утечках", title_s))
    story.append(_safe_para(f"Объект: {target_email}", heading))
    story.append(Paragraph(
        f"Сгенерирован: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}",
        normal))
    story.append(Spacer(1, 0.5*cm))

    srcs = [r[2] for r in results]
    score, level, _ = engine_cls.calculate_risk_score(srcs)
    story.append(Paragraph(f"Уровень угрозы: {level} ({score}/100)", heading))
    story.append(Paragraph(f"Найдено утечек: {len(results)}", normal))
    story.append(Spacer(1, 0.5*cm))

    from collections import Counter
    src_counts = Counter(r[2] for r in results)
    src_text = "  |  ".join(f"{k}: {v}" for k, v in src_counts.most_common())
    story.append(_safe_para(f"Источники: {src_text}", small_s))
    story.append(Spacer(1, 0.4*cm))

    col_widths = [0.8*cm, 4*cm, 5.5*cm, 2.7*cm]
    header = ["#", "Источник", "Утечка / Детали", "Дата"]

    def wrap(text, limit=40):
        return text[:limit] + "…" if len(text) > limit else text

    rows = [header]
    for i, row in enumerate(results, 1):
        _, target, source, breach_name, detail, url, scanned_at, is_new = row
        cell_text = breach_name or detail or "—"
        rows.append([str(i), wrap(source, 22), wrap(cell_text, 40), scanned_at[:10]])

    cell_style = ParagraphStyle("cell", fontName=font, fontSize=8, leading=11)
    hdr_style  = ParagraphStyle("hdr",  fontName=font, fontSize=9, leading=12,
                                 textColor=colors.white)
    para_rows = []
    for r_idx, row in enumerate(rows):
        if r_idx == 0:
            para_rows.append([_safe_para(cell, hdr_style) for cell in row])
        else:
            para_rows.append([_safe_para(cell, cell_style) for cell in row])

    table = Table(para_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1e3a6e")),
        ("TOPPADDING",    (0, 0), (-1, 0),  6),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),
         [colors.HexColor("#f8f8f8"), colors.HexColor("#eef2f8")]),
        ("TEXTCOLOR",     (0, 1), (-1, -1), colors.HexColor("#222222")),
        ("TOPPADDING",    (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.6*cm))

    story.append(Paragraph("Рекомендации:", heading))
    for rec in [
        "• Немедленно смените пароли на всех сервисах из отчёта.",
        "• Включите двухфакторную аутентификацию (2FA).",
        "• Если email в stealer-логах — проверьте устройство на вирусы.",
        "• Используйте уникальный пароль для каждого сервиса.",
    ]:
        story.append(Paragraph(rec, normal))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"DataSentinel · {datetime.datetime.now().strftime('%d.%m.%Y')}",
        ParagraphStyle("footer", fontName=font, fontSize=8,
                       textColor=colors.HexColor("#888888"))))

    doc.build(story)
    if log_fn: log_fn(f"PDF для {target_email} сохранён: {path}")
    webbrowser.open(path)
    return True
