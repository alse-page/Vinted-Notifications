import random
import requests
import time
from requests.exceptions import RequestException
import concurrent.futures
from typing import List, Optional
from logger import get_logger

logger = get_logger(__name__)

_PROXY_CACHE = None
_PROXY_CACHE_INITIALIZED = False
_SINGLE_PROXY = None

_TEST_URL = "https://www.vinted.fr/"
_TEST_TIMEOUT = 2
MAX_PROXY_WORKERS = 10
# CHANGED: было 6 часов — слишком долго держим потенциально спалённые прокси.
# Снижаем до 30 минут, пока не убедимся, что детекция прокси надёжна.
PROXY_RECHECK_INTERVAL = 30 * 60

# Маркеры Datadome-challenge — те же, что используются в requester.py
CHALLENGE_MARKERS = [
    "datadome", "Datadome", "captcha-delivery.com",
    "Just a moment", "Checking your browser",
    "Access denied", "Attention Required",
]


def fetch_proxies_from_link(url: str) -> List[str]:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return [line.strip() for line in response.text.splitlines() if line.strip()]
        return []
    except Exception:
        return []


def check_proxies_parallel(proxies_list: List[str]) -> List[str]:
    working_proxies = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PROXY_WORKERS) as executor:
        future_to_proxy = {
            executor.submit(check_proxy, proxy): proxy for proxy in proxies_list
        }
        for future in concurrent.futures.as_completed(future_to_proxy):
            proxy = future_to_proxy[future]
            try:
                is_working = future.result()
                if is_working:
                    working_proxies.append(proxy)
                else:
                    logger.warning(f"DEBUG proxy check FAILED (challenge or bad status): {proxy}")
            except Exception as e:
                logger.warning(f"DEBUG proxy check EXCEPTION for {proxy}: {e}")
    logger.warning(f"DEBUG proxy check result: {len(working_proxies)}/{len(proxies_list)} passed")
    return working_proxies


def get_random_proxy() -> Optional[str]:
    global _PROXY_CACHE, _PROXY_CACHE_INITIALIZED, _SINGLE_PROXY

    import db

    current_time = time.time()

    last_proxy_check_time_str = db.get_parameter("last_proxy_check_time")
    last_proxy_check_time = (
        float(last_proxy_check_time_str) if last_proxy_check_time_str else 0
    )

    if (
        _PROXY_CACHE_INITIALIZED
        and last_proxy_check_time > 0
        and current_time - last_proxy_check_time > PROXY_RECHECK_INTERVAL
    ):
        _PROXY_CACHE_INITIALIZED = False
        _PROXY_CACHE = None
        _SINGLE_PROXY = None

    if _PROXY_CACHE_INITIALIZED:
        if _PROXY_CACHE is None:
            return None
        if _SINGLE_PROXY is not None:
            return _SINGLE_PROXY
        if _PROXY_CACHE:
            return random.choice(_PROXY_CACHE)
        return None

    _PROXY_CACHE_INITIALIZED = True
    db.set_parameter("last_proxy_check_time", str(current_time))

    all_proxies = []

    proxy_list = db.get_parameter("proxy_list")
    if proxy_list:
        all_proxies = [p.strip() for p in proxy_list.split(";") if p.strip()]

    # DEBUG: сколько прокси реально сконфигурировано
    logger.warning(f"DEBUG configured proxy count: {len(all_proxies)} -> {all_proxies}")

    proxy_list_link = db.get_parameter("proxy_list_link")
    if proxy_list_link:
        link_proxies = fetch_proxies_from_link(proxy_list_link)
        all_proxies.extend(link_proxies)

    if all_proxies:
        check_proxies = db.get_parameter("check_proxies") == "True"
        if check_proxies:
            working_proxies = check_proxies_parallel(all_proxies)
            if working_proxies:
                _PROXY_CACHE = working_proxies
                if len(working_proxies) == 1:
                    _SINGLE_PROXY = working_proxies[0]
                    return _SINGLE_PROXY
                return random.choice(working_proxies)
            else:
                # ВАЖНО: если проверка не прошла ни одна, но прокси всё равно
                # единственный доступный вариант — используем его, а не идём
                # "голым" с IP самого сервера (это ещё хуже для антибота).
                logger.warning(
                    "DEBUG: ALL proxies failed the challenge-aware check! "
                    "Using them anyway since there's no better fallback than going proxy-less."
                )
                _PROXY_CACHE = all_proxies
                if len(all_proxies) == 1:
                    _SINGLE_PROXY = all_proxies[0]
                    return _SINGLE_PROXY
                return random.choice(all_proxies)
        else:
            _PROXY_CACHE = all_proxies
            if len(all_proxies) == 1:
                _SINGLE_PROXY = all_proxies[0]
                return _SINGLE_PROXY
            return random.choice(all_proxies)

    _PROXY_CACHE = None
    return None


def check_proxy(proxy: str) -> bool:
    if proxy is None:
        return False

    proxy_dict = convert_proxy_string_to_dict(proxy)

    try:
        session = requests.Session()

        import db
        import json

        user_agents_json = db.get_parameter("user_agents")
        default_headers_json = db.get_parameter("default_headers")

        user_agents = json.loads(user_agents_json) if user_agents_json else []
        default_headers = (
            json.loads(default_headers_json) if default_headers_json else {}
        )

        headers = {
            "User-Agent": random.choice(user_agents) if user_agents else "Mozilla/5.0",
            **default_headers,
        }
        session.headers.update(headers)

        # CHANGED: GET вместо HEAD, чтобы видеть тело ответа и отличить
        # реальную страницу от Datadome-challenge (у него тоже status 200).
        response = session.get(_TEST_URL, proxies=proxy_dict, timeout=_TEST_TIMEOUT + 3)

        if response.status_code != 200:
            return False

        text_sample = response.text[:20000]
        if any(marker in text_sample for marker in CHALLENGE_MARKERS):
            return False

        return True
    except (RequestException, ConnectionError, TimeoutError):
        return False
    finally:
        if "session" in locals():
            session.close()


def convert_proxy_string_to_dict(proxy: Optional[str]) -> dict:
    if proxy is None:
        return {}

    if "://" in proxy:
        protocol, address = proxy.split("://")
        # ВАЖНО: даже если в строке была указана схема "https://", реальное
        # соединение К ПРОКСИ должно идти по обычному HTTP (прокси сам туннелирует
        # HTTPS-трафик через CONNECT). Использование "https://" здесь заставляет
        # клиент пытаться сделать TLS-рукопожатие с самим прокси-сервером,
        # который слушает как plain HTTP proxy -> WRONG_VERSION_NUMBER.
        return {"http": f"http://{address}", "https": f"http://{address}"}
    else:
        # Без схемы вообще — тот же самый случай, оба ключа должны быть http://
        return {"http": f"http://{proxy}", "https": f"http://{proxy}"}


def configure_proxy(session, proxy: Optional[str] = None) -> bool:
    if proxy is None:
        proxy = get_random_proxy()

    if proxy is None:
        session.proxies.clear()
        return False

    if isinstance(proxy, str):
        proxy = convert_proxy_string_to_dict(proxy)

    session.proxies.update(proxy)
    return True

    session.proxies.update(proxy)
    return True
