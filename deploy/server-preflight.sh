#!/usr/bin/env bash
# Run ON THE SERVER (over SSH) BEFORE installing anything. Read-only checks.
#   bash server-preflight.sh
# Send the full output back to the developer if anything says FAIL / WARN.
set -u
ok(){ printf "  [ OK ] %s\n" "$*"; }
warn(){ printf "  [WARN] %s\n" "$*"; }
fail(){ printf "  [FAIL] %s\n" "$*"; }
echo "== System"
. /etc/os-release 2>/dev/null && echo "  OS: $PRETTY_NAME"
case "${ID:-}-${VERSION_ID:-}" in
  ubuntu-22.04|ubuntu-24.04|debian-12) ok "supported OS";;
  *) warn "recommended: Ubuntu 22.04 / 24.04 LTS (x86-64)";;
esac
arch=$(uname -m); [ "$arch" = "x86_64" ] && ok "CPU arch $arch" || warn "CPU arch is $arch (images are built for linux/amd64)"
virt=$(systemd-detect-virt 2>/dev/null || echo unknown); echo "  virtualization: $virt"
case "$virt" in openvz|lxc|lxc-libvirt) fail "container-based VPS ($virt): Docker usually does NOT work — ask for a KVM VM";; *) ok "virtualization '$virt' is fine for Docker";; esac
cpus=$(nproc); [ "$cpus" -ge 4 ] && ok "CPU cores: $cpus" || warn "CPU cores: $cpus (4+ recommended)"
mem=$(awk '/MemTotal/{printf "%d",$2/1024/1024}' /proc/meminfo); [ "$mem" -ge 7 ] && ok "RAM: ~${mem} GB" || warn "RAM: ~${mem} GB (8+ recommended)"
free=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free" -ge 40 ] && ok "free disk on /: ${free} GB" || warn "free disk on /: ${free} GB (40+ recommended)"
echo "== Software"
command -v docker >/dev/null && ok "docker: $(docker --version)" || warn "docker not installed (deploy/install-docker-ubuntu.sh will install it)"
docker compose version >/dev/null 2>&1 && ok "compose plugin present" || warn "docker compose plugin missing"
echo "== Network (outbound)"
for u in https://registry-1.docker.io/v2/ https://download.docker.com https://archive.ubuntu.com https://pypi.org https://registry.npmjs.org https://github.com; do
  code=$(curl -s -o /dev/null -m 8 -w "%{http_code}" "$u" 2>/dev/null)
  [ "$code" != "000" ] && ok "$u reachable (HTTP $code)" || warn "$u NOT reachable -> use the offline image route"
done
echo "== Ports in use"
for p in 80 443 8080; do (ss -ltn 2>/dev/null | grep -q ":$p ") && warn "port $p already in use" || ok "port $p free"; done
echo "== Time"
timedatectl 2>/dev/null | grep -E "Time zone|synchronized" | sed 's/^/  /'
