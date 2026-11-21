# hydra-mark4 — финальный код

````text
hydra-mark4/
├── .github/
│   └── workflows/
│       └── hydra.yml
├── tests/
│   ├── test_ai.py
│   ├── test_base_h.py
│   └── test_dsl.py
├── .gitignore
├── README.md
├── ai.py
├── base_h.py
├── github_client.py
├── hydra_dsl.py
├── main.py
└── requirements.txt

analyzer.py — удалить (логика перенесена в base_h.py)
````

## Корень репозитория

### `README.md`

````markdown
# hydra-mark4 (Прот4)

Помощник для GitHub: читает issue или текст ошибки, находит вероятную причину, место в коде и способ исправить.
Код сам не меняет.

```
текст / issue ──► AI Base (ai.py) ──► Hydra DSL ──► Base H (base_h.py) ──► отчёт / комментарий
                  OpenAI или правила                локально, без AI
```

## Структура

```
hydra-mark4/
├── .github/workflows/hydra.yml   авто-разбор новых issue
├── tests/                        test_dsl.py, test_base_h.py, test_ai.py
├── main.py                       точка входа (CLI)
├── ai.py                         AI Base: текст -> команды DSL
├── hydra_dsl.py                  парсер и сборщик DSL
├── base_h.py                     Base H: выполнение DSL
├── github_client.py              GitHub API: issue и комментарии
├── requirements.txt
└── .gitignore
```

## Установка

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
```

Ключ OpenAI — только через переменную `OPENAI_API_KEY` (секрет Codespaces / Actions). Без ключа всё работает на правилах.

| Переменная | Зачем | По умолчанию |
|---|---|---|
| `OPENAI_API_KEY` | ключ OpenAI | — (без него режим правил) |
| `HYDRA_AI_PROVIDER` | `openai` или `rules` | `openai` |
| `HYDRA_MODEL` | модель OpenAI | `gpt-5.6-terra` |
| `GITHUB_TOKEN` | доступ к issue | есть в Codespaces и Actions |

## Команды

```bash
python main.py ask "ModuleNotFoundError: No module named 'requests'"
python main.py ask -f error.log
python main.py run "ANALYZE python error=NameError message=\"name 'x' is not defined\" file=main.py line=3"
python main.py issue 12             # только показать
python main.py issue 12 --post      # опубликовать комментарий
```

Флаги: `--json` (сырой JSON), `--no-ai` (без AI), `--show-dsl` (показать команды DSL).

## Hydra DSL

`<OPERATION> <TARGET> [key=value ...]`, значения с пробелами — в двойных кавычках.

| Команда | Что делает |
|---|---|
| `ANALYZE <python\|javascript\|unknown> error=Тип message="..." file="путь" line=N` | причина и шаги исправления |
| `SEARCH <project\|logs> query="текст"` | поиск по файлам проекта (`logs` — по .log/.out/.txt) |
| `INSPECT file path="путь" line=N context=N` | кусок файла вокруг строки |

Base H не читает файлы вне проекта, `.env*`, ключи (`.pem`, `.key`) и папку `.git`.

## Авто-комментарии в issue

1. Settings → Secrets and variables → Actions → New repository secret: `OPENAI_API_KEY` (необязательно).
2. Новый issue → Actions запускает `hydra.yml` → в issue появляется комментарий.
3. Повторный запуск вручную: Actions → Hydra → Run workflow → номер issue.
````

### `requirements.txt`

````text
openai>=1.66
````

### `.gitignore`

````text
__pycache__/
*.pyc
.venv/
venv/
.env
.env.*
````

### `main.py`

````python
"""Hydra-mark4 — точка входа.

  python main.py ask "текст ошибки"            AI Base -> DSL -> Base H
  python main.py ask -f error.log              то же, текст из файла
  python main.py run "ANALYZE python error=X"  DSL сразу в Base H (без AI)
  python main.py issue 12 [--post]             разбор GitHub issue (+ комментарий)

Флаги для всех команд: --json  --no-ai  --show-dsl
"""
import argparse
import json
import re
import sys
from pathlib import Path

import ai
import base_h
import github_client
from hydra_dsl import DSLError, parse_command

CONFIDENCE = {"high": "высокая", "medium": "средняя", "low": "низкая"}


def analyze_text(text, use_ai=True):
    """Текст -> AI Base -> команды DSL -> Base H -> (отчёт, список DSL)."""
    commands, info = ai.translate(text, provider=None if use_ai else "rules")
    for warning in info["warnings"]:
        print(f"! {warning}", file=sys.stderr)
    report = base_h.run(commands)
    report["provider"] = info["provider"]
    return report, info["dsl"]


def to_markdown(report, title="Hydra: разбор проблемы"):
    out = [f"## {title}", "", f"**Что случилось:** {report['what_happened']}", ""]
    if report["where"]:
        out.append("**Где:**")
        for loc in report["where"]:
            place = f"`{loc['file']}:{loc['line']}`" if loc.get("line") else f"`{loc['file']}`"
            out.append(f"- {place} — `{loc['text'].replace('`', chr(39))}`" if loc.get("text") else f"- {place}")
            if loc.get("snippet"):
                out += ["", "````", loc["snippet"], "````", ""]
        out.append("")
    if report.get("why"):
        out += [f"**Почему:** {report['why']}", ""]
    out.append("**Как исправить:**")
    out += [f"{i}. {step}" for i, step in enumerate(report["how_to_fix"], 1)]
    out += ["", f"**Уверенность:** {CONFIDENCE.get(report['confidence'], report['confidence'])}"]
    if report.get("errors"):
        out += ["", "**Не выполнено:** " + "; ".join(report["errors"])]
    if report.get("provider"):
        out += ["", f"<sub>hydra-mark4 · Base H · команды: {report['provider']}</sub>"]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def _read_text(args):
    if args.file:
        return Path(args.file).read_text(encoding="utf-8", errors="replace")
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError('нужен текст: python main.py ask "..." или -f файл')


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="вывести сырой JSON")
    common.add_argument("--no-ai", action="store_true", help="не вызывать AI, только правила")
    common.add_argument("--show-dsl", action="store_true", help="показать команды DSL")

    parser = argparse.ArgumentParser(prog="main.py", description="Hydra-mark4: AI Base -> Hydra DSL -> Base H")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", parents=[common], help="разобрать текст ошибки")
    p.add_argument("text", nargs="?", help="текст ошибки (или -f файл, или stdin)")
    p.add_argument("-f", "--file", help="взять текст из файла")

    p = sub.add_parser("run", parents=[common], help="выполнить команды DSL напрямую (без AI)")
    p.add_argument("commands", nargs="+", help='например: "ANALYZE python error=NameError"')

    p = sub.add_parser("issue", parents=[common], help="разобрать GitHub issue")
    p.add_argument("number", type=int, help="номер issue")
    p.add_argument("--repo", help="owner/name (по умолчанию $GITHUB_REPOSITORY)")
    p.add_argument("--post", action="store_true", help="опубликовать результат комментарием")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    repo = None
    try:
        if args.cmd == "run":
            commands = [c for c in (parse_command(line) for line in args.commands) if c]
            report, dsl = base_h.run(commands), args.commands
            report["provider"] = "DSL напрямую"
        elif args.cmd == "ask":
            report, dsl = analyze_text(_read_text(args), use_ai=not args.no_ai)
        else:
            repo = github_client.resolve_repo(args.repo)
            issue = github_client.get_issue(repo, args.number)
            report, dsl = analyze_text(f"{issue['title']}\n\n{issue['body']}", use_ai=not args.no_ai)
    except DSLError as exc:
        print(f"Ошибка DSL: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except github_client.GitHubError as exc:
        print(f"GitHub: {exc}", file=sys.stderr)
        return 1

    if args.show_dsl:
        print("DSL:\n  " + "\n  ".join(dsl or ["(нет команд)"]), file=sys.stderr)
    body = to_markdown(report)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else body)

    if args.cmd == "issue" and args.post:
        try:
            url = github_client.post_comment(repo, args.number, body.replace("@", "@​"))
        except github_client.GitHubError as exc:
            print(f"GitHub: комментарий не опубликован: {exc}", file=sys.stderr)
            return 1
        print(f"Комментарий опубликован: {url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
````

### `ai.py`

````python
"""AI Base — перевод текста на естественном языке в команды Hydra DSL.

Провайдер: переменная HYDRA_AI_PROVIDER = openai (по умолчанию) | rules
  openai — модель HYDRA_MODEL (по умолчанию gpt-5.6-terra), ключ только из OPENAI_API_KEY
  rules  — локальные правила без AI; включаются сами, если ключа нет или AI не ответил
Base H про провайдера ничего не знает: на выходе всегда команды DSL.
"""
import os
import re

from hydra_dsl import build_command, parse_lines

DEFAULT_MODEL = "gpt-5.6-terra"
MAX_COMMANDS = 5
MAX_INPUT_CHARS = 6000

SYSTEM_PROMPT = """You convert a bug report into Hydra DSL commands for a local code analyzer.
Reply with commands only: one per line, at most 5, no prose, no markdown.

Syntax: OPERATION TARGET key=value ...   (wrap values containing spaces in double quotes)
ANALYZE <python|javascript|unknown> error=<ErrorType> message="<error message>" file="<path>" line=<n>
SEARCH <project|logs> query="<text to find in repository files>"
INSPECT file path="<path>" line=<n>

Rules:
- If the report contains an error, start with exactly one ANALYZE. Take error type and message from the final error line; file and line from the last traceback frame that belongs to the user's project (not site-packages, node_modules or the standard library). Omit file/line if unknown.
- Add SEARCH for an undefined name, missing attribute, failed import name or missing key (query = that name). Do not SEARCH for missing modules or file paths.
- Use INSPECT only for files explicitly named in the report. Never invent paths.
- If there is no error, use SEARCH/INSPECT for names and files mentioned in the report.

Example:
ANALYZE python error=NameError message="name 'greet' is not defined" file="main.py" line=3
SEARCH project query="greet"
"""

ERR_RE = re.compile(r"\b(?:[A-Za-z_]\w*\.)*([A-Z]\w*(?:Error|Exception))\b(?:[ \t]*:[ \t]*([^\n]*))?")
PY_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)')
JS_FRAME_RE = re.compile(r"([\w./\\-]+\.(?:js|mjs|cjs|ts|jsx|tsx)):(\d+)(?::\d+)?")
EXTERNAL_RE = re.compile(r"site-packages|dist-packages|node_modules|node:internal|^<|[/\\]lib[/\\]python3")
FILE_RE = re.compile(r"(?<![\w/.-])([\w./-]+\.(?:py|js|ts|jsx|tsx|html|css|json|ya?ml|toml))\b")
CODE_RE = re.compile(r"`([^`\n]{2,60})`")
JS_ONLY = {"ReferenceError", "RangeError", "EvalError", "URIError"}
TERM_PATTERNS = (  # модули и пути Base H проверяет сам, поиск нужен для имён
    r"cannot import name '(\w+)'",
    r"name '(\w+)' is not defined",
    r"has no attribute '(\w+)'",
    r"^(\w+) is not defined",
    r"\(reading '(\w+)'\)",
)


class _NoKey(Exception):
    pass


def translate(text, provider=None):
    """Текст -> (команды DSL в виде dict, info{provider, dsl, warnings})."""
    text = text or ""
    if not text.strip():
        return [], {"provider": "rules", "dsl": [], "warnings": ["пустой текст"]}
    provider = (provider or os.environ.get("HYDRA_AI_PROVIDER") or "openai").strip().lower()
    warnings = []
    if provider == "openai":
        try:
            commands = _from_openai(text)
            if commands:
                return commands, _info(f"openai/{_model()}", commands, warnings)
            warnings.append("AI не вернул ни одной корректной команды — использую правила")
        except _NoKey:
            warnings.append("OPENAI_API_KEY не найден — работаю без AI (правила)")
        except ImportError:
            warnings.append("пакет openai не установлен (pip install -r requirements.txt) — использую правила")
        except Exception as exc:  # сеть, лимиты, неверная модель — Base H всё равно должен отработать
            warnings.append(f"AI недоступен ({type(exc).__name__}: {str(exc)[:200]}) — использую правила")
    elif provider != "rules":
        warnings.append(f"неизвестный провайдер '{provider}' — использую правила")
    commands, _ = parse_lines("\n".join(rules_translate(text)))
    return commands[:MAX_COMMANDS], _info("rules", commands[:MAX_COMMANDS], warnings)


def _info(provider, commands, warnings):
    dsl = [build_command(c["operation"], c["target"], c["params"]) for c in commands]
    return {"provider": provider, "dsl": dsl, "warnings": warnings}


def _model():
    return os.environ.get("HYDRA_MODEL", "").strip() or DEFAULT_MODEL


def _clip(text):
    if len(text) <= MAX_INPUT_CHARS:
        return text
    head = MAX_INPUT_CHARS // 3
    return text[:head] + "\n...\n" + text[-(MAX_INPUT_CHARS - head):]


def _from_openai(text):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise _NoKey
    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=60, max_retries=1)
    response = client.responses.create(model=_model(), instructions=SYSTEM_PROMPT, input=_clip(text))
    commands, _ = parse_lines(getattr(response, "output_text", "") or "")
    return commands[:MAX_COMMANDS]


# ---------- правила без AI ----------

def rules_translate(text):
    """Текст -> список строк DSL по регулярным выражениям."""
    text = text or ""
    commands = []
    matches = list(ERR_RE.finditer(text))
    if matches:
        last = matches[-1]
        error = last.group(1)
        message = (last.group(2) or "").strip().strip("`").strip()[:200]
        lang = _language(text, error)
        path, line = _location(text, lang)
        commands.append(build_command("ANALYZE", lang, {"error": error, "message": message, "file": path, "line": line}))
        term = _search_term(error, message)
        if term:
            commands.append(build_command("SEARCH", "project", {"query": term}))
    else:
        for path in dict.fromkeys(FILE_RE.findall(text)):
            commands.append(build_command("INSPECT", "file", {"path": path}))
        for term in dict.fromkeys(CODE_RE.findall(text)):
            commands.append(build_command("SEARCH", "project", {"query": term}))
        if not commands:
            commands.append(build_command("ANALYZE", "unknown", {"message": " ".join(text.split())[:200]}))
    return commands[:MAX_COMMANDS]


def _language(text, error):
    if "Traceback (most recent call last)" in text or PY_FRAME_RE.search(text):
        return "python"
    if error in JS_ONLY or JS_FRAME_RE.search(text) or "Uncaught" in text or "Cannot read propert" in text:
        return "javascript"
    return "python" if error else "unknown"


def _location(text, lang):
    frames = JS_FRAME_RE.findall(text) if lang == "javascript" else PY_FRAME_RE.findall(text)[::-1]
    own = [f for f in frames if not EXTERNAL_RE.search(f[0])]
    return (own or frames or [(None, None)])[0]


def _search_term(error, message):
    for pattern in TERM_PATTERNS:
        m = re.search(pattern, message)
        if m:
            return m.group(1)
    if error == "KeyError":
        key = message.strip().strip("'\"")
        if re.fullmatch(r"[\w.-]{1,60}", key):
            return key
    return None
````

### `hydra_dsl.py`

````python
"""Hydra DSL — разбор и сборка команд.

Синтаксис:  <OPERATION> <TARGET> [key=value ...]
Значения с пробелами — в двойных кавычках:  query="где analyze_text"

Операции (выполняет Base H):
  ANALYZE <python|javascript|unknown> error=<Тип> [message="..."] [file="путь"] [line=N]
  SEARCH  <project|logs> query="текст"
  INSPECT file path="путь" [line=N] [context=N]
"""
import re
import shlex

OPERATIONS = ("ANALYZE", "SEARCH", "INSPECT")
_BARE = re.compile(r"[\w./:-]+")
_LIST_PREFIX = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")


class DSLError(ValueError):
    """Строка не является корректной командой Hydra DSL."""


def parse_command(command):
    """'ANALYZE python error=X' -> {'operation': 'ANALYZE', 'target': 'python', 'params': {'error': 'X'}}"""
    if not command or not command.strip():
        return None
    try:
        parts = shlex.split(command.strip())
    except ValueError as exc:  # незакрытая кавычка
        raise DSLError(f"не удалось разобрать '{command.strip()}': {exc}") from None
    if not parts:
        return None
    operation, target, params = parts[0].upper(), None, {}
    for token in parts[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            params[key.strip().lower()] = value
        elif target is None:
            target = token
        else:
            raise DSLError(f"лишний аргумент без '=': {token}")
    return {"operation": operation, "target": target, "params": params}


def quote(value):
    """Значение -> токен DSL (в кавычках, если нужно)."""
    text = " ".join(str(value).split())
    if _BARE.fullmatch(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_command(operation, target=None, params=None):
    """('ANALYZE', 'python', {'error': 'X'}) -> 'ANALYZE python error=X'. Пустые значения пропускаются."""
    parts = [operation.upper()]
    if target:
        parts.append(quote(target))
    for key, value in (params or {}).items():
        if value is not None and str(value).strip():
            parts.append(f"{key}={quote(value)}")
    return " ".join(parts)


def parse_lines(text):
    """Многострочный текст (например, ответ AI) -> (команды, отклонённые строки)."""
    commands, rejected = [], []
    for raw in (text or "").splitlines():
        line = _LIST_PREFIX.sub("", raw.strip().strip("`").strip())
        if not line or line.startswith("#"):
            continue
        if line.split(None, 1)[0].upper() not in OPERATIONS:
            rejected.append(raw)
            continue
        try:
            commands.append(parse_command(line))
        except DSLError:
            rejected.append(raw)
    return commands, rejected
````

### `base_h.py`

````python
"""Base H — локальное выполнение команд Hydra DSL. Работает без AI и без сети.

  execute(command) -> результат одной команды (команда из hydra_dsl.parse_command)
  run(commands)    -> итог: what_happened / where / why / how_to_fix / confidence
"""
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build"}
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".html", ".css", ".json",
            ".toml", ".cfg", ".ini", ".yml", ".yaml", ".txt", ".sh"}
SOURCE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"}
LOG_EXT = {".log", ".out", ".txt"}
PRIVATE_EXT = {".pem", ".key", ".p12", ".pfx"}
MAX_FILE_BYTES = 1_000_000
MAX_HITS = 20

PIP_NAMES = {"cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml", "sklearn": "scikit-learn",
             "bs4": "beautifulsoup4", "dotenv": "python-dotenv", "dateutil": "python-dateutil", "jwt": "pyjwt"}
KNOWN_MODULES = set(sys.stdlib_module_names) | {"requests", "numpy", "pandas", "openai", "flask", "django"}
PY_LITERALS = {"null": "None", "true": "True", "false": "False"}
TERMINAL_LINE = re.compile(r"^\s*(?:EOF\b|cat\s+>|python3?\s+-c\b|pip3?\s+install\b|git\s+\w|\$\s)")

PY_ERRORS = {
    "ModuleNotFoundError": ("Python не нашёл модуль: пакет не установлен в текущем окружении или имя написано с ошибкой.",
                            ["Установи пакет: `pip install <имя>`", "Добавь пакет в requirements.txt",
                             "Если это модуль проекта — запускай из корня репозитория"]),
    "ImportError": ("Модуль найден, но нужного имени в нём нет, либо импорт циклический.",
                    ["Проверь, что имя действительно есть в модуле", "Проверь версию пакета: `pip show <пакет>`",
                     "При циклическом импорте перенеси import внутрь функции"]),
    "NameError": ("Используется имя, которое не определено в этой области видимости.",
                  ["Проверь опечатку в имени", "Определи переменную/функцию до использования", "Добавь недостающий import"]),
    "UnboundLocalError": ("Локальная переменная используется до присваивания (часто присваивание только внутри if/цикла).",
                          ["Присвой переменной значение до if/цикла", "Нужна внешняя переменная — передай её аргументом"]),
    "TypeError": ("Функция или операция получила значение не того типа или не то число аргументов.",
                  ["Выведи тип: `print(type(x))`", "Сверь аргументы с сигнатурой функции",
                   "Приведи тип явно: `int()`, `str()`, `list()`"]),
    "ValueError": ("Тип значения правильный, но само значение недопустимо.",
                   ["Проверь входные данные перед преобразованием", "Оберни преобразование в `try/except ValueError`"]),
    "IndexError": ("Обращение к индексу за пределами списка или строки.",
                   ["Проверь длину: `len(x)`", "Убедись, что список не пустой перед `x[0]`"]),
    "KeyError": ("В словаре нет такого ключа.",
                 ["Используй `d.get(key)` со значением по умолчанию", "Проверь наличие: `if key in d`",
                  "Выведи ключи: `print(d.keys())`"]),
    "AttributeError": ("У объекта нет такого атрибута или метода; часто объект оказался `None`.",
                       ["Проверь тип объекта: `print(type(obj))`", "Проверь опечатку в имени атрибута",
                        "Убедись, что функция, вернувшая объект, не вернула `None`"]),
    "SyntaxError": ("Код нарушает синтаксис Python — файл не запускается вообще.",
                    ["Открой указанную строку и строку перед ней", "Проверь скобки, кавычки и двоеточия",
                     "Удали из файла посторонние строки (например, команды терминала)"]),
    "IndentationError": ("Неправильные отступы.",
                         ["Используй 4 пробела на уровень, без табов", "Проверь отступ строки и блока над ней"]),
    "TabError": ("В отступах смешаны табы и пробелы.", ["Замени табы на 4 пробела во всём файле"]),
    "FileNotFoundError": ("Файл или папка по пути не существует (или путь считается от другой папки).",
                          ["Проверь путь и текущую папку: `pwd`", "Строй путь от файла: `Path(__file__).parent / 'имя'`"]),
    "PermissionError": ("Нет прав на чтение/запись файла или папки.",
                        ["Проверь права: `ls -l`", "Пиши в папку проекта, а не в системные папки"]),
    "ZeroDivisionError": ("Деление на ноль.", ["Проверь делитель перед делением: `if b != 0`"]),
    "RecursionError": ("Функция вызывает сама себя без условия выхода.",
                       ["Добавь или исправь условие выхода из рекурсии", "Замени рекурсию циклом"]),
    "JSONDecodeError": ("Строка не является корректным JSON (часто пустой ответ или HTML вместо JSON).",
                        ["Выведи сырой текст перед `json.loads`", "Проверь код ответа сервера и что ответ не пустой"]),
    "UnicodeDecodeError": ("Файл прочитан не в той кодировке.",
                           ["Открой файл с `encoding='utf-8'`", "Для неизвестной кодировки добавь `errors='replace'`"]),
}
JS_ERRORS = {
    "ReferenceError": ("Используется переменная, которая не объявлена.",
                       ["Проверь опечатку", "Объяви переменную через `let`/`const` до использования",
                        "Проверь import или подключение скрипта"]),
    "TypeError": ("Значение не того типа; чаще всего обращение к свойству `undefined` или `null`.",
                  ["Проверь значение перед обращением: `obj?.prop`", "Выведи значение: `console.log(obj)`",
                   "Убедись, что данные уже загружены (async/await)"]),
    "SyntaxError": ("Код нарушает синтаксис JavaScript (или JSON.parse получил не JSON).",
                    ["Открой указанную строку", "Проверь скобки, запятые и кавычки"]),
    "RangeError": ("Значение вне допустимого диапазона (часто бесконечная рекурсия).",
                   ["Проверь условие выхода из рекурсии", "Проверь размеры массивов и числа"]),
}


# ---------- файлы ----------

def _root(root):
    return Path(root or os.getcwd()).resolve()


def _is_private(rel):
    return rel.name.startswith(".env") or rel.suffix.lower() in PRIVATE_EXT or any(p in SKIP_DIRS for p in rel.parts)


def _locate(root, path):
    """Путь из команды/traceback -> файл внутри проекта или None. За пределы root не выходит."""
    if not path:
        return None
    parts = Path(str(path).strip().replace("\\", "/")).parts
    for i in range(len(parts)):
        cand = root.joinpath(*parts[i:]).resolve()
        if cand.is_relative_to(root) and cand.is_file() and not _is_private(cand.relative_to(root)):
            return cand
    return None


def _iter_files(root, exts=None):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not (d.startswith(".") and d != ".github"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root)
            if (exts is None or path.suffix.lower() in exts) and not _is_private(rel) \
                    and path.resolve().is_relative_to(root):
                yield path, rel


def _read_lines(path, strict=True):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        if strict:
            return path.read_text(encoding="utf-8").splitlines()
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def _snippet(lines, line=None, context=3, head=40):
    if line and 1 <= line <= len(lines):
        start, end = max(1, line - context), min(len(lines), line + context)
    else:
        start, end = 1, min(len(lines), head)
    width = len(str(end))
    return "\n".join(f"{'>' if n == line else ' '} {n:>{width}} | {lines[n - 1]}" for n in range(start, end + 1))


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _norm(name):
    return name.strip().lower().replace("_", "-")


def _requirements(root):
    path = root / "requirements.txt"
    if not path.is_file():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(_norm(re.split(r"[<>=!~\[;@ ]", line, maxsplit=1)[0]))
    return names


def _definitions(root, name, limit=5):
    n = re.escape(name)
    pattern = re.compile(rf"^\s*(?:async\s+def|def|class|function|let|const|var)\s+{n}\b|^\s*{n}\s*(?::[^=]*)?=(?!=)")
    found = []
    for path, rel in _iter_files(root, SOURCE_EXT):
        for i, text in enumerate(_read_lines(path) or [], 1):
            if pattern.search(text):
                found.append({"file": rel.as_posix(), "line": i, "text": text.strip()[:200]})
                if len(found) >= limit:
                    return found
    return found


def _error(message):
    return {"status": "error", "message": message}


# ---------- операции ----------

def _search(root, target, params):
    query = (params.get("query") or params.get("type") or "").strip()
    if not query:
        return _error('SEARCH: нужен параметр query="..."')
    exts = LOG_EXT if (target or "").lower() == "logs" else CODE_EXT
    # имя переменной/функции ищем целым словом, остальное — подстрокой
    if re.fullmatch(r"\w+", query):
        word = re.compile(rf"\b{re.escape(query)}\b", re.IGNORECASE)
        match = word.search
    else:
        needle = query.lower()
        match = lambda text: needle in text.lower()  # noqa: E731
    hits, total = [], 0
    for path, rel in _iter_files(root, exts):
        for i, text in enumerate(_read_lines(path) or [], 1):
            if match(text):
                total += 1
                if len(hits) < MAX_HITS:
                    hits.append({"file": rel.as_posix(), "line": i, "text": text.strip()[:200]})
    return {"status": "ok", "query": query, "hits": hits, "total": total}


def _inspect(root, target, params):
    path = params.get("path") or (target if target and target.lower() != "file" else None)
    if not path:
        return _error('INSPECT: нужен параметр path="..."')
    found = _locate(root, path)
    if not found:
        return _error(f"INSPECT: файл не найден в проекте или закрыт для чтения: {path}")
    lines = _read_lines(found, strict=False)
    if lines is None:
        return _error(f"INSPECT: файл слишком большой или не читается: {path}")
    line = _int(params.get("line"))
    context = _int(params.get("context"))
    context = 5 if context is None else max(0, min(context, 50))
    note = f"строка {line} вне файла (строк: {len(lines)})" if line and not 1 <= line <= len(lines) else None
    return {"status": "ok", "file": found.relative_to(root).as_posix(), "line": line,
            "lines": len(lines), "snippet": _snippet(lines, line, context), "note": note}


def _analyze(root, target, params):
    lang = (target or "unknown").lower()
    lang = "javascript" if lang in ("js", "javascript", "node", "typescript", "ts") else lang
    error = (params.get("error") or "").strip().rsplit(".", 1)[-1] or None
    message = (params.get("message") or "").strip()

    if lang == "javascript":
        entry = JS_ERRORS.get(error)
    elif lang == "python":
        entry = PY_ERRORS.get(error)
    else:
        entry = PY_ERRORS.get(error) or JS_ERRORS.get(error)

    if entry:
        why, fixes = entry[0], list(entry[1])
    else:
        why = "Тип ошибки не распознан — нужен полный текст ошибки (traceback)."
        fixes = ["Приложи полный traceback целиком", "Укажи команду запуска и что ожидалось"]

    where, lines, notes = None, None, []
    line = _int(params.get("line"))
    if params.get("file"):
        found = _locate(root, params["file"])
        lines = _read_lines(found, strict=False) if found else None
        if lines is not None:
            where = {"file": found.relative_to(root).as_posix(), "line": line, "snippet": _snippet(lines, line)}
        else:
            notes.append(f"Файл `{params['file']}` не найден в репозитории — ошибка может быть во внешней библиотеке")

    special_why, specific = _specific(root, lang, error, message, where, lines, line)
    return {"status": "ok", "language": lang, "error": error, "message": message, "known": entry is not None,
            "why": special_why or why, "how_to_fix": (specific or fixes) + notes, "where": where}


def _specific(root, lang, error, message, where, lines, line):
    """Конкретные находки по проекту -> (уточнённое «почему» или None, список шагов)."""
    why, fixes = None, []

    hint = re.search(r"Did you mean:? '?([\w.]+)'?\?", message)
    if hint:
        fixes.append(f"Python подсказывает правильное имя: `{hint.group(1)}`")

    if error == "ModuleNotFoundError":
        m = re.search(r"No module named '([\w.]+)'", message)
        if m:
            mod = m.group(1).split(".")[0]
            pkg = PIP_NAMES.get(mod, mod)
            if (root / f"{mod}.py").is_file() or (root / mod).is_dir():
                fixes.append(f"`{mod}` — модуль этого проекта: запускай команду из корня репозитория")
            elif _norm(pkg) in _requirements(root):
                fixes.append(f"`{pkg}` есть в requirements.txt, но не установлен: `pip install -r requirements.txt`")
            else:
                fixes += [f"Установи: `pip install {pkg}`", f"Добавь строку `{pkg}` в requirements.txt"]

    elif error in ("NameError", "ReferenceError"):
        m = re.search(r"name '(\w+)' is not defined", message) or re.search(r"^(\w+) is not defined", message)
        if m:
            name = m.group(1)
            if lang != "javascript" and name in PY_LITERALS:
                fixes.append(f"В Python пиши `{PY_LITERALS[name]}`, а не `{name}`")
            else:
                defs = _definitions(root, name)
                if not defs:
                    fixes.append(f"`{name}` нигде в проекте не определено — проверь опечатку")
                elif where and defs[0]["file"] == where["file"]:
                    fixes.append(f"`{name}` определено в этом же файле на строке {defs[0]['line']} — "
                                 f"определение должно идти до использования и быть в той же области видимости")
                elif defs[0]["file"].endswith(".py"):
                    module = defs[0]["file"][:-3].replace("/", ".")
                    fixes.append(f"`{name}` определено в `{defs[0]['file']}:{defs[0]['line']}` — "
                                 f"добавь `from {module} import {name}`")
                else:
                    fixes.append(f"`{name}` найдено в `{defs[0]['file']}:{defs[0]['line']}` — подключи этот файл")

    elif error == "AttributeError":
        if "'NoneType' object" in message:
            why = "Объект оказался `None`: функция ничего не вернула (нет `return`) или поиск не дал результата."
            fixes.append("Найди, откуда пришло значение, и проверь `if obj is None` перед обращением")
        m = re.search(r"module '([\w.]+)' has no attribute '(\w+)'", message)
        if m:
            mod, attr = m.group(1).split(".")[0], m.group(2)
            if mod in KNOWN_MODULES and (root / f"{mod}.py").is_file():
                why = f"Файл проекта `{mod}.py` перекрывает настоящий модуль `{mod}`."
                fixes.append(f"Переименуй `{mod}.py` (и удали `__pycache__`), затем запусти снова")
            elif (root / f"{mod}.py").is_file():
                fixes.append(f"Проверь, что в `{mod}.py` есть `{attr}` и имя написано так же")
            else:
                fixes.append(f"Проверь версию: `pip show {mod}` — в ней может не быть `{attr}`")

    elif error == "TypeError" and lang != "javascript":
        if m := re.search(r"missing \d+ required positional arguments?: (.+)", message):
            fixes.append(f"Передай при вызове недостающие аргументы: {m.group(1)}")
        elif re.search(r"takes \d+ positional arguments? but \d+ (?:was|were) given", message):
            fixes.append("Число аргументов не совпадает: для метода класса проверь, что первым параметром стоит `self`")
        elif m := re.search(r"unsupported operand type\(s\) for .+: '(\w+)' and '(\w+)'", message):
            fixes.append(f"Нельзя смешивать `{m.group(1)}` и `{m.group(2)}` — приведи к одному типу")
        elif "'NoneType' object" in message:
            why = "Значение оказалось `None` там, где ждали объект."
            fixes.append("Проверь, что функция возвращает значение (`return`)")

    elif error == "TypeError" and lang == "javascript":
        if m := re.search(r"\(reading '(\w+)'\)", message):
            fixes.append(f"При чтении `{m.group(1)}` объект был undefined/null — используй `obj?.{m.group(1)}` "
                         f"и проверь, что данные загружены")

    elif error == "KeyError":
        key = message.strip().strip("'\"")
        if key:
            fixes.append(f"Ключа `{key}` нет — используй `.get('{key}')` или проверь, откуда пришли данные")

    elif error == "FileNotFoundError":
        m = re.search(r"No such file or directory: '([^']+)'", message)
        if m:
            missing = m.group(1)
            found = _locate(root, missing) or next(
                (p for p, _ in _iter_files(root) if p.name == Path(missing).name), None)
            if found:
                fixes.append(f"Файл есть в проекте: `{found.relative_to(root).as_posix()}` — путь считается от текущей "
                             f"папки: запускай из корня или строй путь через `Path(__file__).parent`")
            else:
                fixes.append(f"Файла `{missing}` нет в репозитории — создай его или исправь путь")

    if error in ("SyntaxError", "IndentationError", "TabError") and lines:
        lo, hi = (max(1, line - 3), min(len(lines), line + 3)) if line else (1, len(lines))
        for n in range(lo, hi + 1):
            if TERMINAL_LINE.search(lines[n - 1]):
                fixes.insert(0, f"Строка {n} похожа на команду терминала (`{lines[n - 1].strip()[:60]}`) — "
                                f"она попала в файл случайно, удали её")
                break

    return why, fixes


HANDLERS = {"ANALYZE": _analyze, "SEARCH": _search, "INSPECT": _inspect}


def execute(command, root=None):
    """Выполнить одну команду DSL локально."""
    if not command:
        return _error("Пустая команда")
    operation = (command.get("operation") or "").upper()
    target = command.get("target")
    params = command.get("params") or {}
    handler = HANDLERS.get(operation)
    if handler is None:
        return {"status": "error", "operation": operation, "target": target, "params": params,
                "message": f"Неизвестная операция: {operation}"}
    try:
        result = handler(_root(root), target, params)
    except OSError as exc:
        result = _error(f"{operation}: ошибка доступа к файлам: {exc}")
    return {"status": result.pop("status"), "operation": operation, "target": target, "params": params, **result}


def run(commands, root=None):
    """Выполнить список команд и собрать итоговый разбор."""
    results = [execute(c, root) for c in commands]
    ok = [r for r in results if r["status"] == "ok"]
    analyses = [r for r in ok if r["operation"] == "ANALYZE"]
    main = next((r for r in analyses if r["known"]), analyses[0] if analyses else None)

    where, seen = [], set()

    def add(loc):
        key = (loc["file"], loc.get("line"))
        if key not in seen:
            seen.add(key)
            where.append(loc)

    if main and main["where"]:
        add(main["where"])
    for r in ok:
        if r["operation"] == "INSPECT":
            add({"file": r["file"], "line": r["line"], "snippet": r["snippet"]})
        elif r["operation"] == "SEARCH":
            for hit in r["hits"][:5]:
                add(dict(hit))

    if main is None:
        what = "Тип ошибки не указан — показываю найденное в проекте" if where else "Ошибка в тексте не найдена"
        why = None
        fixes = ["Для точного разбора приложи полный текст ошибки (traceback)",
                 "Укажи команду, которой запускал, и что ожидалось"]
        confidence = "low"
    else:
        what = ": ".join(x for x in (main["error"], main["message"]) if x) or "Ошибка без названия"
        why, fixes = main["why"], main["how_to_fix"]
        confidence = ("high" if main["where"] else "medium") if main["known"] else "low"

    return {"what_happened": what, "where": where, "why": why, "how_to_fix": fixes, "confidence": confidence,
            "errors": [r["message"] for r in results if r["status"] == "error"], "results": results}
````

### `github_client.py`

````python
"""GitHub REST API: чтение issue и публикация комментария. Только стандартная библиотека.

Токен: GITHUB_TOKEN (есть в Codespaces и GitHub Actions) или GH_TOKEN.
Репозиторий: --repo owner/name или GITHUB_REPOSITORY.
"""
import json
import os
import re
import urllib.error
import urllib.request

API = "https://api.github.com"
HINTS = {401: "токен неверный или истёк", 403: "у токена нет прав (нужно Issues: write)",
         404: "репозиторий или issue не найден, либо нет доступа"}


class GitHubError(RuntimeError):
    pass


def _token():
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise GitHubError("GITHUB_TOKEN не найден")
    return token


def _request(method, path, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Authorization": f"Bearer {_token()}", "Accept": "application/vnd.github+json",
               "User-Agent": "hydra-mark4"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise GitHubError(f"HTTP {exc.code}: {HINTS.get(exc.code, '')} {detail}".strip()) from None
    except urllib.error.URLError as exc:
        raise GitHubError(f"нет связи с GitHub: {exc.reason}") from None


def resolve_repo(repo=None):
    repo = (repo or os.environ.get("GITHUB_REPOSITORY", "")).strip()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise GitHubError("укажи репозиторий: --repo owner/name")
    return repo


def get_issue(repo, number):
    data = _request("GET", f"/repos/{repo}/issues/{int(number)}")
    return {"number": data.get("number", int(number)), "title": data.get("title") or "",
            "body": data.get("body") or "", "url": data.get("html_url", "")}


def post_comment(repo, number, body):
    data = _request("POST", f"/repos/{repo}/issues/{int(number)}/comments", {"body": body})
    return data.get("html_url", "")
````

## .github/workflows/

### `.github/workflows/hydra.yml`

````yaml
name: Hydra

on:
  issues:
    types: [opened]
  workflow_dispatch:
    inputs:
      issue:
        description: "Номер issue"
        required: true

permissions:
  contents: read
  issues: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: Разбор issue и комментарий
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ISSUE_NUMBER: ${{ github.event.issue.number || inputs.issue }}
        run: python main.py issue "$ISSUE_NUMBER" --post
````

## tests/

### `tests/test_dsl.py`

````python
import unittest

from hydra_dsl import DSLError, build_command, parse_command, parse_lines


class TestDSL(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(parse_command("ANALYZE python error=ModuleNotFoundError"),
                         {"operation": "ANALYZE", "target": "python", "params": {"error": "ModuleNotFoundError"}})

    def test_quotes_and_spaces(self):
        cmd = parse_command("""SEARCH project query="где используется analyze_text" message="No module named 'x'" """)
        self.assertEqual(cmd["params"]["query"], "где используется analyze_text")
        self.assertEqual(cmd["params"]["message"], "No module named 'x'")

    def test_empty(self):
        self.assertIsNone(parse_command(""))
        self.assertIsNone(parse_command("   "))

    def test_bad_quote(self):
        with self.assertRaises(DSLError):
            parse_command('SEARCH project query="без конца')

    def test_roundtrip(self):
        params = {"message": 'a "b" \\ c \'d\'', "line": 7}
        cmd = parse_command(build_command("ANALYZE", "python", params))
        self.assertEqual(cmd["params"], {"message": 'a "b" \\ c \'d\'', "line": "7"})

    def test_parse_lines(self):
        text = "```\nANALYZE python error=NameError\nвот команды:\n1. SEARCH project query=x\n```"
        commands, rejected = parse_lines(text)
        self.assertEqual([c["operation"] for c in commands], ["ANALYZE", "SEARCH"])
        self.assertEqual(rejected, ["вот команды:"])


if __name__ == "__main__":
    unittest.main()
````

### `tests/test_base_h.py`

````python
import tempfile
import unittest
from pathlib import Path

from base_h import execute, run
from hydra_dsl import parse_command


class TestBaseH(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "main.py").write_text("import requests\nfrom helpers import greet\nprint(greet(name))\n")
        (self.root / "helpers.py").write_text("def greet(who):\n    return 'hi ' + who\n")
        (self.root / "random.py").write_text("x = 1\n")
        (self.root / "requirements.txt").write_text("openai>=1.66\n")
        (self.root / ".env").write_text("OPENAI_API_KEY=secret\n")
        (self.root / "broken.py").write_text("def f():\n    return 1\nEOF\n")

    def tearDown(self):
        self.tmp.cleanup()

    def ex(self, line):
        return execute(parse_command(line), root=self.root)

    def test_legacy_check(self):
        r = self.ex("ANALYZE python error=ModuleNotFoundError")
        self.assertEqual((r["status"], r["operation"], r["target"], r["params"]),
                         ("ok", "ANALYZE", "python", {"error": "ModuleNotFoundError"}))

    def test_module_not_found(self):
        r = self.ex("ANALYZE python error=ModuleNotFoundError message=\"No module named 'requests'\" file=main.py line=1")
        self.assertTrue(r["known"])
        self.assertIn("import requests", r["where"]["snippet"])
        self.assertTrue(any("pip install requests" in s for s in r["how_to_fix"]))

    def test_module_in_requirements(self):
        r = self.ex("ANALYZE python error=ModuleNotFoundError message=\"No module named 'openai'\"")
        self.assertTrue(any("pip install -r requirements.txt" in s for s in r["how_to_fix"]))

    def test_name_error_definition(self):
        r = self.ex("ANALYZE python error=NameError message=\"name 'greet' is not defined\" file=main.py line=3")
        self.assertTrue(any("from helpers import greet" in s for s in r["how_to_fix"]))

    def test_name_error_unknown(self):
        r = self.ex("ANALYZE python error=NameError message=\"name 'name' is not defined\"")
        self.assertTrue(any("нигде в проекте не определено" in s for s in r["how_to_fix"]))

    def test_shadowed_module(self):
        r = self.ex("ANALYZE python error=AttributeError message=\"module 'random' has no attribute 'randint'\"")
        self.assertIn("random.py", r["why"])

    def test_terminal_garbage(self):
        r = self.ex("ANALYZE python error=SyntaxError message=\"invalid syntax\" file=broken.py line=3")
        self.assertIn("команду терминала", r["how_to_fix"][0])

    def test_absolute_traceback_path(self):
        r = self.ex(f"ANALYZE python error=NameError file=/home/runner/work/x/x/main.py line=3")
        self.assertEqual(r["where"]["file"], "main.py")

    def test_search(self):
        r = self.ex('SEARCH project query="greet"')
        self.assertEqual(r["status"], "ok")
        self.assertEqual({h["file"] for h in r["hits"]}, {"main.py", "helpers.py"})

    def test_search_skips_env(self):
        r = self.ex("SEARCH project query=secret")
        self.assertEqual(r["total"], 0)

    def test_inspect(self):
        r = self.ex("INSPECT file path=helpers.py line=2 context=0")
        self.assertEqual(r["snippet"], "> 2 |     return 'hi ' + who")

    def test_inspect_blocked(self):
        for path in ("../../etc/passwd", "/etc/passwd", ".env"):
            self.assertEqual(self.ex(f"INSPECT file path={path}")["status"], "error", path)

    def test_unknown_operation(self):
        r = self.ex("DELETE file path=main.py")
        self.assertEqual(r["status"], "error")

    def test_run_report(self):
        commands = [parse_command("ANALYZE python error=ModuleNotFoundError "
                                  "message=\"No module named 'requests'\" file=main.py line=1"),
                    parse_command("SEARCH project query=requests")]
        report = run(commands, root=self.root)
        self.assertEqual(report["confidence"], "high")
        self.assertEqual(report["where"][0]["file"], "main.py")
        self.assertEqual(report["errors"], [])

    def test_run_empty(self):
        report = run([], root=self.root)
        self.assertEqual(report["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
````

### `tests/test_ai.py`

````python
import os
import unittest
from unittest import mock

import ai
from hydra_dsl import parse_command

PY_TRACE = """Запускаю бота и падает:
Traceback (most recent call last):
  File "/workspaces/hydra-mark4/main.py", line 3, in <module>
    import requests
  File "/usr/lib/python3.12/site-packages/x.py", line 1, in <module>
ModuleNotFoundError: No module named 'requests'
"""

JS_TRACE = """Uncaught TypeError: Cannot read properties of undefined (reading 'map')
    at App (src/App.js:12:5)
    at node_modules/react/index.js:1:1"""


class TestRules(unittest.TestCase):
    def test_python_traceback(self):
        lines = ai.rules_translate(PY_TRACE)
        first = parse_command(lines[0])
        self.assertEqual(first["operation"], "ANALYZE")
        self.assertEqual(first["target"], "python")
        self.assertEqual(first["params"]["error"], "ModuleNotFoundError")
        self.assertEqual(first["params"]["message"], "No module named 'requests'")
        self.assertEqual(first["params"]["file"], "/workspaces/hydra-mark4/main.py")
        self.assertEqual(first["params"]["line"], "3")
        self.assertEqual(len(lines), 1)

    def test_name_error_adds_search(self):
        lines = ai.rules_translate("NameError: name 'greet' is not defined. Did you mean: 'great'?")
        self.assertEqual(parse_command(lines[1])["params"]["query"], "greet")

    def test_js_traceback(self):
        first = parse_command(ai.rules_translate(JS_TRACE)[0])
        self.assertEqual(first["target"], "javascript")
        self.assertEqual(first["params"]["file"], "src/App.js")

    def test_no_error(self):
        lines = ai.rules_translate("Не работает функция `analyze_text` в файле main.py")
        ops = [parse_command(x)["operation"] for x in lines]
        self.assertEqual(ops, ["INSPECT", "SEARCH"])

    def test_plain_text(self):
        first = parse_command(ai.rules_translate("всё сломалось")[0])
        self.assertEqual(first["target"], "unknown")


class TestTranslate(unittest.TestCase):
    def test_fallback_without_key(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "HYDRA_AI_PROVIDER": "openai"}):
            commands, info = ai.translate(PY_TRACE)
        self.assertEqual(info["provider"], "rules")
        self.assertTrue(info["warnings"])
        self.assertEqual(commands[0]["operation"], "ANALYZE")

    def test_openai_failure_falls_back(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), \
                mock.patch.object(ai, "_from_openai", side_effect=RuntimeError("boom")):
            commands, info = ai.translate(PY_TRACE, provider="openai")
        self.assertEqual(info["provider"], "rules")
        self.assertIn("boom", info["warnings"][0])

    def test_openai_success(self):
        fake = [parse_command("ANALYZE python error=NameError")]
        with mock.patch.object(ai, "_from_openai", return_value=fake):
            commands, info = ai.translate("x", provider="openai")
        self.assertTrue(info["provider"].startswith("openai/"))
        self.assertEqual(info["dsl"], ["ANALYZE python error=NameError"])

    def test_empty(self):
        commands, info = ai.translate("   ")
        self.assertEqual(commands, [])


if __name__ == "__main__":
    unittest.main()
````
