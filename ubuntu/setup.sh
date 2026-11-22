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

# The lock file is tested with Python 3.12 (Ubuntu 24.04's python3). Newer Ubuntu releases
# ship a newer Python (26.04: 3.14), so fetch a standalone Python 3.12 with uv there.
PY=python3
if ! python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
  echo "--> system Python is $(python3 -V 2>&1 | cut -d' ' -f2); installing Python 3.12 with uv"
  # uv from PyPI in its own small venv (no installer script piped into a shell)
  [ -x /opt/uv/bin/uv ] || { python3 -m venv /opt/uv && /opt/uv/bin/pip install -q uv; }
  /opt/uv/bin/uv python install 3.12
  PY="$(/opt/uv/bin/uv python find 3.12)"
fi

echo "--> venv $VENV (Python $("$PY" -V 2>&1 | cut -d' ' -f2))"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
# setuptools<81: MSNoise 1.6 still imports pkg_resources (removed in 81)
"$VENV/bin/pip" install -U pip "setuptools<81" wheel

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

echo "--> MSNoise: SQLAlchemy 2 compatibility shim"
if "$VENV/bin/python" -c "import msnoise" 2>/dev/null; then
  MSN="$SITE/msnoise"
  cp "$SRC/ubuntu/msnoise_sa2_compat.py" "$MSN/_sa2_compat.py"
  grep -q "_sa2_compat" "$MSN/__init__.py" || \
    sed -i '1i from . import _sa2_compat  # noqa: F401  (SEISBOX: SQLAlchemy 2 support)' "$MSN/__init__.py"
fi

echo "--> OpenQuake: accept read-only arrays in idx_start_stop (numba)"
OQP="$SITE/openquake/baselib/performance.py"
if [ -f "$OQP" ] && ! grep -q "SEISBOX patch" "$OQP"; then
  cat "$SRC/ubuntu/openquake_readonly_fix.py" >> "$OQP"
fi

echo "--> quakemt (focal mechanisms / moment-tensor inversion)"
install -m 755 "$SRC/ubuntu/quakemt.py" "$VENV/bin/quakemt"
install -m 755 "$SRC/ubuntu/imgview.py" "$VENV/bin/imgview"   # used by seisview

echo "--> shell startup file for 'geo'"
cp "$SRC/ubuntu/geo_rc" /root/.geo_rc

echo "--> quick self-test"
"$VENV/bin/python" - <<'PY'
import importlib
mods = ["numpy", "scipy", "pandas", "matplotlib", "obspy", "pyrocko", "hvsrpy",
        "pygmt", "geopandas", "msnoise", "shapely", "pyproj", "trimesh", "numba",
        "openquake.engine", "osgeo.gdal", "tkinter", "tplot"]
bad = []
for m in mods:
    try:
        importlib.import_module(m); print(f"  ok   {m}")
    except Exception as e:
        bad.append(m); print(f"  FAIL {m}: {e}")
print("All good." if not bad else f"Problems with: {', '.join(bad)}")
PY
