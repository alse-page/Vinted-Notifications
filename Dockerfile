FROM python:3.11-slim

ARG APP_UID=10001
ARG APP_GID=10001
ARG APP_USER=appuser

# Заставляем логи выводиться мгновенно и даем временный "дом"
ENV PYTHONUNBUFFERED=1
ENV HOME=/tmp

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu wget gnupg xvfb xauth curl unzip ca-certificates \
 && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update \
 && apt-get install -y google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -g ${APP_GID} ${APP_USER} \
 && useradd -u ${APP_UID} -g ${APP_GID} -M ${APP_USER} \
 && mkdir -p /app/data /app/logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && seleniumbase get chromedriver

COPY . .

RUN chown -R ${APP_USER}:${APP_USER} /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Вернули обычный запуск Питона (без xvfb-run)
CMD ["python", "vinted_notifications.py"]
