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

# CHANGED: -m -d /home/${APP_USER} вместо -M — Chrome/undetected-chromedriver
# требуют существующую и доступную для записи $HOME для профиля/кэша,
# иначе Chrome падает при старте ещё до открытия debug-порта.
RUN groupadd -g ${APP_GID} ${APP_USER} \
 && useradd -u ${APP_UID} -g ${APP_GID} -m -d /home/${APP_USER} ${APP_USER} \
 && mkdir -p /app/data /app/logs /home/${APP_USER} \
 && chown -R ${APP_USER}:${APP_USER} /home/${APP_USER}

ENV HOME=/home/appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && seleniumbase get chromedriver

# Создаем и патчим uc_driver заранее, пока есть права записи
RUN python -c "import os, shutil; \
from seleniumbase.undetected import patcher; \
d = '/usr/local/lib/python3.11/site-packages/seleniumbase/drivers'; \
c = os.path.join(d, 'chromedriver'); \
u = os.path.join(d, 'uc_driver'); \
shutil.copy(c, u); \
os.chmod(u, 0o755); \
patcher.Patcher(executable_path=u).patch_exe()"

COPY . .

RUN chown -R ${APP_USER}:${APP_USER} /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "vinted_notifications.py"]
