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
- **Use it on your phone** — a built-in web app runs the same toolkit in a
  browser and installs to your home screen as a PWA on Android and iOS.
  See [Use it on your phone](#use-it-on-your-phone-web-app--android-pwa).

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

## Use it on your phone (web app / Android PWA)

The desktop window is built with Tkinter, which **cannot run on Android or
iOS**. So instead of a native APK, the toolkit ships a built-in **web app**
that runs the exact same logic (sources, MLA/APA citations, timeline, word
counts) and can be **installed on your phone's home screen as a PWA** — on
Android *and* iOS.

It uses only the standard library — no Flask, no extra installs — and shares
the same local database as the desktop app.

**1. Start the server** on a computer (your laptop is fine):

```bash
python ap_research_web.py
```

It prints two URLs, e.g.:

```
  Local:   http://localhost:8000
  Network: http://192.168.1.42:8000   (open this on your phone, same Wi-Fi)
```

**2. Open it on your phone.** Put the phone on the **same Wi-Fi** as the
computer and visit the `Network:` URL in Chrome (Android) or Safari (iOS).

**3. Install it as an app:**

- **iOS (Safari):** tap **Share** → **Add to Home Screen**. Launches
  full-screen with its own icon.
- **Android (Chrome):** tap the **⋮** menu → **Add to Home screen**.

Notes:

- The computer running `python ap_research_web.py` must stay on while you use
  the phone app — it's the server holding your data.
- By default the server binds to all interfaces so phones on your network can
  reach it. Restrict it to just your machine with
  `python ap_research_web.py --host 127.0.0.1`, or change the port with
  `--port 9000`.
- **About full "install" on Android:** Chrome only offers a *true* installed
  PWA (standalone window + offline support via the service worker) over a
  **secure origin** — HTTPS or `localhost`. On a plain `http://` LAN address
  the **Add to Home screen** shortcut still works, but it may open in a browser
  tab and won't cache offline. To get the full installable experience, serve it
  over HTTPS — e.g. host the app on a small server with a certificate, or put it
  behind a tunnel like [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
  or `ngrok`, which give you an HTTPS URL you can open from anywhere. iOS
  Safari's **Add to Home Screen** works either way.

> **Why not a real `.apk`?** Packaging Python for Android (Buildozer,
> python-for-android, BeeWare) only supports their own UI toolkits — none can
> bundle a Tkinter app. A PWA gives you an installable, offline-capable home
> screen app on every phone without rewriting the GUI in a niche framework.

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
