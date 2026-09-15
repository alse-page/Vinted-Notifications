FROM python:3.11-slim

ARG APP_UID=10001
ARG APP_GID=10001
ARG APP_USER=appuser

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu wget gnupg xvfb curl unzip ca-certificates \
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

# --- ХИТРОСТЬ ПРОТИВ READ-ONLY: Делаем ярлык папки драйверов на /tmp ---
RUN mv /usr/local/lib/python3.11/site-packages/seleniumbase/drivers /usr/local/lib/python3.11/site-packages/seleniumbase/drivers_orig \
 && ln -s /tmp/sb_drivers /usr/local/lib/python3.11/site-packages/seleniumbase/drivers

COPY . .

RUN chown -R ${APP_USER}:${APP_USER} /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "vinted_notifications.py"]
