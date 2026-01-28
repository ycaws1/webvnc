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
RUN pip3 install playwright playwright-stealth apscheduler python-dotenv asyncpg asyncio
# RUN playwright install-deps chromium
RUN playwright install chromium

COPY main.py /root/
COPY install.sh /root/

ENV USER=root
ENV HOME=/root
ENV DISPLAY=:1

EXPOSE 6080 5901 8000

# Create xstartup file
RUN mkdir -p /root/.vnc && \
    cat > /root/.vnc/xstartup << 'EOF'
#!/bin/bash
xrdb $HOME/.Xresources
startxfce4 &
sleep 5
xfce4-terminal -e "bash -c 'cd /root && python3 main.py; exec bash'" &
EOF

RUN chmod +x /root/.vnc/xstartup

# Create entrypoint
RUN cat > /entrypoint.sh << 'EOF'
#!/bin/bash
rm -rf /tmp/.X*-lock /tmp/.X11-unix
mkdir -p /root/.vnc
echo "password" | vncpasswd -f > /root/.vnc/passwd
chmod 600 /root/.vnc/passwd
vncserver :1 -geometry 1280x800 -depth 24
ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
/usr/share/novnc/utils/launch.sh --vnc localhost:5901 --listen 8000
EOF

RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]