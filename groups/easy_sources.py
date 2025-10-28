# groups/easy_sources.py
from urllib.parse import urlparse
from parsers.epravda_parser import parse_epravda
from parsers.minfin_parser import parse_minfin

def _detect_source_section(url: str):
    try:
        p = urlparse(url)
        host = p.netloc
        path = p.path.strip("/")
        section = path.split("/")[0] if path else ""
        if "epravda.com.ua" in host:
            source = "epravda"
            section_url = f"https://epravda.com.ua/{section}" if section else "https://epravda.com.ua"
        elif "minfin.com.ua" in host:
            source = "minfin"
            section_url = f"https://minfin.com.ua/ua/{section}" if section else "https://minfin.com.ua/ua"
        else:
            source = host or "unknown"
            section_url = f"https://{host}/{section}" if host else url
        return source, (section or "root"), section_url
    except Exception:
        return "unknown", "root", url

def _sanitize_item(x):
    # Приводимо будь-що до словника потрібного формату або повертаємо None
    if isinstance(x, dict):
        title = str(x.get("title") or x.get("name") or "—").strip()
        date  = str(x.get("date") or x.get("time") or "—").strip()
        url   = str(x.get("url")  or x.get("link") or "").strip()
    elif isinstance(x, (list, tuple)) and len(x) >= 2:
        title, url = str(x[0]).strip(), str(x[1]).strip()
        date = "—"
    elif isinstance(x, str):
        title, url, date = x.strip()[:120], "", "—"
    else:
        return None

    if not url:
        return None

    source, section, section_url = _detect_source_section(url)
    return {
        "title": title or "—",
        "date":  date or "—",
        "url":   url,
        "source": source,
        "section": section,
        "section_url": section_url,
    }

def _collect(parse_fn):
    raw = parse_fn() or []
    sanitized = []
    for it in raw:
        s = _sanitize_item(it)
        if s: sanitized.append(s)
    return sanitized, len(raw)

def run_all():
    # Збір
    epravda_list, epravda_raw = _collect(parse_epravda)
    minfin_list,  minfin_raw  = _collect(parse_minfin)

    # Дедуп за URL всередині джерела
    def dedup_by_url(items):
        seen = set()
        out = []
        for n in items:
            u = n["url"]
            if u in seen: 
                continue
            seen.add(u)
            out.append(n)
        return out

    epravda_unique = dedup_by_url(epravda_list)
    minfin_unique  = dedup_by_url(minfin_list)

    items = epravda_unique + minfin_unique
    stats = {
        "epravda": {"raw": epravda_raw, "unique": len(epravda_unique)},
        "minfin":  {"raw": minfin_raw,  "unique": len(minfin_unique)},
    }
    return {"items": items, "stats": stats}