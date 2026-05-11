"""
smtp_notify.py — Email-уведомления через SMTP
Поддерживает Gmail, Yandex, Mail.ru, любой SMTP-сервер
"""
import smtplib
import ssl
import html as _html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Пресеты популярных провайдеров
SMTP_PRESETS = {
    "Gmail":    {"host": "smtp.gmail.com",     "port": 587},
    "Yandex":   {"host": "smtp.yandex.ru",     "port": 587},
    "Mail.ru":  {"host": "smtp.mail.ru",       "port": 587},
    "Outlook":  {"host": "smtp.office365.com", "port": 587},
    "Custom":   {"host": "",                   "port": 587},
}

def send_breach_email(
    smtp_host: str, smtp_port: int,
    smtp_user: str, smtp_pass: str,
    recipient: str,
    breaches: list,          # [(target, source, breach_name), ...]
    risk_level: str = "СРЕДНИЙ",
    risk_score: int = 0
) -> tuple:
    """
    Отправляет HTML-письмо об обнаруженных утечках.
    Возвращает (True, "") при успехе или (False, "текст ошибки").
    """
    if not all([smtp_host, smtp_user, smtp_pass, recipient]):
        return False, "Не заполнены данные SMTP"

    # HTML шаблон письма. Внешние данные (target/source/breach_name приходят
    # из API утечек) экранируем — иначе вредоносное имя бреча может встроить
    # ссылки/трекеры/ломать вёрстку письма.
    rows_html = ""
    for i, (target, source, breach_name) in enumerate(breaches, 1):
        bg = "#1a0a0a" if i % 2 == 0 else "#200e0e"
        rows_html += f"""
        <tr style="background:{bg}">
            <td style="padding:8px;border:1px solid #333;color:#aaa">{i}</td>
            <td style="padding:8px;border:1px solid #333;color:#5dade2">{_html.escape(str(target))}</td>
            <td style="padding:8px;border:1px solid #333;color:#e67e22">{_html.escape(str(source))}</td>
            <td style="padding:8px;border:1px solid #333;color:#e74c3c;font-weight:bold">{_html.escape(str(breach_name))}</td>
        </tr>"""

    risk_color = {"КРИТИЧЕСКИЙ": "#e74c3c", "СРЕДНИЙ": "#e67e22",
                  "НИЗКИЙ": "#f1c40f", "ОТСУТСТВУЕТ": "#2ecc71"}.get(risk_level, "#aaa")
    risk_level_safe = _html.escape(str(risk_level))

    html = f"""
    <html><body style="background:#0d0d0d;font-family:Segoe UI,sans-serif;padding:24px;color:#ccc">
    <div style="max-width:700px;margin:0 auto;background:#141414;border-radius:12px;
                border:1px solid #333;overflow:hidden">

      <div style="background:#1a1a2e;padding:20px 24px;border-bottom:1px solid #333">
        <h1 style="margin:0;color:#fff;font-size:20px">⚠️ Data Leak Sentinel</h1>
        <p style="margin:4px 0 0;color:#888;font-size:13px">
          Отчёт об утечках · {datetime.now().strftime("%d.%m.%Y %H:%M")}
        </p>
      </div>

      <div style="padding:20px 24px">
        <div style="background:#1e1e2e;border-radius:8px;padding:12px 16px;
                    border-left:4px solid {risk_color};margin-bottom:16px">
          <span style="color:{risk_color};font-weight:bold;font-size:15px">
            Уровень угрозы: {risk_level_safe}
          </span>
          <span style="color:#888;font-size:13px;margin-left:12px">
            Score: {risk_score}/100
          </span>
        </div>

        <p style="color:#888;font-size:13px;margin:0 0 12px">
          Обнаружено новых утечек: <strong style="color:#fff">{len(breaches)}</strong>
        </p>

        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#2d4a7a">
              <th style="padding:10px;border:1px solid #333;color:#fff;text-align:left">#</th>
              <th style="padding:10px;border:1px solid #333;color:#fff;text-align:left">Объект</th>
              <th style="padding:10px;border:1px solid #333;color:#fff;text-align:left">Источник</th>
              <th style="padding:10px;border:1px solid #333;color:#fff;text-align:left">Утечка</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>

        <div style="margin-top:20px;padding:12px 16px;background:#1a2a1a;
                    border-radius:8px;border-left:4px solid #2ecc71">
          <p style="margin:0;color:#7ec87e;font-size:13px">
            💡 Рекомендуется немедленно сменить пароли на затронутых сервисах
            и включить двухфакторную аутентификацию.
          </p>
        </div>
      </div>

      <div style="padding:12px 24px;border-top:1px solid #222;text-align:center">
        <p style="margin:0;color:#555;font-size:11px">
          Data Leak Sentinel · Автоматическое уведомление
        </p>
      </div>
    </div>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ Обнаружены утечки данных — {len(breaches)} новых записей"
    msg["From"]    = smtp_user
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "Ошибка авторизации — проверьте логин/пароль"
    except smtplib.SMTPConnectError:
        return False, f"Нет соединения с {smtp_host}:{smtp_port}"
    except Exception as e:
        # Детали в stdout для отладки, но не в UI-лог: SMTP-сервер может
        # вернуть в exception-сообщении логин или другие чувствительные данные.
        print(f"[smtp] send error: {e!r}", flush=True)
        return False, "Ошибка отправки письма"

def test_smtp_connection(smtp_host: str, smtp_port: int,
                         smtp_user: str, smtp_pass: str) -> tuple:
    """Проверяет подключение без отправки письма."""
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=8) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
        return True, "Подключение успешно!"
    except smtplib.SMTPAuthenticationError:
        return False, "Ошибка авторизации"
    except Exception as e:
        print(f"[smtp] test error: {e!r}", flush=True)
        return False, "Ошибка подключения"
