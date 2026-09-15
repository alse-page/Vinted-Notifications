import sys
import os
import random
import time
from urllib.parse import urlencode

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger
import proxies

from curl_cffi import requests as cffi_requests

logger = get_logger(__name__)

class DummyResponse:
    def __init__(self, text, status_code, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests.exceptions import HTTPError
            raise HTTPError(f"HTTP Error: {self.status_code}")

class Requester:
    def __init__(self, debug=False):
        self.debug = debug
        self.MAX_RETRIES = 3
        self.VINTED_AUTH_URL = "https://www.vinted.fr/"
        # Создаем постоянную сессию, чтобы куки сохранялись между запросами
        self.session = cffi_requests.Session(impersonate="chrome120")

    def set_locale(self, locale):
        self.VINTED_AUTH_URL = f"https://{locale}/"
        if self.debug:
            logger.debug(f"Locale set to {locale}")
        # При установке локали сразу идем на главную за куками
        self.set_cookies()

    def set_cookies(self):
        """Заходим на главную страницу, чтобы получить легитимные куки от Datadome"""
        try:
            proxy_str = proxies.get_random_proxy()
            cffi_proxies = {"http": proxy_str, "https": proxy_str} if proxy_str else None
            logger.info(f"Fetching initial session cookies from {self.VINTED_AUTH_URL}")
            
            # Эмулируем обычный заход на главную страницу
            self.session.get(
                self.VINTED_AUTH_URL, 
                proxies=cffi_proxies, 
                timeout=15
            )
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            logger.error(f"Failed to fetch initial cookies: {e}")

    def get(self, url, params=None):
        if params:
            query_string = urlencode(params)
            url = f"{url}&{query_string}" if "?" in url else f"{url}?{query_string}"

        tried = 0
        while tried < self.MAX_RETRIES:
            tried += 1
            proxy_str = proxies.get_random_proxy()
            
            cffi_proxies = None
            if proxy_str:
                cffi_proxies = {"http": proxy_str, "https": proxy_str}

            logger.warning(f"DEBUG curl_cffi GET attempt {tried}/{self.MAX_RETRIES} for {url}")

            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "accept-language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "referer": self.VINTED_AUTH_URL, # Указываем, что пришли с главной страницы
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "same-origin",
                "upgrade-insecure-requests": "1"
            }

            try:
                # Делаем запрос в рамках нашей сохраненной сессии
                response = self.session.get(
                    url,
                    proxies=cffi_proxies,
                    headers=headers,
                    timeout=15
                )
                
                html = response.text
                
                if "datadome" in html.lower() and "Just a moment" in html:
                    logger.warning(f"Datadome challenge still present on attempt {tried}")
                    # Если нас все-таки поймали, полностью сбрасываем сессию и берем новые куки
                    self.session = cffi_requests.Session(impersonate="chrome120")
                    self.set_cookies()
                    time.sleep(random.uniform(1.0, 3.0))
                    continue
                    
                return response

            except Exception as e:
                logger.error(f"curl_cffi Error on attempt {tried}: {e}")
            
            time.sleep(random.uniform(1.0, 3.0))

        from requests.exceptions import HTTPError
        raise HTTPError(f"Failed to get a valid response via curl_cffi after {self.MAX_RETRIES} attempts")

    def post(self, url, params=None):
        pass

    def update_cookies(self, cookies: dict):
        self.session.cookies.update(cookies)

Requester.setLocale = Requester.set_locale
Requester.setCookies = Requester.set_cookies

requester = Requester()
