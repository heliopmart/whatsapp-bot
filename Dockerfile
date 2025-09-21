# Base leve + Python 3.11
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Dependências do sistema e Google Chrome stable
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg unzip xclip \
    fonts-liberation fonts-noto-color-emoji \
    libnss3 libasound2 libgbm1 libxshmfence1 tzdata \
 && rm -rf /var/lib/apt/lists/*

# Repositório do Google Chrome
RUN mkdir -p /etc/apt/keyrings \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor -o /etc/apt/keyrings/google-linux.gpg \
 && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

# Timezone
ENV TZ=America/Campo_Grande

# Otimiza o webdriver-manager dentro do container
ENV WDM_LOCAL=1 \
    WDM_CACHE_DIR=/wdm
RUN mkdir -p /wdm

# App
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

# Dica: aumente a SHM no docker run (ver comando abaixo)
ENTRYPOINT ["python", "main_v8.py"]
