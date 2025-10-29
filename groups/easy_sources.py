# groups/easy_sources.py
import asyncio
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
    with redirect_stdout(buf):
        # Запускаємо модуль так само, як ти робиш у консолі: python -m parsers.xxx
        runpy.run_module(modname, run_name="__main__")
    return buf.getvalue().strip()

async def run_all() -> List[str]:
    """
    Повертає список готових текстових блоків (у форматі як у консолі),
    які надсилаються в Telegram без змін.
    """
    tasks = [asyncio.to_thread(_run_module_capture, m) for m in MODULES]
    texts = await asyncio.gather(*tasks, return_exceptions=False)
    return [t for t in texts if t]