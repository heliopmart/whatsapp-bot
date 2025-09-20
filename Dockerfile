# 1. A Base: Começamos com uma imagem oficial do Python
FROM python:3.11-slim

# 2. Preparação do Ambiente: Instalamos o `wget` e definimos um diretório de trabalho
WORKDIR /app
RUN apt-get update && apt-get install -y wget

# 3. Instalar o Google Chrome: Baixamos e instalamos o navegador que o Selenium vai usar
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN apt-get install -y ./google-chrome-stable_current_amd64.deb

# 4. Instalar as Dependências Python: Copiamos nossa "lista de compras" e instalamos tudo com pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar o Código do Bot: Agora, copiamos o seu script para dentro do contêiner
COPY main_v6.py .

# 6. O Comando Final: Dizemos ao contêiner o que ele deve fazer quando for iniciado
# O "-u" é para vermos os prints do Python em tempo real nos logs do Docker
CMD ["python", "-u", "main_v6.py"]