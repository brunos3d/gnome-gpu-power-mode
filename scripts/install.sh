#!/usr/bin/env bash
# Install the gpupowerd daemon (root, systemd + system D-Bus) and the GNOME
# extension (current user). Run as your normal user; it calls sudo for the
# system parts.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIBDIR=/usr/local/lib/gpu-power-mode
UUID=gpu-power-mode@bruno
EXTDIR="${HOME}/.local/share/gnome-shell/extensions/${UUID}"

echo "==> Checking dependencies"
missing=""
/usr/bin/python3 -c "import pynvml" 2>/dev/null || missing+=" python-nvidia-ml-py"
/usr/bin/python3 -c "import dbus" 2>/dev/null || missing+=" python-dbus"
/usr/bin/python3 -c "import gi" 2>/dev/null || missing+=" python-gobject"
if [ -n "$missing" ]; then
    echo "Installing missing packages:$missing"
    sudo pacman -S --needed --noconfirm $missing
fi

echo "==> Installing daemon to ${LIBDIR}"
sudo install -Dm755 "${REPO}/daemon/gpupowerd.py"    "${LIBDIR}/gpupowerd.py"
sudo install -Dm644 "${REPO}/daemon/controller.py"   "${LIBDIR}/controller.py"
sudo install -Dm644 "${REPO}/daemon/nvml_backend.py" "${LIBDIR}/nvml_backend.py"

echo "==> Installing D-Bus system policy"
sudo install -Dm644 "${REPO}/daemon/org.bruno.GpuPowerMode.conf" \
    /etc/dbus-1/system.d/org.bruno.GpuPowerMode.conf

echo "==> Installing systemd service"
sudo install -Dm644 "${REPO}/daemon/gpupowerd.service" \
    /etc/systemd/system/gpupowerd.service
sudo systemctl daemon-reload
sudo systemctl enable --now gpupowerd.service

echo "==> Installing GNOME extension to ${EXTDIR}"
mkdir -p "${EXTDIR}"
cp "${REPO}/extension/extension.js" "${REPO}/extension/metadata.json" \
   "${REPO}/extension/stylesheet.css" "${EXTDIR}/"

echo
echo "Done. The daemon is running. To load the extension on Wayland, log out"
echo "and back in, then enable it:"
echo "  gnome-extensions enable ${UUID}"
