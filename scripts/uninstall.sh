#!/usr/bin/env bash
# Remove the daemon, system files and the GNOME extension.
# The GPU keeps whatever power limit was last applied; reset it manually
# with `sudo nvidia-smi -pl <default>` if you want the stock limit back.
set -euo pipefail

UUID=gpu-power-mode@bruno
EXTDIR="${HOME}/.local/share/gnome-shell/extensions/${UUID}"

echo "==> Disabling extension"
gnome-extensions disable "${UUID}" 2>/dev/null || true
rm -rf "${EXTDIR}"

echo "==> Stopping and removing the daemon"
sudo systemctl disable --now gpupowerd.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/gpupowerd.service
sudo rm -f /etc/dbus-1/system.d/org.bruno.GpuPowerMode.conf
sudo rm -rf /usr/local/lib/gpu-power-mode
sudo rm -rf /var/lib/gpu-power-mode
sudo systemctl daemon-reload

echo "Done. Log out and back in to fully unload the extension."
