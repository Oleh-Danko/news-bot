# groups/easy_sources.py
import io
import runpy
from contextlib import redirect_stdout
from typing import List

MODULES = [
    "parsers.epravda_parser",
    "parsers.minfin_parser",
]

def _run_module_capture(modname: str) -> str:
    buf = io.StringIO()
    # ВАЖЛИВО: без жодної паралельності — суворо послідовно
    with redirect_stdout(buf):
        runpy.run_module(modname, run_name="__main__")
    return buf.getvalue().strip()

def run_all() -> List[str]:
    """
    Повертає список готових текстових блоків (у форматі консолі),
    які бот відправляє без змін.
    """
    texts: List[str] = []
    for mod in MODULES:
        out = _run_module_capture(mod)
        if out:
            texts.append(out)
    return texts