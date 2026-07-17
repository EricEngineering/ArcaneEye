# Copyright (C) 2024–2026 Eric Hernandez
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This Python file uses the following encoding: utf-8

import sys, platform, math
from PySide6.QtWidgets import QMainWindow, QWidget, QApplication, QDialog, QSystemTrayIcon, QPushButton
from PySide6.QtWidgets import QMenu, QLabel, QHBoxLayout, QVBoxLayout, QMessageBox, QSizePolicy, QSpacerItem
from PySide6.QtWidgets import QTextEdit, QScrollArea, QLayout
from PySide6.QtCore import QThread, Signal, QEventLoop, QEvent, Qt, QObject, QTimer
from PySide6.QtGui import QIcon, QAction, QCursor, QPixmap, QGuiApplication, QFont, QPalette
from pynput import keyboard
from arcaneeye import __version__
from arcaneeye.screensnip import CaptureScreen
from arcaneeye.capture import is_wayland_session
from arcaneeye.about import AboutDialog, _theme, _rounded_icon
import textwrap
from pathlib import Path

from importlib.resources import files, as_file
import arcaneeye.resources as respkg  # <-- key change

def res_path(name: str) -> str:
    # A) PyInstaller: try the unpacked bundle first (newer PyInstaller puts files under _internal)
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        for p in (
            base / "arcaneeye" / "resources" / name,
            base / "resources" / name,                     # legacy
            base / name,                                   # last resort
        ):
            if p.exists():
                return str(p)

    # B) importlib.resources (works in dev and frozen)
    try:
        with as_file(files(respkg) / name) as p:
            return str(p)
    except Exception:
        pass

    # C) Dev fallback (run from source)
    return str(Path(__file__).resolve().parent / "resources" / name)

icon_path = res_path("icon.png")
trayicon_path = res_path("trayicon.png")


class WelcomeDialog(QDialog):
    """First-launch dialog: Arcane Eye has no main window — it lives in the
    system tray. Explains that and gives the session-aware quick start, then the
    user clicks OK. Reuses the About dialog's theme/icon helpers so the two look
    like one family."""

    def __init__(self, quick_start, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Arcane Eye")
        self.setWindowIcon(QIcon(icon_path))
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        c = _theme(dark)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(0)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        # hero: rounded icon + serif title + subtitle
        hero = QHBoxLayout()
        hero.setSpacing(16)
        ic = QLabel()
        ic.setPixmap(_rounded_icon(icon_path, 72, 15))
        ic.setFixedSize(72, 72)
        hero.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        htext = QVBoxLayout()
        htext.setSpacing(2)
        title = QLabel("Arcane Eye")
        tf = QFont("Georgia")
        tf.setStyleHint(QFont.StyleHint.Serif)
        tf.setPointSize(21)
        tf.setWeight(QFont.Weight.DemiBold)
        title.setFont(tf)
        htext.addWidget(title)
        sub = QLabel("Lives in your system tray — there's no main window.")
        sub.setStyleSheet(f"color:{c['muted']};")
        htext.addWidget(sub)
        hero.addLayout(htext, 1)
        root.addLayout(hero)

        root.addSpacing(18)
        root.addWidget(self._eyebrow("Where to find it", c["violet"]))
        root.addSpacing(6)
        tray = QLabel(
            "Look for the Arcane Eye icon in your system tray. "
            "<b>Every action and setting</b> — choose screen, display size, "
            "Snip, Hide, About — lives in its right-click menu.")
        tray.setWordWrap(True)
        tray.setFixedWidth(440)
        tray.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(tray)

        root.addSpacing(16)
        root.addWidget(self._eyebrow("Quick start", c["violet"]))
        root.addSpacing(6)
        qs = QLabel(quick_start)
        qs.setWordWrap(True)
        qs.setFixedWidth(440)
        qs.setTextFormat(Qt.TextFormat.RichText)
        qs.setContentsMargins(12, 10, 12, 10)
        qs.setStyleSheet(
            f"background:{c['panel']}; border:1px solid {c['border']};"
            f"border-radius:8px;")
        root.addWidget(qs)

        root.addSpacing(18)
        btnrow = QHBoxLayout()
        btnrow.addStretch(1)
        ok = QPushButton("OK")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setDefault(True)
        ok.setStyleSheet(
            f"QPushButton{{padding:8px 24px; border-radius:8px;"
            f"border:1px solid {c['border']};}}"
            f"QPushButton:hover{{border:1px solid {c['violet']};}}")
        ok.clicked.connect(self.accept)
        btnrow.addWidget(ok)
        root.addLayout(btnrow)

    def _eyebrow(self, text, color):
        lbl = QLabel(text.upper())
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 112)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color:{color};")
        return lbl


class DisplayWindow(QWidget): # Changed to QWidget from QMainWindow

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Player View")
        # Set the window icon to a PNG file
        self.setWindowIcon(QIcon(icon_path))
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        #self.setWindowFlag(Qt.SplashScreen) #This Setting Breaks Screen Selection
        self.setWindowFlag(Qt.FramelessWindowHint) # Remove Window Border
        self.setAttribute(Qt.WA_TranslucentBackground) # 100% transparent
        # The player window fills the target screen; the snip is centred on it.
        # Let clicks pass through the transparent area so it never traps the
        # cursor on the player monitor.
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        # Wayland ONLY: make the player a passive, non-locking overlay.
        #  * WA_ShowWithoutActivating — never becomes an exclusive, desktop-locking
        #    fullscreen surface (an *activated* fullscreen window is what KDE turns
        #    exclusive, covering the panel/tray and trapping input).
        #  * WindowDoesNotAcceptFocus — belt-and-suspenders: discourage the overlay
        #    from grabbing keyboard focus so it stays a passive layer over the map.
        # Together these keep the desktop fully interactive while the Player View is
        # up. NOTE: they do NOT rescue the global Esc under Wayland — that problem
        # is unfixable at the window level (pynput can't hear a bare key while a
        # Wayland surface holds focus), so dismissal on Wayland is handled by the
        # Ctrl+Shift+X toggle instead (see TrayApp / CLAUDE.md → Wayland).
        # On X11/Windows/macOS the window activates normally (the proven path).
        if is_wayland_session():
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus)
        self.label = QLabel()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.label, alignment=Qt.AlignCenter)
        self.setLayout(self.layout)
        # Screen the snip should be shown on; set by update_image, used to place
        # the window (fullscreen-on-that-output).
        self._target_screen = None
        # The output the surface is CURRENTLY mapped on. Wayland only assigns a
        # window to an output at map time, so we compare against this to know when
        # a re-map is needed (see _place_on_target).
        self._shown_screen = None

    def update_image(self, grabbedPixMap, screen_index, percent_of_screen):
        print("update player window")

        # Find the selected screen and scale the snip to a percent of it.
        screens = QApplication.screens()
        if not screens:
            return
        if screen_index < 0 or screen_index >= len(screens):
            screen_index = len(screens) - 1
        selected_screen = screens[screen_index]
        geometry = selected_screen.geometry()

        original_width = grabbedPixMap.width()
        original_height = grabbedPixMap.height()
        monitor_width = geometry.width()
        monitor_height = geometry.height()

        if (original_width <= 0) or (original_height <= 0):
            return  # nothing to show (e.g. an empty/failed grab)

        # Fit-within-percent-box: the largest size that fits inside a box of
        # (percent x screen_width) by (percent x screen_height), preserving
        # aspect. So a given percent reads as "that much of the screen" for any
        # selection shape, instead of only sizing one axis.
        box_width = monitor_width * percent_of_screen
        box_height = monitor_height * percent_of_screen
        scale = min(box_width / original_width, box_height / original_height)
        new_width = max(1, math.floor(original_width * scale))
        new_height = max(1, math.floor(original_height * scale))

        # Grab the Device Pixel Ratio so the image is crisp on HiDPI screens.
        dpr = selected_screen.devicePixelRatio()

        resized_pixmap = grabbedPixMap.scaled(round(new_width*dpr), round(new_height*dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        resized_pixmap.setDevicePixelRatio(dpr)

        self.label.setFixedSize(new_width, new_height)
        self.label.setPixmap(resized_pixmap)

        # Remember where to show it; re-place now if already on screen (e.g. a
        # size change or a hot-plug moved the target screen).
        self._target_screen = selected_screen
        if self.isVisible():
            self._place_on_target()

        print(f"Display Pixel Ratio: {dpr}")
        print(f"OG  Image      W:{original_width} H:{original_height}")
        print(f"Screen         W:{monitor_width} H:{monitor_height}")
        print(f"Screen %: {percent_of_screen}: box W:{box_width} H:{box_height}")
        print(f"New Image      W:{new_width} H:{new_height}")
        print(f"label SZ       W:{self.label.width()} H:{self.label.height()}")

    def _place_on_target(self):
        """Show the window fullscreen on the target screen. Three platform paths:

        X11 / Windows: the original, proven path — setGeometry positions onto the
        target screen and showFullScreen() fullscreens (+ activates) there.

        macOS: cover the target screen by GEOMETRY + show() (not showFullScreen()).
        showFullScreen() enters the native full-screen Space, and hiding that Space
        leaves the screen black (same native-Space bug as the snip overlay). Geometry-
        cover gives the same full-screen Player View but hides cleanly.

        Wayland needs two things and gets its own branch:
          * NON-activating fullscreen (setWindowState + show under WA_ShowWithout-
            Activating) so KDE doesn't turn the surface into an EXCLUSIVE, desktop-
            locking fullscreen. It stays a passive click-through overlay.
          * A hide/re-map when the target output changes while visible — Wayland
            only assigns a window to an output at map time, so setScreen() on an
            already-mapped window is ignored.
        """
        screen = self._target_screen or QGuiApplication.primaryScreen()
        if screen is None:
            self.showFullScreen()
            return
        if is_wayland_session():
            # Wayland: non-activating fullscreen + hide-remap on output change.
            if self.isVisible() and self._shown_screen is not screen:
                self.hide()
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
            self.setWindowState(self.windowState() | Qt.WindowFullScreen)
            self.show()
            self.raise_()
        elif sys.platform == "darwin":
            # macOS: cover the target screen by geometry — NOT showFullScreen(),
            # which enters the native full-screen Space. Hiding that Space (Esc →
            # window.hide()) leaves the screen black, exactly like the snip overlay
            # (see screensnip.py / CLAUDE.md → macOS). Geometry-cover gives the same
            # full-screen Player View but hides cleanly with no black.
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
            self.show()
            self.raise_()
        else:
            # X11 / Windows: the original behavior, unchanged.
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
            self.showFullScreen()
        self._shown_screen = screen

    def hideEvent(self, event):
        # Once unmapped, the next show must re-target the output from scratch
        # (Wayland). Harmless on other platforms.
        self._shown_screen = None
        super().hideEvent(event)

    def show_window(self):
        self._place_on_target()
        self.raise_()

class TrayApp:
    def __init__(self):
        # Initialize application

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # Prevent the app from quitting when the last window is closed

        #create an object of the window that will hold the image to be displayed
        self.window = DisplayWindow()

        # Create System Tray Icon
        self.tray_icon = QSystemTrayIcon(QIcon(trayicon_path), self.app)

        # Create context menu for the system tray
        self.menu = QMenu()

        # Add About item to the menu.
        self.tray_action_about = QAction("About / Help")
        self.tray_action_about.triggered.connect(self.show_about)
        self.menu.addAction(self.tray_action_about)

        # Add Show Player Window
        self.show_window_action = QAction("Show Player Window")
        self.menu.addAction(self.show_window_action)
        self.show_window_action.triggered.connect(self.window.show_window)

        # Add Hide Player Window. The dismiss key differs by platform: Esc on
        # X11/Windows/macOS, the Ctrl+Shift+X toggle on Wayland (no Esc there).
        _hide_hint = "ctrl+shift+x" if is_wayland_session() else "esc"
        self.hide_window_action = QAction(f"Hide Player Window ({_hide_hint})")
        self.menu.addAction(self.hide_window_action)
        self.hide_window_action.triggered.connect(self.window.hide)

        # Add screen selection sub-menu
        self.screen_menu = self.menu.addMenu("Select Screen")
        # Initialize selected screen index
        self.selected_screen_index = 0
        # Populate screen selection menu
        self.update_screen_menu()

        # Placeholder shown in the Player Window before anything is snipped —
        # the app icon (was the old logo.png / GM-Snipe art).
        self.snippedPixMap = QPixmap(icon_path)

        # Add Percent of Screen Submenu and default to 0.7
        ##action.setChecked(percent == 0.7)
        self.percent_of_screen = 2 #will later get initialized by set_percent_of_screen()
        self.size_submenu = self.menu.addMenu("Display Size")
        self.menu.addMenu(self.size_submenu)
        # Populate the Percent of Screen Submenu
        for index in range(0,5,1): # index = 5 to 9, python is weird
            percent = 50+(index*10)
            print(f"index: {index}, percent: {percent}")
            action = QAction(f"{percent}% of Screen", self.size_submenu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, idx=index: self.set_percent_of_screen(idx))
            self.size_submenu.addAction(action)
        #print(f"Number of actions: {len(self.screen_menu.actions())}")
        self.set_percent_of_screen(2) #Initialize percent_of_screen to 70%

        # populate the player window with a default image in case someone decides to show the player view without
        #   having performed a screen snip
        self.window.update_image(self.snippedPixMap, self.selected_screen_index, self.percent_of_screen)

        # Add a Snip item to the menu.
        self.tray_action_snip = QAction("Snip (ctrl+shift+x)")
        self.tray_action_snip.triggered.connect(self.screenSnip)
        self.menu.addAction(self.tray_action_snip)

        # Add exit option to tray
        self.menu.addSeparator()
        self.exit_action = QAction("Exit")
        self.menu.addAction(self.exit_action)

        # Assign menu to tray icon
        self.tray_icon.setContextMenu(self.menu)

        # Show the tray icon
        self.tray_icon.show()

        # Connect actions to their handlers
        
        self.exit_action.triggered.connect(self.exit_app)

        # Global hotkey (pynput, all platforms). Ctrl+Shift+X is the primary
        # hotkey everywhere; how "hide" is triggered differs by session type:
        #  * Wayland: Ctrl+Shift+X is a show/hide TOGGLE, and Esc is deliberately
        #    NOT registered — pynput can't hear a bare Esc under Wayland with a
        #    still mouse (it's a modifier-less key; the fullscreen overlay holds
        #    keyboard focus and the compositor withholds it from XWayland), and a
        #    buffered Esc would then ride in on the NEXT hotkey and mis-fire.
        #  * X11/Windows/macOS: Ctrl+Shift+X snips, Esc hides — the proven path.
        # See ArcaneEye CLAUDE.md → "Wayland" for the full mechanism.
        self._wayland = is_wayland_session()
        self.hotkey_thread = HotkeyListenerThread(include_esc=not self._wayland)
        self.hotkey_thread.hotkey_display_activated.connect(self._hotkey_ctrlshiftx)
        self.hotkey_thread.hotkey_close_activated.connect(self.hide_all_windows_cancel_snip)
        self.hotkey_thread.start()
        print("hotkey listener thread started"
              + (" (Wayland: Ctrl+Shift+X toggle, no Esc)" if self._wayland else ""))

        # Store created windows to avoid garbage collection
        #self.windows = []

        # Start timer to periodically check for screen changes and update
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_screens_menu_if_changed)
        self.timer.start(1000)  # 1000ms interval
        # Track the last known screen configuration
        self.last_screens = self.get_screens()

        # First-launch welcome — Arcane Eye has no main window, so tell the user
        # it lives in the tray + how to use it. Shown once the event loop starts.
        QTimer.singleShot(0, self._show_welcome)

    def _show_welcome(self):
        # Session-aware quick start: Wayland uses the Ctrl+Shift+X toggle (no
        # Esc — see the Wayland notes); elsewhere Esc hides.
        if is_wayland_session():
            quick = ("Press <b>Ctrl&nbsp;+&nbsp;Shift&nbsp;+&nbsp;X</b> to snip a "
                     "region and show it on your players' screen. Press "
                     "<b>Ctrl&nbsp;+&nbsp;Shift&nbsp;+&nbsp;X</b> again to hide it.")
        else:
            quick = ("Press <b>Ctrl&nbsp;+&nbsp;Shift&nbsp;+&nbsp;X</b> to snip a "
                     "region and show it on your players' screen. Press "
                     "<b>Esc</b> to hide it.")
        WelcomeDialog(quick).exec()

    def set_percent_of_screen(self, index):
        # Update the checkable state of screen menu items
        # Set all to unchecked
        for action in self.size_submenu.actions():
            action.setChecked(False)
        # Set the newly selected item as checked
        self.size_submenu.actions()[index].setChecked(True)
        self.percent_of_screen = 0.5+(index/10)
        print(f"Percent Set To: {self.percent_of_screen}")
        self.window.update_image(self.snippedPixMap, self.selected_screen_index, self.percent_of_screen)

    def show_about(self):
        AboutDialog(
            app_name="Arcane Eye",
            version=__version__,
            icon_path=icon_path,
            tagline="Snip anything on your screen and put it on your "
                    "players' screen — instantly.",
            license_path=res_path("AGPL_V3.txt"),
        ).exec()

    def get_screens(self):
        # Get a list of available screen names
        return [screen.name() for screen in QApplication.screens()]

    def update_screens_menu_if_changed(self):
        # Check if the screen configuration has changed
        current_screens = self.get_screens()
        if current_screens != self.last_screens:
            print("Screens Changed Detected - Updated Menu")
            self.update_screen_menu()
            self.last_screens = current_screens
            # Reassign menu to make sure it updates (not always necessary)
            # but I needed it on linux kde, not sure of others
            self.tray_icon.setContextMenu(self.menu)
            # if the screens have changed we should update the position
            self.window.update_image(self.snippedPixMap, self.selected_screen_index, self.percent_of_screen)
        #else:
            #print("check screen - No Change")

    def update_screen_menu(self):
        self.screen_menu.clear()
        screens = QApplication.screens()
        
        # Update selected screen index to the last screen found
        if screens:
            self.selected_screen_index = len(screens) - 1
        
        for index, screen in enumerate(screens):
            print(f"screen {index + 1} found")
            action = QAction(f"Screen {index + 1}: {screen.name()}", self.screen_menu)
            action.setCheckable(True)
            action.setChecked(index == self.selected_screen_index)
            action.triggered.connect(lambda checked, idx=index: self.set_selected_screen(idx))
            self.screen_menu.addAction(action)

    def set_selected_screen(self, index):
        self.selected_screen_index = index
        # Update the checkable state of screen menu items
        for action in self.screen_menu.actions():
            action.setChecked(False)
        self.screen_menu.actions()[index].setChecked(True)
        self.window.update_image(self.snippedPixMap, self.selected_screen_index, self.percent_of_screen)

    def hide_all_windows_cancel_snip(self):
        self.window.hide()
        # If esc is pressed and we are in the middle of a snip, it should be canceled
        # If an instance already exists, destroy it
        if CaptureScreen._instance is not None:
            print("destroy old instance")
            CaptureScreen._instance.close()  # Close the previous instance to destroy it

    def _hotkey_ctrlshiftx(self):
        # Ctrl+Shift+X. On Wayland it's a show/hide toggle (hide if the Player
        # View is showing, else snip) — a modifier combo is the ONE thing pynput
        # hears reliably under Wayland, so it doubles as the dismiss key there.
        # Elsewhere it just snips and Esc handles hide.
        if self._wayland and self.window.isVisible():
            self.hide_all_windows_cancel_snip()
        else:
            self.screenSnip()

    def exit_app(self):
        self.tray_icon.hide()
        # terminate the hotkey listener thread when quitting
        self.hotkey_thread.terminate()
        QApplication.quit()

    def run(self):
        sys.exit(self.app.exec())

    def screenSnip(self):
        print("Snipping...")
        snip = CaptureScreen()
        snip.show()
        # Wait until the Snip is Done by monitoring for the widget to be hidden
        loop = QEventLoop()
        snip.hideEvent = lambda event: loop.quit()
        loop.exec() # wait ...
        # grab the snipped pixmap then delete the object
        self.snippedPixMap = snip.grabbedPixMap
        snip.close() # I think this deletes the object???
        snip.setParent(None) # This should also delete...
        # I feel like this whole handshaking/passing pixmap needs help
        print("Finished Snip")
        
        # Get the selected screen
        screens = QApplication.screens()
        if self.selected_screen_index < len(screens):
            selected_screen = screens[self.selected_screen_index]

            # Create and show the window centered on the selected screen
            # update window with new screen snip
            self.window.update_image(self.snippedPixMap, self.selected_screen_index, self.percent_of_screen)
            self.window.show_window()
    
            #print("should see window")
            #loop = QEventLoop()
            #self.window.destroyed.connect(loop.quit)
            #loop.exec()  # Wait until the window is destroyed
            #print("should not reach this")
            # If the above is enabled, then I get multiple should not reach this
            #   upon terminating, is this an issue and does it happen even without the above

class HotkeyListenerThread(QThread):
    hotkey_display_activated = Signal()  # Define a custom signal to notify the main thread when the hotkey is activated
    hotkey_close_activated = Signal()  # Define a custom signal to notify the main thread when the hotkey is activated

    def __init__(self, include_esc=True):
        super().__init__()
        # Whether to register the bare Esc hotkey. Off on Wayland, where a
        # modifier-less key is unreliable and a buffered Esc mis-fires on the
        # next hotkey (see TrayApp.__init__ / CLAUDE.md → Wayland).
        self._include_esc = include_esc

    def run(self):
        def on_activate_display():
            self.hotkey_display_activated.emit()  # Emit the signal when the hotkey is detected
        def on_activate_close():
            self.hotkey_close_activated.emit()  # Emit the signal when the hotkey is detected

        hotkeys = {'<ctrl>+<shift>+X': on_activate_display}
        if self._include_esc:
            hotkeys['<esc>'] = on_activate_close
        with keyboard.GlobalHotKeys(hotkeys) as listener:
            listener.join()

def main() -> int:
    """Entry point for module execution."""
    tray_app = TrayApp()
    tray_app.run()
    return 0  # QApplication already exits internally

if __name__ == "__main__":
    sys.exit(main())




#### THINGS TO DO ####
##I get multiple "should not reach this" when quitting after multiple snips
##need a cool new icon, ask austin
##add a default image for showing the window without snipping before, maybe instructions...
##screensnip only works click drag down right, doesn't work, click drag left up
##screensnip followed by esc causes player view window to stay open yet minimized/hidden, subsequent snips cause issues redrawing display
##clicking on a selected screen causes no screen to be selected, need to fix this



