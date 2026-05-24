#!/usr/bin/env python3
"""
AP Research Toolkit
===================

A single-file desktop app for AP Research students.

Features
--------
* BibTeX source management (import / add / edit / export).
* Automatic MLA (9th ed.) and APA (7th ed.) citation generation:
  - Full works-cited / references entries.
  - Ready-to-copy in-text citations.
  - Export a formatted citation-sheet PDF (hanging indents).
* Research timeline with adjustable dates and the common AP Research
  process checkpoints.
* The 7 required paper sections (Introduction, Literature Review,
  Methodology, Results, Discussion, Limitations, Conclusion) with
  per-section word targets and a 4,000-5,000 word total tracker.
* Multiple parallel projects, stored in a local SQLite database.

Dependencies
------------
Only the Python standard library + tkinter are required.  `reportlab`
is used for nicer PDFs when available; otherwise a built-in pure-Python
PDF writer is used as a fallback, so export always works.

Run:
    python ap_research_toolkit.py
Self-test (no GUI):
    python ap_research_toolkit.py --selftest
"""

from __future__ import annotations

import os
import re
import sys
import json
import sqlite3
import datetime as _dt
from typing import Optional


# ===========================================================================
#  Paths / storage
# ===========================================================================

def app_data_dir() -> str:
    """Return a per-user directory for storing the database."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "APResearchToolkit")
    elif sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/APResearchToolkit")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = os.path.join(base, "ap_research_toolkit")
    os.makedirs(path, exist_ok=True)
    return path


DB_PATH = os.path.join(app_data_dir(), "toolkit.db")


# ===========================================================================
#  Constants
# ===========================================================================

REQUIRED_SECTIONS = [
    ("Introduction", 550),
    ("Literature Review", 1000),
    ("Methodology", 750),
    ("Results", 700),
    ("Discussion", 800),
    ("Limitations", 300),
    ("Conclusion", 400),
]  # targets sum to 4500 (mid-point of the 4000-5000 limit)

DEFAULT_CHECKPOINTS = [
    "Finalize topic & research question",
    "Annotated bibliography (5+ sources)",
    "Literature review draft",
    "Methodology & inquiry plan",
    "Ethics / IRB review (if needed)",
    "Data collection complete",
    "Data analysis & results",
    "First full draft (4,000-5,000 words)",
    "Peer review & revisions",
    "Final paper submission",
    "Presentation & Oral Defense (POD)",
]

# Anchors for the default timeline. The academic year runs Sept 1 -> Apr 30;
# "Final paper submission" is pinned to April 30 and every checkpoint falls
# after September 1.
SEMESTER_START_MONTH, SEMESTER_START_DAY = 9, 1
SUBMISSION_MONTH, SUBMISSION_DAY = 4, 30
SUBMISSION_CHECKPOINT = "Final paper submission"


def academic_window(today: Optional[_dt.date] = None):
    """Return (sept_1, april_30) for the academic year that contains `today`.

    If we are already past this cycle's April 30 (the May-Aug gap), roll
    forward to the upcoming September -> April year so new projects get a
    sensible future timeline.
    """
    today = today or _dt.date.today()
    if today.month >= SEMESTER_START_MONTH:
        sep = _dt.date(today.year, SEMESTER_START_MONTH, SEMESTER_START_DAY)
        apr = _dt.date(today.year + 1, SUBMISSION_MONTH, SUBMISSION_DAY)
    else:
        sep = _dt.date(today.year - 1, SEMESTER_START_MONTH, SEMESTER_START_DAY)
        apr = _dt.date(today.year, SUBMISSION_MONTH, SUBMISSION_DAY)
    if today > apr:  # past submission (late spring/summer) -> next year
        sep = _dt.date(today.year, SEMESTER_START_MONTH, SEMESTER_START_DAY)
        apr = _dt.date(today.year + 1, SUBMISSION_MONTH, SUBMISSION_DAY)
    return sep, apr


def default_checkpoint_dates(today: Optional[_dt.date] = None):
    """ISO target dates for DEFAULT_CHECKPOINTS, aligned to the academic year.

    Checkpoints up to and including the final submission are spread evenly
    between Sept 1 (exclusive) and April 30, so the submission lands exactly
    on April 30. Anything after submission (the POD) is spaced two weeks out.
    """
    sep, apr = academic_window(today)
    span = (apr - sep).days
    try:
        sub_i = DEFAULT_CHECKPOINTS.index(SUBMISSION_CHECKPOINT)
    except ValueError:
        sub_i = len(DEFAULT_CHECKPOINTS) - 1
    n_pre = sub_i + 1
    out = []
    for i in range(len(DEFAULT_CHECKPOINTS)):
        if i <= sub_i:
            d = sep + _dt.timedelta(days=round(span * (i + 1) / n_pre))
        else:
            d = apr + _dt.timedelta(days=14 * (i - sub_i))
        out.append(d.isoformat())
    return out


ENTRY_TYPES = ["article", "book", "incollection", "inproceedings",
               "online", "techreport", "phdthesis", "mastersthesis", "misc"]

# Common fields shown in the source editor (label, bibtex key).
EDITOR_FIELDS = [
    ("Author(s)", "author"),
    ("Title", "title"),
    ("Year", "year"),
    ("Journal", "journal"),
    ("Book / Container title", "booktitle"),
    ("Publisher", "publisher"),
    ("Volume", "volume"),
    ("Number / Issue", "number"),
    ("Pages", "pages"),
    ("Edition", "edition"),
    ("Website / Site name", "howpublished"),
    ("URL", "url"),
    ("DOI", "doi"),
    ("Access date", "urldate"),
    ("Note", "note"),
]

# Italic markers (private control chars) used internally so we can render
# italics in the PDF while keeping plain text for clipboard/display.
I0, I1 = "\x01", "\x02"


def _ital(s: str) -> str:
    return I0 + s + I1


def strip_markers(s: str) -> str:
    return s.replace(I0, "").replace(I1, "")


# ===========================================================================
#  Database layer
# ===========================================================================

class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def _init_schema(self):
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                research_question TEXT DEFAULT '',
                citation_style TEXT DEFAULT 'MLA',
                word_min INTEGER DEFAULT 4000,
                word_max INTEGER DEFAULT 5000,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                cite_key TEXT,
                entry_type TEXT DEFAULT 'article',
                fields TEXT DEFAULT '{}',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT,
                target_date TEXT,
                done INTEGER DEFAULT 0,
                done_date TEXT,
                sort_order INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT,
                current_words INTEGER DEFAULT 0,
                target_words INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0
            );
            """
        )
        c.commit()

    # ---- projects -----------------------------------------------------
    def create_project(self, name: str, with_defaults: bool = True) -> int:
        now = _dt.date.today().isoformat()
        cur = self.conn.execute(
            "INSERT INTO projects(name, created_at) VALUES (?,?)", (name, now)
        )
        pid = cur.lastrowid
        # required sections
        for i, (sname, target) in enumerate(REQUIRED_SECTIONS):
            self.conn.execute(
                "INSERT INTO sections(project_id,name,target_words,sort_order) "
                "VALUES (?,?,?,?)",
                (pid, sname, target, i),
            )
        if with_defaults:
            dates = default_checkpoint_dates()
            for i, cname in enumerate(DEFAULT_CHECKPOINTS):
                self.conn.execute(
                    "INSERT INTO checkpoints(project_id,name,target_date,sort_order) "
                    "VALUES (?,?,?,?)",
                    (pid, cname, dates[i], i),
                )
        self.conn.commit()
        return pid

    def list_projects(self):
        return self.conn.execute(
            "SELECT * FROM projects ORDER BY name COLLATE NOCASE"
        ).fetchall()

    def get_project(self, pid: int):
        return self.conn.execute(
            "SELECT * FROM projects WHERE id=?", (pid,)
        ).fetchone()

    def update_project(self, pid: int, **fields):
        if not fields:
            return
        keys = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [pid]
        self.conn.execute(f"UPDATE projects SET {keys} WHERE id=?", vals)
        self.conn.commit()

    def rename_project(self, pid: int, name: str):
        self.update_project(pid, name=name)

    def delete_project(self, pid: int):
        self.conn.execute("DELETE FROM projects WHERE id=?", (pid,))
        self.conn.commit()

    # ---- sources ------------------------------------------------------
    def list_sources(self, pid: int):
        return self.conn.execute(
            "SELECT * FROM sources WHERE project_id=? ORDER BY id", (pid,)
        ).fetchall()

    def add_source(self, pid: int, cite_key: str, entry_type: str, fields: dict) -> int:
        now = _dt.date.today().isoformat()
        cur = self.conn.execute(
            "INSERT INTO sources(project_id,cite_key,entry_type,fields,created_at) "
            "VALUES (?,?,?,?,?)",
            (pid, cite_key, entry_type, json.dumps(fields), now),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_source(self, sid: int, cite_key: str, entry_type: str, fields: dict):
        self.conn.execute(
            "UPDATE sources SET cite_key=?, entry_type=?, fields=? WHERE id=?",
            (cite_key, entry_type, json.dumps(fields), sid),
        )
        self.conn.commit()

    def delete_source(self, sid: int):
        self.conn.execute("DELETE FROM sources WHERE id=?", (sid,))
        self.conn.commit()

    # ---- checkpoints --------------------------------------------------
    def list_checkpoints(self, pid: int):
        return self.conn.execute(
            "SELECT * FROM checkpoints WHERE project_id=? "
            "ORDER BY (target_date IS NULL), target_date, sort_order, id",
            (pid,),
        ).fetchall()

    def add_checkpoint(self, pid: int, name: str, target_date: Optional[str]):
        n = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order),0)+1 FROM checkpoints WHERE project_id=?",
            (pid,),
        ).fetchone()[0]
        self.conn.execute(
            "INSERT INTO checkpoints(project_id,name,target_date,sort_order) "
            "VALUES (?,?,?,?)",
            (pid, name, target_date, n),
        )
        self.conn.commit()

    def update_checkpoint(self, cid: int, **fields):
        keys = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [cid]
        self.conn.execute(f"UPDATE checkpoints SET {keys} WHERE id=?", vals)
        self.conn.commit()

    def delete_checkpoint(self, cid: int):
        self.conn.execute("DELETE FROM checkpoints WHERE id=?", (cid,))
        self.conn.commit()

    # ---- sections -----------------------------------------------------
    def list_sections(self, pid: int):
        return self.conn.execute(
            "SELECT * FROM sections WHERE project_id=? ORDER BY sort_order, id",
            (pid,),
        ).fetchall()

    def update_section(self, sid: int, **fields):
        keys = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [sid]
        self.conn.execute(f"UPDATE sections SET {keys} WHERE id=?", vals)
        self.conn.commit()


# ===========================================================================
#  BibTeX parsing
# ===========================================================================

def parse_bibtex(text: str):
    """Parse BibTeX text into a list of dicts: {type, key, fields}.

    A small, dependency-free parser that handles brace- and quote-delimited
    values and nested braces.
    """
    entries = []
    i, n = 0, len(text)
    while i < n:
        at = text.find("@", i)
        if at == -1:
            break
        # entry type
        j = at + 1
        while j < n and (text[j].isalpha()):
            j += 1
        etype = text[at + 1:j].strip().lower()
        # find opening brace
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j >= n or text[j] != "{":
            i = at + 1
            continue
        # find the matching closing brace for the whole entry
        depth = 0
        k = j
        while k < n:
            ch = text[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        body = text[j + 1:k]
        i = k + 1
        if etype in ("comment", "preamble", "string"):
            continue
        entry = _parse_entry_body(body)
        if entry is not None:
            entry["type"] = etype
            entries.append(entry)
    return entries


def _parse_entry_body(body: str):
    # first comma separates the cite key from the fields
    comma = body.find(",")
    if comma == -1:
        key = body.strip()
        return {"key": key, "fields": {}}
    key = body[:comma].strip()
    rest = body[comma + 1:]
    fields = {}
    i, n = 0, len(rest)
    while i < n:
        # field name
        while i < n and rest[i] in " \t\r\n,":
            i += 1
        m = re.match(r"[A-Za-z\-_]+", rest[i:])
        if not m:
            break
        fname = m.group(0).lower()
        i += m.end()
        while i < n and rest[i] in " \t\r\n":
            i += 1
        if i >= n or rest[i] != "=":
            break
        i += 1
        while i < n and rest[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        # value: braces, quotes, or bare
        if rest[i] == "{":
            depth = 0
            start = i
            while i < n:
                if rest[i] == "{":
                    depth += 1
                elif rest[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            value = rest[start + 1:i]
            i += 1
        elif rest[i] == '"':
            start = i + 1
            i += 1
            while i < n and rest[i] != '"':
                i += 1
            value = rest[start:i]
            i += 1
        else:
            start = i
            while i < n and rest[i] not in ",\r\n":
                i += 1
            value = rest[start:i].strip()
        fields[fname] = _clean_value(value)
    return {"key": key, "fields": fields}


def _clean_value(v: str) -> str:
    v = v.replace("\n", " ").replace("\r", " ")
    v = re.sub(r"\s+", " ", v).strip()
    v = v.replace("{", "").replace("}", "")
    v = v.replace("\\&", "&").replace("~", " ").replace("--", "-")
    return v.strip()


def to_bibtex(cite_key: str, entry_type: str, fields: dict) -> str:
    lines = [f"@{entry_type}{{{cite_key},"]
    items = [(k, v) for k, v in fields.items() if str(v).strip()]
    for idx, (k, v) in enumerate(items):
        comma = "," if idx < len(items) - 1 else ""
        lines.append(f"  {k} = {{{v}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


# ===========================================================================
#  Author-name handling
# ===========================================================================

def split_authors(author_field: str):
    """Return a list of (last, first) tuples from a BibTeX author field."""
    if not author_field:
        return []
    parts = re.split(r"\s+and\s+", author_field.strip())
    out = []
    for p in parts:
        p = p.strip().strip(",")
        if not p:
            continue
        if "," in p:
            last, first = p.split(",", 1)
            out.append((last.strip(), first.strip()))
        else:
            toks = p.split()
            if len(toks) == 1:
                out.append((toks[0], ""))
            else:
                out.append((toks[-1], " ".join(toks[:-1])))
    return out


def _initials(first: str) -> str:
    """Convert a first / middle name string to APA initials: 'John Q' -> 'J. Q.'"""
    bits = re.split(r"[\s\.\-]+", first.strip())
    out = []
    for b in bits:
        if b:
            out.append(b[0].upper() + ".")
    return " ".join(out)


def authors_mla(authors):
    """MLA author string."""
    if not authors:
        return ""
    if len(authors) == 1:
        last, first = authors[0]
        return f"{last}, {first}".strip().rstrip(",") if first else last
    if len(authors) == 2:
        a = f"{authors[0][0]}, {authors[0][1]}".strip().rstrip(",")
        b = f"{authors[1][1]} {authors[1][0]}".strip()
        return f"{a}, and {b}"
    # 3+ authors -> et al.
    first = authors[0]
    a = f"{first[0]}, {first[1]}".strip().rstrip(",")
    return f"{a}, et al."


def authors_apa(authors):
    """APA author string (up to 20 listed; 21+ uses ellipsis)."""
    if not authors:
        return ""

    def one(a):
        last, first = a
        ini = _initials(first)
        return f"{last}, {ini}".strip().rstrip(",") if ini else last

    if len(authors) == 1:
        return one(authors[0])
    if len(authors) <= 20:
        formatted = [one(a) for a in authors]
        return ", ".join(formatted[:-1]) + ", & " + formatted[-1]
    # 21+ : first 19, ellipsis, final author
    formatted = [one(a) for a in authors[:19]]
    return ", ".join(formatted) + ", . . . " + one(authors[-1])


def intext_authors_mla(authors):
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0][0]
    if len(authors) == 2:
        return f"{authors[0][0]} and {authors[1][0]}"
    return f"{authors[0][0]} et al."


def intext_authors_apa(authors):
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0][0]
    if len(authors) == 2:
        return f"{authors[0][0]} & {authors[1][0]}"
    return f"{authors[0][0]} et al."


# ===========================================================================
#  Citation formatting  (returns text with italic markers I0..I1)
# ===========================================================================

def _g(fields, *keys):
    for k in keys:
        v = fields.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _ensure_period(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s if s.endswith((".", "!", "?")) else s + "."


def _mla_quote(title: str) -> str:
    """MLA: title in quotes with the period (or existing ?/!) inside."""
    t = title.strip()
    if not t:
        return ""
    if t[-1] in "?!":
        return f'"{t}"'
    return f'"{t}."'


def format_citation(entry_type: str, fields: dict, style: str) -> str:
    style = style.upper()
    if style == "APA":
        return _format_apa(entry_type, fields)
    return _format_mla(entry_type, fields)


# ----- MLA 9th -------------------------------------------------------------

def _format_mla(etype: str, f: dict) -> str:
    authors = split_authors(_g(f, "author", "editor"))
    auth = authors_mla(authors)
    title = _g(f, "title")
    year = _g(f, "year", "date")
    out = []
    if auth:
        out.append(_ensure_period(auth))

    if etype in ("book", "phdthesis", "mastersthesis"):
        if title:
            out.append(_ensure_period(_ital(title)))
        pub = _g(f, "publisher", "school", "institution")
        tail = ", ".join(x for x in [pub, year] if x)
        if tail:
            out.append(_ensure_period(tail))

    elif etype in ("online", "misc"):
        if title:
            out.append(_mla_quote(title))
        site = _g(f, "howpublished", "publisher", "journal")
        if site:
            out.append(_ensure_period(_ital(site)))
        date = year
        url = _g(f, "url")
        urldate = _g(f, "urldate")
        seg = ", ".join(x for x in [date, url] if x)
        if seg:
            out.append(_ensure_period(seg))
        if urldate:
            out.append(_ensure_period(f"Accessed {urldate}"))

    else:  # article / inproceedings / incollection / techreport
        if title:
            out.append(_mla_quote(title))
        container = _g(f, "journal", "booktitle")
        bits = []
        if container:
            bits.append(_ital(container))
        vol = _g(f, "volume")
        if vol:
            bits.append(f"vol. {vol}")
        num = _g(f, "number")
        if num:
            bits.append(f"no. {num}")
        if year:
            bits.append(year)
        pages = _g(f, "pages")
        if pages:
            bits.append("pp. " + pages.replace("--", "-"))
        doi = _g(f, "doi")
        url = _g(f, "url")
        if doi:
            bits.append("https://doi.org/" + doi.replace("https://doi.org/", ""))
        elif url:
            bits.append(url)
        if bits:
            out.append(_ensure_period(", ".join(bits)))

    return " ".join(out).strip()


# ----- APA 7th -------------------------------------------------------------

def _format_apa(etype: str, f: dict) -> str:
    authors = split_authors(_g(f, "author", "editor"))
    auth = authors_apa(authors)
    title = _g(f, "title")
    year = _g(f, "year", "date") or "n.d."
    out = []
    if auth:
        out.append(_ensure_period(auth))
    out.append(f"({year}).")

    if etype in ("book", "phdthesis", "mastersthesis"):
        if title:
            out.append(_ensure_period(_ital(title)))
        if etype == "phdthesis":
            out.append("[Doctoral dissertation].")
        elif etype == "mastersthesis":
            out.append("[Master's thesis].")
        pub = _g(f, "publisher", "school", "institution")
        if pub:
            out.append(_ensure_period(pub))

    elif etype in ("online", "misc"):
        if title:
            out.append(_ensure_period(_ital(title)))
        site = _g(f, "howpublished", "publisher")
        if site:
            out.append(_ensure_period(site))
        url = _g(f, "url")
        if url:
            out.append(url)

    else:  # article and similar
        if title:
            out.append(_ensure_period(title))
        container = _g(f, "journal", "booktitle")
        seg = ""
        if container:
            seg = _ital(container)
            vol = _g(f, "volume")
            num = _g(f, "number")
            if vol:
                seg += ", " + _ital(vol)
                if num:
                    seg += f"({num})"
            pages = _g(f, "pages")
            if pages:
                seg += ", " + pages.replace("--", "-")
            out.append(_ensure_period(seg))
        doi = _g(f, "doi")
        if doi:
            out.append("https://doi.org/" + doi.replace("https://doi.org/", ""))
        elif _g(f, "url"):
            out.append(_g(f, "url"))

    return " ".join(out).strip()


# ----- In-text -------------------------------------------------------------

def intext_citation(entry_type: str, fields: dict, style: str, page: str = "") -> str:
    style = style.upper()
    authors = split_authors(_g(fields, "author", "editor"))
    if style == "APA":
        names = intext_authors_apa(authors) or _g(fields, "title")[:25]
        year = _g(fields, "year", "date") or "n.d."
        if page.strip():
            return f"({names}, {year}, p. {page.strip()})"
        return f"({names}, {year})"
    # MLA
    names = intext_authors_mla(authors) or _g(fields, "title")[:25]
    if page.strip():
        return f"({names} {page.strip()})"
    return f"({names})"


def sort_key_for_entry(fields: dict) -> str:
    authors = split_authors(_g(fields, "author", "editor"))
    if authors:
        return authors[0][0].lower()
    return _g(fields, "title").lower()


# ===========================================================================
#  PDF export
# ===========================================================================

def export_citation_pdf(path: str, project_name: str, style: str, citations):
    """citations: list of plain (marker-containing) reference strings,
    already sorted.  Tries reportlab, falls back to a built-in writer."""
    style = style.upper()
    heading = "Works Cited" if style == "MLA" else "References"
    try:
        _export_pdf_reportlab(path, project_name, heading, citations)
    except Exception:
        _export_pdf_fallback(path, project_name, heading, citations)


def _export_pdf_reportlab(path, project_name, heading, citations):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER

    def conv(s):
        # escape XML, then turn italic markers into <i> tags
        s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        s = s.replace(I0, "<i>").replace(I1, "</i>")
        return s

    doc = SimpleDocTemplate(
        path, pagesize=letter,
        leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch,
        title=f"{project_name} - {heading}",
    )
    title_style = ParagraphStyle(
        "title", fontName="Times-Bold", fontSize=14, leading=20,
        alignment=TA_CENTER, spaceAfter=6)
    sub_style = ParagraphStyle(
        "sub", fontName="Times-Italic", fontSize=11, leading=16,
        alignment=TA_CENTER, spaceAfter=18)
    cite_style = ParagraphStyle(
        "cite", fontName="Times-Roman", fontSize=12, leading=24,
        leftIndent=0.5 * inch, firstLineIndent=-0.5 * inch, spaceAfter=12)

    flow = [Paragraph(conv(project_name), title_style),
            Paragraph(conv(heading), sub_style)]
    if not citations:
        flow.append(Paragraph("(No sources yet.)", cite_style))
    for c in citations:
        flow.append(Paragraph(conv(c), cite_style))
    doc.build(flow)


# ---- pure-Python PDF fallback --------------------------------------------

_WIDE = set("mwMW@%&")
_NARROW = set("iljftrI.,;:'!|()[]\" ")


def _char_w(ch: str, size: float) -> float:
    if ch in _WIDE:
        return 0.82 * size
    if ch in _NARROW:
        return 0.30 * size
    if ch.isupper():
        return 0.70 * size
    return 0.50 * size


def _text_w(s: str, size: float) -> float:
    return sum(_char_w(c, size) for c in s)


def _wrap(text: str, size: float, max_w: float):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else cur + " " + w
        if _text_w(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _export_pdf_fallback(path, project_name, heading, citations):
    PAGE_W, PAGE_H = 612.0, 792.0
    MARGIN = 72.0
    usable = PAGE_W - 2 * MARGIN
    size = 12.0
    leading = 24.0
    hang = 36.0  # 0.5 inch hanging indent

    # Build a flat list of (x, text, font) lines, then paginate by leading.
    blocks = []  # (text, font, indent_first, indent_rest)
    blocks.append((project_name, "F2", (usable - _text_w(project_name, 14)) / 2, None, 14))
    blocks.append((heading, "F3", (usable - _text_w(heading, 11)) / 2, None, 11))
    blocks.append(("", "F1", 0, 0, size))  # spacer
    items = citations if citations else ["(No sources yet.)"]
    for c in items:
        plain = strip_markers(c)
        wrapped = _wrap(plain, size, usable - hang)
        for li, line in enumerate(wrapped):
            ind = 0 if li == 0 else hang
            blocks.append((line, "F1", ind, ind, size))
        blocks.append(("", "F1", 0, 0, 6))  # gap between citations

    # paginate
    pages = []
    cur = []
    y = PAGE_H - MARGIN
    for (text, font, ind, _r, fsize) in blocks:
        step = leading if fsize >= 12 else (fsize + 6)
        if y - step < MARGIN:
            pages.append(cur)
            cur = []
            y = PAGE_H - MARGIN
        if text:
            cur.append((MARGIN + ind, y, text, font, fsize))
        y -= step
    if cur:
        pages.append(cur)
    if not pages:
        pages = [[]]

    # assemble PDF objects
    objs = []  # list of byte strings (object bodies)

    def add(obj_bytes):
        objs.append(obj_bytes)
        return len(objs)  # object number

    # Reserve numbering: 1 Catalog, 2 Pages, fonts 3/4/5, then page+content pairs
    font_regular = "BT_PLACEHOLDER"
    # We'll fix references after we know page object numbers.

    # Fonts
    fonts = {
        "F1": b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
        "F2": b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold >>",
        "F3": b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic >>",
    }

    n_catalog = 1
    n_pages = 2
    n_f1, n_f2, n_f3 = 3, 4, 5
    next_obj = 6
    page_obj_nums = []
    content_objs = []  # (num, bytes)
    for pg in pages:
        content_lines = ["BT"]
        for (x, y, text, font, fsize) in pg:
            content_lines.append(f"/{font} {fsize:.1f} Tf")
            content_lines.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
            content_lines.append(f"({_pdf_escape(text)}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("latin-1", "replace")
        content_num = next_obj
        next_obj += 1
        page_num = next_obj
        next_obj += 1
        content_objs.append((content_num, stream))
        page_obj_nums.append((page_num, content_num))

    # Now build the actual object byte bodies in order.
    bodies = {}
    kids = " ".join(f"{pn} 0 R" for pn, _ in page_obj_nums)
    bodies[n_catalog] = f"<< /Type /Catalog /Pages {n_pages} 0 R >>".encode()
    bodies[n_pages] = (
        f"<< /Type /Pages /Count {len(page_obj_nums)} /Kids [ {kids} ] >>".encode()
    )
    bodies[n_f1] = fonts["F1"]
    bodies[n_f2] = fonts["F2"]
    bodies[n_f3] = fonts["F3"]
    for cnum, stream in content_objs:
        bodies[cnum] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream + b"\nendstream"
        )
    for (pnum, cnum) in page_obj_nums:
        bodies[pnum] = (
            f"<< /Type /Page /Parent {n_pages} 0 R "
            f"/MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
            f"/Resources << /Font << /F1 {n_f1} 0 R /F2 {n_f2} 0 R "
            f"/F3 {n_f3} 0 R >> >> /Contents {cnum} 0 R >>"
        ).encode()

    total = max(bodies.keys())
    out = bytearray()
    out += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = {}
    for num in range(1, total + 1):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode()
        out += bodies[num]
        out += b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {total + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, total + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += b"trailer\n"
    out += f"<< /Size {total + 1} /Root {n_catalog} 0 R >>\n".encode()
    out += b"startxref\n"
    out += f"{xref_pos}\n".encode()
    out += b"%%EOF"
    with open(path, "wb") as fh:
        fh.write(bytes(out))


# ===========================================================================
#  GUI
# ===========================================================================

def launch_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog

    db = DB()

    # ensure at least one project exists
    if not db.list_projects():
        db.create_project("My AP Research Project")

    # -------------------------------------------------------------------
    class App(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("AP Research Toolkit")
            self.geometry("1040x680")
            self.minsize(900, 560)
            self.current_pid = None

            self._build_style()
            self._build_topbar()

            self.nb = ttk.Notebook(self)
            self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            self.tab_dash = DashboardTab(self.nb, self)
            self.tab_src = SourcesTab(self.nb, self)
            self.tab_time = TimelineTab(self.nb, self)
            self.tab_sec = SectionsTab(self.nb, self)
            self.nb.add(self.tab_dash, text="  Dashboard  ")
            self.nb.add(self.tab_src, text="  Sources  ")
            self.nb.add(self.tab_time, text="  Timeline  ")
            self.nb.add(self.tab_sec, text="  Sections  ")
            self.nb.bind("<<NotebookTabChanged>>", lambda e: self.refresh_all())

            self.refresh_project_list(select_first=True)

        # ---- style ----
        def _build_style(self):
            s = ttk.Style(self)
            try:
                s.theme_use("clam")
            except Exception:
                pass
            s.configure("TNotebook.Tab", padding=(14, 7), font=("Segoe UI", 10))
            s.configure("Header.TLabel", font=("Segoe UI", 13, "bold"))
            s.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#555")
            s.configure("Big.TLabel", font=("Segoe UI", 22, "bold"))
            s.configure("Card.TFrame", relief="solid", borderwidth=1)

        # ---- top bar ----
        def _build_topbar(self):
            bar = ttk.Frame(self, padding=(10, 8))
            bar.pack(fill="x")
            ttk.Label(bar, text="Project:", font=("Segoe UI", 10, "bold")).pack(side="left")
            self.project_var = tk.StringVar()
            self.project_cb = ttk.Combobox(bar, textvariable=self.project_var,
                                           state="readonly", width=34)
            self.project_cb.pack(side="left", padx=6)
            self.project_cb.bind("<<ComboboxSelected>>", self._on_project_change)

            ttk.Button(bar, text="New", width=6, command=self.new_project).pack(side="left", padx=2)
            ttk.Button(bar, text="Rename", width=8, command=self.rename_project).pack(side="left", padx=2)
            ttk.Button(bar, text="Delete", width=8, command=self.delete_project).pack(side="left", padx=2)

            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
            ttk.Label(bar, text="Citation style:", font=("Segoe UI", 10, "bold")).pack(side="left")
            self.style_var = tk.StringVar(value="MLA")
            ttk.Radiobutton(bar, text="MLA", value="MLA", variable=self.style_var,
                            command=self._on_style_change).pack(side="left", padx=(6, 2))
            ttk.Radiobutton(bar, text="APA", value="APA", variable=self.style_var,
                            command=self._on_style_change).pack(side="left")

        # ---- project helpers ----
        def refresh_project_list(self, select_first=False, select_pid=None):
            projs = db.list_projects()
            self._proj_map = {p["name"]: p["id"] for p in projs}
            names = list(self._proj_map.keys())
            self.project_cb["values"] = names
            if select_pid is not None:
                for nm, pid in self._proj_map.items():
                    if pid == select_pid:
                        self.project_var.set(nm)
                        self.current_pid = pid
                        break
            elif select_first and names:
                self.project_var.set(names[0])
                self.current_pid = self._proj_map[names[0]]
            self._sync_style_from_project()
            self.refresh_all()

        def _on_project_change(self, _e=None):
            nm = self.project_var.get()
            self.current_pid = self._proj_map.get(nm)
            self._sync_style_from_project()
            self.refresh_all()

        def _sync_style_from_project(self):
            if self.current_pid:
                p = db.get_project(self.current_pid)
                if p:
                    self.style_var.set(p["citation_style"] or "MLA")

        def _on_style_change(self):
            if self.current_pid:
                db.update_project(self.current_pid, citation_style=self.style_var.get())
            self.refresh_all()

        def new_project(self):
            name = simpledialog.askstring("New Project", "Project name:", parent=self)
            if not name:
                return
            pid = db.create_project(name.strip())
            self.refresh_project_list(select_pid=pid)

        def rename_project(self):
            if not self.current_pid:
                return
            cur = self.project_var.get()
            name = simpledialog.askstring("Rename Project", "New name:",
                                          initialvalue=cur, parent=self)
            if not name:
                return
            db.rename_project(self.current_pid, name.strip())
            self.refresh_project_list(select_pid=self.current_pid)

        def delete_project(self):
            if not self.current_pid:
                return
            if len(db.list_projects()) <= 1:
                messagebox.showinfo("Cannot delete",
                                    "You must keep at least one project.")
                return
            if not messagebox.askyesno(
                "Delete project",
                f"Delete '{self.project_var.get()}' and all its data?\n"
                "This cannot be undone."):
                return
            db.delete_project(self.current_pid)
            self.refresh_project_list(select_first=True)

        def refresh_all(self):
            if not self.current_pid:
                return
            for tab in (self.tab_dash, self.tab_src, self.tab_time, self.tab_sec):
                try:
                    tab.refresh()
                except Exception:
                    pass

        @property
        def style(self):
            return self.style_var.get()

    # -------------------------------------------------------------------
    class DashboardTab(ttk.Frame):
        def __init__(self, master, app):
            super().__init__(master, padding=14)
            self.app = app
            top = ttk.Frame(self)
            top.pack(fill="x")
            ttk.Label(top, text="Research Question", style="Header.TLabel").pack(anchor="w")
            self.rq = tk.Text(self, height=3, wrap="word", font=("Segoe UI", 10))
            self.rq.pack(fill="x", pady=(4, 2))
            rqbar = ttk.Frame(self)
            rqbar.pack(fill="x")
            ttk.Button(rqbar, text="Save question", command=self.save_rq).pack(side="left")
            ttk.Label(rqbar, text="(your central inquiry — keep it focused)",
                      style="Sub.TLabel").pack(side="left", padx=8)

            ttk.Separator(self).pack(fill="x", pady=12)

            self.cards = ttk.Frame(self)
            self.cards.pack(fill="x")
            self.card_words = self._card(self.cards, "Word Count", 0)
            self.card_sources = self._card(self.cards, "Sources", 1)
            self.card_progress = self._card(self.cards, "Checkpoints", 2)
            for i in range(3):
                self.cards.columnconfigure(i, weight=1)

            ttk.Separator(self).pack(fill="x", pady=12)
            ttk.Label(self, text="Next up", style="Header.TLabel").pack(anchor="w")
            self.next_box = ttk.Frame(self)
            self.next_box.pack(fill="x", pady=4)
            self.next_label = ttk.Label(self.next_box, text="", font=("Segoe UI", 11))
            self.next_label.pack(anchor="w")

            ttk.Separator(self).pack(fill="x", pady=12)
            ttk.Label(self, text="Word budget (4,000-5,000 words required)",
                      style="Header.TLabel").pack(anchor="w")
            self.budget_canvas = tk.Canvas(self, height=34, highlightthickness=0)
            self.budget_canvas.pack(fill="x", pady=6)
            self.budget_label = ttk.Label(self, text="", style="Sub.TLabel")
            self.budget_label.pack(anchor="w")

        def _card(self, parent, title, col):
            f = ttk.Frame(parent, style="Card.TFrame", padding=12)
            f.grid(row=0, column=col, sticky="nsew", padx=6)
            ttk.Label(f, text=title, style="Sub.TLabel").pack(anchor="w")
            big = ttk.Label(f, text="-", style="Big.TLabel")
            big.pack(anchor="w")
            sub = ttk.Label(f, text="", style="Sub.TLabel")
            sub.pack(anchor="w")
            return (big, sub)

        def save_rq(self):
            if not self.app.current_pid:
                return
            db.update_project(self.app.current_pid,
                              research_question=self.rq.get("1.0", "end").strip())
            messagebox.showinfo("Saved", "Research question saved.")

        def refresh(self):
            pid = self.app.current_pid
            if not pid:
                return
            p = db.get_project(pid)
            self.rq.delete("1.0", "end")
            self.rq.insert("1.0", p["research_question"] or "")

            sections = db.list_sections(pid)
            total_words = sum(s["current_words"] for s in sections)
            wmin, wmax = p["word_min"], p["word_max"]
            self.card_words[0].config(text=f"{total_words:,}")
            self.card_words[1].config(text=f"target {wmin:,}-{wmax:,}")

            srcs = db.list_sources(pid)
            self.card_sources[0].config(text=str(len(srcs)))
            self.card_sources[1].config(text=f"{p['citation_style']} citations")

            cps = db.list_checkpoints(pid)
            done = sum(1 for c in cps if c["done"])
            self.card_progress[0].config(text=f"{done}/{len(cps)}")
            self.card_progress[1].config(text="completed")

            # next checkpoint
            upcoming = [c for c in cps if not c["done"] and c["target_date"]]
            today = _dt.date.today()
            nxt = None
            for c in upcoming:
                try:
                    d = _dt.date.fromisoformat(c["target_date"])
                except Exception:
                    continue
                if nxt is None or d < nxt[1]:
                    nxt = (c, d)
            if nxt:
                days = (nxt[1] - today).days
                when = ("overdue by %d days" % -days if days < 0
                        else "due today" if days == 0 else f"in {days} days")
                self.next_label.config(
                    text=f"→  {nxt[0]['name']}  —  {nxt[1].isoformat()} ({when})")
            else:
                self.next_label.config(text="All checkpoints complete ✓")

            self._draw_budget(total_words, wmin, wmax)

        def _draw_budget(self, total, wmin, wmax):
            c = self.budget_canvas
            c.delete("all")
            c.update_idletasks()
            w = c.winfo_width() or 600
            h = 34
            scale_max = max(wmax * 1.15, total * 1.05, 1)
            # background track
            c.create_rectangle(0, 8, w, h - 2, fill="#e9e9e9", outline="")
            # acceptable band
            x1 = w * wmin / scale_max
            x2 = w * wmax / scale_max
            c.create_rectangle(x1, 8, x2, h - 2, fill="#cfe9cf", outline="")
            # fill
            fillx = min(w, w * total / scale_max)
            if total < wmin:
                col = "#e0a83e"
            elif total <= wmax:
                col = "#3a9d4a"
            else:
                col = "#cc4b3b"
            c.create_rectangle(0, 8, fillx, h - 2, fill=col, outline="")
            c.create_line(x1, 4, x1, h, fill="#2a7d3a")
            c.create_line(x2, 4, x2, h, fill="#2a7d3a")
            status = ("under the minimum" if total < wmin
                      else "within the limit ✓" if total <= wmax
                      else "OVER the maximum")
            self.budget_label.config(
                text=f"{total:,} words — {status}. Green band = {wmin:,}-{wmax:,}.")

    # -------------------------------------------------------------------
    class SourcesTab(ttk.Frame):
        def __init__(self, master, app):
            super().__init__(master, padding=10)
            self.app = app

            toolbar = ttk.Frame(self)
            toolbar.pack(fill="x")
            ttk.Button(toolbar, text="Add source", command=self.add_source).pack(side="left")
            ttk.Button(toolbar, text="Edit", command=self.edit_source).pack(side="left", padx=3)
            ttk.Button(toolbar, text="Delete", command=self.delete_source).pack(side="left")
            ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
            ttk.Button(toolbar, text="Import BibTeX…", command=self.import_bibtex).pack(side="left")
            ttk.Button(toolbar, text="Export BibTeX…", command=self.export_bibtex).pack(side="left", padx=3)
            ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
            ttk.Button(toolbar, text="Export Citation Sheet (PDF)…",
                       command=self.export_pdf).pack(side="left")

            paned = ttk.Panedwindow(self, orient="vertical")
            paned.pack(fill="both", expand=True, pady=(8, 0))

            # source list
            list_frame = ttk.Frame(paned)
            cols = ("key", "type", "author", "year", "title")
            self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=10)
            for c, txt, wd in (("key", "Key", 120), ("type", "Type", 90),
                               ("author", "Author", 180), ("year", "Year", 60),
                               ("title", "Title", 360)):
                self.tree.heading(c, text=txt)
                self.tree.column(c, width=wd, anchor="w")
            self.tree.pack(side="left", fill="both", expand=True)
            sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
            sb.pack(side="right", fill="y")
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.bind("<<TreeviewSelect>>", self.on_select)
            self.tree.bind("<Double-1>", lambda e: self.edit_source())
            paned.add(list_frame, weight=3)

            # citation detail panel
            detail = ttk.Frame(paned, padding=(2, 8))
            ttk.Label(detail, text="Full citation", style="Header.TLabel").pack(anchor="w")
            self.full_txt = tk.Text(detail, height=4, wrap="word", font=("Georgia", 11),
                                    background="#fbfbf5")
            self.full_txt.pack(fill="x", pady=(2, 2))
            fbar = ttk.Frame(detail)
            fbar.pack(fill="x")
            ttk.Button(fbar, text="Copy full citation",
                       command=self.copy_full).pack(side="left")
            ttk.Label(fbar, text="(italics shown with *asterisks* for plain-text copy)",
                      style="Sub.TLabel").pack(side="left", padx=8)

            itf = ttk.Frame(detail)
            itf.pack(fill="x", pady=(10, 0))
            ttk.Label(itf, text="In-text citation", style="Header.TLabel").pack(side="left")
            ttk.Label(itf, text="   page #:", style="Sub.TLabel").pack(side="left")
            self.page_var = tk.StringVar()
            pg = ttk.Entry(itf, textvariable=self.page_var, width=8)
            pg.pack(side="left", padx=4)
            self.page_var.trace_add("write", lambda *a: self._refresh_intext())
            self.intext_lbl = ttk.Label(detail, text="", font=("Georgia", 13, "bold"),
                                        foreground="#22427a")
            self.intext_lbl.pack(anchor="w", pady=4)
            ttk.Button(detail, text="Copy in-text citation",
                       command=self.copy_intext).pack(anchor="w")
            paned.add(detail, weight=2)

            self._row_to_sid = {}

        # -- data ops --
        def refresh(self):
            pid = self.app.current_pid
            self.tree.delete(*self.tree.get_children())
            self._row_to_sid.clear()
            if not pid:
                return
            srcs = db.list_sources(pid)
            for s in srcs:
                f = json.loads(s["fields"] or "{}")
                authors = split_authors(_g(f, "author", "editor"))
                aname = authors[0][0] if authors else "(no author)"
                if len(authors) > 1:
                    aname += " et al."
                iid = self.tree.insert("", "end", values=(
                    s["cite_key"], s["entry_type"], aname,
                    _g(f, "year", "date"), _g(f, "title")))
                self._row_to_sid[iid] = s["id"]
            self.full_txt.delete("1.0", "end")
            self.intext_lbl.config(text="")

        def _selected_source(self):
            sel = self.tree.selection()
            if not sel:
                return None
            sid = self._row_to_sid.get(sel[0])
            if sid is None:
                return None
            for s in db.list_sources(self.app.current_pid):
                if s["id"] == sid:
                    return s
            return None

        def on_select(self, _e=None):
            s = self._selected_source()
            if not s:
                return
            f = json.loads(s["fields"] or "{}")
            full = format_citation(s["entry_type"], f, self.app.style)
            # show italics as *asterisks* in the editable plain-text display
            display = full.replace(I0, "*").replace(I1, "*")
            self.full_txt.delete("1.0", "end")
            self.full_txt.insert("1.0", display)
            self._refresh_intext()

        def _refresh_intext(self):
            s = self._selected_source()
            if not s:
                self.intext_lbl.config(text="")
                return
            f = json.loads(s["fields"] or "{}")
            txt = intext_citation(s["entry_type"], f, self.app.style,
                                  page=self.page_var.get())
            self.intext_lbl.config(text=txt)

        def copy_full(self):
            s = self._selected_source()
            if not s:
                return
            f = json.loads(s["fields"] or "{}")
            txt = strip_markers(format_citation(s["entry_type"], f, self.app.style))
            self._copy(txt)

        def copy_intext(self):
            txt = self.intext_lbl.cget("text")
            if txt:
                self._copy(txt)

        def _copy(self, txt):
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.app.bell()

        def add_source(self):
            if not self.app.current_pid:
                return
            SourceEditor(self, self.app, None)

        def edit_source(self):
            s = self._selected_source()
            if not s:
                messagebox.showinfo("No selection", "Select a source to edit.")
                return
            SourceEditor(self, self.app, s)

        def delete_source(self):
            s = self._selected_source()
            if not s:
                return
            if messagebox.askyesno("Delete source", f"Delete '{s['cite_key']}'?"):
                db.delete_source(s["id"])
                self.refresh()

        def import_bibtex(self):
            ImportDialog(self, self.app)

        def export_bibtex(self):
            pid = self.app.current_pid
            srcs = db.list_sources(pid)
            if not srcs:
                messagebox.showinfo("Nothing to export", "No sources yet.")
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".bib", filetypes=[("BibTeX", "*.bib")],
                initialfile="sources.bib")
            if not path:
                return
            chunks = []
            for s in srcs:
                f = json.loads(s["fields"] or "{}")
                chunks.append(to_bibtex(s["cite_key"], s["entry_type"], f))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n\n".join(chunks) + "\n")
            messagebox.showinfo("Exported", f"Saved {len(srcs)} entries to:\n{path}")

        def export_pdf(self):
            pid = self.app.current_pid
            p = db.get_project(pid)
            srcs = db.list_sources(pid)
            style = self.app.style
            entries = []
            for s in srcs:
                f = json.loads(s["fields"] or "{}")
                entries.append((sort_key_for_entry(f),
                                format_citation(s["entry_type"], f, style)))
            entries.sort(key=lambda x: x[0])
            citations = [c for _, c in entries]
            heading = "Works Cited" if style == "MLA" else "References"
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                initialfile=f"{heading.replace(' ', '_')}.pdf")
            if not path:
                return
            try:
                export_citation_pdf(path, p["name"], style, citations)
            except Exception as e:
                messagebox.showerror("Export failed", str(e))
                return
            messagebox.showinfo("Exported",
                                f"{heading} sheet ({style}) saved to:\n{path}")

    # -------------------------------------------------------------------
    class SourceEditor(tk.Toplevel):
        def __init__(self, parent, app, source):
            super().__init__(parent)
            self.app = app
            self.source = source
            self.title("Edit Source" if source else "Add Source")
            self.geometry("560x620")
            self.transient(parent)
            self.grab_set()

            frm = ttk.Frame(self, padding=12)
            frm.pack(fill="both", expand=True)

            top = ttk.Frame(frm)
            top.pack(fill="x")
            ttk.Label(top, text="Cite key:").grid(row=0, column=0, sticky="w")
            self.key_var = tk.StringVar()
            ttk.Entry(top, textvariable=self.key_var, width=24).grid(row=0, column=1, sticky="w", padx=6)
            ttk.Label(top, text="Type:").grid(row=0, column=2, sticky="w", padx=(12, 0))
            self.type_var = tk.StringVar(value="article")
            ttk.Combobox(top, textvariable=self.type_var, values=ENTRY_TYPES,
                         state="readonly", width=14).grid(row=0, column=3, sticky="w", padx=6)

            ttk.Separator(frm).pack(fill="x", pady=10)

            self.vars = {}
            grid = ttk.Frame(frm)
            grid.pack(fill="both", expand=True)
            for i, (label, key) in enumerate(EDITOR_FIELDS):
                ttk.Label(grid, text=label + ":").grid(row=i, column=0, sticky="w", pady=2)
                v = tk.StringVar()
                ttk.Entry(grid, textvariable=v, width=52).grid(row=i, column=1, sticky="w", padx=6, pady=2)
                self.vars[key] = v
            grid.columnconfigure(1, weight=1)

            hint = ("Tip: enter authors as 'Last, First and Last, First'. "
                    "Only fill the fields relevant to the source type.")
            ttk.Label(frm, text=hint, style="Sub.TLabel", wraplength=520).pack(anchor="w", pady=(8, 4))

            btns = ttk.Frame(frm)
            btns.pack(fill="x", pady=(6, 0))
            ttk.Button(btns, text="Save", command=self.save).pack(side="right")
            ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

            if source:
                self.key_var.set(source["cite_key"])
                self.type_var.set(source["entry_type"])
                f = json.loads(source["fields"] or "{}")
                for k, v in f.items():
                    if k in self.vars:
                        self.vars[k].set(v)

        def save(self):
            key = self.key_var.get().strip()
            if not key:
                messagebox.showwarning("Missing key", "Please enter a cite key.", parent=self)
                return
            fields = {k: v.get().strip() for k, v in self.vars.items() if v.get().strip()}
            etype = self.type_var.get()
            if self.source:
                db.update_source(self.source["id"], key, etype, fields)
            else:
                db.add_source(self.app.current_pid, key, etype, fields)
            self.app.refresh_all()
            self.destroy()

    # -------------------------------------------------------------------
    class ImportDialog(tk.Toplevel):
        def __init__(self, parent, app):
            super().__init__(parent)
            self.app = app
            self.title("Import BibTeX")
            self.geometry("620x520")
            self.transient(parent)
            self.grab_set()
            frm = ttk.Frame(self, padding=12)
            frm.pack(fill="both", expand=True)
            ttk.Label(frm, text="Paste BibTeX below, or load a .bib file:",
                      style="Header.TLabel").pack(anchor="w")
            self.txt = tk.Text(frm, wrap="none", font=("Consolas", 10))
            self.txt.pack(fill="both", expand=True, pady=8)
            btns = ttk.Frame(frm)
            btns.pack(fill="x")
            ttk.Button(btns, text="Load file…", command=self.load_file).pack(side="left")
            ttk.Button(btns, text="Import", command=self.do_import).pack(side="right")
            ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

        def load_file(self):
            path = filedialog.askopenfilename(
                filetypes=[("BibTeX", "*.bib"), ("All files", "*.*")])
            if not path:
                return
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                self.txt.delete("1.0", "end")
                self.txt.insert("1.0", fh.read())

        def do_import(self):
            text = self.txt.get("1.0", "end")
            entries = parse_bibtex(text)
            if not entries:
                messagebox.showwarning("Nothing found",
                                       "No BibTeX entries were detected.", parent=self)
                return
            existing = {s["cite_key"] for s in db.list_sources(self.app.current_pid)}
            n = 0
            for e in entries:
                key = e["key"] or f"source{n+1}"
                base, suffix = key, 1
                while key in existing:
                    suffix += 1
                    key = f"{base}_{suffix}"
                existing.add(key)
                db.add_source(self.app.current_pid, key,
                              e.get("type", "misc"), e["fields"])
                n += 1
            self.app.refresh_all()
            messagebox.showinfo("Imported", f"Imported {n} source(s).", parent=self)
            self.destroy()

    # -------------------------------------------------------------------
    class TimelineTab(ttk.Frame):
        def __init__(self, master, app):
            super().__init__(master, padding=10)
            self.app = app
            bar = ttk.Frame(self)
            bar.pack(fill="x")
            ttk.Button(bar, text="Add checkpoint", command=self.add_cp).pack(side="left")
            ttk.Button(bar, text="Edit", command=self.edit_cp).pack(side="left", padx=3)
            ttk.Button(bar, text="Toggle done", command=self.toggle_cp).pack(side="left")
            ttk.Button(bar, text="Delete", command=self.delete_cp).pack(side="left", padx=3)
            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
            ttk.Button(bar, text="Restore default checkpoints",
                       command=self.add_defaults).pack(side="left")

            cols = ("status", "name", "date", "left")
            self.tree = ttk.Treeview(self, columns=cols, show="headings")
            for c, txt, wd, anc in (("status", "", 44, "center"),
                                    ("name", "Checkpoint", 420, "w"),
                                    ("date", "Target date", 130, "center"),
                                    ("left", "Days remaining", 140, "center")):
                self.tree.heading(c, text=txt)
                self.tree.column(c, width=wd, anchor=anc)
            self.tree.pack(fill="both", expand=True, pady=8)
            self.tree.tag_configure("done", foreground="#2a7d3a")
            self.tree.tag_configure("overdue", foreground="#cc4b3b")
            self.tree.bind("<Double-1>", lambda e: self.edit_cp())
            ttk.Label(self, text="Double-click a row to edit. Dates are fully adjustable.",
                      style="Sub.TLabel").pack(anchor="w")
            self._row_to_cid = {}

        def refresh(self):
            self.tree.delete(*self.tree.get_children())
            self._row_to_cid.clear()
            pid = self.app.current_pid
            if not pid:
                return
            today = _dt.date.today()
            for c in db.list_checkpoints(pid):
                tag = ""
                if c["done"]:
                    status = "✓"
                    left = "done"
                    tag = "done"
                else:
                    status = "○"
                    left = "-"
                    if c["target_date"]:
                        try:
                            d = _dt.date.fromisoformat(c["target_date"])
                            days = (d - today).days
                            if days < 0:
                                left = f"{-days}d overdue"
                                tag = "overdue"
                            elif days == 0:
                                left = "today"
                            else:
                                left = f"{days}d"
                        except Exception:
                            pass
                iid = self.tree.insert("", "end",
                                       values=(status, c["name"],
                                               c["target_date"] or "-", left),
                                       tags=(tag,) if tag else ())
                self._row_to_cid[iid] = c["id"]

        def _sel(self):
            sel = self.tree.selection()
            if not sel:
                return None
            cid = self._row_to_cid.get(sel[0])
            for c in db.list_checkpoints(self.app.current_pid):
                if c["id"] == cid:
                    return c
            return None

        def add_cp(self):
            CheckpointEditor(self, self.app, None)

        def edit_cp(self):
            c = self._sel()
            if not c:
                messagebox.showinfo("No selection", "Select a checkpoint.")
                return
            CheckpointEditor(self, self.app, c)

        def toggle_cp(self):
            c = self._sel()
            if not c:
                return
            new = 0 if c["done"] else 1
            db.update_checkpoint(c["id"], done=new,
                                 done_date=_dt.date.today().isoformat() if new else None)
            self.app.refresh_all()

        def delete_cp(self):
            c = self._sel()
            if not c:
                return
            if messagebox.askyesno("Delete", f"Delete checkpoint '{c['name']}'?"):
                db.delete_checkpoint(c["id"])
                self.refresh()

        def add_defaults(self):
            pid = self.app.current_pid
            dates = default_checkpoint_dates()
            for i, name in enumerate(DEFAULT_CHECKPOINTS):
                db.add_checkpoint(pid, name, dates[i])
            self.app.refresh_all()

    # -------------------------------------------------------------------
    class CheckpointEditor(tk.Toplevel):
        def __init__(self, parent, app, cp):
            super().__init__(parent)
            self.app = app
            self.cp = cp
            self.title("Edit Checkpoint" if cp else "Add Checkpoint")
            self.geometry("420x210")
            self.transient(parent)
            self.grab_set()
            frm = ttk.Frame(self, padding=14)
            frm.pack(fill="both", expand=True)
            ttk.Label(frm, text="Name:").grid(row=0, column=0, sticky="w", pady=4)
            self.name_var = tk.StringVar(value=cp["name"] if cp else "")
            ttk.Entry(frm, textvariable=self.name_var, width=36).grid(row=0, column=1, pady=4)
            ttk.Label(frm, text="Target date\n(YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=4)
            self.date_var = tk.StringVar(
                value=(cp["target_date"] if cp and cp["target_date"] else _dt.date.today().isoformat()))
            ttk.Entry(frm, textvariable=self.date_var, width=20).grid(row=1, column=1, sticky="w", pady=4)
            self.done_var = tk.IntVar(value=cp["done"] if cp else 0)
            ttk.Checkbutton(frm, text="Completed", variable=self.done_var).grid(
                row=2, column=1, sticky="w", pady=4)
            btns = ttk.Frame(frm)
            btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
            ttk.Button(btns, text="Save", command=self.save).pack(side="right")
            ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)

        def save(self):
            name = self.name_var.get().strip()
            if not name:
                messagebox.showwarning("Missing name", "Enter a checkpoint name.", parent=self)
                return
            date = self.date_var.get().strip()
            if date:
                try:
                    _dt.date.fromisoformat(date)
                except ValueError:
                    messagebox.showwarning("Bad date", "Use YYYY-MM-DD format.", parent=self)
                    return
            done = self.done_var.get()
            if self.cp:
                db.update_checkpoint(self.cp["id"], name=name, target_date=date or None,
                                     done=done,
                                     done_date=_dt.date.today().isoformat() if done else None)
            else:
                db.add_checkpoint(self.app.current_pid, name, date or None)
            self.app.refresh_all()
            self.destroy()

    # -------------------------------------------------------------------
    class SectionsTab(ttk.Frame):
        def __init__(self, master, app):
            super().__init__(master, padding=10)
            self.app = app
            ttk.Label(self, text="Required AP Research sections", style="Header.TLabel").pack(anchor="w")
            ttk.Label(self, text="Track your word count per section. Double-click to edit "
                                 "current/target words and notes.",
                      style="Sub.TLabel").pack(anchor="w", pady=(0, 6))

            cols = ("section", "current", "target", "bar")
            self.tree = ttk.Treeview(self, columns=cols, show="headings", height=9)
            for c, txt, wd, anc in (("section", "Section", 200, "w"),
                                    ("current", "Words", 90, "center"),
                                    ("target", "Target", 90, "center"),
                                    ("bar", "Progress", 420, "w")):
                self.tree.heading(c, text=txt)
                self.tree.column(c, width=wd, anchor=anc)
            self.tree.pack(fill="x", pady=4)
            self.tree.bind("<Double-1>", lambda e: self.edit_section())
            ttk.Button(self, text="Edit selected section", command=self.edit_section).pack(anchor="w", pady=4)

            ttk.Separator(self).pack(fill="x", pady=10)
            self.total_lbl = ttk.Label(self, text="", font=("Segoe UI", 12, "bold"))
            self.total_lbl.pack(anchor="w")

            ttk.Label(self, text="Notes for selected section", style="Header.TLabel").pack(anchor="w", pady=(10, 2))
            self.notes = tk.Text(self, height=6, wrap="word", font=("Segoe UI", 10))
            self.notes.pack(fill="both", expand=True)
            nbar = ttk.Frame(self)
            nbar.pack(fill="x", pady=4)
            ttk.Button(nbar, text="Save notes", command=self.save_notes).pack(side="left")
            self.tree.bind("<<TreeviewSelect>>", self.on_select)
            self._row_to_sid = {}

        def refresh(self):
            self.tree.delete(*self.tree.get_children())
            self._row_to_sid.clear()
            pid = self.app.current_pid
            if not pid:
                return
            secs = db.list_sections(pid)
            total = 0
            for s in secs:
                total += s["current_words"]
                pct = 0 if not s["target_words"] else min(1.0, s["current_words"] / s["target_words"])
                bar = self._bar(pct)
                iid = self.tree.insert("", "end", values=(
                    s["name"], s["current_words"], s["target_words"],
                    f"{bar} {int(pct*100)}%"))
                self._row_to_sid[iid] = s["id"]
            p = db.get_project(pid)
            wmin, wmax = p["word_min"], p["word_max"]
            if total < wmin:
                status = f"  —  {wmin-total:,} words under the minimum"
            elif total <= wmax:
                status = "  —  within the 4,000-5,000 limit ✓"
            else:
                status = f"  —  {total-wmax:,} words OVER the maximum"
            self.total_lbl.config(text=f"Total: {total:,} / {wmin:,}-{wmax:,}{status}")

        @staticmethod
        def _bar(pct, width=20):
            filled = int(round(pct * width))
            return "█" * filled + "░" * (width - filled)

        def _sel(self):
            sel = self.tree.selection()
            if not sel:
                return None
            sid = self._row_to_sid.get(sel[0])
            for s in db.list_sections(self.app.current_pid):
                if s["id"] == sid:
                    return s
            return None

        def on_select(self, _e=None):
            s = self._sel()
            self.notes.delete("1.0", "end")
            if s:
                self.notes.insert("1.0", s["notes"] or "")

        def save_notes(self):
            s = self._sel()
            if not s:
                messagebox.showinfo("No selection", "Select a section first.")
                return
            db.update_section(s["id"], notes=self.notes.get("1.0", "end").strip())
            messagebox.showinfo("Saved", "Notes saved.")

        def edit_section(self):
            s = self._sel()
            if not s:
                messagebox.showinfo("No selection", "Select a section to edit.")
                return
            cur = simpledialog.askinteger("Word count",
                                          f"Current words in '{s['name']}':",
                                          initialvalue=s["current_words"], minvalue=0,
                                          parent=self)
            if cur is None:
                return
            tgt = simpledialog.askinteger("Target",
                                          f"Target words for '{s['name']}':",
                                          initialvalue=s["target_words"], minvalue=0,
                                          parent=self)
            if tgt is None:
                tgt = s["target_words"]
            db.update_section(s["id"], current_words=cur, target_words=tgt)
            self.app.refresh_all()

    App().mainloop()


# ===========================================================================
#  Self-test (headless)
# ===========================================================================

def selftest():
    import tempfile
    print("Running self-test...")

    bib = """
    @article{smith2020,
      author = {Smith, John and Doe, Jane},
      title = {The Effects of Sleep on Learning},
      journal = {Journal of Cognitive Science},
      year = {2020}, volume = {12}, number = {3}, pages = {45--67},
      doi = {10.1000/abc123}
    }
    @book{brown2019,
      author = {Brown, Alice},
      title = {Research Methods for Students},
      publisher = {Academic Press}, year = {2019}
    }
    @online{web2021,
      author = {Lee, Sam},
      title = {Understanding Climate Data},
      howpublished = {Climate Org},
      year = {2021}, url = {https://example.org/climate},
      urldate = {2021-05-01}
    }
    """
    entries = parse_bibtex(bib)
    assert len(entries) == 3, f"expected 3 entries, got {len(entries)}"
    assert entries[0]["key"] == "smith2020"
    assert entries[0]["fields"]["volume"] == "12"
    print(" BibTeX parse: OK (3 entries)")

    for e in entries:
        for style in ("MLA", "APA"):
            full = strip_markers(format_citation(e["type"], e["fields"], style))
            it = intext_citation(e["type"], e["fields"], style, page="42")
            assert full and it, "empty citation"
            print(f"  [{style:3}] {full}")
            print(f"        in-text: {it}")

    # APA author edge cases
    a = split_authors("Smith, John and Doe, Jane and Lee, Sam")
    assert authors_apa(a) == "Smith, J., Doe, J., & Lee, S.", authors_apa(a)
    assert intext_authors_apa(a) == "Smith et al."
    assert authors_mla(a) == "Smith, John, et al."
    print(" Author formatting: OK")

    # DB round-trip in a temp file
    tmp = os.path.join(tempfile.gettempdir(), "_aprt_selftest.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    db = DB(tmp)
    pid = db.create_project("Test Project")
    assert len(db.list_sections(pid)) == 7
    assert len(db.list_checkpoints(pid)) == len(DEFAULT_CHECKPOINTS)

    # default timeline: starts after Sept 1, submission pinned to April 30
    for probe in (_dt.date(2026, 5, 24), _dt.date(2026, 10, 5),
                  _dt.date(2027, 2, 1)):
        sep, apr = academic_window(probe)
        assert (sep.month, sep.day) == (9, 1) and (apr.month, apr.day) == (4, 30)
        assert apr > sep and apr.year == sep.year + 1
        dates = [_dt.date.fromisoformat(d) for d in default_checkpoint_dates(probe)]
        assert all(d > sep for d in dates), "a checkpoint is on/before Sept 1"
        sub = dates[DEFAULT_CHECKPOINTS.index(SUBMISSION_CHECKPOINT)]
        assert sub == apr, f"submission {sub} != April 30 {apr}"
    print(" Timeline window (Sep 1 -> Apr 30 submission): OK")

    sid = db.add_source(pid, "smith2020", "article", entries[0]["fields"])
    assert len(db.list_sources(pid)) == 1
    db.delete_source(sid)
    assert len(db.list_sources(pid)) == 0
    print(" Database round-trip: OK")

    # PDF export (both paths)
    citations = [format_citation(e["type"], e["fields"], "MLA") for e in entries]
    citations.sort(key=lambda s: s.lower())
    p1 = os.path.join(tempfile.gettempdir(), "_aprt_test_reportlab.pdf")
    p2 = os.path.join(tempfile.gettempdir(), "_aprt_test_fallback.pdf")
    try:
        _export_pdf_reportlab(p1, "Test", "Works Cited", citations)
        assert os.path.getsize(p1) > 400
        print(f" PDF (reportlab): OK -> {p1} ({os.path.getsize(p1)} bytes)")
    except Exception as ex:
        print(f" PDF (reportlab): skipped ({ex})")
    _export_pdf_fallback(p2, "Test", "Works Cited", citations)
    assert os.path.getsize(p2) > 400
    with open(p2, "rb") as fh:
        assert fh.read(5) == b"%PDF-", "fallback PDF header wrong"
    print(f" PDF (fallback):  OK -> {p2} ({os.path.getsize(p2)} bytes)")

    db.close()
    os.remove(tmp)
    print("\nAll self-tests passed.")


# ===========================================================================
#  Entry point
# ===========================================================================

def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    launch_gui()


if __name__ == "__main__":
    main()
