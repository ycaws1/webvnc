FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    xfce4 xfce4-goodies \
    tightvncserver \
    novnc websockify \
    python3 \
    && apt-get clean

ENV USER=root
ENV HOME=/root
ENV DISPLAY=:1

EXPOSE 6080 5901 8000

RUN echo "#!/bin/bash\n\
rm -rf /tmp/.X*-lock /tmp/.X11-unix\n\
mkdir -p /root/.vnc\n\
echo 'password' | vncpasswd -f > /root/.vnc/passwd\n\
chmod 600 /root/.vnc/passwd\n\
# This line ensures XFCE starts with the VNC session\n\
echo 'startxfce4 &' > /root/.vnc/xstartup\n\
chmod +x /root/.vnc/xstartup\n\
vncserver :1 -geometry 1280x800 -depth 24\n\
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 8000" > /entrypoint.sh

RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
