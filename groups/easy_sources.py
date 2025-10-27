import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin


def run_all():
    results = {}

    print("🔹 Парсимо Epravda...")
    try:
        epravda_news = parse_epravda()
        results["epravda"] = epravda_news
    except Exception as e:
        print(f"❌ Epravda не вдалося: {e}")
        results["epravda"] = []

    print("🔹 Парсимо Minfin...")
    try:
        minfin_news = parse_minfin()
        results["minfin"] = minfin_news
    except Exception as e:
        print(f"❌ Minfin не вдалося: {e}")
        results["minfin"] = []

    return results


def format_news(results: dict) -> str:
    text = ""

    # === EPRAVDA ===
    epravda = results.get("epravda", [])
    if epravda:
        text += f"✅ epravda - результат:\n"
        text += f"   Усього знайдено {len(epravda)} (з урахуванням дублів)\n"
        text += f"   Унікальних новин: {len(epravda)}\n\n"

        finances = [n for n in epravda if n.get("section") == "finances"]
        columns = [n for n in epravda if n.get("section") == "columns"]

        if finances:
            text += f"Джерело: https://epravda.com.ua/finances — {len(finances)} новин:\n"
            for i, n in enumerate(finances, 1):
                text += f"{i}. {n['title']} ({n['date']})\n   {n['url']}\n"
            text += "\n"

        if columns:
            text += f"Джерело: https://epravda.com.ua/columns — {len(columns)} новин:\n"
            for i, n in enumerate(columns, 1):
                text += f"{i}. {n['title']} ({n['date']})\n   {n['url']}\n"
            text += "\n"

    # === MINFIN ===
    minfin = results.get("minfin", [])
    if minfin:
        text += f"✅ minfin - результат:\n"
        text += f"   Унікальних новин: {len(minfin)}\n\n"
        text += f"Джерела: https://minfin.com.ua/news ...\n"
        for i, n in enumerate(minfin, 1):
            text += f"{i}. {n['title']} ({n['date']})\n   {n['url']}\n"
        text += "\n"

    return text