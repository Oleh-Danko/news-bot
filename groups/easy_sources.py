# groups/easy_sources.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin

def run_all():
    all_news = []

    try:
        epravda_news = parse_epravda()
        all_news.extend(epravda_news)
    except Exception as e:
        print(f"Epravda error: {e}")

    try:
        minfin_news = parse_minfin()
        all_news.extend(minfin_news)
    except Exception as e:
        print(f"Minfin error: {e}")

    # дедуп за URL
    seen, unique = set(), []
    for n in all_news:
        url = n.get("url")
        if url and url not in seen:
            unique.append(n)
            seen.add(url)

    return unique