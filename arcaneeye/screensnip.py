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

#from PySide6.QtWidgets import QApplication
from PySide6 import QtCore, QtGui, QtWidgets

from PySide6.QtCore import Qt, QThread, Signal, QEventLoop, QEvent
from PySide6.QtGui import QIcon
import time

from arcaneeye.capture import is_wayland_session, portal_grab_fullscreen


class CaptureScreen(QtWidgets.QLabel):
    _instance = None 

    def __init__(self):
        # If an instance already exists, destroy it
        if CaptureScreen._instance is not None:
            print("destroy old instance")
            CaptureScreen._instance.close()  # Close the previous instance to destroy it

        # Initialize the new instance
        super(CaptureScreen, self).__init__()

        self.setWindowTitle("Screen Snip")

        # Set this instance as the current one
        CaptureScreen._instance = self

        print("NEW")

        #self.setWindowState(QtCore.Qt.WindowFullscreen)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowIcon(QIcon("icon.png"))

        # Points on screen marking the origin and end of regtangle area.
        self.origin = QtCore.QPoint(0,0)
        self.end = QtCore.QPoint(0,0)

        # A drawing widget for representing bounding area
        self.rubberBand = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)

        self.createDimScreenEffect()
        self.setCursor(QtCore.Qt.CrossCursor)

        self.grabbedPixMap = QtGui.QPixmap()

    def closeEvent(self, event):
        # Clear the reference when the widget is closed
        CaptureScreen._instance = None
        super().closeEvent(event)

    def createDimScreenEffect(self):
        """Fill the overlay with a semi-transparent black to dim the screen.

        The dim is baked into the pixmap's own alpha channel (paired with
        WA_TranslucentBackground) rather than requested via setWindowOpacity().
        setWindowOpacity() is a compositor-side, whole-window effect that
        Wayland has no protocol for, so the Wayland Qt plugin treats it as a
        no-op -> the overlay rendered as solid opaque black. Per-pixel alpha is
        drawn by the client, so it works identically on Wayland, X11 and Windows.
        """

        # Get the screen geometry of the main desktop screen for size ref
        primScreenGeo = QtGui.QGuiApplication.primaryScreen().geometry()

        screenPixMap = QtGui.QPixmap(primScreenGeo.width(), primScreenGeo.height())
        # ~40% opaque black (alpha 102/255) — matches the old 0.4 window opacity
        screenPixMap.fill(QtGui.QColor(0, 0, 0, 102))

        # Let the transparent regions of the pixmap show the desktop through
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setPixmap(screenPixMap)

        self.setWindowState(QtCore.Qt.WindowFullScreen)

    def mousePressEvent(self, event):
        """Show rectangle at mouse position when left-clicked"""
        if event.button() == QtCore.Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubberBand.setGeometry(QtCore.QRect(self.origin, QtCore.QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        """Resize rectangle as we move mouse, after left-clicked."""
        self.rubberBand.setGeometry(QtCore.QRect(self.origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):
        """Upon mouse released, capture the selected screen region."""
        if event.button() == QtCore.Qt.LeftButton:
            self.end = event.position().toPoint()
            self.rubberBand.hide()
            self.setWindowOpacity(0)
            self.repaint()      #find a better way to do this
            self.hide()         #find a better way to do this
            # Make sure the dim overlay is actually off-screen before we grab,
            # otherwise it would appear in the screenshot.
            QtWidgets.QApplication.processEvents()
            time.sleep(0.2)     #find a better way to do this

            # Selection rect in this (fullscreen) widget's local coords.
            # normalized() makes it valid for any drag direction, which also
            # fixes the old "only drag down-right works" bug.
            rect = QtCore.QRect(self.origin, self.end).normalized()

            if is_wayland_session():
                self.grabbedPixMap = self._grab_wayland(rect)
            else:
                self.grabbedPixMap = self._grab_x11(rect)

    def _grab_x11(self, rect):
        """Direct region grab (X11 / Windows). grabWindow(0, ...) reads the root
        window at the overlay-local coordinates, matching the original behavior."""
        primaryScreen = QtGui.QGuiApplication.primaryScreen()
        return primaryScreen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())

    def _grab_wayland(self, rect):
        """Wayland: grab the whole desktop via the portal, then crop to the
        selection. grabWindow returns an empty pixmap under Wayland."""
        full = portal_grab_fullscreen()  # QImage of the virtual desktop (physical px)
        if full is None or full.isNull():
            return QtGui.QPixmap()

        # The overlay is fullscreen on one screen, so its local (0,0) is that
        # screen's top-left. Offset by the screen's position to get virtual-
        # desktop coords (mapToGlobal is unreliable on Wayland). Then scale into
        # the portal image's physical pixels (handles HiDPI; dpr 1.0 -> 1:1).
        screen = self.screen() or QtGui.QGuiApplication.primaryScreen()
        sgeo = screen.geometry()
        vgeo = QtGui.QGuiApplication.primaryScreen().virtualGeometry()
        sx = full.width() / vgeo.width()
        sy = full.height() / vgeo.height()

        gx = (sgeo.x() + rect.x()) - vgeo.x()
        gy = (sgeo.y() + rect.y()) - vgeo.y()
        crop = QtCore.QRect(
            round(gx * sx), round(gy * sy),
            round(rect.width() * sx), round(rect.height() * sy),
        ).intersected(full.rect())
        if crop.isEmpty():
            return QtGui.QPixmap()
        return QtGui.QPixmap.fromImage(full.copy(crop))
