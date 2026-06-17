# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Tkinter desktop app (`ap_research_toolkit.py`) for AP Research students: BibTeX source management, automatic MLA/APA citation generation + PDF export, a research timeline (with `.ics` calendar export), and per-section word-count tracking across multiple parallel projects.

A second entry point, `ap_research_web.py`, exposes the *same* toolkit as a mobile-friendly web app / installable PWA (for phones, where Tkinter can't run). It is a thin stdlib-only `http.server` layer that **imports and reuses** all of `ap_research_toolkit`'s logic — `DB`, the citation engine, BibTeX parsing, `build_ics`, and `export_citation_pdf` — rather than duplicating any of it. The browser UI lives in `web/` (vanilla JS SPA + `manifest.webmanifest`/`sw.js` for PWA install). When you change citation/DB/parsing logic, the web app picks it up automatically; just keep `source_payload`/route handlers in `ap_research_web.py` in step if you change a function's signature or return shape. Note `ap_research_toolkit` imports `tkinter` lazily inside `launch_gui` (not at module top), which is what lets the web layer import it on a headless/Tk-less machine — preserve that.

## Commands

- Run the app: `python ap_research_toolkit.py`
- Run the web/PWA app: `python ap_research_web.py` (stdlib only; `--host 127.0.0.1` to restrict to this machine, `--port N` to change port)
- Run the headless test suite: `python ap_research_toolkit.py --selftest` (covers BibTeX parsing, MLA/APA full + in-text citations, author-formatting edge cases, a DB round-trip, and both PDF export paths)
- GUI smoke test (build window + refresh tabs without blocking on `mainloop`): monkeypatch `tk.Tk.mainloop` to call `update_idletasks(); update(); refresh_all(); destroy()`, then call `m.launch_gui()`.

There is no separate test runner, linter, or build step — `--selftest` is the test suite. When changing citation logic, update the assertions in `selftest()` accordingly.

## Dependencies

Standard library + Tkinter only. `reportlab` is **optional**: PDF export tries it first and silently falls back to the built-in pure-Python PDF writer (`_export_pdf_fallback`) if it's missing or errors. Never make `reportlab` a hard requirement — the app must run on a machine with nothing installed.

## Architecture

The file is organized top-to-bottom in dependency order: storage → parsing → citation logic → PDF → GUI → entry point. Key boundaries:

- **`app_data_dir()` / `DB_PATH`**: the SQLite database lives in a per-user OS-specific data dir (`%APPDATA%\APResearchToolkit` on Windows), **not** in the repo. User data persists across runs and is independent of where the script is launched.

- **`DB` class**: all SQL lives here. Four tables (`projects`, `sources`, `checkpoints`, `sections`) with `ON DELETE CASCADE` from `projects`. `create_project()` auto-seeds the 7 required sections (`REQUIRED_SECTIONS`) and the default timeline (`DEFAULT_CHECKPOINTS`). Source `fields` are stored as a JSON blob, not columns.

- **Citation engine** (`format_citation`, `_format_mla`, `_format_apa`, `intext_citation`): the central correctness-sensitive code. Formatters return strings containing **private italic markers** `I0`/`I1` (`\x01`/`\x02`) wrapping text that should be italic. Consumers translate these: `strip_markers()` for clipboard/plain text, `.replace(I0,'*')` for the on-screen editable display, and `<i>`/`<li>` tags or stripping for the two PDF paths. Author-name handling (`split_authors`, `authors_mla`, `authors_apa`, and the `intext_*` variants) implements the 1 / 2 / 3+ → *et al.* rules and APA initials/ampersand conventions — edit these rather than the per-type formatters when author rules change.

- **BibTeX** (`parse_bibtex`, `_parse_entry_body`, `to_bibtex`): hand-written brace/quote-aware parser, no external lib. `_clean_value` normalizes whitespace and strips braces.

- **Calendar export** (`build_ics`): emits RFC 5545 iCalendar with one all-day `VEVENT` per dated checkpoint (CRLF line endings, `_ics_escape` for text values, `_ics_fold` to keep lines ≤75 octets, a `VALARM` reminder on pending items). The GUI writes it with `newline=""` so CRLFs aren't doubled on Windows.

- **GUI** (`launch_gui`): all Tk classes are nested inside this function so they share the single module-level `db` instance via closure. `App` owns the project selector + style toggle and holds `current_pid` and `style_var`; the four tabs (`DashboardTab`, `SourcesTab`, `TimelineTab`, `SectionsTab`) each implement a `refresh()` method. `App.refresh_all()` fans out to all tabs and is the single re-render entry point — call it after any data mutation. The current citation style is read via `app.style`.

## Conventions

- Dates are stored and compared as ISO strings (`YYYY-MM-DD`) via `datetime.date.fromisoformat`.
- The default timeline is anchored to an academic year via `academic_window()` / `default_checkpoint_dates()`: checkpoints spread evenly from Sept 1 (exclusive) through April 30, with the `SUBMISSION_CHECKPOINT` ("Final paper submission") pinned to April 30 and the POD trailing two weeks after. Both `DB.create_project` and `TimelineTab.add_defaults` must call `default_checkpoint_dates()` rather than re-deriving dates, so they stay in sync.
- The required word range is 4,000–5,000; `REQUIRED_SECTIONS` targets sum to 4,500 (the midpoint). Keep that invariant if editing section defaults.
- When adding a new BibTeX entry type, update `ENTRY_TYPES`, both `_format_mla`/`_format_apa` branch logic, and the relevant `selftest()` assertions.
