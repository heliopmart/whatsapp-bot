# Base leve + Python 3.11
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Dependências de sistema (sem xvfb, xclip, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg unzip wget jq \
 && rm -rf /var/lib/apt/lists/*

# Seção para instalar Google Chrome e o Chromedriver correspondente (mantenha como estava)
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-linux.gpg \
 && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && rm -rf /var/lib/apt/lists/*
RUN CHROME_VERSION=$(google-chrome --version | cut -d " " -f3 | cut -d "." -f1-3) \
 && DRIVER_VERSION=$(curl -sS "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json" | jq -r ".versions[] | select(.version | startswith(\"$CHROME_VERSION\")) | .downloads.chromedriver[] | select(.platform==\"linux64\") | .url" | head -n 1) \
 && wget -O /tmp/chromedriver.zip "$DRIVER_VERSION" \
 && unzip /tmp/chromedriver.zip -d /tmp \
 && mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
 && chmod +x /usr/local/bin/chromedriver \
 && rm /tmp/chromedriver.zip && rm -rf /tmp/chromedriver-linux64

# App
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# O CMD volta a ser simples
CMD ["python", "main_v8.py"]