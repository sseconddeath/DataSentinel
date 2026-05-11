"""
build_inject.py — управление встраиванием API-ключей в сборку.

Использование:
    python build_inject.py inject    — прочитать ключи из secrets.local,
                                       сгенерировать случайные _B-байты,
                                       вычислить _A = key XOR _B,
                                       записать пары в соответствующие файлы
    python build_inject.py restore   — заменить все пары на пустые b''

build.bat вызывает inject перед PyInstaller и restore после.

secrets.local НЕ коммитится в git (gitignored). Формат:
    GROQ_API_KEY=gsk_xxxxxxxxxxxx
    RAPIDAPI_KEY=xxxxxxxxxxxxxxxxxxx
    INTELX_API_KEY=xxxxxxxxxxxxxxxxxxx

Это НЕ криптозащита: даже после обфускации ключи извлекаются реверсом .exe.
Цель — чтобы ключи не лежали открыто в публичном git-репо.
"""
import os, re, sys, secrets as _secrets

SECRETS_FILE = "secrets.local"

# Описание встраиваемых ключей: какой ключ из secrets.local идёт в какой файл и в какие переменные.
INJECTIONS = [
    {"key": "GROQ_API_KEY",   "file": os.path.join("services", "ai_assistant.py"), "vars": ("_A",  "_B")},
    {"key": "RAPIDAPI_KEY",   "file": os.path.join("core",     "engine.py"),        "vars": ("_RA", "_RB")},
    {"key": "INTELX_API_KEY", "file": os.path.join("core",     "engine.py"),        "vars": ("_IA", "_IB")},
]


def _read_secrets() -> dict:
    if not os.path.exists(SECRETS_FILE):
        sys.exit(
            f"ERROR: {SECRETS_FILE} не найден.\n"
            f"Создайте его рядом с build_inject.py со строками:\n"
            f"  GROQ_API_KEY=gsk_xxxxxxxxxxxx\n"
            f"  RAPIDAPI_KEY=xxxxxxxxxxxxxxxxxxx\n"
            f"  INTELX_API_KEY=xxxxxxxxxxxxxxxxxxx\n"
            f"(см. secrets.local.example)"
        )
    out = {}
    with open(SECRETS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, val = line.partition("=")
            out[name.strip()] = val.strip().strip('"').strip("'")
    return out


def _obfuscate(key: str) -> tuple[bytes, bytes]:
    raw = key.encode("utf-8")
    b = _secrets.token_bytes(len(raw))
    a = bytes(x ^ y for x, y in zip(raw, b))
    return a, b


def _write_var(text: str, var: str, value: bytes) -> tuple[str, int]:
    """Заменяет в исходном тексте строку '<var> = ...' на '<var> = <repr(value)>'."""
    # lambda-replacement: \xNN в repr(bytes) иначе парсится как regex-escape
    pat = re.compile(r"^" + re.escape(var) + r"\s*=\s*.*$", re.MULTILINE)
    return pat.subn(lambda m: f"{var} = {repr(value)}", text, count=1)


def _apply_to_file(file: str, updates: list[tuple[str, bytes]]) -> None:
    """updates — список (var_name, value_bytes), все применяются к одному файлу."""
    with open(file, "r", encoding="utf-8") as f:
        text = f.read()
    for var, value in updates:
        text, n = _write_var(text, var, value)
        if n != 1:
            sys.exit(f"ERROR: переменная '{var}' не найдена в {file}")
    with open(file, "w", encoding="utf-8") as f:
        f.write(text)


def cmd_inject() -> None:
    secrets = _read_secrets()
    # Группируем обновления по файлу: некоторые файлы получают несколько пар (engine.py — две).
    per_file: dict[str, list[tuple[str, bytes]]] = {}
    summary = []
    for inj in INJECTIONS:
        key = secrets.get(inj["key"], "")
        if not key:
            print(f"[inject] WARN — {inj['key']} в {SECRETS_FILE} пустой → {inj['vars']} останутся stub")
            a_bytes, b_bytes = b"", b""
        else:
            a_bytes, b_bytes = _obfuscate(key)
            summary.append(f"{inj['key']}({len(key)} chars) -> {inj['file']}:{inj['vars']}")
        per_file.setdefault(inj["file"], []).extend([
            (inj["vars"][0], a_bytes),
            (inj["vars"][1], b_bytes),
        ])
    for file, updates in per_file.items():
        _apply_to_file(file, updates)
    for s in summary:
        print(f"[inject] OK — {s}")


def cmd_restore() -> None:
    per_file: dict[str, list[tuple[str, bytes]]] = {}
    for inj in INJECTIONS:
        per_file.setdefault(inj["file"], []).extend([
            (inj["vars"][0], b""),
            (inj["vars"][1], b""),
        ])
    for file, updates in per_file.items():
        _apply_to_file(file, updates)
        print(f"[restore] OK — {file} приведён к stub-состоянию")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("inject", "restore"):
        sys.exit("Usage: python build_inject.py [inject|restore]")
    {"inject": cmd_inject, "restore": cmd_restore}[sys.argv[1]]()
