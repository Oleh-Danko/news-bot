import sys, os
from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin

def run_all():
    all_news = []

    print("�� Парсимо Epravda...")
    try:
        epravda_news = parse_epravda()
        all_news.extend(epravda_news)
    except Exception as e:
        print(f"❌ Epravda не вдалося: {e}")

    print("🔹 Парсимо Minfin...")
    try:
        minfin_news = parse_minfin()
        all_news.extend(minfin_news)
    except Exception as e:
        print(f"❌ Minfin не вдалося: {e}")

    # Видалення дублів за URL
    unique = []
    seen = set()
    for n in all_news:
        url = n.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(n)

    return unique
