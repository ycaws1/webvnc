rm -rf /tmp/.X*-lock /tmp/.X11-unix
mkdir -p /root/.vnc
echo 'password' | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
vncserver :1 -geometry 1280x800 -depth 24
# /usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 6080
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 8000