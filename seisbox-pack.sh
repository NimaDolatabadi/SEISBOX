#!/data/data/com.termux/files/usr/bin/bash
# seisbox-pack.sh — make an OFFLINE bundle of this phone's SEISBOX setup,
# to install on other phones with seisbox-restore.sh (no internet, no compiling).
#
#   bash ~/SEISBOX/seisbox-pack.sh [OUTPUT_DIR]        (default /sdcard/SEISBOX-bundle)
#
# Bundle contents:
#   Termux.apk, Termux-X11.apk, Termux-API.apk   apps copied from this phone (if installed)
#   termux-prefix.tar.gz    Termux packages ($PREFIX), without the Ubuntu container
#   ubuntu.tar.gz           Ubuntu 24.04 container incl. the geo Python venv
#   seisbox-repo.tar.gz     this repo (shortcuts, welcome screen, projects)
#   seisbox-restore.sh      run this on the new phone
#   SHA256SUMS, README.txt
#
# Personal data is NOT included: your Termux home folder, shell histories,
# pip caches, Claude Code data/logins, SSH host keys, temp files and logs.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-/sdcard/SEISBOX-bundle}"
FILES=/data/data/com.termux/files
CONTAINERS="$PREFIX/var/lib/proot-distro/containers"
say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

[ -d "$CONTAINERS/ubuntu/rootfs" ] || { echo "No Ubuntu container found — run install.sh first."; exit 1; }
if proot-distro ps 2>/dev/null | grep -q ubuntu; then
  echo "Ubuntu is in use (geo/ubx/seislive open somewhere). Exit those sessions first."; exit 1
fi
command -v pigz >/dev/null || pkg install -y pigz || true
GZ="$(command -v pigz || command -v gzip)"

mkdir -p "$OUT"
NEED=$(( $(du -sk "$CONTAINERS/ubuntu" | cut -f1) / 1024 / 1024 + 2 ))
echo "Output: $OUT  (needs roughly ${NEED} GB free there)"

say "1/5  Apps (APKs)"
for p in com.termux:Termux com.termux.x11:Termux-X11 com.termux.api:Termux-API; do
  apk="$(pm path "${p%%:*}" 2>/dev/null | sed -n 's/^package://p' | grep base.apk || true)"
  if [ -n "$apk" ]; then cp "$apk" "$OUT/${p#*:}.apk"; echo "  ${p#*:}.apk"; else echo "  ${p#*:}: not installed, skipped"; fi
done

say "2/5  Termux packages → termux-prefix.tar.gz"
tar -c -C "$FILES" \
  --exclude='./usr/var/lib/proot-distro' \
  --exclude='./usr/tmp/?*' \
  --exclude='./usr/var/log/?*' \
  --exclude='./usr/var/cache/apt/archives/*.deb' \
  --exclude='./usr/etc/ssh/ssh_host_*' \
  ./usr | "$GZ" > "$OUT/termux-prefix.tar.gz"

say "3/5  Ubuntu + geo venv → ubuntu.tar.gz (the big one)"
# same layout as `proot-distro backup` (ubuntu/manifest.json + ubuntu/rootfs/)
tar -c -C "$CONTAINERS" --owner=0 --group=0 --numeric-owner \
  --exclude='ubuntu/rootfs/root/.cache' \
  --exclude='ubuntu/rootfs/root/.claude' \
  --exclude='ubuntu/rootfs/root/.claude.json' \
  --exclude='ubuntu/rootfs/root/.bash_history' \
  --exclude='ubuntu/rootfs/root/.python_history' \
  --exclude='ubuntu/rootfs/root/.lesshst' \
  --exclude='ubuntu/rootfs/tmp/?*' \
  --exclude='ubuntu/rootfs/var/tmp/?*' \
  --exclude='ubuntu/rootfs/var/lib/apt/lists/?*' \
  --exclude='ubuntu/rootfs/var/cache/apt/*.bin' \
  --exclude='ubuntu/rootfs/var/cache/apt/archives/*.deb' \
  --exclude='ubuntu/rootfs/var/log/?*' \
  ubuntu/manifest.json ubuntu/rootfs | "$GZ" > "$OUT/ubuntu.tar.gz"
# (no bare "ubuntu/" entry: proot-distro restore rejects archives that have one)

say "4/5  SEISBOX repo + restore script"
if git -C "$REPO" rev-parse HEAD >/dev/null 2>&1; then
  git -C "$REPO" archive --format=tar --prefix=SEISBOX/ HEAD | "$GZ" > "$OUT/seisbox-repo.tar.gz"
else
  tar -c -C "$(dirname "$REPO")" --exclude=.git "$(basename "$REPO")" | "$GZ" > "$OUT/seisbox-repo.tar.gz"
fi
cp "$REPO/seisbox-restore.sh" "$OUT/"
cp "$HOME/.termux/termux.properties" "$OUT/termux.properties" 2>/dev/null || true

cat > "$OUT/README.txt" <<'EOF'
SEISBOX offline bundle — Python seismology workstation for Android (aarch64)

On the NEW phone:
 1. Install Termux.apk (and Termux-X11.apk for plot windows, Termux-API.apk optional).
    Android may ask to allow installing from this source — allow it.
 2. Open Termux once, wait for "Installing bootstrap packages" to finish.
 3. Run:  termux-setup-storage      (tap Allow)
 4. Run:  bash /sdcard/SEISBOX-bundle/seisbox-restore.sh
    (change the path if you copied the folder somewhere else)
 5. Close Termux completely and open it again. Type: geo

Needs ~6 GB free internal storage. Full docs: https://github.com/NimaDolatabadi/SEISBOX
EOF

say "5/5  Checksums"
( cd "$OUT" && sha256sum *.apk *.tar.gz seisbox-restore.sh > SHA256SUMS 2>/dev/null || sha256sum *.tar.gz seisbox-restore.sh > SHA256SUMS )

say "Bundle ready: $OUT"
ls -lh "$OUT"
echo
echo "Copy the whole folder to the other phone (USB, SD card, Google Drive...)"
echo "and follow README.txt inside it."
