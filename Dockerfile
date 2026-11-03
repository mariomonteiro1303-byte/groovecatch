FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GROOVECATCH_CLOUD=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
RUN mkdir -p /tmp/groovecatch/storage /tmp/groovecatch/instance
ENV GROOVECATCH_STORAGE=/tmp/groovecatch/storage GROOVECATCH_DB=/tmp/groovecatch/instance/history.sqlite3 PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn 'app:create_app()' --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 240 --access-logfile - --error-logfile -"]
