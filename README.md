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

### Installing Tkinter on macOS

If running from source fails with `ModuleNotFoundError: No module named
'tkinter'` (or `_tkinter`), your Python was built without Tk support. macOS
does **not** reliably bundle a working Tkinter, so it often needs to be added
separately. Pick the option that matches how you installed Python:

- **python.org installer (easiest)** — Download Python from
  [python.org/downloads/macos](https://www.python.org/downloads/macos/). These
  official builds ship with their own Tcl/Tk, so Tkinter works out of the box
  with no extra steps.

- **Homebrew Python** — install the matching Tk package:

  ```bash
  brew install python-tk
  ```

  If you have several Python versions, target yours explicitly, e.g.
  `brew install python-tk@3.12`. Run `which python3` to confirm you're using the
  Homebrew Python (`/opt/homebrew/bin/python3` on Apple Silicon, or
  `/usr/local/bin/python3` on Intel) rather than the bare system Python.

- **pyenv** — pyenv compiles Python from source, so Tk must be present *before*
  you build. Install it and then (re)install your Python version:

  ```bash
  brew install tcl-tk
  pyenv install 3.12          # re-run for the version you use; reinstalls with Tk
  ```

  Recent pyenv auto-detects Homebrew's `tcl-tk`. If the build still misses it,
  point the compiler at it explicitly:

  ```bash
  export PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I$(brew --prefix tcl-tk)/include' --with-tcltk-libs='-L$(brew --prefix tcl-tk)/lib'"
  pyenv install 3.12
  ```

**Verify it works** — this should pop up a small test window:

```bash
python3 -c "import tkinter; tkinter._test()"
```

(If you don't want to deal with any of this, just grab the prebuilt macOS app
from [Releases](../../releases) — it bundles everything and needs no Python.)

## Download (no Python required)

Prebuilt standalone executables are attached to the
[**Releases**](../../releases) page:

| Platform | File | How to run |
|----------|------|------------|
| Windows  | `ap_research_toolkit.exe` | Double-click. Windows SmartScreen may warn on an unsigned app — choose **More info → Run anyway**. |
| macOS    | `ap_research_toolkit-mac.zip` | Unzip, then double-click `ap_research_toolkit.app`. The app is unsigned, so the first time **right-click → Open** (or allow it under **System Settings → Privacy & Security**). |

No Python install is needed to run these.

## Running from source

```bash
python ap_research_toolkit.py
```

## Building your own executable

The standalone executables are built with [PyInstaller](https://pyinstaller.org).
Install it first:

```bash
pip install pyinstaller
```

Then build from the project root using the bundled spec file (recommended, so
the build options stay consistent):

```bash
pyinstaller ap_research_toolkit.spec
```

…or generate a one-file, windowed build from scratch:

```bash
pyinstaller --onefile --windowed --name ap_research_toolkit ap_research_toolkit.py
```

The result lands in `dist/`:

- **Windows** → `dist/ap_research_toolkit.exe`
- **macOS** → `dist/ap_research_toolkit.app` (zip the `.app` bundle to share it)

Notes:

- PyInstaller is **not** cross-platform — build the Windows `.exe` on Windows
  and the macOS `.app` on a Mac.
- The build needs only PyInstaller plus the same runtime dependencies as the
  app (standard library + Tkinter; optionally `reportlab` for nicer PDFs).
- `build/`, `dist/`, and the packaged `.zip` are generated artifacts and are
  not tracked in git — publish them as Release assets instead (see below).

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
