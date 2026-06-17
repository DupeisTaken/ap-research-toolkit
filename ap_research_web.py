#!/usr/bin/env python3
"""Mobile/web front-end for the AP Research Toolkit.

This serves the same toolkit as a small web app you can use from a phone
browser and install as a PWA (Progressive Web App) — including on Android,
where the Tkinter desktop GUI cannot run.

It is a thin HTTP layer on top of the existing, correctness-sensitive logic
in ``ap_research_toolkit`` (the SQLite ``DB`` class, the BibTeX parser, the
MLA/APA citation engine, ``.ics`` and PDF export). None of that logic is
duplicated here — this module only translates HTTP requests into calls
against it and renders the results as JSON / downloadable files.

Run it::

    python ap_research_web.py            # http://localhost:8000
    python ap_research_web.py --port 9000
    python ap_research_web.py --host 0.0.0.0   # reachable from your phone

Like the rest of the project it uses only the Python standard library
(``reportlab`` remains optional and is used for PDF export when present).
The data lives in the same per-user SQLite database as the desktop app, so
the two stay in sync.
"""

from __future__ import annotations

import os
import re
import sys
import json
import html
import socket
import argparse
import tempfile
import datetime as _dt
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import ap_research_toolkit as art

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# A single shared database connection. We deliberately run the server
# single-threaded (plain HTTPServer) so this sqlite connection is only ever
# touched from one thread — matching how the desktop app uses it.
db = art.DB(art.DB_PATH)

_STYLES = ("MLA", "APA")
_PROJECT_FIELDS = {"name", "research_question", "citation_style",
                   "word_min", "word_max"}


# ---------------------------------------------------------------------------
#  Rendering helpers
# ---------------------------------------------------------------------------

def markers_to_html(s: str) -> str:
    """Turn a citation string (with private italic markers) into safe HTML,
    converting the markers into <em> tags after escaping everything else."""
    escaped = html.escape(s)
    return escaped.replace(art.I0, "<em>").replace(art.I1, "</em>")


def _load_fields(source_row) -> dict:
    try:
        return json.loads(source_row["fields"])
    except Exception:
        return {}


def source_payload(s, style: str) -> dict:
    """JSON view of one source row, with rendered citations for the UI."""
    f = _load_fields(s)
    full = art.format_citation(s["entry_type"], f, style)
    return {
        "id": s["id"],
        "cite_key": s["cite_key"],
        "entry_type": s["entry_type"],
        "fields": f,
        "citation_html": markers_to_html(full),
        "citation_text": art.strip_markers(full),
        "intext": art.intext_citation(s["entry_type"], f, style),
        "bibtex": art.to_bibtex(s["cite_key"] or "", s["entry_type"], f),
    }


def project_payload(p) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "research_question": p["research_question"] or "",
        "citation_style": (p["citation_style"] or "MLA").upper(),
        "word_min": p["word_min"],
        "word_max": p["word_max"],
    }


# ---------------------------------------------------------------------------
#  Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "APResearchToolkitWeb/1.0"

    # -- low-level response helpers ------------------------------------
    def _send(self, status, body: bytes, content_type, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The app is single-user/local; avoid stale API responses.
        if content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, status=200):
        self._send(status, json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8")

    def error(self, status, message):
        self.json({"error": message}, status)

    def download(self, data, content_type, filename):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._send(200, data, content_type,
                   {"Content-Disposition": f'attachment; filename="{filename}"'})

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None  # caller treats None as a 400

    # -- dispatch ------------------------------------------------------
    def do_GET(self):
        self.dispatch("GET")

    def do_HEAD(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        self.query = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                if not self.route_api(method, path):
                    self.error(404, "No such API endpoint")
            elif method == "GET":
                self.serve_static(path)
            else:
                self.error(405, "Method not allowed")
        except BrokenPipeError:
            pass
        except Exception as e:  # never crash the server on a bad request
            self.error(500, f"{type(e).__name__}: {e}")

    # -- static files --------------------------------------------------
    _MIME = {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".webmanifest": "application/manifest+json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }

    def serve_static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        # Prevent path traversal outside WEB_DIR.
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            self.error(404, "Not found")
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = self._MIME.get(ext, "application/octet-stream")
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    # -- API routing ---------------------------------------------------
    def route_api(self, method, path):
        routes = [
            ("GET",    r"^/api/meta$",                          self.meta),
            ("GET",    r"^/api/projects$",                      self.projects_list),
            ("POST",   r"^/api/projects$",                      self.project_create),
            ("GET",    r"^/api/projects/(\d+)$",                self.project_get),
            ("PATCH",  r"^/api/projects/(\d+)$",                self.project_update),
            ("DELETE", r"^/api/projects/(\d+)$",                self.project_delete),

            ("GET",    r"^/api/projects/(\d+)/sources$",        self.sources_list),
            ("POST",   r"^/api/projects/(\d+)/sources$",        self.source_create),
            ("POST",   r"^/api/projects/(\d+)/sources/import$", self.sources_import),
            ("GET",    r"^/api/projects/(\d+)/sources/export\.bib$", self.sources_export_bib),
            ("GET",    r"^/api/projects/(\d+)/citations\.pdf$", self.citations_pdf),
            ("PATCH",  r"^/api/sources/(\d+)$",                 self.source_update),
            ("DELETE", r"^/api/sources/(\d+)$",                 self.source_delete),

            ("GET",    r"^/api/projects/(\d+)/checkpoints$",    self.checkpoints_list),
            ("POST",   r"^/api/projects/(\d+)/checkpoints$",    self.checkpoint_create),
            ("GET",    r"^/api/projects/(\d+)/calendar\.ics$",  self.calendar_ics),
            ("PATCH",  r"^/api/checkpoints/(\d+)$",             self.checkpoint_update),
            ("DELETE", r"^/api/checkpoints/(\d+)$",             self.checkpoint_delete),

            ("GET",    r"^/api/projects/(\d+)/sections$",       self.sections_list),
            ("POST",   r"^/api/projects/(\d+)/sections/reset$", self.sections_reset),
            ("PATCH",  r"^/api/sections/(\d+)$",                self.section_update),
        ]
        for m, pattern, fn in routes:
            if m != method:
                continue
            match = re.match(pattern, path)
            if match:
                fn(*match.groups())
                return True
        return False

    # ---- meta --------------------------------------------------------
    def meta(self):
        self.json({
            "entry_types": art.ENTRY_TYPES,
            "editor_fields": [{"label": l, "key": k} for l, k in art.EDITOR_FIELDS],
            "required_sections": [{"name": n, "target": t}
                                  for n, t in art.REQUIRED_SECTIONS],
            "default_checkpoints": art.DEFAULT_CHECKPOINTS,
            "styles": list(_STYLES),
            "today": _dt.date.today().isoformat(),
        })

    # ---- projects ----------------------------------------------------
    def projects_list(self):
        self.json([project_payload(p) for p in db.list_projects()])

    def project_create(self):
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        name = (data.get("name") or "").strip()
        if not name:
            return self.error(400, "Project name is required")
        pid = db.create_project(name)
        self.json(project_payload(db.get_project(pid)), 201)

    def _require_project(self, pid):
        p = db.get_project(int(pid))
        if p is None:
            self.error(404, "Project not found")
            return None
        return p

    def project_get(self, pid):
        p = self._require_project(pid)
        if p:
            self.json(project_payload(p))

    def project_update(self, pid):
        if self._require_project(pid) is None:
            return
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        updates = {k: v for k, v in data.items() if k in _PROJECT_FIELDS}
        if "citation_style" in updates:
            style = str(updates["citation_style"]).upper()
            if style not in _STYLES:
                return self.error(400, "citation_style must be MLA or APA")
            updates["citation_style"] = style
        if "name" in updates:
            updates["name"] = str(updates["name"]).strip()
            if not updates["name"]:
                return self.error(400, "Project name cannot be empty")
        for wk in ("word_min", "word_max"):
            if wk in updates:
                try:
                    updates[wk] = int(updates[wk])
                except (TypeError, ValueError):
                    return self.error(400, f"{wk} must be a number")
        if updates:
            db.update_project(int(pid), **updates)
        self.json(project_payload(db.get_project(int(pid))))

    def project_delete(self, pid):
        if self._require_project(pid) is None:
            return
        db.delete_project(int(pid))
        self.json({"ok": True})

    # ---- sources -----------------------------------------------------
    def _style_for(self, pid):
        p = db.get_project(int(pid))
        return (p["citation_style"] or "MLA").upper() if p else "MLA"

    def sources_list(self, pid):
        if self._require_project(pid) is None:
            return
        style = self._style_for(pid)
        self.json([source_payload(s, style) for s in db.list_sources(int(pid))])

    def source_create(self, pid):
        if self._require_project(pid) is None:
            return
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        cite_key = (data.get("cite_key") or "").strip()
        entry_type = (data.get("entry_type") or "misc").strip().lower()
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            return self.error(400, "fields must be an object")
        fields = {k: v for k, v in fields.items() if str(v).strip()}
        sid = db.add_source(int(pid), cite_key, entry_type, fields)
        src = next((s for s in db.list_sources(int(pid)) if s["id"] == sid), None)
        self.json(source_payload(src, self._style_for(pid)), 201)

    def _find_source(self, sid):
        row = db.conn.execute(
            "SELECT * FROM sources WHERE id=?", (int(sid),)).fetchone()
        return row

    def source_update(self, sid):
        src = self._find_source(sid)
        if src is None:
            return self.error(404, "Source not found")
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        cite_key = (data.get("cite_key", src["cite_key"]) or "").strip()
        entry_type = (data.get("entry_type", src["entry_type"]) or "misc").strip().lower()
        if "fields" in data:
            fields = data.get("fields") or {}
            if not isinstance(fields, dict):
                return self.error(400, "fields must be an object")
            fields = {k: v for k, v in fields.items() if str(v).strip()}
        else:
            fields = _load_fields(src)
        db.update_source(int(sid), cite_key, entry_type, fields)
        self.json(source_payload(self._find_source(sid),
                                 self._style_for(src["project_id"])))

    def source_delete(self, sid):
        src = self._find_source(sid)
        if src is None:
            return self.error(404, "Source not found")
        db.delete_source(int(sid))
        self.json({"ok": True})

    def sources_import(self, pid):
        if self._require_project(pid) is None:
            return
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        text = data.get("bibtex") or ""
        entries = art.parse_bibtex(text)
        for e in entries:
            db.add_source(int(pid), e.get("key", ""),
                          e.get("type", "misc"), e.get("fields", {}))
        style = self._style_for(pid)
        self.json({
            "imported": len(entries),
            "sources": [source_payload(s, style) for s in db.list_sources(int(pid))],
        })

    def sources_export_bib(self, pid):
        if self._require_project(pid) is None:
            return
        chunks = []
        for s in db.list_sources(int(pid)):
            chunks.append(art.to_bibtex(s["cite_key"] or "", s["entry_type"],
                                        _load_fields(s)))
        self.download("\n\n".join(chunks) + "\n", "application/x-bibtex",
                      "sources.bib")

    def citations_pdf(self, pid):
        p = self._require_project(pid)
        if p is None:
            return
        style = (p["citation_style"] or "MLA").upper()
        entries = []
        for s in db.list_sources(int(pid)):
            f = _load_fields(s)
            entries.append((art.sort_key_for_entry(f),
                            art.format_citation(s["entry_type"], f, style)))
        entries.sort(key=lambda x: x[0])
        citations = [c for _, c in entries]
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            art.export_citation_pdf(tmp, p["name"], style, citations)
            with open(tmp, "rb") as fh:
                data = fh.read()
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        fname = art.safe_filename(p["name"]) + "_citations.pdf"
        self.download(data, "application/pdf", fname)

    # ---- checkpoints -------------------------------------------------
    def checkpoints_list(self, pid):
        if self._require_project(pid) is None:
            return
        self.json([dict(c) for c in db.list_checkpoints(int(pid))])

    def checkpoint_create(self, pid):
        if self._require_project(pid) is None:
            return
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        name = (data.get("name") or "").strip()
        if not name:
            return self.error(400, "Checkpoint name is required")
        target = (data.get("target_date") or "").strip() or None
        if target and not _valid_date(target):
            return self.error(400, "target_date must be YYYY-MM-DD")
        db.add_checkpoint(int(pid), name, target)
        self.json([dict(c) for c in db.list_checkpoints(int(pid))], 201)

    def _find_checkpoint(self, cid):
        return db.conn.execute(
            "SELECT * FROM checkpoints WHERE id=?", (int(cid),)).fetchone()

    def checkpoint_update(self, cid):
        c = self._find_checkpoint(cid)
        if c is None:
            return self.error(404, "Checkpoint not found")
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        updates = {}
        if "name" in data:
            nm = (data["name"] or "").strip()
            if not nm:
                return self.error(400, "name cannot be empty")
            updates["name"] = nm
        if "target_date" in data:
            td = (data["target_date"] or "").strip() or None
            if td and not _valid_date(td):
                return self.error(400, "target_date must be YYYY-MM-DD")
            updates["target_date"] = td
        if "done" in data:
            done = 1 if data["done"] else 0
            updates["done"] = done
            updates["done_date"] = _dt.date.today().isoformat() if done else None
        if updates:
            db.update_checkpoint(int(cid), **updates)
        self.json(dict(self._find_checkpoint(cid)))

    def checkpoint_delete(self, cid):
        if self._find_checkpoint(cid) is None:
            return self.error(404, "Checkpoint not found")
        db.delete_checkpoint(int(cid))
        self.json({"ok": True})

    def calendar_ics(self, pid):
        p = self._require_project(pid)
        if p is None:
            return
        cps = db.list_checkpoints(int(pid))
        ics, _count = art.build_ics(p["name"], cps)
        fname = art.safe_filename(p["name"]) + ".ics"
        self.download(ics, "text/calendar; charset=utf-8", fname)

    # ---- sections ----------------------------------------------------
    def sections_list(self, pid):
        if self._require_project(pid) is None:
            return
        self.json([dict(s) for s in db.list_sections(int(pid))])

    def sections_reset(self, pid):
        if self._require_project(pid) is None:
            return
        db.reset_sections(int(pid))
        self.json([dict(s) for s in db.list_sections(int(pid))])

    def _find_section(self, sid):
        return db.conn.execute(
            "SELECT * FROM sections WHERE id=?", (int(sid),)).fetchone()

    def section_update(self, sid):
        s = self._find_section(sid)
        if s is None:
            return self.error(404, "Section not found")
        data = self.read_json()
        if data is None:
            return self.error(400, "Invalid JSON")
        updates = {}
        for k in ("current_words", "target_words"):
            if k in data:
                try:
                    updates[k] = max(0, int(data[k]))
                except (TypeError, ValueError):
                    return self.error(400, f"{k} must be a number")
        if "notes" in data:
            updates["notes"] = str(data["notes"])
        if updates:
            db.update_section(int(sid), **updates)
        self.json(dict(self._find_section(sid)))

    # Quieter logging: one tidy line, no noisy default format.
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def _valid_date(s: str) -> bool:
    try:
        _dt.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _lan_ip():
    """Best-effort LAN IP so we can print a URL reachable from a phone."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="AP Research Toolkit web app")
    parser.add_argument("--host", default="0.0.0.0",
                        help="bind address (default 0.0.0.0 = reachable on your "
                             "network; use 127.0.0.1 to restrict to this machine)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    httpd = HTTPServer((args.host, args.port), Handler)
    print(f"AP Research Toolkit — web app")
    print(f"  Local:   http://localhost:{args.port}")
    if args.host == "0.0.0.0":
        ip = _lan_ip()
        if ip:
            print(f"  Network: http://{ip}:{args.port}   "
                  f"(open this on your phone, same Wi-Fi)")
    print(f"  Database: {art.DB_PATH}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
