import sys
import os
import random
import time
from urllib.parse import urlencode

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger
import proxies

# Берем легкую библиотеку для обхода Datadome вместо тяжелого браузера
from curl_cffi import requests as cffi_requests

logger = get_logger(__name__)

class Requester:
    def __init__(self, debug=False):
        self.debug = debug
        self.MAX_RETRIES = 3
        self.VINTED_AUTH_URL = "https://www.vinted.fr/"

    def set_locale(self, locale):
        self.VINTED_AUTH_URL = f"https://{locale}/"
        if self.debug:
            logger.debug(f"Locale set to {locale}")

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

            logger.warning(f"DEBUG curl_cffi GET attempt {tried}/{self.MAX_RETRIES} for {url} via {proxy_str}")

            try:
                # impersonate="chrome120" заставляет сервер думать, что мы настоящий Chrome
                response = cffi_requests.get(
                    url,
                    proxies=cffi_proxies,
                    impersonate="chrome120",
                    timeout=15
                )
                
                html = response.text
                
                if "datadome" in html.lower() and "Just a moment" in html:
                    logger.warning(f"Datadome challenge still present on attempt {tried}")
                    time.sleep(random.uniform(2.0, 4.0))
                    continue
                    
                return response

            except Exception as e:
                logger.error(f"curl_cffi Error on attempt {tried}: {e}")
            
            time.sleep(random.uniform(1.0, 3.0))

        from requests.exceptions import HTTPError
        raise HTTPError(f"Failed to get a valid response via curl_cffi after {self.MAX_RETRIES} attempts")

    def post(self, url, params=None):
        pass

    def set_cookies(self):
        pass

    def update_cookies(self, cookies: dict):
        pass

Requester.setLocale = Requester.set_locale
Requester.setCookies = Requester.set_cookies

requester = Requester()
