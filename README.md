# AP Research Toolkit

The AP Research Toolkit is a desktop (and optional phone/web) app for AP
Research students. It manages your sources, generates correctly formatted
MLA/APA citations, tracks your research timeline, and monitors your word
counts — all in one place, with everything stored locally on your machine.

This guide explains how to **install**, **run**, and **troubleshoot** the
toolkit. If you hit a problem, jump straight to
[Troubleshooting](#troubleshooting) or the [FAQ](#frequently-asked-questions).

![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)

---

## Contents

- [What the toolkit does](#what-the-toolkit-does)
- [System requirements](#system-requirements)
- [Installation](#installation)
  - [Option A — Prebuilt app (recommended)](#option-a--prebuilt-app-recommended)
  - [Option B — Run from source](#option-b--run-from-source)
- [Using the toolkit on your phone](#using-the-toolkit-on-your-phone)
- [Troubleshooting](#troubleshooting)
- [Frequently asked questions](#frequently-asked-questions)
- [For developers](#for-developers)
- [License](#license)

---

## What the toolkit does

| Capability | Details |
|------------|---------|
| **Source management** | Import, add, edit, and export BibTeX sources. The BibTeX parser is built in — no external libraries needed. |
| **Automatic citations** | MLA (9th ed.) and APA (7th ed.): full works-cited / references entries with correct italics and hanging indents, ready-to-copy in-text citations (with proper *et al.* handling), and a citation-sheet **PDF** export. |
| **Research timeline** | Adjustable checkpoint dates for the common AP Research process, anchored to the academic year (Sept 1 – Apr 30). Export as an **`.ics` calendar** for Google Calendar, Outlook, or Apple Calendar. |
| **Section tracker** | The 7 required paper sections (Introduction, Literature Review, Methodology, Results, Discussion, Limitations, Conclusion) with per-section word targets and a 4,000–5,000-word total tracker. |
| **Multiple projects** | Run several parallel projects, each in a local SQLite database. |
| **Phone / web access** | A built-in web app runs the same toolkit in a browser and installs to your phone's home screen as a PWA. See [Using the toolkit on your phone](#using-the-toolkit-on-your-phone). |

---

## System requirements

| Item | Requirement |
|------|-------------|
| **Operating system** | Windows, macOS, or Linux. |
| **To run the prebuilt app** | Nothing — the executable is self-contained. See [Option A](#option-a--prebuilt-app-recommended). |
| **To run from source** | **Python 3.x** with **Tkinter** (bundled with most Python installs; see the [Tkinter note for macOS](#symptom-modulenotfounderror-no-module-named-tkinter)). |
| **Extra packages** | None required. The app uses only the Python standard library. |
| **Optional** | `reportlab` — if installed, PDFs are rendered with it; otherwise the app automatically falls back to a built-in pure-Python PDF writer, so **PDF export always works** even with nothing extra installed. |

---

## Installation

You have two options. Most students should use **Option A**.

### Option A — Prebuilt app (recommended)

No Python required. Download the standalone executable for your platform from
the [**Releases**](../../releases) page, then:

| Platform | File | How to run |
|----------|------|------------|
| **Windows** | `ap_research_toolkit.exe` | Double-click it. If Windows SmartScreen warns about an unsigned app, see [this troubleshooting entry](#symptom-windows-smartscreen-blocks-the-app). |
| **macOS** | `ap_research_toolkit-mac.zip` | Unzip, then open `ap_research_toolkit.app`. The app is unsigned — see [this troubleshooting entry](#symptom-macos-wont-open-the-app-unidentified-developer) the first time. |

### Option B — Run from source

Requires Python 3.x with Tkinter (see [System requirements](#system-requirements)).

```bash
python ap_research_toolkit.py
```

If this fails with a `tkinter` error, see
[ModuleNotFoundError: No module named 'tkinter'](#symptom-modulenotfounderror-no-module-named-tkinter).

---

## Using the toolkit on your phone

The desktop window is built with Tkinter, which **cannot run on Android or
iOS**. Instead, the toolkit ships a built-in **web app** that runs the exact
same logic (sources, MLA/APA citations, timeline, word counts) and can be
**installed on your phone's home screen as a PWA**. It uses only the standard
library — no Flask, no extra installs — and shares the same local database as
the desktop app.

**Step 1 — Start the server** on a computer (your laptop is fine):

```bash
python ap_research_web.py
```

It prints two URLs, for example:

```
  Local:   http://localhost:8000
  Network: http://192.168.1.42:8000   (open this on your phone, same Wi-Fi)
```

**Step 2 — Open it on your phone.** Put the phone on the **same Wi-Fi** as the
computer, then visit the `Network:` URL in Chrome (Android) or Safari (iOS).
If the page doesn't load, see
[My phone can't reach the Network URL](#symptom-my-phone-cant-reach-the-network-url).

**Step 3 — Install it to your home screen:**

- **iOS (Safari):** tap **Share** → **Add to Home Screen**.
- **Android (Chrome):** tap the **⋮** menu → **Add to Home screen**. For a
  *full* installed PWA (standalone window + offline support), see
  [Android won't fully install the app](#symptom-android-wont-fully-install-the-app-offline).

**Server options:**

- The computer running `python ap_research_web.py` must stay on while you use
  the phone app — it is the server holding your data.
- Restrict access to just your machine: `python ap_research_web.py --host 127.0.0.1`
- Change the port: `python ap_research_web.py --port 9000`

---

## Troubleshooting

Find your symptom below. Each entry lists the likely **cause** and the
**resolution**.

### Symptom: Windows SmartScreen blocks the app

> "Windows protected your PC" / "Microsoft Defender SmartScreen prevented an
> unrecognized app from starting."

- **Cause:** The executable is unsigned (no paid code-signing certificate),
  which is normal for free, open-source tools.
- **Resolution:** Click **More info**, then **Run anyway**. You only need to do
  this the first time.

### Symptom: macOS won't open the app ("unidentified developer")

> "ap_research_toolkit.app cannot be opened because it is from an unidentified
> developer."

- **Cause:** The app is unsigned and not notarized through the Apple Developer
  program.
- **Resolution:** **Right-click (or Control-click) the app → Open**, then
  confirm. Alternatively, allow it under **System Settings → Privacy &
  Security**. This is only required the first time you launch it.

### Symptom: `ModuleNotFoundError: No module named 'tkinter'`

> Running from source fails with `No module named 'tkinter'` (or `_tkinter`).

- **Cause:** Your Python was built without Tk support. macOS in particular does
  **not** reliably bundle a working Tkinter.
- **Resolution:** Install Tkinter for your Python, then verify. Pick the method
  that matches how you installed Python:

  **python.org installer (easiest):** Download Python from
  [python.org/downloads/macos](https://www.python.org/downloads/macos/). The
  official builds ship with their own Tcl/Tk, so Tkinter works with no extra
  steps.

  **Homebrew Python:** install the matching Tk package:

  ```bash
  brew install python-tk
  ```

  If you have several Python versions, target yours explicitly, e.g.
  `brew install python-tk@3.12`. Run `which python3` to confirm you're using the
  Homebrew Python (`/opt/homebrew/bin/python3` on Apple Silicon, or
  `/usr/local/bin/python3` on Intel) rather than the bare system Python.

  **pyenv:** pyenv compiles Python from source, so Tk must be present *before*
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

  **Verify the fix** — this should pop up a small test window:

  ```bash
  python3 -c "import tkinter; tkinter._test()"
  ```

  **Shortcut:** if you'd rather not deal with this, use the prebuilt macOS app
  from [Releases](../../releases) — it bundles everything and needs no Python.

### Symptom: PDF export looks plain / I want nicer PDFs

- **Cause:** `reportlab` is not installed, so the app uses its built-in
  pure-Python PDF writer.
- **Resolution:** This is expected and PDF export still works. For richer
  formatting, install reportlab: `pip install reportlab`. The app will use it
  automatically next time.

### Symptom: My phone can't reach the `Network:` URL

- **Cause:** The phone and computer are on different networks, or a firewall is
  blocking the connection.
- **Resolution:**
  1. Confirm both devices are on the **same Wi-Fi** (not guest/cellular).
  2. Make sure the server is still running and **not** restricted to localhost
     (don't use `--host 127.0.0.1` for phone access).
  3. Allow Python through your computer's firewall if prompted.
  4. Retype the exact `Network:` URL, including the port (e.g. `:8000`).

### Symptom: Android won't fully install the app (offline)

- **Cause:** Chrome only offers a *true* installed PWA (standalone window +
  offline support via the service worker) over a **secure origin** — HTTPS or
  `localhost`. A plain `http://` LAN address is not a secure origin.
- **Resolution:** **Add to Home screen** still works over `http://` but may open
  in a browser tab and won't cache offline. For the full installable
  experience, serve the app over **HTTPS** — for example host it on a small
  server with a certificate, or put it behind a tunnel such as
  [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
  or `ngrok`, which give you an HTTPS URL you can open from anywhere. iOS
  Safari's **Add to Home Screen** works either way.

### Symptom: Is there an Android `.apk`?

- **Cause:** Packaging Python for Android (Buildozer, python-for-android,
  BeeWare) only supports those frameworks' own UI toolkits — none can bundle a
  Tkinter app.
- **Resolution:** Use the PWA instead (see
  [Using the toolkit on your phone](#using-the-toolkit-on-your-phone)). It gives
  you an installable, offline-capable home-screen app on every phone without a
  GUI rewrite.

---

## Frequently asked questions

**Where is my data stored?**
In a per-user application data directory — **not** in this repository — so it
persists across runs regardless of where you launch the app:

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\APResearchToolkit` |
| macOS | `~/Library/Application Support/APResearchToolkit` |
| Linux | `$XDG_DATA_HOME/ap_research_toolkit` (or `~/.local/share/...`) |

**Do I need an internet connection?**
No. The desktop app is fully offline. The phone/web app only needs your local
network to reach the computer running the server.

**Can I run more than one project?**
Yes — the toolkit supports multiple parallel projects, each stored in the same
local SQLite database.

**Does the desktop app and the phone app share data?**
Yes. The web app reads and writes the same local database as the desktop app.

**How do I back up or move my data?**
Copy the database from the data directory listed above to your new machine's
matching location.

---

## For developers

### Build your own executable

The standalone executables are built with
[PyInstaller](https://pyinstaller.org):

```bash
pip install pyinstaller
```

Build using the bundled spec file (recommended, so options stay consistent):

```bash
pyinstaller ap_research_toolkit.spec
```

…or generate a one-file, windowed build from scratch:

```bash
pyinstaller --onefile --windowed --name ap_research_toolkit ap_research_toolkit.py
```

Output lands in `dist/`:

- **Windows** → `dist/ap_research_toolkit.exe`
- **macOS** → `dist/ap_research_toolkit.app` (zip the `.app` bundle to share it)

Notes:

- PyInstaller is **not** cross-platform — build the Windows `.exe` on Windows
  and the macOS `.app` on a Mac.
- The build needs only PyInstaller plus the same runtime dependencies as the app
  (standard library + Tkinter; optionally `reportlab` for nicer PDFs).
- `build/`, `dist/`, and the packaged `.zip` are generated artifacts and are not
  tracked in git — publish them as Release assets instead.

### Run the test suite

```bash
python ap_research_toolkit.py --selftest
```

This headless suite covers BibTeX parsing, MLA/APA full and in-text citations,
author-formatting edge cases, a database round-trip, and both PDF export paths.
There is no separate test runner — `--selftest` *is* the test suite.

### Architecture

The desktop app lives in `ap_research_toolkit.py`, organized top-to-bottom in
dependency order: storage → parsing → citation logic → PDF → GUI → entry point.
The phone/web app (`ap_research_web.py` plus the `web/` directory) is a thin
standard-library HTTP layer that reuses that same logic. See `CLAUDE.md` for a
fuller tour of the architecture and conventions.

---

## License

MIT
