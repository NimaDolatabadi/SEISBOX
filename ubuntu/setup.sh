#!/bin/bash
# Runs INSIDE the Ubuntu 24.04 container (install.sh calls it).
# Builds the Python 3.12 venv /root/geo with the seismology / geo stack.
set -euo pipefail
SRC=/opt/seisbox          # repo, bind-mounted by install.sh
VENV=/root/geo
MODE="${SEISBOX_PY:-lock}"
export DEBIAN_FRONTEND=noninteractive

echo "--> apt packages (Python 3.12, compilers, GMT, GDAL, Tk, chafa)"
apt-get update
apt-get install -y \
  python3 python3-venv python3-dev python3-pip python3-tk \
  build-essential gfortran pkg-config git curl ca-certificates \
  gmt gmt-dcw gmt-gshhg libgmt-dev ghostscript \
  libgdal-dev gdal-bin \
  chafa x11-utils

echo "--> venv $VENV"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -U pip setuptools wheel

GDAL_VER="$(gdal-config --version)"   # 3.8.4 on Ubuntu 24.04
if [ "$MODE" = latest ]; then
  echo "--> pip: newest versions of main packages (GDAL bindings = $GDAL_VER)"
  "$VENV/bin/pip" install "gdal==$GDAL_VER" -r "$SRC/requirements.txt"
else
  echo "--> pip: exact tested versions (requirements-lock.txt)"
  # --no-deps: the lock file already lists every dependency, and OpenQuake
  # declares gdal~=3.13 while Ubuntu ships GDAL $GDAL_VER. Its Python bindings
  # must match the system library, so we keep $GDAL_VER (works fine in practice).
  sed "s/^gdal==.*/gdal==$GDAL_VER/I" "$SRC/requirements-lock.txt" > /tmp/seisbox-lock.txt
  # numpy must exist first: building the gdal bindings needs its headers
  "$VENV/bin/pip" install "$(grep -i '^numpy==' /tmp/seisbox-lock.txt)"
  "$VENV/bin/pip" install --no-build-isolation "gdal==$GDAL_VER"
  "$VENV/bin/pip" install --no-deps -r /tmp/seisbox-lock.txt
fi

echo "--> tplot (matplotlib plt.show() drawn in the terminal)"
SITE="$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
cp "$SRC/ubuntu/tplot.py" "$SITE/tplot.py"

echo "--> shell startup file for 'geo'"
cp "$SRC/ubuntu/geo_rc" /root/.geo_rc

echo "--> quick self-test"
"$VENV/bin/python" - <<'PY'
import importlib
mods = ["numpy", "scipy", "pandas", "matplotlib", "obspy", "pyrocko", "hvsrpy",
        "pygmt", "geopandas", "shapely", "pyproj", "trimesh", "numba",
        "openquake.engine", "osgeo.gdal", "tkinter", "tplot"]
bad = []
for m in mods:
    try:
        importlib.import_module(m); print(f"  ok   {m}")
    except Exception as e:
        bad.append(m); print(f"  FAIL {m}: {e}")
print("All good." if not bad else f"Problems with: {', '.join(bad)}")
PY
