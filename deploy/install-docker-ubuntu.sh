#!/usr/bin/env bash
# Installs Docker Engine + Compose plugin on Ubuntu 22.04/24.04 (needs internet) and a basic firewall.
#   sudo bash install-docker-ubuntu.sh [--firewall]
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
. /etc/os-release
[ "$ID" = "ubuntu" ] || { echo "this script is for Ubuntu (found $ID)"; exit 1; }
apt-get update -y
apt-get install -y ca-certificates curl gnupg ufw
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
# let the login user run docker without sudo (log out/in once)
[ -n "${SUDO_USER:-}" ] && usermod -aG docker "$SUDO_USER" || true
# log rotation for ALL containers (safety net on top of compose settings)
mkdir -p /etc/docker
[ -f /etc/docker/daemon.json ] || cat > /etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
JSON
systemctl restart docker
if [ "${1:-}" = "--firewall" ]; then
  ufw allow OpenSSH
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw allow 8080/tcp      # remove this line if you serve only via HTTPS (80/443)
  ufw --force enable
  ufw status
fi
docker --version && docker compose version
echo "OK. Log out and back in (docker group), then run:  docker run --rm hello-world"
