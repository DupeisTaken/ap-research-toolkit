# AP Research Toolkit

A single-file desktop app for AP Research students. It manages your sources,
generates correctly formatted citations, tracks your research timeline, and
keeps an eye on your word counts — all in one window, with everything stored
locally on your machine.

![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)

## Features

- **BibTeX source management** — import, add, edit, and export your sources.
  The BibTeX parser is hand-written, so no external libraries are needed.
- **Automatic citations** in MLA (9th ed.) and APA (7th ed.):
  - Full works-cited / references entries with proper italics and hanging indents.
  - Ready-to-copy in-text citations (with correct *et al.* handling).
  - Export a formatted citation-sheet **PDF**.
- **Research timeline** with adjustable dates and the common AP Research
  process checkpoints, anchored to the academic year (Sept 1 – Apr 30).
  Export it as an **`.ics` calendar** file you can import into Google Calendar,
  Outlook, or Apple Calendar.
- **Section tracker** for the 7 required paper sections (Introduction,
  Literature Review, Methodology, Results, Discussion, Limitations, Conclusion)
  with per-section word targets and a 4,000–5,000 word total tracker.
- **Multiple parallel projects**, each stored in a local SQLite database.

## Requirements

- **Python 3.x** with **Tkinter** (included in standard Python installs).
- That's it — the app uses only the Python standard library.

`reportlab` is **optional**: if it's installed, PDFs are rendered with it;
otherwise the app silently falls back to a built-in pure-Python PDF writer, so
export always works even on a machine with nothing extra installed.

## Running

```bash
python ap_research_toolkit.py
```

A prebuilt standalone executable is also available under `dist/` (no Python
required to run it).

## Where your data lives

Your projects, sources, timeline, and sections are saved in a SQLite database
in a per-user application data directory — **not** in this repository:

| Platform | Location |
|----------|----------|
| Windows  | `%APPDATA%\APResearchToolkit` |
| macOS    | `~/Library/Application Support/APResearchToolkit` |
| Linux    | `$XDG_DATA_HOME/ap_research_toolkit` (or `~/.local/share/...`) |

Your data persists across runs and is independent of where you launch the script.

## Development

The entire app lives in `ap_research_toolkit.py`, organized top-to-bottom in
dependency order: storage → parsing → citation logic → PDF → GUI → entry point.

Run the headless test suite (no GUI):

```bash
python ap_research_toolkit.py --selftest
```

This covers BibTeX parsing, MLA/APA full and in-text citations, author-formatting
edge cases, a database round-trip, and both PDF export paths. There is no separate
test runner — `--selftest` is the test suite. See `CLAUDE.md` for a fuller tour of
the architecture and conventions.

## License

MIT
