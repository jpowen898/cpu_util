#!/usr/bin/env bash

set -euo pipefail

APP_NAME="CPU Monitor"
APP_ID="cpu-monitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="${HOME}/.local/share/applications/${APP_ID}.desktop"
ICON_DIR="${HOME}/.local/share/icons/hicolor/256x256/apps"
ICON_TARGET="${ICON_DIR}/${APP_ID}.png"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER="${BIN_DIR}/${APP_ID}"

mkdir -p "${ICON_DIR}" "${BIN_DIR}" "$(dirname "${DESKTOP_FILE}")"

if [[ ! -f "${SCRIPT_DIR}/cpu_monitor.py" ]]; then
    echo "cpu_monitor.py not found in ${SCRIPT_DIR}" >&2
    exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/icon.png" ]]; then
    echo "icon.png not found in ${SCRIPT_DIR}" >&2
    exit 1
fi

cp "${SCRIPT_DIR}/icon.png" "${ICON_TARGET}"

cat > "${LAUNCHER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail

cd "${SCRIPT_DIR}"

if [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
    exec "${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/cpu_monitor.py"
fi

exec python3 "${SCRIPT_DIR}/cpu_monitor.py"
EOF

chmod +x "${LAUNCHER}"

cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=${APP_NAME}
Comment=Real-time CPU monitoring dashboard
Exec=${LAUNCHER}
Icon=${ICON_TARGET}
StartupWMClass=${APP_ID}
Terminal=false
Categories=System;Monitor;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$(dirname "${DESKTOP_FILE}")" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Installed ${APP_NAME}."
echo "Launcher: ${DESKTOP_FILE}"
echo "Command: ${LAUNCHER}"
echo "You can now search for '${APP_NAME}' in the Ubuntu app launcher."