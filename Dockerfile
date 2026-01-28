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

RUN echo "#!/bin/bash
rm -rf /tmp/.X*-lock /tmp/.X11-unix
mkdir -p /root/.vnc
echo 'password' | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
vncserver :1 -geometry 1280x800 -depth 24
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 6080 &
# health check server
python3 -m http.server 8000 --bind 0.0.0.0
" > /entrypoint.sh

RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
