# DataSentinel

Десктопное приложение для мониторинга утечек персональных данных. Проверяет email-адреса, номера телефонов, username'ы и пароли по 9+ открытым источникам, ведёт журнал инцидентов, шлёт уведомления о новых утечках и предоставляет AI-помощника для анализа.

## Возможности

**Мониторинг утечек**
- 9 источников: HIBP (Pwned Passwords), LeakCheck, Hudson Rock (email и username), XposedOrNot, ProxyNova COMB, EmailRep, BreachDirectory, IntelX (Dark Web), Pastebin Dumps
- Автоопределение типа объекта: email / phone / username / password — каждый идёт по релевантным источникам
- Автоматическое фоновое сканирование по расписанию (от 2 минут до 48 часов), запуск ровно в начало минуты
- Risk Score с диминишн-кривой и tier-весами по серьёзности источника (5 уровней)

**Безопасность**
- Все чувствительные данные в БД шифруются через Fernet
- Ключ Fernet защищён Windows DPAPI (привязка к учётке пользователя)
- API-ключи источников хранятся зашифрованными
- SSRF-защита и cap'ы на размер при скачивании внешних HTTP-ресурсов

**AI-помощник**
- Встроенная Groq (Llama 3.3 70B) — работает «из коробки»
- Опциональный локальный Ollama (без интернета)
- Контекст из реального журнала утечек

**Новости кибербезопасности**
- 6 RU + 6 EN RSS-источников (Habr ИБ, Xakep, Kaspersky, Roskomsvoboda, OpenNet, Habr News, BleepingComputer, The Hacker News, Krebs, DarkReading, SecurityWeek, Schneier)
- In-app reader (без переходов в браузер) с автоматической экстракцией полного текста через trafilatura
- Фильтрация по категориям: Утечки / Уязвимости / Малварь / Приватность
- Автообновление каждые 30 минут + относительные даты («5 мин назад», «сегодня в 14:11»)
- Кэширование в SQLite, помечание прочитанных

**Уведомления**
- Toast-уведомления Windows (через winotify)
- Email через SMTP (с тестом подключения)
- Системный трей

**Прочее**
- Светлая / тёмная / системная темы — переключение live, без рестарта
- Журнал инцидентов с экспортом в PDF (ReportLab, поддержка кириллицы)
- Генератор паролей (random / memorable / PIN) и проверка стойкости
- Frameless-окно с нативным resize/snap, кастомный titlebar
- Single-instance lock (запуск второго экземпляра восстанавливает первое окно)

## Установка

### Для пользователей

Скачайте `DataSentinel_Setup_X.X.X.exe` из [Releases](https://github.com/sseconddeath/DataSentinel/releases), запустите и следуйте инструкциям.

При установке можно опционально установить [Ollama](https://ollama.com) для локального AI-ассистента (вместо Groq).

### Для разработчиков

Требуется Python 3.11+ (тестировалось на 3.14) и Windows 10/11.

```bash
git clone https://github.com/sseconddeath/DataSentinel.git
cd DataSentinel
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main_qt.py
```

## Сборка установщика

Требуется [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
build.bat
```

Результат: `installer_output\DataSentinel_Setup_X.X.X.exe`

## Стек

- **UI:** PySide6 (Qt 6, frameless), Geist шрифт
- **БД:** SQLite (WAL) + Fernet + DPAPI
- **AI:** Groq API / Ollama
- **Новости:** RSS + trafilatura для readability-экстракции
- **PDF:** ReportLab
- **Внешние API:** HIBP, LeakCheck, Hudson Rock, IntelX, BreachDirectory, EmailRep, XposedOrNot, ProxyNova COMB, PSBDMP

## Архитектура

```
main_qt.py                точка входа, MainWindow, frameless + tray + IPC

core/
  config.py               темы (dark/light) + design tokens
  database.py             DBManager — SQLite + Fernet + DPAPI + миграции
  engine.py               LeakEngine — все внешние API-вызовы и password tools

services/
  ai_assistant.py         Groq / Ollama / унифицированный AIAssistant
  pdf_export.py           PDF-отчёты
  smtp_notify.py          SMTP-уведомления

ui/
  qt_dashboard.py         дашборд (статус, метрики, активность)
  qt_manager.py           менеджер целей и API-ключей
  qt_journal.py           журнал инцидентов
  qt_tools.py             генератор/проверка паролей
  qt_settings.py          тема, SMTP, источники, лог
  qt_ai.py                AI-чат (Groq/Ollama)
  qt_news.py              новости (RSS + trafilatura reader)
  qt_scan.py              ScanWorker (QThread)
  qt_icons.py             SVG-иконки типов объектов
```

## Хранение данных

Всё локально, в подпапке `data/` рядом с приложением:
- `storage.db` — SQLite БД (зашифрованные значения)
- `secret.key` — Fernet-ключ, защищён DPAPI
- `news_cache/` — кэш картинок новостей
- `.ipc_token` — токен для single-instance IPC

Все эти файлы — в `.gitignore` и в установщике пользовательские данные не попадают.

## Лицензия

MIT
