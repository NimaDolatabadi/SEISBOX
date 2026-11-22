# SEISBOX shortcuts — installed as ~/.seisbox.bashrc and sourced from ~/.bashrc
export SEISBOX_PROJECTS="/sdcard/termux/projects"

# geo: Ubuntu shell with the Python 3.12 venv active (terminal plots via tplot)
alias geo='proot-distro login ubuntu -- bash --rcfile /root/.geo_rc'

# ubx: same as geo, plus X11 display :0 so matplotlib opens real windows
#      in the Termux:X11 app (starts the X server if it is not running)
alias ubx='[ -S $PREFIX/tmp/.X11-unix/X0 ] || { pkill -f "^termux-x11 com.termux.x11"; XDG_RUNTIME_DIR=$PREFIX/tmp termux-x11 :0 >/dev/null 2>&1 & sleep 2; }; am start -n com.termux.x11/.MainActivity >/dev/null 2>&1; proot-distro login ubuntu --shared-tmp --env DISPLAY=:0 -- bash --rcfile /root/.geo_rc'

# gpy: run one script with the geo Python without entering the shell
#      e.g.  gpy /sdcard/termux/projects/myscript.py
alias gpy='proot-distro login ubuntu -- /root/geo/bin/python'

# welcome screen
alias welcome='cat ~/.termux_welcome'
[[ $- == *i* && $SHLVL -le 1 && -f ~/.termux_welcome ]] && cat ~/.termux_welcome
