import sys
import os
import random
import time
from urllib.parse import urlencode

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger
import proxies

from seleniumbase import SB

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
            
            sb_proxy = proxy_str.replace("http://", "").replace("https://", "") if proxy_str else None

            logger.warning(f"DEBUG SeleniumBase GET attempt {tried}/{self.MAX_RETRIES} for {url} via {sb_proxy}")

            old_cwd = os.getcwd()
            try:
                os.chdir("/tmp")
                
                with SB(uc=True, proxy=sb_proxy, headless=True) as sb:
                    sb.driver.get(url)
                    time.sleep(random.uniform(5.0, 8.0))
                    
                    html = sb.driver.page_source
                    
                    if "datadome" in html.lower() and "Just a moment" in html:
                        logger.warning(f"Datadome challenge still present on attempt {tried}")
                        time.sleep(random.uniform(2, 4))
                        continue
                        
                    return DummyResponse(text=html, status_code=200)

            except Exception as e:
                logger.error(f"SeleniumBase Error on attempt {tried}: {e}")
            finally:
                os.chdir(old_cwd)
            
            time.sleep(random.uniform(1, 3))

        from requests.exceptions import HTTPError
        raise HTTPError(f"Failed to get a valid response via SeleniumBase after {self.MAX_RETRIES} attempts")

    def post(self, url, params=None):
        pass

    def set_cookies(self):
        pass

    def update_cookies(self, cookies: dict):
        pass

Requester.setLocale = Requester.set_locale
Requester.setCookies = Requester.set_cookies

requester = Requester()
