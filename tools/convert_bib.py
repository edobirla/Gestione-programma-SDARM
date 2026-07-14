"""Dev-time tool: convert a BibleShow .bib (MS Access MDB) into a bundled SQLite DB.

Run once per language/version. The produced .db lives in <app>/bibles/ and is the
ONLY thing the app reads at runtime — no mdbtools / access-parser needed by users.

Usage:
    python3 tools/convert_bib.py LND1991.bib
    python3 tools/convert_bib.py path/to/Romanian.bib --code ro
"""
import os
import re
import sqlite3

# access_parser is imported lazily inside detect_info()/convert() rather than
# at module level: this module is now also imported by the running app (the
# Impostazioni → Bibbia "Aggiungi versione/lingua" flow) to reuse this exact
# conversion logic, and an app-level import must never crash the whole app
# just because the optional access-parser package isn't installed — the
# caller catches ImportError and shows a message instead.

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_scripture(text):
    """BibleShow scripture fields carry rich-text markup (<span class=...>,
    <i>, <p>, <br>) and footnote/cross-reference markers (^, *) meant for its
    own renderer — meaningless (and ugly, projected as literal text) in this
    app, which only ever displays plain verse text. <br> becomes a space
    first so words on either side of it don't get glued together once the
    tag itself is stripped."""
    if not text:
        return text
    text = _BR_RE.sub(" ", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("^", "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()

LANG_CODE_BY_NAME = {
    "italian": "it", "italiano": "it",
    "romanian": "ro", "română": "ro", "romana": "ro",
    "spanish": "es", "español": "es", "espanol": "es",
    "english": "en", "inglese": "en",
    "french": "fr", "francese": "fr",
    "portuguese": "pt", "portoghese": "pt",
}


def _info_dict(db):
    data = db.parse_table("Info")
    out = {}
    n = len(data["ID"])
    for i in range(n):
        out[str(data["Parameter"][i])] = data["Value"][i]
    return out


def detect_info(bib_path: str) -> dict:
    """Peek at a BibleShow .bib's language/version metadata without writing
    anything — used to show a confirm/correct step before the (slower) full
    conversion runs. Raises ImportError if access-parser isn't installed."""
    from access_parser import AccessParser
    db = AccessParser(bib_path)
    info = _info_dict(db)
    language = (info.get("Language") or "").strip()
    short = (info.get("BibleShortName") or "").strip() or os.path.splitext(os.path.basename(bib_path))[0]
    full = (info.get("BibleFullName") or "").strip() or short
    code = LANG_CODE_BY_NAME.get(language.lower(), language.lower()[:2] or "xx")
    return {"language": language, "short": short, "full": full, "code": code}


def convert(bib_path: str, out_dir: str, forced_code: str = None) -> dict:
    """Convert bib_path into <out_dir>/<code>_<short>.db. Returns a summary
    dict instead of just printing, so the app UI can show it (the CLI
    entry point below still prints it). Raises ImportError if access-parser
    isn't installed."""
    from access_parser import AccessParser
    db = AccessParser(bib_path)
    info = _info_dict(db)

    language = (info.get("Language") or "").strip()
    short = (info.get("BibleShortName") or "").strip() or os.path.splitext(os.path.basename(bib_path))[0]
    full = (info.get("BibleFullName") or "").strip() or short
    code = forced_code or LANG_CODE_BY_NAME.get(language.lower(), language.lower()[:2] or "xx")

    out_name = f"{code}_{short}".replace(" ", "_").replace("/", "_") + ".db"
    out_path = os.path.join(out_dir, out_name)
    if os.path.isfile(out_path):
        os.remove(out_path)

    conn = sqlite3.connect(out_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("""CREATE TABLE books (
        num INTEGER PRIMARY KEY, list_title TEXT, full_title TEXT,
        abbrev TEXT, chapters INTEGER, position INTEGER)""")
    cur.execute("""CREATE TABLE verses (
        book INTEGER, chapter INTEGER, verse INTEGER, scripture TEXT)""")
    cur.execute("CREATE INDEX idx_bcv ON verses(book, chapter, verse)")

    for k, v in [("code", code), ("language", language),
                 ("version_short", short), ("version_full", full)]:
        cur.execute("INSERT INTO meta VALUES (?,?)", (k, str(v)))

    # Books
    st = db.parse_table("Structure")
    nb = len(st["ID"])
    for i in range(nb):
        cur.execute("INSERT INTO books VALUES (?,?,?,?,?,?)", (
            int(st["ID"][i]),
            st["ListTitle"][i],
            st["FullTitle"][i],
            st["Abbreviation"][i],
            int(st["Chapters"][i]) if st["Chapters"][i] is not None else 0,
            int(st["BibPosition"][i]) if st["BibPosition"][i] is not None else int(st["ID"][i]),
        ))

    # Verses
    bt = db.parse_table("Bible")
    nv = len(bt["ID"])
    rows = []
    for i in range(nv):
        try:
            rows.append((
                int(bt["Book"][i]), int(bt["Chapter"][i]),
                int(bt["Verse"][i]), _clean_scripture(bt["Scripture"][i]),
            ))
        except (ValueError, TypeError):
            continue
    cur.executemany("INSERT INTO verses VALUES (?,?,?,?)", rows)

    conn.commit()
    conn.close()
    return {"code": code, "language": language, "short": short, "full": full,
            "books": nb, "verses": len(rows), "out_path": out_path}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("bib")
    ap.add_argument("--code", default=None, help="codice lingua forzato (it, ro, es...)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "bibles"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    result = convert(args.bib, args.out, args.code)
    print(f"OK -> {result['out_path']}")
    print(f"   lingua={result['language']} versione={result['short']} ({result['full']}) "
          f"libri={result['books']} versetti={result['verses']}")
