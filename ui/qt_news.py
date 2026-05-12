"""Страница «Новости»: RU/EN ленты RSS, in-app reader, кэш в SQLite."""
from __future__ import annotations

import datetime
import hashlib
import ipaddress
import os
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Optional
from urllib.parse import urlparse

from PySide6.QtCore import (
    Qt, QObject, QThread, Signal, QTimer, QSize, QUrl,
    QAbstractListModel, QModelIndex, QSortFilterProxyModel, QRect, QRectF,
)
from PySide6.QtGui import (
    QPixmap, QDesktopServices, QPainter, QColor, QBrush, QPen, QPainterPath,
    QFont,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QStackedWidget, QSizePolicy, QButtonGroup, QTextBrowser,
    QListView, QStyledItemDelegate, QStyle, QStackedLayout,
)

import core.config as cfg
from core.engine import LeakEngine

SOURCES = {
    # Третий элемент tuple — флаг «применять keyword-фильтр». True ставим
    # для общетехнических лент (OpenNet, Habr News) — там много нерелевантного
    # (релизы редакторов, AI-новости, бизнес). Без флага — фид считается
    # тематическим и проходит как есть.
    "ru": [
        ("Habr · Информационная безопасность",
         "https://habr.com/ru/rss/hub/infosecurity/all/?fl=ru", False),
        ("Хакер (xakep.ru)",
         "https://xakep.ru/feed/", False),
        ("Kaspersky Daily",
         "https://www.kaspersky.ru/blog/feed/", False),
        ("Roskomsvoboda",
         "https://roskomsvoboda.org/feed/", False),
        # OpenNet: IT+security, нужно фильтровать чтобы убрать релизы Linux-софта.
        ("OpenNet",
         "https://www.opennet.ru/opennews/opennews_all_utf.rss", True),
        # Habr News: общая лента, отфильтровываем не-security.
        ("Habr · Новости",
         "https://habr.com/ru/rss/news/?fl=ru", True),
    ],
    "en": [
        ("BleepingComputer",
         "https://www.bleepingcomputer.com/feed/", False),
        ("The Hacker News",
         "https://feeds.feedburner.com/TheHackersNews", False),
        ("Krebs on Security",
         "https://krebsonsecurity.com/feed/", False),
        ("DarkReading",
         "https://www.darkreading.com/rss.xml", False),
        ("SecurityWeek",
         "https://www.securityweek.com/feed/", False),
        ("Schneier on Security",
         "https://www.schneier.com/feed/atom/", False),
    ],
}

# Авто-обновление лент: 30 минут.
AUTO_REFRESH_MS = 30 * 60 * 1000

# Категории фильтра — keyword-фильтр по заголовку и excerpt'у. Регистр
# игнорируется. None в keys = «Все».
CATEGORIES = [
    ("all", "Все", None),
    # Замечание про keywords: длинные/уникальные подстроки. Короткие
    # 3-буквенные (rce) или общие слова с пробелом (hack ) дают много
    # false positives (NetHack, Source, force, recipe и т.п.). Поэтому
    # rce, hack, ddos — НЕ в списке; вместо них берём длинные синонимы.
    ("breach", "Утечки",
     ("утечк", "утеч", "слив", "база данных", "дамп", "украл", "украд",
      "взлом", "взлома", "скомпром",
      "leak", "breach", "exposed", "data dump", "credential", "stolen",
      "compromised", "compromise", "hacked")),
    ("cve", "Уязвимости",
     ("уязвим", "эксплойт", "эксплуатац", "патч", "обновление безопасн",
      "бэкдор", "буфер",
      "cve-", "vulnerab", "exploit", "zero-day", "0-day",
      "patched", "advisory", "security update", "backdoor")),
    ("malware", "Малварь",
     ("малвар", "вирус", "троян", "стилер", "вредонос", "шифровальщик",
      "инфостилер", "ботнет", "rootkit",
      "ransomware", "trojan", "malware", "spyware", "infostealer",
      "botnet", "stealer", "miner ")),
    ("privacy", "Приватность",
     ("приватн", "персональн", "слежк", "роскомнадзор", "цензур",
      "блокиров", "анонимн", "конфиденциальн", "vpn", "шифрован",
      "deанонимиз", "доксин",
      "privacy", "tracking", "surveillance", "gdpr", "cookie", "doxxing",
      "anonymity", "encryption", "censorship")),
]

# Объединяем keywords всех CATEGORIES (кроме "all") + общие security-термины.
# Используем для фильтрации общетехнических лент: пропускаем item только если
# его title или excerpt содержит хотя бы один из этих токенов.
_RELEVANCE_KW: tuple = tuple({
    kw
    for _id, _label, kws in CATEGORIES
    if kws
    for kw in kws
} | {
    # Дополнительные общие термины: атаки, апдейты безопасности, шифрование,
    # авторизация. То, чего нет в категориях, но это явный security-контент.
    "хак", "атак", "взлом", "фишинг", "пароль", "шифрован", "защит",
    "роскомнадзор", "блокиров", "цензур",
    "hack", "attack", "phishing", "password", "encryption", "ransomware",
    "infosec", "cyber", "security update", "patch", "advisory", "cisa",
    "ddos", "botnet", "malicious", "compromise",
})

def _is_security_relevant(item: dict) -> bool:
    """Проверяет наличие security-ключевого слова в title или excerpt.
    Регистр игнорируется."""
    text = ((item.get("title") or "") + " " + (item.get("excerpt") or "")).lower()
    return any(kw in text for kw in _RELEVANCE_KW)

NAMESPACES = {
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Браузерный UA — без него многие сайты (Cloudflare, BleepingComputer,
# DarkReading, SecurityLab) возвращают 403 / страницу-капчу вместо XML.
def _news_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, "
                  "application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }

def _cache_dir() -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.abspath(__file__))
    p = os.path.join(base, "data", "news_cache")
    os.makedirs(p, exist_ok=True)
    return p

def _resolve_image_path(path: str) -> str:
    """Если сохранённый в БД абсолютный image_path не находится (например,
    юзер переименовал папку приложения), пытаемся найти файл по basename
    в текущем _cache_dir(). Возвращает рабочий путь или ''. """
    if not path:
        return ""
    if os.path.exists(path):
        return path
    try:
        candidate = os.path.join(_cache_dir(), os.path.basename(path))
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return ""

def _format_relative_date(d: datetime.datetime) -> str:
    """Дату публикации показываем относительно текущего времени:
    «N мин назад», «сегодня в HH:MM», «вчера в HH:MM», иначе обычная дата.
    Если статья «в будущем» (RSS отдала будущий timestamp, мы клампим в БД,
    но на всякий случай) — показываем «только что»."""
    now = datetime.datetime.now()
    delta = now - d
    secs = delta.total_seconds()
    if secs < 60:
        return "только что"
    if secs < 3600:
        m = int(secs // 60)
        return f"{m} мин назад"
    if d.date() == now.date():
        return f"сегодня в {d.strftime('%H:%M')}"
    yesterday = (now - datetime.timedelta(days=1)).date()
    if d.date() == yesterday:
        return f"вчера в {d.strftime('%H:%M')}"
    return d.strftime("%d.%m.%Y %H:%M")

_TAG_RE = re.compile(r"<[^>]+>")
_IMG_TAG_RE = re.compile(r'<img\b([^>]*)>', re.IGNORECASE)
# Lazy-load атрибуты приоритетнее src — в них реальный URL картинки.
_IMG_ATTRS = ("data-src", "data-original", "data-lazy-src", "data-lazyload",
              "data-actualsrc", "src")

def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = unescape(s)
    s = _TAG_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _extract_img_from_html(html: str) -> Optional[str]:
    """Ищет первую <img> с пригодным URL. Понимает lazy-loading: BleepingComputer,
    The Hacker News и многие другие держат реальный URL в data-src, а в src
    лежит base64-плейсхолдер."""
    if not html:
        return None
    for m in _IMG_TAG_RE.finditer(html):
        attrs = m.group(1) or ""
        for attr in _IMG_ATTRS:
            am = re.search(
                rf'\b{attr}\s*=\s*["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if not am:
                continue
            url = (am.group(1) or "").strip()
            if (not url or url.startswith("data:")
                    or "placeholder" in url.lower()
                    or url.endswith(".svg")):
                continue
            return url
    return None

def _extract_image(item: ET.Element, description: str) -> Optional[str]:
    # 1) <enclosure type="image/*" url="..."/>
    enc = item.find("enclosure")
    if enc is not None:
        if (enc.get("type") or "").startswith("image"):
            url = enc.get("url")
            if url:
                return url
    # 2) <media:content url="..." medium="image"/>
    for mc in item.findall("media:content", NAMESPACES):
        url = mc.get("url")
        if url and (mc.get("medium") == "image"
                    or (mc.get("type") or "").startswith("image")):
            return url
    # 3) <media:thumbnail url="..."/>
    mt = item.find("media:thumbnail", NAMESPACES)
    if mt is not None and mt.get("url"):
        return mt.get("url")
    # 4) <img> в description / content:encoded — с поддержкой lazy-load
    return _extract_img_from_html(description)

def _parse_pubdate(s: str) -> Optional[datetime.datetime]:
    """Парсит RFC 2822 / ISO. Возвращает naive UTC datetime — иначе при
    сортировке Python ругается на mix offset-aware / offset-naive."""
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is not None:
            d = d.astimezone(tz=datetime.timezone.utc).replace(tzinfo=None)
        return d
    except Exception:
        return None

def _parse_feed(xml_bytes, source_name: str) -> list[dict]:
    """Универсальный парсер RSS 2.0 и Atom. Принимает bytes (xml.etree
    сам разбирается с encoding из <?xml encoding="..."?>). Возвращает
    [{title, link, source, date, excerpt, full_html, image}]."""
    out: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"[news] parse error: {e}", flush=True)
        return out
    tag = root.tag.lower()
    if tag.endswith("}feed") or tag == "feed":
        return _parse_atom(root, source_name)
    # RSS 2.0
    channel = root.find("channel") or root
    for item in channel.findall("item"):
        title = _strip_html((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        if not (title and link):
            continue
        pub = _parse_pubdate(item.findtext("pubDate") or "")
        if pub is None:
            # dc:date как fallback (часто у RSS 1.0-подобных)
            pub = _parse_pubdate(
                item.findtext("dc:date", default="", namespaces=NAMESPACES))
        desc_raw = (item.findtext("description") or "")
        # content:encoded — полный HTML статьи (лучше и для картинок,
        # и для in-app читалки)
        ce = item.find("content:encoded", NAMESPACES)
        full_html = ce.text if (ce is not None and ce.text) else desc_raw
        excerpt = _strip_html(desc_raw or full_html)[:240]
        image = _extract_image(item, full_html or desc_raw)
        out.append({
            "title": title, "link": link, "source": source_name,
            "date": pub, "excerpt": excerpt,
            "full_html": full_html, "image": image,
        })
    return out

def _parse_atom(root: ET.Element, source_name: str) -> list[dict]:
    """Atom-фид: <feed><entry>… The Hacker News (через feedburner)
    отдаётся именно так."""
    out: list[dict] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        title = _strip_html(
            (entry.findtext(f"{ATOM_NS}title") or "").strip())
        # <link rel="alternate" href="..."/> — выбираем первую alternate.
        # rel="enclosure" ловим отдельно для картинок ниже.
        link = ""
        enclosure_img = None
        for l in entry.findall(f"{ATOM_NS}link"):
            href = l.get("href") or ""
            rel = l.get("rel") or "alternate"
            ltype = l.get("type") or ""
            if rel == "enclosure" and ltype.startswith("image"):
                enclosure_img = enclosure_img or href
            elif href and rel == "alternate" and not link:
                link = href
        if not link:
            link = (entry.findtext(f"{ATOM_NS}id") or "").strip()
        if not (title and link):
            continue
        # Atom — ISO 8601: 2026-05-08T12:34:56Z
        date_iso = (entry.findtext(f"{ATOM_NS}published")
                    or entry.findtext(f"{ATOM_NS}updated") or "").strip()
        pub = None
        if date_iso:
            try:
                pub = datetime.datetime.fromisoformat(
                    date_iso.replace("Z", "+00:00"))
                # Нормализуем к naive UTC — иначе сортировка падает на
                # mix offset-aware / naive datetime'ах.
                if pub.tzinfo is not None:
                    pub = pub.astimezone(
                        tz=datetime.timezone.utc).replace(tzinfo=None)
            except Exception:
                pub = None
        # content (полный HTML) или summary
        ce = entry.find(f"{ATOM_NS}content")
        sm = entry.find(f"{ATOM_NS}summary")
        full_html = ""
        if ce is not None:
            full_html = "".join(ce.itertext()) or (ce.text or "")
        if not full_html and sm is not None:
            full_html = "".join(sm.itertext()) or (sm.text or "")
        excerpt = _strip_html(full_html)[:240]
        # Картинка: enclosure → media:content → media:thumbnail → <img> в content.
        image = enclosure_img
        if not image:
            for mc in entry.findall("media:content", NAMESPACES):
                url = mc.get("url")
                if url and (mc.get("medium") == "image"
                            or (mc.get("type") or "").startswith("image")):
                    image = url
                    break
        if not image:
            mt = entry.find("media:thumbnail", NAMESPACES)
            if mt is not None and mt.get("url"):
                image = mt.get("url")
        if not image:
            image = _extract_img_from_html(full_html)
        out.append({
            "title": title, "link": link, "source": source_name,
            "date": pub, "excerpt": excerpt,
            "full_html": full_html, "image": image,
        })
    return out

class NewsWorker(QObject):
    """Грузит RSS + картинки. Эмитит done(lang, items, new_count).
    Сохраняет в БД-кэш."""
    done = Signal(str, list, int)

    def __init__(self, lang: str, db=None):
        super().__init__()
        self.lang = lang
        self.db = db

    def run(self):
        items: list[dict] = []
        # Балансировка: берём не больше 15 свежих с каждого источника,
        # чтобы Habr с его 40 items не вытеснял всех остальных.
        PER_SOURCE_LIMIT = 15
        for entry in SOURCES.get(self.lang, []):
            # Поддерживаем и 2-tuple (legacy), и 3-tuple (с флагом фильтра).
            if len(entry) == 3:
                name, url, needs_filter = entry
            else:
                name, url = entry
                needs_filter = False
            count = 0
            dropped = 0
            try:
                res = LeakEngine.session.get(
                    url, headers=_news_headers(), timeout=15)
                if res.status_code != 200:
                    print(f"[news] {name}: HTTP {res.status_code}", flush=True)
                    continue
                # Передаём bytes, чтобы xml.etree сам обработал encoding
                # из XML-декларации (важно для cp1251 у некоторых RU-сайтов).
                parsed = _parse_feed(res.content, name)
                # Внутри одного источника RSS уже отсортирован по свежести,
                # но на всякий случай сортируем сами.
                parsed.sort(
                    key=lambda it: it.get("date") or datetime.datetime.min,
                    reverse=True)
                if needs_filter:
                    # Для общетехнических лент: отбрасываем item'ы без
                    # security-keyword в title/excerpt. Лимит применяем
                    # уже после фильтрации, чтобы 15 релевантных, а не
                    # 15 любых из которых половина — не по теме.
                    before = len(parsed)
                    parsed = [it for it in parsed if _is_security_relevant(it)]
                    dropped = before - len(parsed)
                parsed = parsed[:PER_SOURCE_LIMIT]
                count = len(parsed)
                items.extend(parsed)
            except Exception as e:
                print(f"[news] {name} fetch failed: {e}", flush=True)
            note = f" (отфильтровано {dropped})" if dropped else ""
            print(f"[news] {name}: {count} items{note}", flush=True)
        # Глобальная сортировка по дате, итого до 50 свежих со всех источников
        items.sort(key=lambda it: it.get("date") or datetime.datetime.min,
                   reverse=True)
        items = items[:50]
        # Качаем картинки. Для статей без image из RSS — пробуем
        # вытянуть og:image со страницы статьи (медленнее, но даёт картинки
        # для BleepingComputer / THN / Schneier, которые в RSS их не кладут).
        with_image = 0
        og_recovered = 0
        for it in items:
            url = it.get("image")
            link = it.get("link") or ""
            if not url:
                # OG fallback — отдельный HTTP-запрос на саму статью.
                og_url = _fetch_og_image(link)
                if og_url:
                    url = og_url
                    it["image"] = og_url
                    og_recovered += 1
            if url:
                it["image_path"] = _download_image(url, referer=link)
                if it.get("image_path"):
                    with_image += 1
        print(f"[news] {self.lang}: {with_image}/{len(items)} with images "
              f"({og_recovered} via og:image fallback)", flush=True)
        # Сохраняем в кэш — потокобезопасно (sqlite3 с check_same_thread=False).
        new_count = 0
        if self.db is not None and items:
            try:
                new_count = self.db.cache_news_items(self.lang, items) or 0
            except Exception as e:
                print(f"[news] cache write failed: {e}", flush=True)
        print(f"[news] {self.lang} TOTAL: {len(items)} items "
              f"({new_count} new)", flush=True)
        self.done.emit(self.lang, items, new_count)

# Защита от SSRF: блокируем запросы по http(s) к private/loopback/link-local
# адресам. RSS-фид может (в т.ч. при компрометации источника) подсунуть URL
# вида http://169.254.169.254/... (cloud metadata), http://localhost:5432
# (внутренний сервис) и т.п. Резолвим один раз при старте запроса —
# полная защита от DNS-rebinding не нужна для нашей модели угроз (источники
# жёстко прошиты в SOURCES, RSS приходит по HTTPS).
def _is_safe_external_url(url: str) -> bool:
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            return False
        host = (u.hostname or "").strip().strip(".")
        if not host:
            return False
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return True  # обычный hostname — пропускаем
        return not (addr.is_private or addr.is_loopback
                    or addr.is_link_local or addr.is_reserved
                    or addr.is_multicast or addr.is_unspecified)
    except Exception:
        return False

# Лимит на размер скачиваемой картинки. Без него атакующий через RSS
# может отдавать 10ГБ-стрим и забивать память/диск.
_MAX_IMAGE_BYTES = 5 * 1024 * 1024   # 5 MB
_MAX_HTML_BYTES = 200 * 1024         # 200 KB для og:image-fetcher
_MAX_ARTICLE_BYTES = 1 * 1024 * 1024 # 1 MB для тела статьи (trafilatura)

def _stream_download(url: str, max_bytes: int,
                     headers: Optional[dict] = None,
                     timeout: int = 10) -> Optional[bytes]:
    """Качает URL с потоковым лимитом по размеру. Прерывает скачивание
    как только пришло max_bytes байт. Также проверяет Content-Length до
    скачивания (если сервер его отдал)."""
    if not _is_safe_external_url(url):
        return None
    try:
        with LeakEngine.session.get(
                url, headers=headers or _news_headers(),
                timeout=timeout, stream=True, allow_redirects=True) as res:
            if res.status_code != 200:
                return None
            cl = res.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                return None
            buf = bytearray()
            for chunk in res.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    return None
            return bytes(buf)
    except Exception:
        return None

def _download_image(url: str, referer: Optional[str] = None) -> Optional[str]:
    """Скачивает картинку с лимитом размера и проверкой URL.
    Некоторые CDN (WP-Engine, Cloudflare у BleepingComputer) требуют
    Referer — без него возвращают 403. Передаём URL статьи как Referer."""
    try:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        ext = ".jpg"
        m = re.search(r"\.(jpg|jpeg|png|webp|gif)(\?|$)", url, re.IGNORECASE)
        if m:
            ext = "." + m.group(1).lower()
        path = os.path.join(_cache_dir(), h + ext)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        headers = _news_headers()
        if referer:
            headers["Referer"] = referer
        data = _stream_download(url, _MAX_IMAGE_BYTES, headers=headers)
        if data:
            with open(path, "wb") as f:
                f.write(data)
            return path
    except Exception:
        pass
    return None

# Регекс для og:image. Атрибуты могут быть в любом порядке — нужны 2 паттерна.
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE,
)
_TWITTER_IMAGE_RE = re.compile(
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

def _fetch_og_image(article_url: str) -> Optional[str]:
    """Тянет URL картинки из <meta property="og:image"> со страницы статьи.
    Скачиваем только первые 200КБ потоком — og:image всегда в <head>."""
    data = _stream_download(article_url, _MAX_HTML_BYTES, timeout=8)
    if not data:
        return None
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return None
    for rx in (_OG_IMAGE_RE, _OG_IMAGE_RE_ALT, _TWITTER_IMAGE_RE):
        m = rx.search(text)
        if m:
            url = m.group(1).strip()
            if url and not url.startswith("data:"):
                return url
    return None

# trafilatura отдаёт упрощённый XML-схожий HTML с <graphic> для картинок,
# QTextBrowser его не понимает — приводим к стандартному <img>.
_GRAPHIC_OPEN_RE = re.compile(r"<graphic\b", re.IGNORECASE)
_GRAPHIC_CLOSE_RE = re.compile(r"</graphic>", re.IGNORECASE)

def _normalize_extracted_html(s: str) -> str:
    s = _GRAPHIC_OPEN_RE.sub("<img", s)
    s = _GRAPHIC_CLOSE_RE.sub("", s)
    return s

def _extract_full_article(article_url: str) -> Optional[str]:
    """Скачивает страницу статьи (cap 1 МБ) и прогоняет через trafilatura
    для выделения main-content. Возвращает HTML или None если экстрактор
    ничего не вытащил/упал. SSRF-проверка делается в _stream_download."""
    try:
        import trafilatura  # ленивый импорт — стартап не страдает
    except ImportError:
        return None
    data = _stream_download(article_url, _MAX_ARTICLE_BYTES, timeout=12)
    if not data:
        return None
    try:
        html = data.decode("utf-8", errors="replace")
    except Exception:
        return None
    try:
        out = trafilatura.extract(
            html, output_format="html",
            include_images=True, include_links=True,
            include_tables=True, favor_recall=True,
        )
    except Exception:
        return None
    if not out or len(out) < 200:
        return None
    return _normalize_extracted_html(out)


class ArticleExtractWorker(QObject):
    """Фоновый QThread-worker: качает страницу статьи и прогоняет через
    trafilatura. Эмитит done(link, html_or_empty)."""
    done = Signal(str, str)

    def __init__(self, link: str, parent=None):
        super().__init__(parent)
        self._link = link

    def run(self):
        html = ""
        try:
            extracted = _extract_full_article(self._link)
            if extracted:
                html = extracted
        except Exception as e:
            print(f"[news] extract failed: {type(e).__name__}: {e}",
                  flush=True)
        self.done.emit(self._link, html)

# Виртуальный список: QListView + delegate рисует только видимый viewport
# (~8-10 элементов), что бы ни лежало в модели. uniformItemSizes гарантирует
# мгновенный layout при resize окна.

CARD_HEIGHT = 124           # высота строки в QListView
CARD_PAD_V = 5              # вертикальный gap между карточками
IMG_W, IMG_H = 140, 90

class _NewsModel(QAbstractListModel):
    ItemRole = Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        i = index.row()
        if i < 0 or i >= len(self._items):
            return None
        if role == _NewsModel.ItemRole:
            return self._items[i]
        return None

    def set_items(self, items: list[dict]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def update_item(self, link: str, **kwargs):
        for i, it in enumerate(self._items):
            if it.get("link") == link:
                it.update(kwargs)
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [_NewsModel.ItemRole])
                return

class _NewsFilterProxy(QSortFilterProxyModel):
    """Фильтр по ключевым словам в title+excerpt."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._keywords: tuple = ()

    def set_keywords(self, kw):
        self._keywords = tuple(kw) if kw else ()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if not self._keywords:
            return True
        src = self.sourceModel()
        if src is None:
            return True
        item = src.index(row, 0, parent).data(_NewsModel.ItemRole)
        if not item:
            return False
        text = (
            (item.get("title") or "") + " " +
            (item.get("excerpt") or "")
        ).lower()
        return any(k in text for k in self._keywords)

class _NewsDelegate(QStyledItemDelegate):
    """Рисует одну карточку в QPainter. Кэширует scaled QPixmap по пути,
    чтобы не пересчитывать масштабирование на каждый paint."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmaps: dict[str, QPixmap] = {}

    def sizeHint(self, option, index):
        return QSize(option.rect.width() if option.rect.width() > 0 else 600,
                     CARD_HEIGHT)

    @staticmethod
    def _mk_font(px: int, bold: bool = False) -> QFont:
        """Тот же паттерн, что в qt_journal: явная семья из cfg + hinting +
        antialias. Без них QFont в QPainter делегатах берёт fallback-шрифт
        и буквы отличаются от QLabel."""
        family = (cfg.QT_FONT_FAMILY if hasattr(cfg, "QT_FONT_FAMILY")
                  else getattr(cfg, "FONT_FAMILY", "Geist"))
        f = QFont(family)
        f.setPixelSize(px)
        if bold:
            f.setBold(True)
        f.setHintingPreference(QFont.PreferNoHinting)
        f.setStyleStrategy(QFont.PreferAntialias)
        return f

    def _get_pixmap(self, path: str) -> Optional[QPixmap]:
        if not path:
            return None
        pm = self._pixmaps.get(path)
        if pm is not None:
            return pm
        if not os.path.exists(path):
            return None
        raw = QPixmap(path)
        if raw.isNull():
            return None
        pm = raw.scaled(IMG_W * 2, IMG_H * 2,
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation)
        self._pixmaps[path] = pm
        return pm

    def paint(self, painter, option, index):
        item = index.data(_NewsModel.ItemRole)
        if not item:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 14px справа резервируем под полосу прокрутки QListView.
        rect = option.rect
        card = QRect(rect.left(), rect.top() + CARD_PAD_V,
                     rect.width() - 14,
                     rect.height() - CARD_PAD_V * 2)

        is_hover = bool(option.state & QStyle.State_MouseOver)
        is_read = bool(item.get("is_read"))

        bg_color = QColor(cfg.BG_SURFACE)
        border_color = QColor(cfg.ACCENT) if is_hover else QColor(cfg.BORDER)
        path = QPainterPath()
        path.addRoundedRect(QRectF(card), 12, 12)
        painter.fillPath(path, bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)

        inner_top = card.top() + 12
        x = card.left() + 14
        x += 12  # лёгкий отступ от левой кромки карточки

        img_rect = QRect(x, inner_top, IMG_W, IMG_H)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(img_rect), 8, 8)
        painter.save()
        painter.setClipPath(clip_path)
        pm = self._get_pixmap(_resolve_image_path(item.get("image_path") or ""))
        if pm is not None:
            painter.drawPixmap(img_rect, pm)
        else:
            painter.fillRect(img_rect, QColor(cfg.BG_ELEVATED))
            ph_font = self._mk_font(28)
            painter.setFont(ph_font)
            painter.setPen(QColor(cfg.TEXT_MUTED))
            painter.drawText(img_rect, Qt.AlignCenter, "📰")
        painter.restore()

        text_x = img_rect.right() + 14
        text_w = card.right() - text_x - 14
        if text_w < 50:
            painter.restore()
            return

        # Заголовок (жирный, до 2 строк). Меряем реальную высоту после
        # word-wrap, чтобы метаданные ложились вплотную и не было пустоты
        # для коротких заголовков.
        painter.setFont(self._mk_font(17, bold=True))
        painter.setPen(QColor(cfg.TEXT_PRIMARY))
        title = item.get("title") or "—"
        fm_title = painter.fontMetrics()
        title_bounds = fm_title.boundingRect(
            QRect(text_x, inner_top, text_w, 50),
            Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
            title,
        )
        title_h = min(title_bounds.height(), 48)
        title_rect = QRect(text_x, inner_top, text_w, title_h)
        painter.drawText(title_rect,
                         Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
                         title)

        meta_y = inner_top + title_h + 4
        meta = item.get("source") or ""
        d = item.get("date")
        if isinstance(d, datetime.datetime):
            meta += "  ·  " + _format_relative_date(d)

        meta_x = text_x
        if not is_read:
            badge_font = self._mk_font(10, bold=True)
            painter.setFont(badge_font)
            badge_text = "НОВОЕ"
            badge_w = painter.fontMetrics().horizontalAdvance(badge_text) + 14
            badge_h = 18
            badge_rect = QRect(meta_x, meta_y - 1, badge_w, badge_h)
            badge_path = QPainterPath()
            badge_path.addRoundedRect(QRectF(badge_rect), 9, 9)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(cfg.ACCENT))
            painter.drawPath(badge_path)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge_rect, Qt.AlignCenter, badge_text)
            meta_x += badge_w + 8

        painter.setFont(self._mk_font(13))
        painter.setPen(QColor(cfg.TEXT_MUTED))
        metrics = painter.fontMetrics()
        meta_w = card.right() - meta_x - 14
        meta_rect = QRect(meta_x, meta_y, meta_w, 18)
        painter.drawText(
            meta_rect, Qt.AlignTop | Qt.AlignLeft,
            metrics.elidedText(meta, Qt.ElideRight, meta_w))

        excerpt = (item.get("excerpt") or "").strip()
        if excerpt:
            painter.setFont(self._mk_font(12))
            painter.setPen(QColor(cfg.TEXT_SECONDARY))
            metrics = painter.fontMetrics()
            ex_rect = QRect(text_x, meta_y + 22, text_w, 18)
            painter.drawText(
                ex_rect, Qt.AlignTop | Qt.AlignLeft,
                metrics.elidedText(excerpt, Qt.ElideRight, text_w))

        painter.restore()

class _FeedView(QWidget):
    """Контейнер с QListView (виртуальный список) и плейсхолдером."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{cfg.BG_APP};")
        self._on_card_open = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._stack = QStackedLayout()
        outer.addLayout(self._stack)

        self._placeholder = QLabel("Загрузка ленты...", self)
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:14px;"
            f"background:transparent; padding:40px;")
        self._stack.addWidget(self._placeholder)

        self._list = QListView(self)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self._list.setSelectionMode(QListView.NoSelection)
        self._list.setUniformItemSizes(True)  # все строки одной высоты — speedup
        self._list.setMouseTracking(True)
        self._list.viewport().setMouseTracking(True)
        self._list.setCursor(Qt.PointingHandCursor)
        self._list.setStyleSheet(f"""
            QListView {{ background:{cfg.BG_APP}; border:none;
                         outline: none; }}
            QListView::item {{ background:transparent; border:none; }}
            QListView::item:selected {{ background:transparent; }}
            QScrollBar:vertical {{
                background:transparent; width:10px; margin:4px 2px 4px 0;
                border:none;
            }}
            QScrollBar::handle:vertical {{
                background:{cfg.BORDER}; border-radius:3px; min-height:24px;
            }}
            QScrollBar::handle:vertical:hover {{ background:{cfg.BORDER_HOVER}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height:0; background:transparent; border:none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:transparent; border:none;
            }}
        """)
        self._model = _NewsModel(self)
        self._proxy = _NewsFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._list.setModel(self._proxy)
        self._delegate = _NewsDelegate(self._list)
        self._list.setItemDelegate(self._delegate)
        self._list.clicked.connect(self._on_item_clicked)
        self._stack.addWidget(self._list)

        self._stack.setCurrentWidget(self._placeholder)

    @property
    def _cards(self) -> list:
        # Совместимость: NewsPage проверяет `view._cards` truthiness, чтобы
        # понять есть ли контент. Возвращаем список нужной длины.
        return [None] * self._model.rowCount()

    def _on_item_clicked(self, idx):
        item = idx.data(_NewsModel.ItemRole)
        if not item:
            return
        link = item.get("link")
        if link and not item.get("is_read"):
            self._model.update_item(link, is_read=True)
        if self._on_card_open is not None:
            self._on_card_open(item)

    def _set_placeholder(self, text: str):
        self._placeholder.setText(text)
        self._stack.setCurrentWidget(self._placeholder)

    def set_items(self, items: list[dict]):
        if not items:
            self._set_placeholder("Не удалось загрузить ленту.")
            self._model.set_items([])
            return
        self._model.set_items(items)
        self._stack.setCurrentWidget(self._list)

    def apply_filter(self, keywords):
        self._proxy.set_keywords(keywords)

class _ReaderView(QWidget):
    """Полноэкранная читалка статьи внутри приложения. Берёт full_html из
    кэша и рендерит через QTextBrowser. Если full_html пустой —
    показывает только заголовок + excerpt + кнопку «Открыть в браузере»."""
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{cfg.BG_APP};")
        self._link = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 8)
        top.setSpacing(8)
        self._back_btn = QPushButton("←  Назад", self)
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setFixedHeight(32)
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                font-family:'Geist'; background:{cfg.BG_ELEVATED};
                color:{cfg.TEXT_SECONDARY}; border:1px solid {cfg.BORDER};
                border-radius:6px; padding:0 14px; font-size:12px;
                font-weight:600;
            }}
            QPushButton:hover {{ border-color:{cfg.ACCENT}; color:{cfg.TEXT_PRIMARY}; }}
        """)
        self._back_btn.clicked.connect(self.back_requested)
        top.addWidget(self._back_btn)
        top.addStretch(1)

        self._open_btn = QPushButton("Открыть в браузере  →", self)
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.setFixedHeight(32)
        self._open_btn.setStyleSheet(f"""
            QPushButton {{
                font-family:'Geist'; background:{cfg.ACCENT}; color:white;
                border:none; border-radius:6px; padding:0 14px;
                font-size:12px; font-weight:600;
            }}
            QPushButton:hover {{ background:{cfg.ACCENT_HOVER}; }}
        """)
        self._open_btn.clicked.connect(self._open_in_browser)
        top.addWidget(self._open_btn)
        outer.addLayout(top)

        # QTextBrowser в роли «article view» — рендерит HTML, поддерживает
        # картинки и кликабельные ссылки.
        self._browser = QTextBrowser(self)
        self._browser.setOpenLinks(False)  # ловим anchorClicked сами
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        self._browser.setStyleSheet(f"""
            QTextBrowser {{
                background:{cfg.BG_SURFACE}; color:{cfg.TEXT_PRIMARY};
                border:1px solid {cfg.BORDER}; border-radius:12px;
                padding:24px 28px; font-family:'Geist';
                font-size:14px;
            }}
            QScrollBar:vertical {{
                background:transparent; width:10px; margin:8px 4px;
                border:none;
            }}
            QScrollBar::handle:vertical {{
                background:{cfg.BORDER}; border-radius:3px; min-height:24px;
            }}
            QScrollBar::handle:vertical:hover {{ background:{cfg.BORDER_HOVER}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height:0; border:none; background:transparent;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:transparent; border:none;
            }}
        """)
        outer.addWidget(self._browser, 1)

    def load_item(self, item: dict, loading: bool = False):
        self._link = item.get("link") or ""
        title = item.get("title") or ""
        source = item.get("source") or ""
        d = item.get("date")
        date_str = ""
        if isinstance(d, datetime.datetime):
            date_str = _format_relative_date(d)
        full_html = (item.get("full_html") or "").strip()
        excerpt = item.get("excerpt") or ""
        image_path = _resolve_image_path(item.get("image_path") or "")

        # Стили для тела статьи. Используем inline-стили, потому что
        # QTextBrowser поддерживает только подмножество CSS.
        meta = (
            f"<div style='color:{cfg.TEXT_MUTED}; font-size:12px; "
            f"margin-bottom:16px;'>{source}"
            + (f" &middot; {date_str}" if date_str else "")
            + "</div>"
        )
        title_html = (
            f"<h1 style='color:{cfg.TEXT_PRIMARY}; font-size:24px; "
            f"font-weight:700; margin:0 0 8px 0;'>{_strip_html(title)}</h1>"
        )
        img_html = ""
        if image_path and os.path.exists(image_path):
            # QTextBrowser принимает локальные пути через file:///.
            uri = "file:///" + image_path.replace("\\", "/")
            img_html = (
                f"<p><img src='{uri}' width='720' "
                f"style='border-radius:10px;'/></p>"
            )
        loading_note = (
            f"<p style='color:{cfg.TEXT_MUTED}; font-size:12px; "
            f"margin-top:16px;'>Загружаю полную статью...</p>"
            if loading else
            f"<p style='color:{cfg.TEXT_MUTED}; font-size:12px; "
            f"margin-top:24px;'>Полный текст этой статьи доступен только "
            f"на сайте источника. Нажми «Открыть в браузере» сверху.</p>"
        )
        if full_html:
            body = full_html
            # «Короткий» full_html (excerpt + «Читать далее») оставляем как
            # тизер, плюс показываем индикатор загрузки если экстракт идёт.
            if loading and len(full_html) < 1500:
                body += loading_note
        else:
            body = (
                f"<p style='color:{cfg.TEXT_SECONDARY}; font-size:14px; "
                f"line-height:160%;'>{_strip_html(excerpt)}</p>"
                + loading_note
            )

        html = (
            f"<html><body style='color:{cfg.TEXT_PRIMARY}; "
            f"font-family:Geist; font-size:14px;'>"
            f"{title_html}{meta}{img_html}{body}"
            f"</body></html>"
        )
        self._browser.setHtml(html)
        self._browser.verticalScrollBar().setValue(0)

    def _open_in_browser(self):
        if self._link:
            QDesktopServices.openUrl(QUrl(self._link))

    def _on_anchor_clicked(self, url: QUrl):
        # Открываем только http(s). RSS может содержать вредоносные
        # file://, javascript:, mailto:?body=… и пр. — игнорируем.
        if url.scheme().lower() in ("http", "https"):
            QDesktopServices.openUrl(url)

class NewsPage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setStyleSheet(f"background:{cfg.BG_APP};")

        page_lay = QVBoxLayout(self)
        page_lay.setContentsMargins(32, 28, 32, 20)
        page_lay.setSpacing(0)

        # Внешний stack: список новостей или читалка статьи.
        self._mode_stack = QStackedWidget(self)
        page_lay.addWidget(self._mode_stack)

        list_view = QWidget(self)
        outer = QVBoxLayout(list_view)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        title = QLabel("Новости", list_view)
        title.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_PRIMARY}; font-size:28px;"
            f"font-weight:700; background:transparent;")
        outer.addWidget(title)
        subtitle = QLabel("Свежие материалы по утечкам и кибербезопасности",
                          list_view)
        subtitle.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_SECONDARY};"
            f"font-size:14px; background:transparent;")
        outer.addWidget(subtitle)
        outer.addSpacing(4)

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.setSpacing(8)

        self._tabs = QButtonGroup(self)
        self._tabs.setExclusive(True)
        self._btn_ru = self._make_tab("Русские", primary=True)
        self._btn_en = self._make_tab("English", primary=True)
        self._tabs.addButton(self._btn_ru, 0)
        self._tabs.addButton(self._btn_en, 1)
        tabs_row.addWidget(self._btn_ru)
        tabs_row.addWidget(self._btn_en)
        tabs_row.addStretch(1)

        self._updated_lbl = QLabel("", self)
        self._updated_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:11px;"
            f"background:transparent;")
        tabs_row.addWidget(self._updated_lbl)

        self._refresh_btn = QPushButton("Обновить", self)
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                font-family:'Geist'; background:{cfg.BG_ELEVATED};
                color:{cfg.TEXT_SECONDARY}; border:1px solid {cfg.BORDER};
                border-radius:6px; padding:0 14px; font-size:12px;
                font-weight:600;
            }}
            QPushButton:hover {{ border-color:{cfg.ACCENT}; color:{cfg.TEXT_PRIMARY}; }}
        """)
        self._refresh_btn.clicked.connect(self._force_refresh)
        tabs_row.addWidget(self._refresh_btn)

        outer.addLayout(tabs_row)

        # Состояние, к которому обращаются обработчики toggled и setChecked
        # ниже — инициализируем до создания тумблеров.
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, NewsWorker] = {}
        self._last_update: dict[str, datetime.datetime] = {}
        self._new_since_view: dict[str, int] = {"ru": 0, "en": 0}

        # Filter pills (категории) — создаём сейчас, но setChecked откладываем
        # до того момента, когда feeds появятся (toggled triggers _set_filter,
        # который смотрит self._feed_ru/_feed_en).
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(6)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_btns: dict[str, QPushButton] = {}
        self._active_filter_kw = None
        for cat_id, label, kw in CATEGORIES:
            b = self._make_tab(label, primary=False)
            self._filter_group.addButton(b)
            self._filter_btns[cat_id] = b
            b.toggled.connect(
                lambda on, k=kw: on and self._set_filter(k))
            filter_row.addWidget(b)
        filter_row.addStretch(1)
        outer.addLayout(filter_row)

        self._stack = QStackedWidget(list_view)
        self._feed_ru = _FeedView(list_view)
        self._feed_en = _FeedView(list_view)
        self._feed_ru._on_card_open = self._open_reader
        self._feed_en._on_card_open = self._open_reader
        self._stack.addWidget(self._feed_ru)
        self._stack.addWidget(self._feed_en)
        outer.addWidget(self._stack, 1)

        # list_view готов — добавляем во внешний stack + читалку.
        self._mode_stack.addWidget(list_view)
        self._reader = _ReaderView(self)
        self._reader.back_requested.connect(self._exit_reader)
        self._mode_stack.addWidget(self._reader)
        self._mode_stack.setCurrentIndex(0)

        self._btn_ru.toggled.connect(
            lambda on: on and self._on_lang_tab_clicked("ru"))
        self._btn_en.toggled.connect(
            lambda on: on and self._on_lang_tab_clicked("en"))
        self._btn_ru.setChecked(True)
        # Теперь, когда feeds существуют — выставляем активную таблетку.
        self._filter_btns["all"].setChecked(True)

        # Сразу подсовываем кэш из БД — мгновенный показ при старте, даже офлайн.
        for lang, view in (("ru", self._feed_ru), ("en", self._feed_en)):
            try:
                cached = self.db.get_cached_news(lang, 50)
                if cached:
                    view.set_items(cached)
            except Exception as e:
                print(f"[news] cache read failed ({lang}): {e}", flush=True)

        # Чистим записи старше 30 дней (одноразово на старте страницы).
        try:
            self.db.cleanup_old_news(30)
        except Exception as e:
            print(f"[news] cleanup failed: {e}", flush=True)

        QTimer.singleShot(120, lambda: self._fetch("ru"))
        QTimer.singleShot(220, lambda: self._fetch("en"))

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._auto_refresh)
        self._auto_timer.start(AUTO_REFRESH_MS)

    def _make_tab(self, label: str, primary: bool = True) -> QPushButton:
        """primary=True — большой акцентный таб (язык). False — компактная
        фильтр-таблетка (категория)."""
        b = QPushButton(label, self)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        if primary:
            b.setFixedHeight(34)
            padding, fs = "0 18px", 13
        else:
            b.setFixedHeight(28)
            padding, fs = "0 12px", 12
        b.setStyleSheet(f"""
            QPushButton {{
                font-family:'Geist'; background:{cfg.BG_ELEVATED};
                color:{cfg.TEXT_SECONDARY}; border:1px solid {cfg.BORDER};
                border-radius:8px; padding:{padding}; font-size:{fs}px;
                font-weight:600;
            }}
            QPushButton:hover {{ border-color:{cfg.BORDER_HOVER}; }}
            QPushButton:checked {{
                background:{cfg.ACCENT}; color:white;
                border-color:{cfg.ACCENT};
            }}
        """)
        return b

    def _set_filter(self, keywords):
        self._active_filter_kw = keywords
        self._feed_ru.apply_filter(keywords)
        self._feed_en.apply_filter(keywords)

    def _open_reader(self, item: dict):
        link = item.get("link") or ""
        if link:
            try:
                self.db.mark_news_read(link)
            except Exception as e:
                print(f"[news] mark_read failed: {e}", flush=True)
        full_html = (item.get("full_html") or "").strip()
        needs_extract = bool(link) and link.startswith(("http://", "https://"))\
            and len(full_html) < 1500
        # Плашку «Загружаю...» не показываем: для части источников
        # (xakep, сайты за Cloudflare) экстрактор всё равно ничего не
        # вытащит, а ложное обещание раздражает. Где экстракция
        # сработает — текст молча подменится через _on_extracted.
        self._reader.load_item(item, loading=False)
        self._mode_stack.setCurrentIndex(1)
        if needs_extract:
            self._start_extract(link, item)

    def _start_extract(self, link: str, item: dict):
        # Один воркер на ссылку — клики по той же карточке пока он работает
        # ничего не дублируют.
        if not hasattr(self, "_extract_threads"):
            self._extract_threads: dict = {}
        if link in self._extract_threads:
            return
        thread = QThread(self)
        worker = ArticleExtractWorker(link)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(
            lambda lk, html, it=item: self._on_extracted(lk, html, it))
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda lk=link: self._extract_threads.pop(lk, None))
        self._extract_threads[link] = thread
        thread.start()

    def _on_extracted(self, link: str, html: str, item: dict):
        if not html:
            # Экстрактор не справился — оставляем что было, убираем
            # «Загружаю...» (если читалка ещё показывает эту статью).
            if self._reader._link == link:
                self._reader.load_item(item, loading=False)
            return
        # Кэшируем full_html в БД — следующее открытие будет мгновенным.
        try:
            self.db._conn.execute(
                "UPDATE news_cache SET full_html=? WHERE link=?", (html, link))
            self.db._conn.commit()
        except Exception as e:
            print(f"[news] cache update failed: {e}", flush=True)
        # Перерисовываем читалку только если юзер всё ещё смотрит эту статью.
        if self._reader._link == link:
            updated = dict(item)
            updated["full_html"] = html
            self._reader.load_item(updated, loading=False)

    def _exit_reader(self):
        self._mode_stack.setCurrentIndex(0)

    def _on_lang_tab_clicked(self, lang: str):
        """Переключение языковой вкладки + сброс счётчика «новых» в этом
        языке (юзер их сейчас увидит)."""
        self._stack.setCurrentWidget(
            self._feed_ru if lang == "ru" else self._feed_en)
        self._new_since_view[lang] = 0
        self._refresh_meta_label()

    def showEvent(self, event):
        """Срабатывает когда NewsPage становится видимой (юзер клацнул
        «Новости» в сайдбаре). Если последнее обновление было давно —
        дёргаем silent re-fetch."""
        super().showEvent(event)
        import time as _t
        STALE_SEC = 5 * 60   # 5 минут — порог «свежести»
        for lang in ("ru", "en"):
            last = self._last_update.get(lang)
            if last is None:
                continue  # стартовый фетч сделается по QTimer.singleShot
            age = (datetime.datetime.now() - last).total_seconds()
            if age > STALE_SEC and lang not in self._threads:
                self._fetch(lang, silent=True)

    def _fetch(self, lang: str, silent: bool = False):
        if lang in self._threads:
            return  # уже фетчится
        view = self._feed_ru if lang == "ru" else self._feed_en
        # При авто-обновлении и при наличии кэшированных карточек на экране —
        # не показываем плейсхолдер, чтобы UI не моргал.
        if (not silent and lang not in self._last_update
                and not view._cards):
            view._set_placeholder("Загрузка ленты...")
        thread = QThread(self)
        worker = NewsWorker(lang, db=self.db)
        worker.moveToThread(thread)
        # Визуальный фидбек: пока хоть один поток в работе — кнопка disabled.
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Обновляю...")
        self._refresh_meta_label()
        thread.started.connect(worker.run)
        worker.done.connect(self._on_loaded)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(lambda l=lang: self._cleanup_thread(l))
        thread.finished.connect(thread.deleteLater)
        self._threads[lang] = thread
        self._workers[lang] = worker
        thread.start()

    def _cleanup_thread(self, lang: str):
        self._threads.pop(lang, None)
        self._workers.pop(lang, None)
        # Когда последний поток завершился — возвращаем кнопке её обычный вид.
        if not self._threads:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Обновить")
            self._refresh_meta_label()

    def _on_loaded(self, lang: str, items: list, new_count: int):
        view = self._feed_ru if lang == "ru" else self._feed_en
        # Если фетч вернул пусто (нет интернета / RSS лежит) — не стираем
        # текущее содержимое (там либо кэш из БД, либо предыдущая лента).
        if not items and view._cards:
            self._refresh_meta_label()
            return
        # После фетча перечитываем уже обновлённый кэш — там корректно
        # стоят флаги is_read для существующих ссылок.
        try:
            cached = self.db.get_cached_news(lang, 50)
            view.set_items(cached or items)
        except Exception:
            view.set_items(items)
        if items:
            self._last_update[lang] = datetime.datetime.now()
            # Накапливаем суммарно новые с момента открытия вкладки —
            # сбрасываются когда юзер кликает на любую вкладку RU/EN.
            self._new_since_view[lang] = (
                self._new_since_view.get(lang, 0) + new_count
            )
            self._refresh_meta_label()

    def _refresh_meta_label(self):
        # Если хоть какой-то фетч сейчас в работе — показываем индикатор.
        if self._threads:
            self._updated_lbl.setText("обновляется...")
            self._updated_lbl.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.ACCENT_TEXT};"
                f"font-size:11px; font-weight:600; background:transparent;")
            return
        # Базовый цвет — приглушённый.
        self._updated_lbl.setStyleSheet(
            f"font-family:'Geist'; color:{cfg.TEXT_MUTED}; font-size:11px;"
            f"background:transparent;")
        if not self._last_update:
            self._updated_lbl.setText("")
            return
        ts = min(self._last_update.values())
        # Суммарно новых статей с момента открытия страницы.
        new_total = sum(self._new_since_view.values())
        if new_total > 0:
            self._updated_lbl.setText(
                f"обновлено: {ts.strftime('%H:%M')} · "
                f"+{new_total} новых · авто каждые 30 мин")
            self._updated_lbl.setStyleSheet(
                f"font-family:'Geist'; color:{cfg.ACCENT_TEXT};"
                f"font-size:11px; font-weight:600; background:transparent;")
        else:
            self._updated_lbl.setText(
                f"обновлено: {ts.strftime('%H:%M')} · авто каждые 30 мин")

    def _force_refresh(self):
        # Принудительный refetch обеих лент.
        for lang in ("ru", "en"):
            if lang not in self._threads:
                self._fetch(lang)

    def _auto_refresh(self):
        # Тихий тик авто-обновления — стартуем те ленты, которые сейчас
        # не фетчатся. Карточки не трогаем до прихода свежих результатов.
        for lang in ("ru", "en"):
            if lang not in self._threads:
                self._fetch(lang, silent=True)
