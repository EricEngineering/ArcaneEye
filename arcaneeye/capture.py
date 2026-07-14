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

"""Screen-capture backends.

X11 / Windows: ``QScreen.grabWindow`` grabs the requested region directly.

Wayland: ``grabWindow`` returns an EMPTY pixmap under Wayland (the compositor
security model forbids a client from reading the framebuffer), so we ask the
compositor for the shot via **xdg-desktop-portal** instead. The portal grabs
the whole virtual desktop and hands back an image file URI; the caller crops it
to the user's selection. There is a one-time permission prompt, which the
portal remembers thereafter.

Why this must be done in-process (not via a `gdbus` subprocess): the portal
delivers the result asynchronously by emitting a ``Response`` signal *on the
D-Bus connection that made the call*. A short-lived `gdbus call` process exits
before that signal arrives, so the reply is lost. Keeping the request on the
app's own persistent QDBus connection is what makes it work.

PySide6 gotcha (6.11.1): ``QDBusConnection.connect`` only binds a signal when
the slot is passed as a **str with a leading "1"** (the old Qt ``SLOT()``
marker), e.g. ``"1onResponse(uint,QVariantMap)"``. A ``bytes`` slot raises, and
an unprefixed ``str`` has its first character eaten as the marker.
"""

import os
import sys
import uuid

from PySide6.QtCore import QObject, Slot, QEventLoop, QUrl, QTimer
from PySide6.QtGui import QGuiApplication, QImage


def is_wayland_session() -> bool:
    """True when running under a Wayland session (where grabWindow can't grab)."""
    if sys.platform != "linux":
        return False
    app = QGuiApplication.instance()
    if app is not None and app.platformName().startswith("wayland"):
        return True
    # Also treat an XWayland (xcb-on-Wayland) run as Wayland: grabWindow returns
    # black there too, so the portal is still the right backend.
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class _PortalShooter(QObject):
    """One portal Screenshot request, awaited on the app's QDBus connection."""

    PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
    PORTAL_PATH = "/org/freedesktop/portal/desktop"

    def __init__(self):
        super().__init__()
        self._uri = None
        self._loop = None

    @Slot("uint", "QVariantMap")
    def onResponse(self, code, results):
        if int(code) == 0:
            v = results.get("uri")
            # a{sv}: the value may arrive as a plain str or a QDBusVariant.
            self._uri = v.variant() if hasattr(v, "variant") else v
        if self._loop is not None:
            self._loop.quit()

    def grab(self, timeout_ms: int = 30000):
        """Return a full virtual-desktop QImage, or None on failure/timeout."""
        # Imported lazily so the module still imports on a build without QtDBus.
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return None

        token = "arcaneeye_" + uuid.uuid4().hex[:8]
        sender = bus.baseService()  # e.g. ":1.42"
        sender_token = (sender[1:] if sender.startswith(":") else sender).replace(".", "_")
        request_path = f"{self.PORTAL_PATH}/request/{sender_token}/{token}"

        # Subscribe to the request's Response BEFORE issuing the call (avoids a race).
        bus.connect(
            self.PORTAL_SERVICE, request_path,
            "org.freedesktop.portal.Request", "Response",
            self, "1onResponse(uint,QVariantMap)",
        )

        iface = QDBusInterface(
            self.PORTAL_SERVICE, self.PORTAL_PATH,
            "org.freedesktop.portal.Screenshot", bus,
        )
        options = {"handle_token": token, "interactive": False, "modal": False}
        reply = iface.call("Screenshot", "", options)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return None

        self._loop = QEventLoop()
        QTimer.singleShot(timeout_ms, self._loop.quit)
        self._loop.exec()

        if not self._uri:
            return None
        path = QUrl(self._uri).toLocalFile()
        img = QImage(path)
        # The portal writes the shot to a file (KDE: ~/Pictures). Arcane Eye snips
        # are ephemeral, so delete the file we just caused to be created rather
        # than accumulate one per snip.
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return img if not img.isNull() else None


def portal_grab_fullscreen():
    """Full virtual-desktop QImage via xdg-desktop-portal, or None on failure."""
    return _PortalShooter().grab()
