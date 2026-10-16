#!/usr/bin/env python3
"""Entry point for the ONVIF Profile M Native AI Analytics & Metadata Inspector GUI."""

from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from onvif_capture.gui import ONVIFProfileMWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("onvif-capture")
    app.setApplicationDisplayName("ONVIF Inspector")
    app.setDesktopFileName("onvif-capture.desktop")

    # Locate application icon
    icon_path = Path(__file__).resolve().parent / "assets" / "icons" / "onvif-capture.png"
    if not icon_path.exists():
        icon_path = Path("/usr/share/icons/hicolor/256x256/apps/onvif-capture.png")
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)

    win = ONVIFProfileMWindow()
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

