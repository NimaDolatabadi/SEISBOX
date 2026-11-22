#!/data/data/com.termux/files/usr/bin/bash
# SEISBOX installer — run inside Termux (not inside Ubuntu).
#
#   pkg install -y git && git clone https://github.com/NimaDolatabadi/SEISBOX ~/SEISBOX
#   bash ~/SEISBOX/install.sh
#
# Safe to re-run: every step skips what is already done.
# Options (environment variables):
#   SEISBOX_PY=lock    (default) install the exact tested package versions
#   SEISBOX_PY=latest  install the newest versions of the main packages instead
#   SEISBOX_PROJECTS=/sdcard/termux/projects   where your scripts/data live
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISTRO=ubuntu
IMAGE=ubuntu:24.04
PROJECTS="${SEISBOX_PROJECTS:-/sdcard/termux/projects}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

[ -n "${PREFIX:-}" ] && [ -d /data/data/com.termux ] || { echo "Run this in Termux."; exit 1; }
[ "$(uname -m)" = aarch64 ] || echo "Warning: tested only on aarch64 (64-bit ARM)."

say "1/6  Updating Termux packages"
pkg update -y -o Dpkg::Options::=--force-confnew
pkg upgrade -y -o Dpkg::Options::=--force-confnew

say "2/6  Installing Termux packages"
pkg install -y proot-distro git curl wget chafa gnuplot python x11-repo
pkg install -y termux-x11-nightly

say "3/6  Shared storage (/sdcard)"
if [ ! -w /sdcard ]; then
  echo "Android will ask for storage permission — tap Allow."
  termux-setup-storage
  for i in $(seq 1 30); do [ -w /sdcard ] && break; sleep 1; done
fi
mkdir -p "$PROJECTS"

say "4/6  Ubuntu 24.04 container ($DISTRO)"
if proot-distro login "$DISTRO" -- true 2>/dev/null; then
  echo "Container '$DISTRO' already installed — reusing it."
else
  proot-distro install --name "$DISTRO" "$IMAGE"
fi

say "5/6  Python 3.12 'geo' environment inside Ubuntu (slow: 20-60 min)"
proot-distro login "$DISTRO" --bind "$REPO:/opt/seisbox" \
  --env SEISBOX_PY="${SEISBOX_PY:-lock}" -- bash /opt/seisbox/ubuntu/setup.sh

say "6/6  Termux shortcuts, welcome screen, example projects"
install -m 755 "$REPO/termux/bin/seislive" "$PREFIX/bin/seislive"
install -m 755 "$REPO/termux/bin/Events" "$PREFIX/bin/Events"
ln -sf Events "$PREFIX/bin/events"
cp "$REPO/termux/seisbox.bashrc" "$HOME/.seisbox.bashrc"
sed -i "s|^export SEISBOX_PROJECTS=.*|export SEISBOX_PROJECTS=\"$PROJECTS\"|" "$HOME/.seisbox.bashrc"
grep -qs 'seisbox.bashrc' "$HOME/.bashrc" || \
  printf '\n# SEISBOX\n[ -f ~/.seisbox.bashrc ] && . ~/.seisbox.bashrc\n' >> "$HOME/.bashrc"
[ -f "$HOME/.termux_welcome" ] || cp "$REPO/termux/welcome.txt" "$HOME/.termux_welcome"
[ -f "$HOME/.gnuplot" ] || cp "$REPO/termux/gnuplot" "$HOME/.gnuplot"
touch "$HOME/.hushlogin"   # hide default Termux MOTD; our welcome replaces it
# copy example projects without overwriting your own edits
cp -rn "$REPO/projects/." "$PROJECTS/"
cp -n "$REPO/examples/"*.py "$PROJECTS/"

say "Done!"
cat <<EOF
Close Termux completely and open it again (or run: source ~/.bashrc).
Then try:
  geo                        Ubuntu shell with Python 3.12 + all packages
  python $PROJECTS/tplot_demo.py     (inside geo) plot in the terminal
  seislive IU.ANMO.00.BHZ    live seismogram (needs the Termux:X11 app)
  Events                     latest earthquakes worldwide (filter by source, region, magnitude)
  welcome                    show the command list
EOF
