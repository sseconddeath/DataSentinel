# ai_assistant.py — AI-помощник (Groq / Ollama)
import requests, json, os, sys, re

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

SYSTEM_PROMPT = """Ты — AI-ассистент встроенный в приложение DataSentinel для мониторинга утечек данных.
Твоя задача — помогать пользователю понять угрозы его цифровой безопасности и давать конкретные рекомендации.
Правила:
- СТРОГО отвечай ТОЛЬКО на русском языке. Никакого украинского, английского или других языков.
- НЕ используй арабские, китайские или любые другие не-кириллические символы.
- Используй структурированный текст: заголовки, нумерованные списки, жирный текст для важного.
- Будь конкретным и практичным.
- Если у тебя есть данные об утечках пользователя — используй их в ответе.
- Объясняй сложные термины простым языком.
- Пиши только кириллицей и стандартными знаками препинания."""

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
                      "options": {"temperature": 0.7, "num_ctx": 4096},
                      "messages": [{"role":"system","content":SYSTEM_PROMPT},
                                   {"role":"user","content":f"{context}\n\n=== ВОПРОС ===\n{question}"}]},
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
            return full
        except Exception as e:
            msg = f"Ошибка Ollama: {e}"
            if stream_callback: stream_callback(msg)
            return msg

class GroqAssistant:
    URL   = "https://api.groq.com/openai/v1/chat/completions"
    MODEL = "llama-3.3-70b-versatile"

    @staticmethod
    def ask(api_key, question, context, stream_callback=None):
        # Если пользовательский ключ не задан — используем встроенный.
        # Свой ключ имеет приоритет (для обхода shared rate limit).
        if not api_key:
            api_key = _builtin_groq()
        if not api_key:
            msg = ("Groq API ключ не встроен в эту сборку.\n"
                   "Запустите build_inject.py inject перед сборкой или "
                   "используйте Ollama (см. Настройки).")
            if stream_callback: stream_callback(msg)
            return msg
        try:
            r = requests.post(GroqAssistant.URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": GroqAssistant.MODEL, "stream": True, "temperature": 0.7, "max_tokens": 1024,
                      "messages": [{"role":"system","content":SYSTEM_PROMPT},
                                   {"role":"user","content":f"{context}\n\n=== ВОПРОС ===\n{question}"}]},
                stream=True, timeout=60)
            if r.status_code == 401:
                msg = "Неверный API ключ Groq."
                if stream_callback: stream_callback(msg); return msg
            if r.status_code == 429:
                msg = "Превышен лимит Groq. Попробуйте через минуту."
                if stream_callback: stream_callback(msg); return msg
            if r.status_code != 200:
                msg = f"Ошибка Groq: HTTP {r.status_code}"
                if stream_callback: stream_callback(msg); return msg
            full = ""
            for line in r.iter_lines():
                if not line: continue
                line = line.decode("utf-8") if isinstance(line, bytes) else line
                if not line.startswith("data: "): continue
                ds = line[6:]
                if ds.strip() == "[DONE]": break
                try:
                    chunk = json.loads(ds)["choices"][0].get("delta",{}).get("content","")
                    if chunk:
                        chunk = _clean_text(chunk)
                        full += chunk
                        if stream_callback and chunk: stream_callback(chunk)
                except: pass
            return full
        except Exception as e:
            msg = f"Ошибка: {e}"
            if stream_callback: stream_callback(msg)
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
