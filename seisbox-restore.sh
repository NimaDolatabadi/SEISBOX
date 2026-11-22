#!/data/data/com.termux/files/usr/bin/bash
# seisbox-restore.sh — install a SEISBOX offline bundle on a new phone.
# Run in a FRESH Termux (installed from the bundle's Termux.apk):
#
#   termux-setup-storage
#   bash /sdcard/SEISBOX-bundle/seisbox-restore.sh
#
# WARNING: replaces this phone's Termux packages ($PREFIX) and Ubuntu container
# with the bundle's. Your Termux home folder (~) is kept.
set -uo pipefail

B="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES=/data/data/com.termux/files
PROJECTS="${SEISBOX_PROJECTS:-/sdcard/termux/projects}"
say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*"; exit 1; }

[ -d "$FILES/usr" ] || die "Run this inside Termux."
[ "$(uname -m)" = aarch64 ] || die "This bundle is for 64-bit ARM (aarch64) phones; this one is $(uname -m)."
for f in termux-prefix.tar.gz ubuntu.tar.gz seisbox-repo.tar.gz; do
  [ -f "$B/$f" ] || die "Missing $B/$f — copy the whole bundle folder."
done

FREE_GB=$(( $(df -k "$FILES" | awk 'NR==2{print $4}') / 1024 / 1024 ))
[ "$FREE_GB" -ge 6 ] || die "Only ${FREE_GB} GB free; need about 6 GB."

if [ -f "$B/SHA256SUMS" ]; then
  say "Checking files (sha256)…"
  ( cd "$B" && sha256sum -c --quiet SHA256SUMS ) || die "Bundle files are damaged or incomplete — copy them again."
fi

if [ -d "$FILES/usr/var/lib/proot-distro/containers/ubuntu" ]; then
  printf 'An Ubuntu container already exists here and will be REPLACED. Continue? [y/N] '
  read -r a; [ "$a" = y ] || [ "$a" = Y ] || exit 1
fi

# Copy the archives into Termux's own storage first: after step 1 replaces the
# Termux packages, everything we need must already be unpacked or local.
WORK="$FILES/home/.seisbox-restore"; rm -rf "$WORK"; mkdir -p "$WORK"
tar -xzf "$B/seisbox-repo.tar.gz" -C "$WORK" || die "Cannot unpack seisbox-repo.tar.gz"

say "1/4  Termux packages (do not close Termux…)"
# Same method as Termux's own termux-restore. Files of running programs stay
# usable while being replaced, so this is safe from inside Termux.
tar -x -C "$FILES" -f "$B/termux-prefix.tar.gz" -z --recursive-unlink --preserve-permissions ./usr \
  || die "Restoring Termux packages failed."
hash -r
mkdir -p "$PREFIX/tmp" "$PREFIX/var/log"
command -v ssh-keygen >/dev/null && ssh-keygen -A >/dev/null 2>&1 || true   # new SSH host keys

say "2/4  Ubuntu + Python environment (several minutes)"
proot-distro restore "$B/ubuntu.tar.gz" || die "Restoring Ubuntu failed."
proot-distro login ubuntu -- true || die "Ubuntu does not start."

say "3/4  Shortcuts and welcome screen"
R="$WORK/SEISBOX"
cp "$R/termux/seisbox.bashrc" "$HOME/.seisbox.bashrc"
sed -i "s|^export SEISBOX_PROJECTS=.*|export SEISBOX_PROJECTS=\"$PROJECTS\"|" "$HOME/.seisbox.bashrc"
grep -qs 'seisbox.bashrc' "$HOME/.bashrc" || \
  printf '\n# SEISBOX\n[ -f ~/.seisbox.bashrc ] && . ~/.seisbox.bashrc\n' >> "$HOME/.bashrc"
[ -f "$HOME/.termux_welcome" ] || cp "$R/termux/welcome.txt" "$HOME/.termux_welcome"
[ -f "$HOME/.gnuplot" ] || cp "$R/termux/gnuplot" "$HOME/.gnuplot"
install -m 755 "$R/termux/bin/seislive" "$PREFIX/bin/seislive"
if [ -f "$B/termux.properties" ] && [ ! -f "$HOME/.termux/termux.properties" ]; then
  mkdir -p "$HOME/.termux"; cp "$B/termux.properties" "$HOME/.termux/"
  termux-reload-settings 2>/dev/null || true
fi
touch "$HOME/.hushlogin"
cp "$R/ubuntu/geo_rc" "$FILES/usr/var/lib/proot-distro/containers/ubuntu/rootfs/root/.geo_rc"
# keep a copy of the repo for docs / future updates
[ -d "$HOME/SEISBOX" ] || cp -r "$R" "$HOME/SEISBOX"

say "4/4  Work folder $PROJECTS"
if [ -w /sdcard ]; then
  mkdir -p "$PROJECTS"
  cp -rn "$R/projects/." "$PROJECTS/"; cp -n "$R/examples/"*.py "$PROJECTS/"
else
  echo "No /sdcard access — run termux-setup-storage, then copy ~/SEISBOX/projects yourself."
fi
rm -rf "$WORK"

say "Quick test"
proot-distro login ubuntu -- /root/geo/bin/python -W ignore -c \
  "import obspy, pyrocko, pygmt, geopandas, msnoise, openquake.engine, numba; print('All good: Python environment works.')" \
  || echo "Some packages failed to import — see the message above."

say "Done!"
echo "Close Termux completely (type: exit) and open it again, then type: geo"
