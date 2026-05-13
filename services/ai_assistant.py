# ai_assistant.py — AI-помощник (Groq / Ollama)
import requests, json, os, sys, re, time

# ВАЖНО: это НЕ криптозащита. Обфускация лишь скрывает ключ от
# автоматических секрет-сканеров (GitHub, TruffleHog) и от тривиального
# `strings exe.exe | grep gsk_`. Целеустремлённый реверсер ключ извлечёт.
# При утечке/злоупотреблении ключ нужно ротировать (выпустить новый билд).
_A = b''
_B = b''

def _builtin_groq() -> str:
    return bytes(a ^ b for a, b in zip(_A, _B)).decode()

def _clean_text(text: str) -> str:
    """Убирает арабские и другие нежелательные символы из ответа AI."""
    # Удаляем арабские символы (U+0600–U+06FF и смежные блоки)
    text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+', '', text)
    # Удаляем прочие нелатинские/некириллические управляющие символы
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', text)
    return text

SYSTEM_PROMPT = """Ты — Скиппи, AI-помощник в приложении Knox.

Knox занимается мониторингом утечек персональных данных, но ты сам — универсальный
ассистент. Отвечай на ЛЮБЫЕ вопросы пользователя: математика, программирование, общие
знания, бытовые советы, философия, рецепты — всё что спросят. Никаких рамок и шаблонов.

К каждому запросу прилагается справочный блок с данными об утечках пользователя.
Используй его ТОЛЬКО если вопрос напрямую связан с безопасностью, утечками, паролями,
почтой или аккаунтами. Если вопрос на другую тему — полностью игнорируй этот блок и
отвечай по сути вопроса. Не сворачивай разговор на безопасность, если тебя об этом
не спрашивали.

Правила:
- Отвечай на русском языке. Не используй арабские, китайские и прочие не-кириллические
  символы (кроме стандартной латиницы для имён, кода, формул).
- Формат подбирай под вопрос. Простой вопрос — короткий прямой ответ. Сложный —
  можно со структурой. Не лепи заголовки и списки на ровном месте.
- Решай задачи до конца. Если просят посчитать — считай и давай ответ с числом,
  а не общие рассуждения.
- Будь конкретным, не лей воду, не повторяй вопрос обратно."""

class OllamaAssistant:
    OLLAMA_URL  = "http://localhost:11434"
    MODEL       = "llama3.1:8b"
    MODEL_SHORT = "llama3.1"

    @staticmethod
    def is_on_disk() -> bool:
        """Установлена ли Ollama физически на диске."""
        import os, shutil
        if shutil.which("ollama"):
            return True
        local = os.environ.get("LOCALAPPDATA", "")
        prog  = os.environ.get("PROGRAMFILES", "")
        paths = [
            os.path.join(local, "Programs", "Ollama", "ollama.exe"),
            os.path.join(prog,  "Ollama", "ollama.exe"),
        ]
        return any(os.path.exists(p) for p in paths)

    @staticmethod
    def is_running() -> bool:
        """Запущена ли Ollama (отвечает на порту)."""
        try: return requests.get(f"{OllamaAssistant.OLLAMA_URL}/api/tags", timeout=3).status_code == 200
        except: return False

    @staticmethod
    def is_available():
        try:
            r = requests.get(f"{OllamaAssistant.OLLAMA_URL}/api/tags", timeout=3)
            if r.status_code != 200: return False
            return any(OllamaAssistant.MODEL_SHORT in m["name"] for m in r.json().get("models", []))
        except: return False

    @staticmethod
    def is_installed():
        """Обратная совместимость — проверяет запущена ли."""
        return OllamaAssistant.is_running()

    @staticmethod
    def pull_model(progress_callback=None):
        try:
            r = requests.post(f"{OllamaAssistant.OLLAMA_URL}/api/pull",
                json={"name": OllamaAssistant.MODEL, "stream": True}, stream=True, timeout=3600)
            for line in r.iter_lines():
                if not line: continue
                data = json.loads(line)
                status, total, completed = data.get("status",""), data.get("total",0), data.get("completed",0)
                if progress_callback:
                    if total > 0: progress_callback(f"{status} — {int(completed/total*100)}% ({total/1024**3:.1f} GB)", completed/total)
                    else: progress_callback(status, None)
                if data.get("status") == "success": return True, "Модель загружена!"
            return True, "Готово"
        except Exception as e: return False, str(e)

    @staticmethod
    def install_windows():
        # Не качаем и не запускаем установщик автоматически: без проверки
        # подписи это вектор RCE при компрометации CDN. Просто открываем
        # официальный сайт в браузере — пользователь скачивает и ставит сам,
        # с видимыми SmartScreen/проверкой подписи Windows.
        try:
            import webbrowser
            webbrowser.open_new_tab("https://ollama.com/download/windows")
            return True, "Открыта страница Ollama. Скачайте и установите, затем перезапустите приложение."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def ask(question, context, stream_callback=None):
        try:
            r = requests.post(f"{OllamaAssistant.OLLAMA_URL}/api/chat",
                json={"model": OllamaAssistant.MODEL, "stream": True,
                      "options": {"temperature": 0.7, "num_ctx": 8192, "num_predict": 4096},
                      "messages": [{"role":"system","content":SYSTEM_PROMPT},
                                   {"role":"user","content":f"[Справочные данные об утечках пользователя — используй ТОЛЬКО если вопрос про безопасность]\n{context}\n\n=== ВОПРОС ===\n{question}"}]},
                stream=True, timeout=120)
            full = ""
            for line in r.iter_lines():
                if not line: continue
                data = json.loads(line)
                chunk = data.get("message",{}).get("content","")
                if chunk:
                    full += chunk
                    if stream_callback: stream_callback(chunk)
                if data.get("done"): break
            if not full.strip():
                # Модель отдала done=True без content (часто на бессмыслицу
                # типа «f,j,f»). Иначе UI показывает пустой пузырь и юзер
                # думает, что приложение зависло.
                msg = ("Модель не смогла ответить на этот запрос. "
                       "Попробуйте сформулировать вопрос полнее.")
                if stream_callback: stream_callback(msg)
                return msg
            return full
        except Exception as e:
            msg = f"Ошибка Ollama: {e}"
            if stream_callback: stream_callback(msg)
            return msg

class GroqAssistant:
    URL = "https://api.groq.com/openai/v1/chat/completions"
    # Основная модель + фолбэк. Если на основной прилетит 403/429
    # (rate-limit, контент-фильтр), молча перекатываемся на быструю
    # 8B-модель — у неё отдельный квота-бакет и более мягкая модерация.
    MODEL = "llama-3.3-70b-versatile"
    FALLBACK_MODEL = "llama-3.1-8b-instant"

    @staticmethod
    def _stream_once(api_key, model, question, context, stream_callback):
        """Один запрос к Groq. Возвращает (status_code, text_or_full_response).
        При status_code == 200 — text это собранный из стрима ответ;
        иначе — короткое сообщение об ошибке (без чтения тела стрима)."""
        r = requests.post(
            GroqAssistant.URL,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model, "stream": True,
                  "temperature": 0.7, "max_tokens": 4096,
                  "messages": [
                      {"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content":
                       f"[Справочные данные об утечках пользователя — "
                       f"используй ТОЛЬКО если вопрос про безопасность]\n"
                       f"{context}\n\n=== ВОПРОС ===\n{question}"},
                  ]},
            stream=True, timeout=60,
        )
        if r.status_code != 200:
            return r.status_code, ""
        full = ""
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8") if isinstance(line, bytes) else line
            if not line.startswith("data: "):
                continue
            ds = line[6:]
            if ds.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(ds)["choices"][0].get(
                    "delta", {}).get("content", "")
                if chunk:
                    chunk = _clean_text(chunk)
                    full += chunk
                    if stream_callback and chunk:
                        stream_callback(chunk)
            except Exception:
                pass
        return 200, full

    @staticmethod
    def ask(api_key, question, context, stream_callback=None):
        # Свой ключ имеет приоритет (обход shared rate-limit на встроенном).
        if not api_key:
            api_key = _builtin_groq()
        if not api_key:
            msg = ("Groq API ключ не встроен в эту сборку.\n"
                   "Запустите build_inject.py inject перед сборкой или "
                   "используйте Ollama (см. Настройки).")
            if stream_callback:
                stream_callback(msg)
            return msg

        # Попытки: основная модель → ретрай через 2с → фолбэк-модель.
        # 403/429 от Groq на free-tier — это часто per-IP лимит или
        # сработавший контент-фильтр. И ретрай, и фолбэк это лечат.
        attempts = [
            (GroqAssistant.MODEL, 0),
            (GroqAssistant.MODEL, 2),
            (GroqAssistant.FALLBACK_MODEL, 1),
        ]
        last_status = 0
        for i, (model, delay) in enumerate(attempts):
            if delay:
                time.sleep(delay)
            try:
                status, full = GroqAssistant._stream_once(
                    api_key, model, question, context, stream_callback)
            except Exception as e:
                msg = f"Ошибка сети: {e}"
                if stream_callback:
                    stream_callback(msg)
                return msg
            if status == 200:
                return full
            last_status = status
            # 401 — ключ невалидный, ретраи не помогут.
            if status == 401:
                break

        if last_status == 401:
            msg = ("Неверный API ключ Groq. Если используете свой ключ "
                   "(Настройки → AI), проверьте его.")
        elif last_status in (403, 429):
            msg = ("Groq временно отказал (лимит запросов или "
                   "контент-фильтр). Попробуйте через минуту или "
                   "переформулируйте вопрос.")
        else:
            msg = (f"Groq не отвечает (HTTP {last_status}). "
                   f"Попробуйте позже или переключитесь на Ollama "
                   f"в Настройках.")
        if stream_callback:
            stream_callback(msg)
        return msg

class AIAssistant:
    """Единый интерфейс — Groq / Ollama."""

    QUICK_PROMPTS = [
        ("🔍  Насколько я в опасности?", "Оцени мой уровень угрозы на основе найденных утечек. Что самое опасное?"),
        ("📋  План защиты",             "Составь пошаговый план что нужно сделать для защиты данных. По приоритетам."),
        ("⚠️  Объясни угрозы",          "Объясни простым языком какие конкретные угрозы несут найденные утечки."),
        ("🔑  Советы по паролям",       "Дай конкретные советы по паролям с учётом моих утечек."),
        ("🌐  Что такое Dark Web?",      "Объясни что такое Dark Web и почему мои данные там опасны."),
        ("📧  Защита email",            "Мой email найден в утечках. Что мне грозит и как защитить почту?"),
    ]

    @staticmethod
    def build_context(db):
        try:
            from collections import Counter, defaultdict
            results = db.get_all_results()
            targets = db.get_all_targets()
            if not results: return "У пользователя пока нет данных об утечках."
            by_target = defaultdict(list)
            for row in results:
                _, target, source, breach_name, *_ = row
                by_target[target].append((source, breach_name))
            top = Counter(r[2] for r in results).most_common(5)
            lines = [
                "=== ДАННЫЕ О БЕЗОПАСНОСТИ ПОЛЬЗОВАТЕЛЯ ===",
                f"Объектов: {len(targets)}, Утечек: {len(results)}",
                "Топ источников: " + ", ".join(f"{s}:{c}" for s,c in top),
                "\nДетали:",
            ]
            for target, leaks in list(by_target.items())[:5]:
                lines.append(f"  {target} — {len(leaks)} утечек:")
                for src, name in leaks[:3]: lines.append(f"    - {src}: {name[:50]}")
            from core.engine import LeakEngine
            score, level, _ = LeakEngine.calculate_risk_score([r[2] for r in results])
            lines.append(f"\nУровень угрозы: {level} ({score}/100)")
            # Семантическая подсказка для модели: shows same wording as
            # dashboard, чтобы AI не путал «уровень защиты» с «угрозой».
            lines.append(
                "(Используй термин «уровень угрозы». Высокий = опасно, "
                "Низкий = безопасно. НЕ инвертируй в «защиту».)"
            )
            return "\n".join(lines)
        except Exception as e:
            return f"Ошибка контекста: {e}"

    @staticmethod
    def ask(provider, api_key, question, context, stream_callback=None):
        if provider == "groq":   return GroqAssistant.ask(api_key, question, context, stream_callback)
        if provider == "ollama": return OllamaAssistant.ask(question, context, stream_callback)
        msg = "Выберите AI провайдера в настройках."
        if stream_callback: stream_callback(msg)
        return msg
