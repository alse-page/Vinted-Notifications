FROM python:3.11-slim

ARG APP_UID=10001
ARG APP_GID=10001
ARG APP_USER=appuser

WORKDIR /app

# Устанавливаем только самые базовые утилиты
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu curl \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -g ${APP_GID} ${APP_USER} \
 && useradd -u ${APP_UID} -g ${APP_GID} -M ${APP_USER} \
 && mkdir -p /app/data /app/logs

COPY requirements.txt .
# Ставим только питоновские пакеты, никакой установки chromedriver!
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R ${APP_USER}:${APP_USER} /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "vinted_notifications.py"]
