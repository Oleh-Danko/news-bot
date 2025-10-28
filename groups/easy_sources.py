# groups/easy_sources.py
from urllib.parse import urlparse
from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin

def _dedupe(items):
    seen = set()
    out = []
    for n in items:
        url = (n.get("url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            out.append(n)
    return out

def _section_url(u: str) -> str:
    """
    Групуємо за секціями:
      • epravda.com.ua -> https://epravda.com.ua/<перший-сегмент>
      • minfin.com.ua  -> https://minfin.com.ua/  або https://minfin.com.ua/ua
    """
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        path = (p.path or "/").strip("/")
        if "epravda.com.ua" in host:
            seg = (path.split("/", 1)[0] if path else "").strip()
            return f"https://epravda.com.ua/{seg}" if seg else "https://epravda.com.ua/"
        if "minfin.com.ua" in host:
            seg = (path.split("/", 1)[0] if path else "").strip()
            # якщо перший сегмент 'ua' — виділяємо окрему секцію
            return "https://minfin.com.ua/ua" if seg == "ua" else "https://minfin.com.ua/"
    except Exception:
        pass
    return u

def _normalize_list(lst, source_name: str):
    norm = []
    for n in lst or []:
        norm.append({
            "title": n.get("title", "—").strip(),
            "date":  n.get("date", "—").strip(),
            "url":   (n.get("url") or "").strip(),
            "source": source_name
        })
    return norm

def _group_by_section(items):
    by_sec = {}
    for n in items:
        sec = _section_url(n["url"])
        by_sec.setdefault(sec, []).append(n)
    # сортуємо в кожній секції: новіші (за рядком дати YYYY-MM-DD) вище; якщо дати немає — лишаємо порядок
    def key_date(n):
        d = n.get("date") or ""
        return d if len(d) == 10 and d[4] == "-" and d[7] == "-" else ""
    for sec, arr in by_sec.items():
        arr.sort(key=lambda x: key_date(x), reverse=True)
    # стабільний порядок секцій
    ordered = sorted(by_sec.items(), key=lambda kv: kv[0])
    return [{"url": sec, "items": arr} for sec, arr in ordered]

def run_all():
    """
    Повертає структуру по кожному джерелу окремо для форматування під вимоги.
    {
      "epravda": {
         "raw_total": <з урахуванням дублів>,
         "unique_total": <унікальних>,
         "sections": [ { "url": "...", "items": [ {title,date,url,source}, ... ] }, ... ]
      },
      "minfin": { ... }
    }
    """
    # 1) Сирі списки (можуть бути дублікати)
    ep_raw = _normalize_list(parse_epravda(), "epravda")
    mf_raw = _normalize_list(parse_minfin(),  "minfin")

    # 2) Дедуплікація всередині кожного джерела
    ep_unique = _dedupe(ep_raw)
    mf_unique = _dedupe(mf_raw)

    # 3) Групування за секціями (URL секції в шапці)
    ep_sections = _group_by_section(ep_unique)
    mf_sections = _group_by_section(mf_unique)

    return {
        "epravda": {
            "raw_total": len(ep_raw),
            "unique_total": len(ep_unique),
            "sections": ep_sections,
        },
        "minfin": {
            "raw_total": len(mf_raw),
            "unique_total": len(mf_unique),
            "sections": mf_sections,
        },
    }