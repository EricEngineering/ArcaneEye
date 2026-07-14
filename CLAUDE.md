# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Arcane Eye ("Arcane Eye") is a small PySide6 (Qt for Python) **system-tray utility** for in-person tabletop RPGs where a TV is used as the shared tabletop. The GM presses a global hotkey, rubber-band-selects any region of their own screen, and that snip is instantly mirrored — scaled to a chosen percentage of a chosen monitor — onto a **frameless, always-on-top, transparent-background Player View window** on the players' TV. A second hotkey hides it. That is the entire app: quick "show them what's on my screen" mirroring, with no map/asset/scene model.

It is the lightweight sibling of the author's larger **ArcaneAtlas** virtual-tabletop app (same author, same domain, same PySide6 + `res_path` + PyInstaller/Inno-Setup conventions). Arcane Eye deliberately does *one* thing; reach for ArcaneAtlas when a real battle-map layout is needed.

## Naming
- Product name and repo: **ArcaneEye** (CamelCase, one word)
- Python package, `.spec`, `.iss`: **arcaneeye** (lowercase)
- Human-facing display text: **"Arcane Eye"** (two words)

## Commands

Run from source:
```bash
./runlin.sh                 # Linux: activates .venv (if present) and runs `python3 -m arcaneeye`
python3 -m arcaneeye          # or directly
```
On Windows use `runwin.bat` (set `LOG_ENABLED=1` inside it to capture logs to `.\logs\`; it also `taskkill`s any running `Arcane Eye.exe` first).

Build the standalone Windows app + installer (Windows only):
```bash
build_exe.bat               # clean PyInstaller build (kills running instances first) -> dist\Arcane Eye\
build_installer.bat         # Inno Setup installer from arcaneeye.iss (admin/Program Files install)
```

There is **no test suite, linter, CI, or `.ui` file** — the entire GUI is hand-built in code. (Unlike ArcaneAtlas, there is no Qt Designer step.)

## Runtime dependencies

- **PySide6** — the GUI, tray icon, screen grab, and pixmap scaling.
- **pynput** — OS-level global hotkeys (works even when no Arcane Eye window has focus). This is the one non-Qt dependency and the main portability risk (see Gotchas).

Dev/prod runs on **Python 3.14** locally (the `.venv`), though the README still says 3.12 — same bleeding-edge PySide6/shiboken stack as ArcaneAtlas.

## Architecture

### Module layout (tiny + flat)
Almost everything lives in two files under `arcaneeye/`:

- **`arcaneeye/main.py`** (~535 lines) — `res_path()` and the resource path constants, plus every GUI class: **`TrayApp`** (the orchestrator — owns the tray icon, menu, hotkey thread, screen/size state, and the snip flow), **`DisplayWindow`** (the Player View), **`AboutWindow`** + **`LicenseDialog`** + **`ScaledLabel`** (about/help UI), and **`HotkeyListenerThread`** (the pynput listener on a `QThread`). `main()` at the bottom just constructs `TrayApp` and runs it.
- **`arcaneeye/screensnip.py`** (~106 lines) — **`CaptureScreen`**, the full-screen dimmed rubber-band overlay used to select the region to grab.
- **`arcaneeye/__main__.py`** — entry point (`python -m arcaneeye` → `main()`).
- **`arcaneeye/resources/`** — icons (`icon.png`/`.ico`, `trayicon.png`), `banner.png`/`logo.png`, and `AGPL_V3.txt` (shown in the license dialog). Loaded via `res_path`.
- **`arcaneeye/nondistribute_resources/`** — source art (PSDs, SVGs, old logo revisions) **not shipped** with the app.

There is no worker/networking/transcode split like ArcaneAtlas — the app is small enough that one orchestrator class is fine. Keep it that way unless it grows substantially.

### The core flow (snip → display)
1. **Global hotkey** `Ctrl+Shift+X` (or the tray "Snip" action) → `TrayApp.screenSnip()`.
2. `screenSnip()` constructs a `CaptureScreen`, shows it, and **blocks on a nested `QEventLoop`** that quits when the overlay hides (`snip.hideEvent = lambda …: loop.quit()`). This is the handshake that waits for the user to finish selecting.
3. `CaptureScreen` covers the primary screen with a **40%-opacity black pixmap** (`createDimScreenEffect`), shows a `QRubberBand` on left-drag, and on mouse-release grabs the selected rectangle with `QGuiApplication.primaryScreen().grabWindow(0, x, y, w, h)` into `self.grabbedPixMap`.
4. Back in `screenSnip()`, the pixmap is read off the overlay, the overlay is closed, and `DisplayWindow.update_image(pixmap, screen_index, percent)` scales + positions it, then `show_window()` raises the Player View.
5. **Dismiss** → `TrayApp.hide_all_windows_cancel_snip()` hides the Player View + About window and closes any in-progress `CaptureScreen`. The dismiss key is **`Esc`** on X11/Windows/macOS but the **`Ctrl+Shift+X` toggle** on Wayland (Esc is unreliable there — see the Wayland section).

### The Player View (`DisplayWindow`)
- A `QWidget` (not `QMainWindow`) with `WindowStaysOnTopHint | FramelessWindowHint` and `WA_TranslucentBackground` — a borderless, always-on-top, transparent frame holding a single `QLabel` that shows the scaled snip. (`Qt.SplashScreen` was tried and **breaks screen selection** — noted in a code comment; don't re-add it.) On **Wayland** it also gets `WA_ShowWithoutActivating | WindowDoesNotAcceptFocus` and a non-activating fullscreen placement (`_place_on_target`) — see the Wayland section.
- **`update_image()` does the scaling math** (the important part): it fits the snipped pixmap into `percent_of_screen` of the *target* monitor's `availableGeometry`, preserving aspect ratio, and clamps to 90% of the monitor in the constraining dimension. It applies the target screen's `devicePixelRatio` (grabs at `w*dpr × h*dpr`, then `setDevicePixelRatio(dpr)`) so the image is crisp on HiDPI displays, sets the label to a fixed size, `adjustSize()`s the window, and centers it on the target screen. It's called on **every** state change — snip, screen change, size change, monitor hot-plug — so the display stays correct.

### Screen selection & display size (tray menu)
- **`Select Screen` submenu** — one checkable action per `QApplication.screens()` entry. `update_screen_menu()` (re)builds it and **defaults the selection to the *last* screen** (assumed to be the players' TV). A `QTimer` polling every **1000 ms** (`update_screens_menu_if_changed`) compares screen names against `last_screens` and rebuilds the menu + reassigns it to the tray icon when monitors are plugged/unplugged (the reassignment was needed specifically on Linux KDE).
- **`Display Size` submenu** — five checkable options, 50%–90% in 10% steps, mapped to `percent_of_screen` (`0.5 + index/10`), defaulting to 70%. `set_percent_of_screen(index)` re-renders the Player View immediately.
- Both submenus manually manage the checkable/exclusive state (uncheck all, check the selected one).

### Global hotkeys (`HotkeyListenerThread`)
- A `QThread` running a `pynput.keyboard.GlobalHotKeys` listener, each hotkey emitting a Qt `Signal` back to `TrayApp` on the GUI thread. This is what makes the hotkeys work with no window focused. On exit, `TrayApp.exit_app()` calls `hotkey_thread.terminate()` (see Gotchas — this is an abrupt `QThread.terminate`).
- **The registered hotkeys depend on the session type** (`HotkeyListenerThread(include_esc=...)`, set from `TrayApp._wayland = is_wayland_session()`):
  - **X11 / Windows / macOS:** `<ctrl>+<shift>+X` → snip, `<esc>` → hide/cancel. The proven behavior — `Ctrl+Shift+X` just snips (`screenSnip`) and `Esc` hides.
  - **Wayland:** **only** `<ctrl>+<shift>+X` is registered (`include_esc=False`), and it's a **show/hide TOGGLE** (`_hotkey_ctrlshiftx`: hide if the Player View is visible, else snip). **Esc is deliberately not registered on Wayland** — see the Wayland section for the (important, non-obvious) reason. The tray "Hide Player Window" label and the `Ctrl+Shift+X` handler both branch on `_wayland`.

### Wayland (the hard-won platform notes — read before touching hotkeys/capture/display)
Wayland deliberately breaks three things X11 apps take for granted: reading the framebuffer, positioning your own windows, and eavesdropping on the global keyboard. Each has a Wayland-only workaround; **none of it touches the X11/Windows/macOS paths** (all Wayland branches are gated on `is_wayland_session()` from `capture.py`, which is True under native Wayland *and* XWayland).

**1. Screen capture → xdg-desktop-portal** (`capture.py`). `QScreen.grabWindow` returns an **empty/black** pixmap under Wayland (and under XWayland), so the snip can't grab directly. Instead `capture.py` asks the compositor via the **Screenshot portal** over QDBus (`_PortalShooter`), which grabs the whole virtual desktop to a file URI that the caller crops. `screensnip.py`'s `mouseReleaseEvent` branches `is_wayland_session()` → portal vs. `grabWindow`. It **must** stay on the app's persistent QDBus connection (a `gdbus` subprocess would exit before the async `Response` signal arrives). **PySide6 6.11.1 gotcha:** `QDBusConnection.connect` only binds when the slot is a `str` with a leading `"1"` marker, e.g. `"1onResponse(uint,QVariantMap)"`.

**2. Player View display → non-activating fullscreen + hide-remap** (`DisplayWindow`). Wayland won't let an app place its own window on a chosen output — the *only* way to target a specific monitor is **fullscreen state**. But an **activated** fullscreen window is what KDE turns into an **exclusive, desktop-locking** surface (panel/tray hidden, input trapped — the "unresponsive" trap). So on Wayland `_place_on_target()` sets the fullscreen **state** but shows the window **without activating** it (`WA_ShowWithoutActivating` + `WindowDoesNotAcceptFocus` + `setWindowState(...FullScreen) | show()`, **not** `showFullScreen()` which activates). It stays a passive, click-through (`WA_TransparentForMouseEvents`) overlay and the desktop stays interactive. Also: Wayland assigns a window to an output **only at map time**, so `setScreen()` on an already-visible window is ignored — switching the target monitor while shown requires a **hide → re-map** (that's the `_shown_screen` compare + `self.hide()` in the Wayland branch). This fixed the original "Player View won't move to the newly-selected monitor" bug. X11/Win/mac keep the original `setScreen; setGeometry; showFullScreen()`.

**3. Global hotkeys → pynput works, but ONLY for modifier combos.** This is the subtle one. pynput's Linux backend reads keys via XWayland, and Wayland routes keystrokes **only to the focused surface**. Once the fullscreen Player View maps it holds keyboard focus (a native Wayland surface), so keys stop reaching XWayland and pynput goes deaf — **but not uniformly**:
  - **A bare, modifier-less key (Esc) is NOT delivered** while the overlay holds focus and the mouse is still. It sits **buffered** until the pipeline is flushed by pointer motion (moving the mouse / hovering the taskbar) **or by a subsequent modifier keypress**. (Verified with timestamped diagnostics: pynput's Esc callback fired only at the instant the mouse moved, not when Esc was pressed.)
  - **A modifier combo (Ctrl+Shift+X) IS delivered reliably**, even with a dead-still mouse. Pressing Ctrl/Shift generates modifier events that XWayland *does* receive, and that **flushes the pipeline**, so the whole combo lands. This is why the snip hotkey always felt reliable while Esc never did.
  - **Consequences that drive the design:**
    - The dismiss key on Wayland is the **`Ctrl+Shift+X` toggle**, not Esc — a modifier combo is the one thing pynput hears reliably there, so it doubles as show *and* hide.
    - **Esc is not registered at all on Wayland.** If it were, a buffered Esc would be delivered on the *next* Ctrl+Shift+X press (the modifiers flush it), firing hide **and** the toggle in one shot (e.g. hide-then-immediately-re-snip). Not registering Esc removes the stale-buffered-key mis-fire entirely.
  - **`WA_ShowWithoutActivating`/`WindowDoesNotAcceptFocus` do NOT rescue Esc** — they keep the desktop interactive (no exclusive lock) but don't restore keyboard delivery to pynput; only the modifier-combo behavior above does. Don't re-add an Esc-focused window flag hoping to fix it.

**Rejected alternative — the GlobalShortcuts portal.** Before discovering the modifier-combo reliability, a compositor-level global shortcut via **`org.freedesktop.portal.GlobalShortcuts`** (using **jeepney**, because PySide6's QtDBus *core-dumps* marshalling the required `a(sa{sv})` argument) was built and then removed as unnecessary. It works (proven end-to-end on KDE), but it needs a pure-Python D-Bus dependency, a worker thread, and a one-time KDE bind dialog — all avoided by the `Ctrl+Shift+X` toggle. **If the modifier-flush trick ever fails on some other compositor/config, the portal is the known-good fallback** (jeepney: `CreateSession` → `BindShortcuts` with a distinct combo → `Activated` signal on a persistent connection; session dies with the connection, so it must live for the app's lifetime).

### Resource loading (dev vs frozen)
`res_path(name)` resolves bundled resources across three modes, in order: **PyInstaller** `sys._MEIPASS` (tries `arcaneeye/resources/<name>`, then legacy `resources/<name>`, then bundle root), **`importlib.resources`** over the `arcaneeye.resources` package, then a **dev source fallback** next to `main.py`. This mirrors ArcaneAtlas's `res_path`. The path constants (`icon_path`, `trayicon_path`, `banner_path`, `logo_path`) are computed once at import.

### Packaging (Windows)
- **`arcaneeye.spec`** — PyInstaller. Keeps `Analysis.datas` **empty** and ships `resources/` via a `Tree("arcaneeye/resources", prefix="arcaneeye/resources")` in `COLLECT` (same convention as ArcaneAtlas — keep resource bundling in the `Tree`, not in `datas`). `console=False` for the windowed release. `hiddenimports` come from `collect_submodules("arcaneeye")`.
- **`arcaneeye.iss`** — Inno Setup, installs to Program Files (`PrivilegesRequired=admin`), `LicenseFile` + `SetupIconFile` are staged into `installer\assets\` by the build script right before `ISCC` runs.
- `build_exe.bat` kills running `ArcaneEye.exe` and any `arcaneeye` Python processes and waits for DLL handles to release before a clean rebuild — do that before diagnosing "file locked" build failures.
- **The built exe/folder is `ArcaneEye` (space-free)** — normalized from the old `Arcane Eye.exe`/`dist/Arcane Eye/` so paths match ArcaneAtlas/ArcaneAudio and CI needs no space-quoting. The user-visible display name (Inno `MyAppName`, shortcuts) stays **"Arcane Eye"**. The spec `APP_NAME`, `.iss` `MyAppExeName`/`OutputBaseFilename`/`DefaultDirName`, and `build_installer.bat` all use the space-free form.

## Release automation (GitHub Actions)
`.github/workflows/release.yml` builds the **Windows installer + Linux tarball + macOS `.dmg`** and publishes them to a GitHub Release, code-signed. It is a **sibling copy of ArcaneAtlas's workflow** — see ArcaneAtlas `CLAUDE.md` → "Release automation (GitHub Actions)" for the full mechanics (how to trigger via tag or `workflow_dispatch`, idempotent re-runs, the asset-name contract, the `az login --service-principal` Windows auth, macOS import-cert → build → notarize → staple → `spctl` verify, and the secret list). **Keep the three apps' workflows in sync; only the `env:` block and per-app quirks differ.** ArcaneEye specifics:
- **Assets** (the `arcanetools.org/_redirects` contract): `ArcaneEye-Setup-windows.exe`, `ArcaneEye-linux.tar.gz`, `ArcaneEye-macos.dmg`.
- **macOS is a universal2 (arm64 + x86_64) build** — same as ArcaneAtlas: built on the `macos-14` arm64 runner via a **python.org universal2 Python** (replacing arch-specific `setup-python`) + universal2 PySide6 wheels + `target_arch='universal2'` in the spec, so the `.dmg` runs on both Apple Silicon and Intel Macs without ever touching the Intel `macos-13` runner.
- **No ffmpeg** — screen capture is in-process Qt, so all ffmpeg fetch/sign steps are omitted (unlike Atlas/Audio).
- **`pynput` on Linux** — the Linux build installs `xvfb` and runs PyInstaller under **`xvfb-run -a`** so importing pynput's Xorg backend during `collect_submodules` analysis can't stumble on a missing `$DISPLAY`.
- **Version = single source of truth** in `arcaneeye/__init__.py` (0.8.0). The `.iss` `MyAppVersion` is `#ifndef`-guarded; CI and `build_installer.bat` derive `/DMyAppVersion` from `__init__.py` (previously the version was hardcoded in three places).
- **Unique `AppId`** (`8D7F0B1B-…`) — it previously **reused ArcaneAtlas's exact GUID**, which would make Windows treat the two apps as the same for install/upgrade.
- **Signing infra added**: macOS `BUNDLE` + `codesign_identity`/`entitlements_file` in the spec (platform-guarded), `packaging/entitlements.mac.plist`, and a `requirements.txt` (`PySide6`, `pynput`, `pyinstaller`) — none of which existed before. **Signing reuses Atlas's secrets** (one Trusted Signing account + one Apple Developer ID cover all three apps): paste the identical 6 `AZURE_*`/`TRUSTED_SIGNING_*` + 7 `MACOS_*` secrets into this repo.

## Conventions / gotchas

- **`ui_mainwindow.py` does not exist** — there is no `.ui`/Qt Designer step. All widgets are built in code, so just edit the Python directly (no regenerate step, unlike ArcaneAtlas).
- **The snip only works dragging *down-right*** (known bug). `CaptureScreen.mouseReleaseEvent` grabs with raw `self.end.x() - self.origin.x()` (and same for y), which goes **negative** for an up-left drag even though the rubber band itself uses `.normalized()`. Fix by normalizing origin/end (min/abs) before `grabWindow`.
- **`time.sleep(0.2)` on the GUI thread** in `CaptureScreen.mouseReleaseEvent` blocks the event loop to let the dimming overlay repaint-away before the grab (so the 40% black doesn't end up in the screenshot). The author flagged it ("find a better way"). Any replacement must still guarantee the overlay is *actually* hidden on screen before `grabWindow` fires.
- **Debug `print()`s are everywhere**, including hot paths (`update_image`, menu rebuilds). There is no logging framework. When adding code, don't pile on more `print`; if diagnostics matter, introduce a real logger rather than extending the print soup.
- **`QThread.terminate()` on exit** (`exit_app`) is an abrupt kill of the pynput listener thread. It works but is unsafe in principle; a clean shutdown would stop the `GlobalHotKeys` listener and `wait()` on the thread.
- **Wayland / cross-platform caveats** (the real portability risk):
  - `pynput` global hotkeys and `QScreen.grabWindow(0, …)` are **X11-oriented** and behave very differently under **Wayland** — capture, window placement, and hotkey delivery all have Wayland-only workarounds. **See the dedicated "Wayland" section under Architecture before touching any of them.** The dev machine is Arch/EndeavourOS KDE (Wayland); verify under the active session type before assuming a hotkey/grab/display bug is app logic.
  - macOS needs **Accessibility permission** for `pynput` to see global keys; the app is untested on Mac despite the cross-platform goal.
  - `grabWindow` uses `primaryScreen()` with primary-screen-relative coordinates, so snipping on a **non-primary** monitor can grab the wrong region on multi-monitor setups (X11 path; Wayland grabs the whole virtual desktop via the portal and crops).
- **`QIcon("icon.png")` in `screensnip.py`** is a bare relative path that won't resolve when run as a module or frozen — it should use `res_path("icon.png")` like `main.py` does. (Harmless — it's just a missing window icon on the fullscreen overlay.)
- **License: AGPLv3.** The project (and the whole Arcane Tools suite) is licensed under the **GNU Affero General Public License v3.0** — chosen over plain GPLv3 to close the SaaS loophole for the planned remote-play/networking features (a modified, network-hosted version must share its source). Every source file carries the standard AGPL header with `Copyright (C) 2024–2026 Eric Hernandez`; the license text is `resources/AGPL_V3.txt` (shown in the About → License dialog and used as the installer's `LicenseFile`). Eric is the sole copyright holder — **require a CLA before accepting outside contributions** to preserve dual-licensing/commercial options.
- **Known-issues list** lives at the bottom of `main.py` under `#### THINGS TO DO ####` — the authoritative bug backlog (repeated "should not reach this" on quit after multiple snips, up-left drag, Esc-mid-snip leaving the Player View in a bad redraw state, clicking an already-selected screen deselecting all). Treat it as the TODO source of truth.
- **`nondistribute_resources/` is source art only** — never bundle it; shipped assets live in `arcaneeye/resources/`.
