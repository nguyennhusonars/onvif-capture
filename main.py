#!/usr/bin/env python3
"""Entry point for the ONVIF Profile M Native AI Analytics & Metadata Inspector GUI."""

import sys
from PySide6.QtWidgets import QApplication
from onvif_capture.gui import ONVIFProfileMWindow


def main() -> None:
    app = QApplication(sys.argv)
    win = ONVIFProfileMWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

