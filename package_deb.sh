#!/usr/bin/env bash
set -euo pipefail

# Build script for onvif-capture Debian package (.deb)
APP_NAME="onvif-capture"
VERSION="1.0.0"
ARCH="amd64"
PKG_DIR="build_deb/${APP_NAME}_${VERSION}_${ARCH}"
DIST_DIR="dist"
DEB_FILE="${DIST_DIR}/${APP_NAME}_${VERSION}_${ARCH}.deb"

# 0. Build binary with PyInstaller if missing or explicitly requested
if [ "${1:-}" = "--rebuild" ] || [ ! -f "dist/${APP_NAME}/${APP_NAME}" ]; then
    echo "=== Compiling standalone binary via PyInstaller ==="
    PYINSTALLER_BIN="$(which pyinstaller || true)"
    if [ -z "${PYINSTALLER_BIN}" ] && [ -x "/home/sonnn/miniconda3/bin/pyinstaller" ]; then
        PYINSTALLER_BIN="/home/sonnn/miniconda3/bin/pyinstaller"
    fi
    PYTHON_BIN="$(which python3 || true)"
    if [ -x "/home/sonnn/miniconda3/bin/python3" ]; then
        PYTHON_BIN="/home/sonnn/miniconda3/bin/python3"
    fi

    WSDL_DIR="$(${PYTHON_BIN} -c 'import os, onvif; print(os.path.join(os.path.dirname(os.path.dirname(onvif.__file__)), "wsdl"))' 2>/dev/null || true)"
    WSDL_ARG=""
    if [ -n "${WSDL_DIR}" ] && [ -d "${WSDL_DIR}" ]; then
        WSDL_ARG="--add-data ${WSDL_DIR}:wsdl"
    fi

    "${PYINSTALLER_BIN}" --noconfirm --onedir --windowed \
      --name "${APP_NAME}" \
      --add-data "assets:assets" \
      ${WSDL_ARG} \
      --exclude-module PyQt5 \
      --exclude-module PyQt6 \
      --exclude-module matplotlib \
      --exclude-module tkinter \
      --hidden-import "appdirs" \
      --hidden-import "zeep" \
      --hidden-import "zeep.wsse.username" \
      --hidden-import "onvif" \
      --hidden-import "lxml" \
      --hidden-import "lxml.etree" \
      main.py
fi

echo "=== Preparing Debian Package Directory Structure ==="
rm -rf "build_deb"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/opt/${APP_NAME}"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/icons/hicolor/scalable/apps"

# 1. Copy standalone binary bundle to /opt/onvif-capture
echo "Copying PyInstaller distribution to /opt/${APP_NAME}..."
cp -r "dist/${APP_NAME}/"* "${PKG_DIR}/opt/${APP_NAME}/"

# 2. Launcher symlink in /usr/bin/onvif-capture
ln -s "/opt/${APP_NAME}/${APP_NAME}" "${PKG_DIR}/usr/bin/${APP_NAME}"

# 3. Desktop Entry file
echo "Installing desktop launcher..."
cp "assets/${APP_NAME}.desktop" "${PKG_DIR}/usr/share/applications/"

# 4. App icons for all standard resolutions
echo "Installing application icons..."
cp "assets/icons/${APP_NAME}.svg" "${PKG_DIR}/usr/share/icons/hicolor/scalable/apps/${APP_NAME}.svg"

for SIZE in 16 32 48 64 128 256 512; do
    ICON_SRC="assets/icons/hicolor/${SIZE}x${SIZE}/apps/${APP_NAME}.png"
    ICON_DEST_DIR="${PKG_DIR}/usr/share/icons/hicolor/${SIZE}x${SIZE}/apps"
    if [ -f "${ICON_SRC}" ]; then
        mkdir -p "${ICON_DEST_DIR}"
        cp "${ICON_SRC}" "${ICON_DEST_DIR}/${APP_NAME}.png"
    fi
done

# 5. Debian control file
echo "Generating DEBIAN/control..."
cat << 'EOF' > "${PKG_DIR}/DEBIAN/control"
Package: onvif-capture
Version: 1.0.0
Section: video
Priority: optional
Architecture: amd64
Maintainer: ONVIF Analytics Team <support@onvif-capture.org>
Depends: ffmpeg, libxcb-cursor0, libxkbcommon-x11-0, libgl1
Description: ONVIF Profile M Native AI Analytics and Metadata Inspector
 Standalone desktop application for real-time inspection, capture, and
 visualization of ONVIF Profile M AI object analytics, bounding boxes,
 rule triggers, and alarm snapshots from any compliant IP camera.
EOF

# 6. Post-install / Post-remove scripts for icon & desktop cache updates
cat << 'EOF' > "${PKG_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if which gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

cat << 'EOF' > "${PKG_DIR}/DEBIAN/postrm"
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if which gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postrm"

# 7. Build .deb package
echo "Building Debian package with dpkg-deb..."
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${DEB_FILE}"

echo "=== Package successfully built at: ${DEB_FILE} ==="
dpkg-deb -I "${DEB_FILE}"

echo "Cleaning up staging build directory..."
rm -rf "build_deb"

