import json
import proxies
import sys
import os
import db
import random
import cloudscraper
from requests.exceptions import HTTPError

# Add the parent directory to sys.path to import logger
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import get_logger

# Get logger for this module
logger = get_logger(__name__)


class Requester:
    """
    A class for handling HTTP requests to Vinted.

    This class manages session headers, cookies, and provides methods for making
    HTTP requests with retry logic for handling authentication issues.
    """

    def __init__(self, debug=False):
        """
        Initialize the Requester with default headers and session.
        """

        # Add the parent directory to sys.path to import db
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import db

        # Get user agents and default headers from the database
        user_agents_json = db.get_parameter("user_agents")
        default_headers_json = db.get_parameter("default_headers")

        # Parse JSON strings
        user_agents = json.loads(user_agents_json) if user_agents_json else []
        default_headers = (
            json.loads(default_headers_json) if default_headers_json else {}
        )

        self.HEADER = {
            # Grabs a user agent from the database
            "User-Agent": random.choice(user_agents) if user_agents else "Mozilla/5.0",
            **(default_headers or {}),
            "Host": "www.vinted.fr",
        }
        self.VINTED_AUTH_URL = "https://www.vinted.fr/"
        self.MAX_RETRIES = 3
        
        # CHANGED: Use cloudscraper to mimic a real Chrome browser
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.session.headers.update(self.HEADER)
        self.debug = debug

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
        if self.debug:
            logger.debug(
                f"Locale set to {locale} with User-Agent: {self.HEADER['User-Agent']}"
            )

    def get(self, url, params=None):
        """
        Make a GET request with retry logic.
        """
        proxy_configured = proxies.configure_proxy(self.session)
        if self.debug and proxy_configured:
            logger.debug(f"Using proxy: {self.session.proxies}")

        tried = 0
        new_session = False
        while tried < self.MAX_RETRIES:
            tried += 1
            with self.session.get(url, params=params) as response:
                if response.status_code in (401, 404) and tried < self.MAX_RETRIES:
                    print(f"Cookies invalid, retrying {tried}/{self.MAX_RETRIES}")
                    if self.debug:
                        logger.debug(
                            f"Cookies invalid retrying {tried}/{self.MAX_RETRIES}"
                        )
                    self.set_cookies()
                elif response.status_code == 200:
                    return response
                elif tried == self.MAX_RETRIES:
                    if response.status_code in (401, 403) and not new_session:
                        logger.error(
                            f"Received {response.status_code} error for URL: {url}\n"
                            f"Response headers: {dict(response.headers)}\n"
                            f"Response body (first 500 chars): {response.text[:500]}"
                        )

                        new_session = True
                        
                        # CHANGED: Use cloudscraper again when resetting session
                        self.session = cloudscraper.create_scraper(
                            browser={
                                'browser': 'chrome',
                                'platform': 'windows',
                                'desktop': True
                            }
                        )
                        self.session.headers.update(self.HEADER)
                        
                        proxy_configured = proxies.configure_proxy(self.session)
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
        """
        Make a POST request.
        """
        proxy_configured = proxies.configure_proxy(self.session)
        if self.debug and proxy_configured:
            logger.debug(f"Using proxy: {self.session.proxies}")

        response = self.session.post(url, params)
        response.raise_for_status()
        return response

    def set_cookies(self):
        """
        Reset and fetch new cookies for authentication.
        """
        self.session.cookies.clear_session_cookies()
        try:
            self.session.head(self.VINTED_AUTH_URL)
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
