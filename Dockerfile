
FROM python:3.12-slim

# Configurações do Python e do GrooveCatch
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GROOVECATCH_CLOUD=1

# Instala FFmpeg, certificados e ferramentas necessárias ao Deno
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        unzip && \
    rm -rf /var/lib/apt/lists/*

# Instala o runtime JavaScript Deno
RUN curl -fsSL https://deno.land/install.sh | \
    DENO_INSTALL=/opt/deno sh && \
    ln -s /opt/deno/bin/deno /usr/local/bin/deno

# Diretório principal da aplicação
WORKDIR /app

# Instala as dependências Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia os arquivos do GrooveCatch
COPY . .

# Cria diretórios temporários
RUN mkdir -p /tmp/groovecatch/storage \
    /tmp/groovecatch/instance

# Configurações de armazenamento e porta
ENV GROOVECATCH_STORAGE=/tmp/groovecatch/storage \
    GROOVECATCH_DB=/tmp/groovecatch/instance/history.sqlite3 \
    PORT=10000

EXPOSE 10000

# Inicia a aplicação
CMD ["sh", "-c", "exec gunicorn 'app:create_app()' --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 240 --access-logfile - --error-logfile -"]

