import json
import proxies
import sys
import os
import db
import random
from curl_cffi import requests
from requests.exceptions import HTTPError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger
from pyVintedVN.settings import Urls

logger = get_logger(__name__)

# Какую версию Chrome подделывать при TLS-рукопожатии
IMPERSONATE_TARGET = "chrome124"


class Requester:
    def __init__(self, debug=False):
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import db

        self.locale = "www.vinted.fr"
        self.VINTED_AUTH_URL = f"https://{self.locale}/"
        self.MAX_RETRIES = 3
        # CHANGED: curl_cffi вместо голого requests — подделывает TLS/JA3
        # отпечаток под настоящий Chrome. Без этого даже запрос за куками
        # к главной странице блокируется с 403 и без единой куки.
        self.session = requests.Session(impersonate=IMPERSONATE_TARGET)
        self.debug = debug
        self._refresh_headers()

        if self.debug:
            logger.debug(f"Using User-Agent: {self.HEADER['User-Agent']}")

    def _refresh_headers(self):
        user_agents_json = db.get_parameter("user_agents")
        default_headers_json = db.get_parameter("default_headers")

        user_agents = json.loads(user_agents_json) if user_agents_json else []
        default_headers = (
            json.loads(default_headers_json) if default_headers_json else {}
        )

        self.HEADER = {
            "User-Agent": random.choice(user_agents) if user_agents else "Mozilla/5.0",
            **(default_headers or {}),
        }
        self.session.headers.update(self.HEADER)

    def set_locale(self, locale):
        self.locale = locale
        self.VINTED_AUTH_URL = f"https://{locale}/"
        self._refresh_headers()
        if self.debug:
            logger.debug(
                f"Locale set to {locale} with User-Agent: {self.HEADER['User-Agent']}"
            )

    def get_api_host(self):
        locale = self.locale
        if locale.startswith(Urls.VINTED_AUTH_HOST_PREFIX):
            locale = locale[len(Urls.VINTED_AUTH_HOST_PREFIX):]
        return f"{Urls.VINTED_API_HOST_PREFIX}{locale}"

    def _auth_headers(self):
        headers = {
            "Accept": "application/json",
            "Referer": self.VINTED_AUTH_URL,
            "Origin": self.VINTED_AUTH_URL.rstrip("/"),
        }
        token = self.session.cookies.get("access_token_web")
        anon_id = self.session.cookies.get("anon_id")

        # CHANGED: пробуем несколько возможных имён CSRF-куки — Vinted не
        # документирует точное имя публично, разные форки сообщали разные
        # варианты. Если ни одна не найдётся, headers["X-Csrf-Token"] просто
        # не будет установлен, и мы это увидим в DEBUG-логе ниже.
        csrf_token = (
            self.session.cookies.get("x-csrf-token")
            or self.session.cookies.get("X-Csrf-Token")
            or self.session.cookies.get("csrf_token")
            or self.session.cookies.get("_csrf_token")
        )

        if token:
            headers["Authorization"] = f"Bearer {token}"
        if anon_id:
            headers["x-anon-id"] = anon_id
        if csrf_token:
            headers["X-Csrf-Token"] = csrf_token

        if self.debug or not csrf_token:
            logger.warning(
                f"DEBUG auth headers: has_token={bool(token)} has_anon_id={bool(anon_id)} "
                f"has_csrf={bool(csrf_token)} all_cookie_names={list(self.session.cookies.keys())}"
            )

        return headers

    def get(self, url, params=None):
        proxy_configured = proxies.configure_proxy(self.session)
        if self.debug and proxy_configured:
            logger.debug(f"Using proxy: {self.session.proxies}")

        if not self.session.cookies.get("access_token_web"):
            self.set_cookies()

        tried = 0
        new_session = False
        while tried < self.MAX_RETRIES:
            tried += 1
            response = self.session.get(
                url, params=params, headers=self._auth_headers(), impersonate=IMPERSONATE_TARGET
            )
            if response.status_code == 200:
                return response
            elif response.status_code in (401, 403) and tried < self.MAX_RETRIES:
                logger.warning(
                    f"Token rejected ({response.status_code}), refreshing {tried}/{self.MAX_RETRIES}. "
                    f"Body (first 300 chars): {response.text[:300]}"
                )
                self.set_cookies()
            elif tried == self.MAX_RETRIES:
                if response.status_code in (401, 403) and not new_session:
                    logger.error(
                        f"Received {response.status_code} error for URL: {url}\n"
                        f"Response headers: {dict(response.headers)}\n"
                        f"Response body (first 500 chars): {response.text[:500]}"
                    )
                    new_session = True
                    self.session = requests.Session(impersonate=IMPERSONATE_TARGET)
                    self._refresh_headers()
                    proxy_configured = proxies.configure_proxy(self.session)
                    self.set_cookies()
                    if self.debug:
                        logger.debug(
                            f"Session reset due to {response.status_code} error"
                        )
                    tried = 0
                    continue
                return response

        raise HTTPError(
            f"Failed to get a valid response after {self.MAX_RETRIES} attempts"
        )

    def post(self, url, params=None):
        proxy_configured = proxies.configure_proxy(self.session)
        if self.debug and proxy_configured:
            logger.debug(f"Using proxy: {self.session.proxies}")

        response = self.session.post(url, data=params, impersonate=IMPERSONATE_TARGET)
        response.raise_for_status()
        return response

    def set_cookies(self):
        self.session.cookies.clear()
        try:
            resp = self.session.get(self.VINTED_AUTH_URL, impersonate=IMPERSONATE_TARGET)
            if not self.session.cookies.get("access_token_web"):
                logger.warning(
                    f"No access_token_web cookie returned by {self.VINTED_AUTH_URL}"
                )
            logger.warning(
                f"DEBUG set_cookies: status={resp.status_code} "
                f"cookies_received={list(self.session.cookies.keys())}"
            )
        except Exception:
            if self.debug:
                logger.error(
                    "There was an error fetching cookies for vinted", exc_info=True
                )

    def update_cookies(self, cookies: dict):
        self.session.cookies.update(cookies)
        if self.debug:
            logger.debug(f"Cookies manually updated ({len(cookies)} cookies received)")

    setLocale = set_locale
    setCookies = set_cookies


requester = Requester()
