FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Install Desktop, VNC, and Python dependencies
RUN apt-get update && apt-get install -y \
    xfce4 xfce4-goodies \
    xfce4-terminal \
    xterm \
    tightvncserver novnc websockify \
    python3 python3-pip \
    && apt-get clean

# Install Playwright system dependencies
# RUN pip3 install playwright playwright-stealth
# RUN playwright install-deps chromium
# RUN playwright install chromium

COPY main.py /root/
COPY install.sh /root/

ENV USER=root
ENV HOME=/root
ENV DISPLAY=:1

EXPOSE 6080 5901 8000

# Ensure XFCE and a terminal start with VNC
# RUN echo "#!/bin/bash\n\
# rm -rf /tmp/.X*-lock /tmp/.X11-unix\n\
# mkdir -p /root/.vnc\n\
# echo 'password' | vncpasswd -f > /root/.vnc/passwd\n\
# chmod 600 /root/.vnc/passwd\n\
# echo 'startxfce4 &' > /root/.vnc/xstartup\n\
# chmod +x /root/.vnc/xstartup\n\
# vncserver :1 -geometry 1280x800 -depth 24\n\
# # Redirect root to vnc.html for convenience\n\
# ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html\n\
# /usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 8000" > /entrypoint.sh
RUN echo "#!/bin/bash\n\
rm -rf /tmp/.X*-lock /tmp/.X11-unix\n\
mkdir -p /root/.vnc\n\
echo 'password' | vncpasswd -f > /root/.vnc/passwd\n\
chmod 600 /root/.vnc/passwd\n\
echo '#!/bin/bash\n\
xrdb \$HOME/.Xresources\n\
startxfce4 &\n\
# Wait for desktop to load\n\
sleep 5\n\
# Run install script in a terminal\n\
xfce4-terminal -e \"bash -c 'cd /root && bash install.sh; exec bash'\" &\n\
' > /root/.vnc/xstartup\n\
chmod +x /root/.vnc/xstartup\n\
vncserver :1 -geometry 1280x800 -depth 24\n\
ln -s /usr/share/novnc/vnc.html /usr/share/novnc/index.html\n\
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 8000" > /entrypoint.sh

RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
