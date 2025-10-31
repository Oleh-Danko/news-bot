# groups/easy_sources.py
import io
import runpy
import contextlib

def _run_and_capture(module_name: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        runpy.run_module(module_name, run_name="__main__")
    return buf.getvalue().strip()

def run_all() -> list[str]:
    modules = (
        "parsers.epravda_parser",
        "parsers.minfin_parser",
        "parsers.coindesk_parser",
    )
    blocks: list[str] = []
    for mod in modules:
        try:
            out = _run_and_capture(mod)
            if out:
                blocks.append(out)
        except Exception as e:
            blocks.append(f"❌ Помилка запуску {mod}: {e}")
    return blocks

if __name__ == "__main__":
    for block in run_all():
        print(block)
        print()