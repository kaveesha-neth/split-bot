FROM python:3.12-slim

# Install rar (unrar-free doesn't support creating archives; we need the real rar)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install rarlinux from RARLab (free for Linux, just no warranty)
RUN curl -fsSL https://www.rarlab.com/rar/rarlinux-x64-700b3.tar.gz \
    | tar -xz -C /usr/local/bin --strip-components=1 rar/rar rar/unrar \
    && chmod +x /usr/local/bin/rar /usr/local/bin/unrar

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Temp storage lives here; mount a volume if you want persistence
ENV DOWNLOAD_DIR=/tmp/tgbot/downloads \
    OUTPUT_DIR=/tmp/tgbot/output \
    SPLIT_SIZE_MB=1000 \
    MIN_SIZE_MB=1000

CMD ["python", "-u", "bot.py"]
