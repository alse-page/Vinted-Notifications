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
_TEST_TIMEOUT = 5
MAX_PROXY_WORKERS = 10
PROXY_RECHECK_INTERVAL = 6 * 60 * 60


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
            except Exception:
                pass
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

    proxy_list_link = db.get_parameter("proxy_list_link")
    if proxy_list_link:
        link_proxies = fetch_proxies_from_link(proxy_list_link)
        all_proxies.extend(link_proxies)

    if all_proxies:
        check_proxies = db.get_parameter("check_proxies") == "True"
        if check_proxies:
            working_proxies = check_proxies_parallel(all_proxies)
            # Если ни один не прошёл простую проверку статус-кода, всё равно
            # используем весь список — единственная альтернатива (без прокси
            # вообще, с IP самого сервера) почти наверняка хуже.
            pool = working_proxies if working_proxies else all_proxies
            _PROXY_CACHE = pool
            if len(pool) == 1:
                _SINGLE_PROXY = pool[0]
                return _SINGLE_PROXY
            return random.choice(pool)
        else:
            _PROXY_CACHE = all_proxies
            if len(all_proxies) == 1:
                _SINGLE_PROXY = all_proxies[0]
                return _SINGLE_PROXY
            return random.choice(all_proxies)

    _PROXY_CACHE = None
    return None


def check_proxy(proxy: str) -> bool:
    """Простая проверка: прокси считается рабочим, если через него вообще
    получаем ответ с кодом 200 от Vinted (не проверяем содержимое — это
    оказалось ненадёжным индикатором и создавало ложные срабатывания)."""
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

        response = session.get(_TEST_URL, proxies=proxy_dict, timeout=_TEST_TIMEOUT)
        return response.status_code == 200
    except (RequestException, ConnectionError, TimeoutError):
        return False
    finally:
        if "session" in locals():
            session.close()


def convert_proxy_string_to_dict(proxy: Optional[str]) -> dict:
    if proxy is None:
        return {}

    if "://" in proxy:
        _protocol, address = proxy.split("://")
        # Схема к самому прокси всегда http:// — прокси сам туннелирует
        # HTTPS через CONNECT, установка "https://" вызывает попытку TLS
        # прямо к прокси-серверу и падает с WRONG_VERSION_NUMBER.
        return {"http": f"http://{address}", "https": f"http://{address}"}
    else:
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
