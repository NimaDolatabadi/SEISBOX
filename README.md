# SEISBOX

**A Python seismology workstation on an Android phone.** It runs in Termux, with no root.

SEISBOX gives you a full Python 3.12 scientific and seismology stack on your phone:
ObsPy, Pyrocko, OpenQuake Engine, MSNoise, PyGMT (with GMT 6.5), GeoPandas, hvsrpy, NumPy, SciPy,
pandas, numba and more. You also get plots in the terminal, real plot windows through
Termux:X11, and a live seismogram viewer.

```
geo                 # enter the Python environment
python my_script.py # use obspy, pygmt, openquake ... as on a PC
seislive IU.ANMO.00.BHZ --filter 0.5 5   # live waveforms from EarthScope SeedLink
```

---

## Contents

1. [How it works](#1-how-it-works)
2. [Requirements](#2-requirements)
3. [Install from zero (quick)](#3-install-from-zero-quick)
4. [Install from zero (step by step, manual)](#4-install-from-zero-step-by-step-manual)
5. [Daily use](#5-daily-use)
6. [Plotting: terminal, X11 windows, files](#6-plotting)
7. [Included tools](#7-included-tools)
8. [Repository layout](#8-repository-layout)
9. [Updating, backup, uninstall, offline bundle](#9-updating-backup-uninstall)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. How it works

```
Android
 └─ Termux app              (Linux userland, Android libc "Bionic")
     ├─ termux-x11          (X server → shows windows in the Termux:X11 app)
     ├─ aliases: geo, ubx, gpy, seislive
     └─ proot-distro
         └─ Ubuntu 24.04    (normal glibc Linux, runs without root via proot)
             ├─ apt: python3.12, GMT 6.5, GDAL 3.8, Tk, compilers
             └─ /root/geo   ← Python venv with all science packages
```

**Why not just use Termux's own Python?**

* Termux only ships the newest Python (3.14 at the time of writing). OpenQuake, numba and
  others need 3.12.
* Termux uses Android's C library (Bionic), not glibc. The ready-made Linux wheels on PyPI
  (`manylinux_aarch64`) only work on glibc. In Termux, NumPy, SciPy, numba, Shapely, pyproj and
  other packages would all have to be **compiled from source**, which takes hours, often
  fails, and can break on Termux updates.
* GMT, which PyGMT needs, is not packaged for Termux.

Inside Ubuntu, `pip install` downloads prebuilt wheels and `apt install gmt` simply works.
proot is **not** a virtual machine: code runs at native CPU speed. Only heavy file I/O is
somewhat slower. The cost is about 3–5 GB of storage.

`/sdcard` (your phone's shared storage) is visible inside Ubuntu at the same path. You
can edit scripts with any Android editor and run them in `geo`.

---

## 2. Requirements

| Item | Notes |
|---|---|
| Android 7+ phone, **64-bit ARM (aarch64)** | Almost every phone from the last 7 years |
| **~5 GB free** internal storage | Ubuntu, compilers, Python packages |
| Internet | ~1.5 GB of downloads during install |
| **Termux** app | From **F-Droid** or **GitHub**, *not* Google Play (the Play version is outdated) |
| **Termux:X11** app (optional) | Only for plot windows and `seislive` |
| 30–90 minutes | Mostly pip downloading/compiling (pyrocko builds from source) |

Download links:

* Termux: <https://f-droid.org/packages/com.termux/> or <https://github.com/termux/termux-app/releases>
  (pick `termux-app_*_arm64-v8a.apk`)
* Termux:X11: <https://github.com/termux/termux-x11/releases> (download the `app-arm64-v8a-debug.apk` from the *nightly* release)

> Install all Termux apps from the **same source** (all GitHub or all F-Droid). Mixing them
> gives a signature error.

---

## 3. Install from zero (quick)

1. Install the **Termux** app (and optionally **Termux:X11**) from the links above. Open Termux.
2. Paste:

   ```bash
   pkg update -y && pkg install -y git
   git clone https://github.com/NimaDolatabadi/SEISBOX ~/SEISBOX
   bash ~/SEISBOX/install.sh
   ```

3. Tap **Allow** when Android asks for storage permission.
4. Wait. It ends with a self-test that prints `ok` for each package and `All good.`
5. Close Termux completely (swipe it away, or type `exit`) and open it again. You will see the
   SEISBOX welcome screen.

Keep the screen on, or keep Termux in the foreground, during the install. Android may pause
background apps. You can also pull down the Termux notification and tap **Acquire wakelock**.

**Install options**, set before `bash install.sh`:

```bash
SEISBOX_PY=latest bash ~/SEISBOX/install.sh        # newest package versions instead of the tested lock
SEISBOX_PROJECTS=/sdcard/Documents/seis bash ~/SEISBOX/install.sh   # different work folder
```

The default (`lock`) installs exactly the versions in `requirements-lock.txt`, which are known to
work together. `install.sh` is safe to run again: finished steps are skipped.

---

## 4. Install from zero (step by step, manual)

This is exactly what `install.sh` does, so you can understand it, repeat it or fix one step.

### 4.1 Termux base

```bash
pkg update -y && pkg upgrade -y
pkg install -y proot-distro git curl wget chafa gnuplot x11-repo
pkg install -y termux-x11-nightly          # X server for plot windows (needs x11-repo)
termux-setup-storage                       # tap "Allow" → gives Termux /sdcard access
mkdir -p /sdcard/termux/projects           # your work folder
```

| Package | Why |
|---|---|
| `proot-distro` | Installs and runs the Ubuntu container without root |
| `git`, `curl`, `wget` | Downloading |
| `chafa` | Draws images as text characters (terminal plots) |
| `gnuplot` | Optional quick plotting in Termux itself |
| `x11-repo`, `termux-x11-nightly` | X11 server that shows Linux windows in the Termux:X11 app |

### 4.2 Ubuntu 24.04 container

```bash
proot-distro install --name ubuntu ubuntu:24.04
proot-distro login ubuntu          # you are now root@localhost inside Ubuntu
```

The version is pinned to **24.04** on purpose: it ships Python 3.12 and GDAL 3.8.4, which this
stack is tested with. Its files live in
`$PREFIX/var/lib/proot-distro/containers/ubuntu/rootfs`.

> Never put the container or the venv on `/sdcard`. Shared storage does not allow executables
> or symlinks.

### 4.3 System packages inside Ubuntu

Run these as root inside Ubuntu (`proot-distro login ubuntu`):

```bash
apt-get update
apt-get install -y \
  python3 python3-venv python3-dev python3-pip python3-tk \
  build-essential gfortran pkg-config git curl ca-certificates \
  gmt gmt-dcw gmt-gshhg libgmt-dev ghostscript \
  libgdal-dev gdal-bin \
  chafa x11-utils
```

| Package | Why |
|---|---|
| `python3*` | Python 3.12 + venv + headers |
| `python3-tk` | Tk backend so matplotlib can open windows on X11 |
| `build-essential`, `gfortran`, `pkg-config` | Compile packages that have no ARM wheel (pyrocko, GDAL bindings) |
| `gmt gmt-dcw gmt-gshhg libgmt-dev ghostscript` | GMT 6.5 with coastlines/borders, required by PyGMT |
| `libgdal-dev gdal-bin` | GDAL library for the `osgeo.gdal` bindings (OpenQuake, rasters) |
| `chafa` | Terminal image display used by `tplot` |

### 4.4 The `geo` Python venv

```bash
python3 -m venv /root/geo
/root/geo/bin/pip install -U pip setuptools wheel

# GDAL's Python bindings must match the system GDAL exactly (3.8.4)
/root/geo/bin/pip install numpy==2.2.6
/root/geo/bin/pip install --no-build-isolation gdal==$(gdal-config --version)

# Everything else, exact versions (repo copied/bound at /opt/seisbox)
/root/geo/bin/pip install --no-deps -r /opt/seisbox/requirements-lock.txt
```

`--no-deps` is used because OpenQuake declares `gdal~=3.13`, but Ubuntu 24.04 has GDAL 3.8.4.
The lock file already lists every dependency, so pip doesn't need to resolve anything. OpenQuake
works with 3.8.4. `pip check` will report this mismatch; that is expected. If a raster
input to OpenQuake ever fails, this is the first thing to suspect.

Notable pins:

* `numpy==2.2.6`, `numba==0.61.2`: numba only supports specific NumPy versions.
* `plotext==5.3.2`: version 6 removed the `plt.plot()` style API.
* `setuptools<81`: MSNoise 1.6.5 still imports `pkg_resources`, which setuptools 81 removed.
  You may see a harmless `pkg_resources is deprecated` warning when running `msnoise`.

### 4.5 Terminal plotting helper (`tplot`)

```bash
cp /opt/seisbox/ubuntu/tplot.py /root/geo/lib/python3.12/site-packages/
```

### 4.6 `geo` shell startup file

```bash
cp /opt/seisbox/ubuntu/geo_rc /root/.geo_rc
```

It loads the normal `.bashrc` and activates the venv. When an X11 display is present (`ubx`),
it also sets matplotlib to the Tk backend.

### 4.7 Termux side: shortcuts and welcome screen

Back in Termux (`exit` out of Ubuntu):

```bash
install -m 755 ~/SEISBOX/termux/bin/seislive $PREFIX/bin/
cp ~/SEISBOX/termux/seisbox.bashrc ~/.seisbox.bashrc
echo '[ -f ~/.seisbox.bashrc ] && . ~/.seisbox.bashrc' >> ~/.bashrc
cp ~/SEISBOX/termux/welcome.txt ~/.termux_welcome
cp ~/SEISBOX/termux/gnuplot ~/.gnuplot
touch ~/.hushlogin
cp -rn ~/SEISBOX/projects/. /sdcard/termux/projects/
source ~/.bashrc
```

---

## 5. Daily use

All commands are typed in **Termux**:

| Command | What it does |
|---|---|
| `geo` | Opens an Ubuntu shell with the venv active, so `python` means Python 3.12 + all packages. `exit` returns to Termux. |
| `ubx` | Same as `geo`, plus it starts the X server and sets `DISPLAY=:0`. Matplotlib windows open in the Termux:X11 app. |
| `gpy script.py` | Runs one script with the geo Python without opening a shell. Use full paths, e.g. `gpy /sdcard/termux/projects/x.py`. |
| `seislive ...` | Live waveform viewer (see below). |
| `welcome` | Shows the command list again. |

Typical session:

```bash
geo
cd /sdcard/termux/projects
python my_analysis.py
ipython                       # interactive
exit
```

Example (ObsPy):

```python
from obspy.clients.fdsn import Client
from obspy import UTCDateTime
import tplot, matplotlib.pyplot as plt

st = Client("EARTHSCOPE").get_waveforms("IU", "ANMO", "00", "BHZ",
                                        UTCDateTime() - 3600, UTCDateTime() - 3000)
st.filter("bandpass", freqmin=0.5, freqmax=5)
st.plot(show=False); plt.show()          # drawn right in the terminal
```

---

## 6. Plotting

There are three ways to see plots:

1. **In the terminal (`tplot`)**: add `import tplot` at the top of a script. After that,
   `plt.show()` renders the figure with `chafa` as colored characters. Use
   `plt.show(size="80x25")` to choose the size. Try `python /sdcard/termux/projects/tplot_demo.py`.
   Zoom out in Termux (pinch) for more detail.
2. **Real windows (`ubx`)**: open the Termux:X11 app once, then run `ubx` in Termux. Matplotlib
   uses TkAgg, and windows appear in Termux:X11 with zoom and pan. Switch back to Termux with
   the Android app switcher.
3. **Files**: `plt.savefig("/sdcard/termux/projects/fig.png", dpi=200)` and open it in the gallery.
   PyGMT: `fig.savefig("/sdcard/.../map.png")`.

`plotext` (5.3.2) is also installed for pure-text line plots.

---

## 7. Included tools

Copied to your work folder (`/sdcard/termux/projects`) on install.

### `seislive`: live seismograms

Streams real-time data from the EarthScope (IRIS) SeedLink server and draws a scrolling
plot in Termux:X11. It is fast enough for phones: it uses ring buffers, stateful causal filtering
and pixel-column min/max decimation.

```bash
seislive                                        # default: IU.ANMO.00.BHZ, 10 min
seislive IU.ANMO.00.BHZ IU.COLA.00.BHZ --minutes 10 --filter 0.5 5
```

### `irsc_bulletin`: Iranian Seismological Center catalogue

IRSC has no FDSN service, but it reports to the ISC as agency `TEH`. This tool queries the ISC
and keeps the IRSC origins and magnitudes, then writes a CSV.

```bash
geo
cd /sdcard/termux/projects/irsc_bulletin
python irsc_bulletin.py --start 2024-06-01 --end 2024-07-01
python irsc_bulletin.py --start 2024-01-01 --lat 35.7 --lon 51.4 --radius 2
python irsc_tui.py            # full-screen form (curses)
```

### MSNoise: ambient-noise monitoring (dv/v)

MSNoise 1.6.5 is installed with a SQLite database backend (no MySQL server needed). Each project
is a folder holding its `db.ini` and database:

```bash
geo
mkdir -p /sdcard/termux/projects/noise && cd /sdcard/termux/projects/noise
msnoise db init                 # choose 1 (sqlite), then accept defaults
msnoise config set data_folder=/sdcard/termux/projects/noise/SDS
msnoise config set data_structure=SDS
msnoise populate                # fill the station table from the archive
msnoise scan_archive --init
msnoise new_jobs --init
msnoise compute_cc              # cross-correlations
msnoise info                    # status of config and jobs
```

`msnoise admin` starts the web configuration page. Open the printed `http://localhost:5000`
address in your phone's browser.

Ambient-noise processing is heavy. On a phone, start with a few stations and days, and keep
Termux in the foreground (or use **Acquire wakelock**).

---

## 8. Repository layout

```
SEISBOX/
├── install.sh                  # run in Termux: does everything (online)
├── seisbox-pack.sh             # make an offline bundle of this phone's setup
├── seisbox-restore.sh          # install that bundle on another phone
├── requirements-lock.txt       # exact tested versions (default)
├── requirements.txt            # main packages, unpinned (SEISBOX_PY=latest)
├── ubuntu/
│   ├── setup.sh                # runs inside Ubuntu: apt + venv + pip + self-test
│   ├── geo_rc                  # → /root/.geo_rc
│   └── tplot.py                # → venv site-packages
├── termux/
│   ├── seisbox.bashrc          # → ~/.seisbox.bashrc (aliases geo, ubx, gpy, welcome)
│   ├── welcome.txt             # → ~/.termux_welcome
│   ├── gnuplot                 # → ~/.gnuplot (braille terminal output)
│   └── bin/seislive            # → $PREFIX/bin/seislive
├── examples/tplot_demo.py
└── projects/
    ├── seis_live/seis_live.py
    └── irsc_bulletin/{irsc_bulletin.py, irsc_tui.py}
```

---

## 9. Updating, backup, uninstall

**Add a package**: `geo`, then `pip install <name>`.

**Update SEISBOX files**: `cd ~/SEISBOX && git pull && bash install.sh`.

**Back up the whole environment** (to restore later or move to another phone):

```bash
proot-distro backup ubuntu --output /sdcard/seisbox-ubuntu.tar.gz
proot-distro restore /sdcard/seisbox-ubuntu.tar.gz
```

### Offline bundle: copy your setup to other phones

No internet or compiling is needed on the other phone. Make the bundle on a phone where SEISBOX
already works:

```bash
bash ~/SEISBOX/seisbox-pack.sh            # → /sdcard/SEISBOX-bundle/  (~2–3 GB, 10–30 min)
```

The bundle folder contains:

| File | What |
|---|---|
| `Termux.apk`, `Termux-X11.apk`, `Termux-API.apk` | The apps, copied from your phone |
| `termux-prefix.tar.gz` | All Termux packages |
| `ubuntu.tar.gz` | Ubuntu 24.04 + the whole `geo` Python environment |
| `seisbox-repo.tar.gz` | This repo (shortcuts, welcome screen, projects) |
| `seisbox-restore.sh`, `README.txt`, `SHA256SUMS` | Installer, instructions, checksums |

These are **not** included: your Termux home folder, shell histories, pip caches,
Claude Code data and logins, SSH host keys (new ones are generated), temp files and logs.

Copy the folder to the new phone (USB cable, SD card, Google Drive, …), then on that phone:

1. Install `Termux.apk` (and `Termux-X11.apk`). Uninstall any Termux from Google Play first.
2. Open Termux and wait until the first setup finishes.
3. `termux-setup-storage` → **Allow**
4. `bash /sdcard/SEISBOX-bundle/seisbox-restore.sh`
5. Close and reopen Termux, then type `geo`.

The new phone must be 64-bit ARM (aarch64) and have about 6 GB free. The restore replaces that
phone's Termux packages and Ubuntu container. Its Termux home folder is kept.

The bundle is too large for git. Share it as a file, or attach it to a GitHub Release
(files must be < 2 GB each: `split -b 1900M ubuntu.tar.gz ubuntu.tar.gz.part-`, and
rejoin with `cat ubuntu.tar.gz.part-* > ubuntu.tar.gz`).

**Rebuild just the venv**:

```bash
proot-distro login ubuntu -- rm -rf /root/geo
bash ~/SEISBOX/install.sh
```

**Uninstall everything**:

```bash
proot-distro remove ubuntu
rm -f $PREFIX/bin/seislive ~/.seisbox.bashrc ~/.termux_welcome ~/.hushlogin
sed -i '/seisbox.bashrc/d' ~/.bashrc
```

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `[Process completed (signal 9)]` or Termux gets killed during long jobs | Android 12+ "phantom process killer". On Android 14+: Developer options → **Disable child process restrictions**. On Android 12–13, from a PC: `adb shell "/system/bin/device_config put activity_manager max_phantom_processes 2147483647"` |
| Install stops when the screen turns off | Termux notification → **Acquire wakelock**, then run `install.sh` again |
| `Permission denied` on `/sdcard` | Run `termux-setup-storage` and allow. On Android 11+ check App info → Permissions → Files → Allow all |
| `ubx` / `seislive` shows nothing | Open the Termux:X11 app. If it is stuck: `pkill -f termux-x11`, then run `ubx` again |
| `_tkinter` / `TclError: no display` | You are in `geo`, not `ubx`. Use `import tplot`, or start with `ubx` |
| pip fails building a package | Check that `build-essential python3-dev` are installed (step 4.3). Re-run `install.sh`; finished steps are skipped |
| `pip check` complains about `gdal` and `openquake-engine` | Expected (see 4.4), harmless |
| Termux app installs fail with a signature error | All Termux apps must come from the same source (GitHub *or* F-Droid) |
| `pkg` mirror errors | `termux-change-repo` and choose another mirror |

---

Built and used on Android 17 (aarch64) with Ubuntu 24.04.5 under proot-distro and Python 3.12.3.
