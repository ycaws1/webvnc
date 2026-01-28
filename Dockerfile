FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install Python
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    && apt-get clean

# Install Python packages
RUN pip3 install playwright playwright-stealth apscheduler python-dotenv asyncpg asyncio fastapi uvicorn

# Install Playwright browser
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application files
COPY main.py /root/
COPY install.sh /root/

WORKDIR /root

EXPOSE 8000

CMD ["python3", "-u", "main.py"]