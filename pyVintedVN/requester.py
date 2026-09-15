import sys
import os
import random
import time
from urllib.parse import urlencode

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger
import proxies

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync

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
            
            pw_proxy = None
            if proxy_str:
                clean_proxy = proxy_str.replace("http://", "").replace("https://", "")
                if "@" in clean_proxy:
                    auth, host = clean_proxy.split("@", 1)
                    user, pwd = auth.split(":", 1)
                    pw_proxy = {
                        "server": f"http://{host}",
                        "username": user,
                        "password": pwd
                    }
                else:
                    pw_proxy = {"server": f"http://{clean_proxy}"}

            logger.warning(f"DEBUG Playwright GET attempt {tried}/{self.MAX_RETRIES} for {url} via {pw_proxy}")

            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox", 
                            "--disable-setuid-sandbox", 
                            "--disable-blink-features=AutomationControlled"
                        ]
                    )
                    
                    context = browser.new_context(
                        proxy=pw_proxy,
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        viewport={'width': 1920, 'height': 1080}
                    )
                    
                    page = context.new_page()
                    stealth_sync(page)

                    # Используем domcontentloaded, чтобы быстрее начать взаимодействие со страницей
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    
                    # --- ИМИТАЦИЯ ДЕЙСТВИЙ ЧЕЛОВЕКА ---
                    try:
                        # Хаотичные движения мыши
                        page.mouse.move(random.randint(100, 500), random.randint(100, 500))
                        page.wait_for_timeout(random.randint(400, 800))
                        page.mouse.move(random.randint(500, 1000), random.randint(300, 800))
                        page.wait_for_timeout(random.randint(400, 800))
                        
                        # Клик по центру экрана (часто активирует чекбокс или запускает проверку)
                        page.mouse.click(960, 540)
                        
                        # Ждем 6 секунд, чтобы скрытая JS-капча успела сработать и пустить нас дальше
                        page.wait_for_timeout(6000)
                    except Exception as e:
                        logger.warning(f"Mouse simulation failed: {e}")
                    
                    html = page.content()
                    status = response.status if response else 200
                    headers = response.headers if response else {}
                    
                    browser.close()

                    # Проверяем, прошли ли мы защиту
                    if "datadome" in html.lower() and "Just a moment" in html:
                        logger.warning(f"Datadome challenge still present on attempt {tried}")
                        time.sleep(random.uniform(2, 4))
                        continue
                        
                    return DummyResponse(text=html, status_code=status, headers=headers)

            except PlaywrightTimeoutError:
                logger.warning(f"Playwright Timeout on attempt {tried} for {url}")
            except Exception as e:
                logger.error(f"Playwright Error on attempt {tried}: {e}")
            
            time.sleep(random.uniform(1, 3))

        from requests.exceptions import HTTPError
        raise HTTPError(f"Failed to get a valid response via Playwright after {self.MAX_RETRIES} attempts")

    def post(self, url, params=None):
        pass

    def set_cookies(self):
        pass

    def update_cookies(self, cookies: dict):
        pass

Requester.setLocale = Requester.set_locale
Requester.setCookies = Requester.set_cookies

requester = Requester()
