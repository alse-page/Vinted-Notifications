import json
import proxies
import sys
import os
import db
import random
import time
from curl_cffi import requests as cf_requests
from requests.exceptions import HTTPError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger

logger = get_logger(__name__)

# Маркеры, по которым узнаём страницу-челлендж Datadome, даже если status_code == 200
DATADOME_MARKERS = [
    "datadome",
    "Datadome",
    "captcha-delivery.com",
    "geo.captcha-delivery.com",
    "Just a moment",
    "Checking your browser",
    "Access denied",
    "Attention Required",
]

# Какого браузера Chrome прикидываться (curl_cffi поддерживает конкретные версии, не любые)
IMPERSONATE_TARGET = "chrome124"


def is_challenge_page(response) -> bool:
    """Проверяет, является ли ответ Datadome-челленджем, а не настоящей страницей."""
    if response is None:
        return True
    text_sample = response.text[:20000]  # маркеры всегда в начале документа/head
    return any(marker in text_sample for marker in DATADOME_MARKERS)


class Requester:
    """
    A class for handling HTTP requests to Vinted.
    Uses curl_cffi with Chrome TLS impersonation instead of cloudscraper,
    plus content-based Datadome-challenge detection (not just status codes).
    """

    def __init__(self, debug=False):
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import db

        user_agents_json = db.get_parameter("user_agents")
        default_headers_json = db.get_parameter("default_headers")

        user_agents = json.loads(user_agents_json) if user_agents_json else []
        default_headers = (
            json.loads(default_headers_json) if default_headers_json else {}
        )

        self.HEADER = {
            "User-Agent": random.choice(user_agents) if user_agents else "Mozilla/5.0",
            **(default_headers or {}),
            "Host": "www.vinted.fr",
        }
        self.VINTED_AUTH_URL = "https://www.vinted.fr/"
        self.MAX_RETRIES = 3

        # CHANGED: curl_cffi вместо cloudscraper — подделывает TLS/JA3 отпечаток под реальный Chrome
        self.session = cf_requests.Session(impersonate=IMPERSONATE_TARGET)
        self.session.headers.update(self.HEADER)
        self.debug = debug
        self._warmed_up = False

        if self.debug:
            logger.debug(f"Using User-Agent: {self.HEADER['User-Agent']}")

    def set_locale(self, locale):
        """
        Set the locale of the requester.
        """
        self.VINTED_AUTH_URL = f"https://{locale}/"
        user_agents_json = db.get_parameter("user_agents")
        default_headers_json = db.get_parameter("default_headers")

        user_agents = json.loads(user_agents_json) if user_agents_json else []
        default_headers = (
            json.loads(default_headers_json) if default_headers_json else {}
        )

        self.HEADER = {
            "User-Agent": random.choice(user_agents) if user_agents else "Mozilla/5.0",
            **(default_headers or {}),
            "Host": f"{locale}",
        }
        self.session.headers.update(self.HEADER)
        self._warmed_up = False  # locale сменился -> нужно заново прогреть куки для этого домена
        if self.debug:
            logger.debug(
                f"Locale set to {locale} with User-Agent: {self.HEADER['User-Agent']}"
            )

    def _configure_proxy(self):
        proxy_configured = proxies.configure_proxy(self.session)
        if self.debug and proxy_configured:
            logger.debug(f"Using proxy: {self.session.proxies}")
        return proxy_configured

    def _warm_up_session(self):
        """Заходит на главную страницу домена, чтобы получить настоящие Datadome-куки
        до того, как бить по catalog-эндпоинтам напрямую."""
        try:
            self.session.get(self.VINTED_AUTH_URL, impersonate=IMPERSONATE_TARGET)
            self._warmed_up = True
            if self.debug:
                logger.debug(f"Warmed up session on {self.VINTED_AUTH_URL}")
        except Exception:
            if self.debug:
                logger.error("Warm-up request failed", exc_info=True)

    def _reset_session(self, reason=""):
        """Полностью пересоздаёт сессию: новый impersonate-контекст + новый прокси из ротации."""
        self.session = cf_requests.Session(impersonate=IMPERSONATE_TARGET)
        self.session.headers.update(self.HEADER)
        self._configure_proxy()
        self._warmed_up = False
        if self.debug:
            logger.debug(f"Session reset ({reason})")

    def get(self, url, params=None):
        """
        Make a GET request with retry logic, including Datadome-challenge detection.
        """
        self._configure_proxy()

        tried = 0
        while tried < self.MAX_RETRIES:
            tried += 1

            # ВАЖНО: проверяем прогрев на КАЖДОЙ попытке, а не только один раз до цикла —
            # иначе после reset_session() ретрай идёт с холодной сессией без кук.
            if not self._warmed_up:
                logger.warning(f"DEBUG: warming up session before attempt {tried} for host {url.split('/')[2]}")
                self._warm_up_session()
                time.sleep(random.uniform(0.5, 1.5))

            response = self.session.get(url, params=params, impersonate=IMPERSONATE_TARGET)
            logger.warning(
                f"DEBUG: attempt {tried}/{self.MAX_RETRIES} status={response.status_code} "
                f"cookies_count={len(self.session.cookies)} is_challenge={is_challenge_page(response)} "
                f"proxy={self.session.proxies if hasattr(self.session, 'proxies') else 'n/a'}"
            )

            if is_challenge_page(response):
                logger.warning(
                    f"Datadome challenge detected (attempt {tried}/{self.MAX_RETRIES}) for {url}"
                )
                self._reset_session(reason="datadome challenge")
                time.sleep(random.uniform(1.0, 3.0))
                continue

            if response.status_code in (401, 404) and tried < self.MAX_RETRIES:
                if self.debug:
                    logger.debug(f"Cookies invalid retrying {tried}/{self.MAX_RETRIES}")
                self.set_cookies()
                continue
            elif response.status_code == 200:
                return response
            elif tried == self.MAX_RETRIES:
                if response.status_code in (401, 403):
                    logger.error(
                        f"Received {response.status_code} error for URL: {url}\n"
                        f"Response headers: {dict(response.headers)}\n"
                        f"Response body (first 500 chars): {response.text[:500]}"
                    )
                    self._reset_session(reason=f"{response.status_code} on final retry")
                return response

        raise HTTPError(
            f"Failed to get a valid (non-challenge) response after {self.MAX_RETRIES} attempts"
        )

    def post(self, url, params=None):
        """
        Make a POST request.
        """
        self._configure_proxy()
        response = self.session.post(url, params=params, impersonate=IMPERSONATE_TARGET)
        response.raise_for_status()
        return response

    def set_cookies(self):
        """
        Reset and fetch new cookies for authentication.
        """
        try:
            self.session.cookies.clear()
        except Exception:
            pass
        try:
            self.session.get(self.VINTED_AUTH_URL, impersonate=IMPERSONATE_TARGET)
            self._warmed_up = True
            if self.debug:
                logger.debug("Cookies set!")
        except Exception:
            if self.debug:
                logger.error(
                    "There was an error fetching cookies for vinted", exc_info=True
                )

    def update_cookies(self, cookies: dict):
        """
        Update the session cookies with the provided dictionary.
        """
        self.session.cookies.update(cookies)
        if self.debug:
            logger.debug(f"Cookies manually updated ({len(cookies)} cookies received)")

    setLocale = set_locale
    setCookies = set_cookies


requester = Requester()
