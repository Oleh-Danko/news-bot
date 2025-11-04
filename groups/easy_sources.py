# groups/easy_sources.py
import os
import io
import runpy
import contextlib

def _run_and_capture(module_name: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        runpy.run_module(module_name, run_name="__main__")
    text = buf.getvalue().strip()
    if not text:
        return ""
    # додаємо 🟢 перед "Джерело:" у всіх виводах парсерів
    text = text.replace("Джерело: ", "🟢Джерело: ")
    return text

@contextlib.contextmanager
def _temp_env(key: str, value: str | None):
    old = os.environ.get(key)
    try:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

def run_all(today_only: bool = False) -> list[str]:
    modules = (
        "parsers.epravda_parser",
        "parsers.minfin_parser",
        "parsers.coindesk_parser",
    )
    blocks: list[str] = []
    with _temp_env("ONLY_TODAY", "1" if today_only else None):
        for mod in modules:
            try:
                out = _run_and_capture(mod)
                if out:
                    blocks.append(out)
            except Exception as e:
                blocks.append(f"❌ Помилка запуску {mod}: {e}")
    return blocks

def run_all_today() -> list[str]:
    return run_all(today_only=True)

if __name__ == "__main__":
    for block in run_all():
        print(block)
        print()