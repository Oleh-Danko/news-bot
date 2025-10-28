cat > groups/easy_sources.py << 'PY'
import os, sys
# Додаємо корінь проєкту в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin

def run_all():
    all_news = []

    try:
        all_news.extend(parse_epravda())
    except Exception as e:
        print(f"Epravda error: {e}")

    try:
        all_news.extend(parse_minfin())
    except Exception as e:
        print(f"Minfin error: {e}")

    # Дедуп за URL
    unique, seen = [], set()
    for n in all_news:
        url = n.get("url")
        if url and url not in seen:
            unique.append(n)
            seen.add(url)
    return unique

def format_grouped(news):
    """
    Групуємо за 'source' і віддаємо акуратний текст.
    """
    by_src = {}
    for n in news:
        by_src.setdefault(n.get("source", "Unknown"), []).append(n)

    lines = []
    for src, items in by_src.items():
        lines.append(f"{src}")
        for i, n in enumerate(items, 1):
            title = n.get("title", "(без назви)")
            date = n.get("date", "—")
            url = n.get("url", "")
            lines.append(f"{i}. {title} ({date})\n{url}")
        lines.append("")  # порожній рядок між блоками
    return "\n".join(lines).strip()
PY