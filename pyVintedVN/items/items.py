from pyVintedVN.items.item import Item
from pyVintedVN.requester import requester
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from requests.exceptions import HTTPError
from typing import List, Dict, Optional
from pyVintedVN.settings import Urls
import json as json_module
import re
import logging

logger = logging.getLogger(__name__)

class Items:
    def search(
        self,
        url: str,
        nbr_items: int = 20,
        page: int = 1,
        time: Optional[int] = None,
        json: bool = False,
    ) -> List[Item]:
        
        locale = urlparse(url).netloc
        requester.set_locale(locale)

        parsed_url = urlparse(url)
        query_params = dict(parse_qsl(parsed_url.query))
        query_params['page'] = str(page)
        query_params['per_page'] = str(nbr_items)
        
        new_query = urlencode(query_params)
        target_url = urlunparse(parsed_url._replace(query=new_query))

        try:
            response = requester.get(url=target_url)
            if not response or not hasattr(response, 'text'):
                raise HTTPError("Empty response from requester")
                
            response.raise_for_status()

            items = []
            
            # Ищем все application/json скрипты
            scripts_content = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', response.text, re.DOTALL | re.IGNORECASE)

            for script_content in scripts_content:
                try:
                    data = json_module.loads(script_content)
                    if isinstance(data, dict):
                        # ДИАГНОСТИКА: Выводим главные ключи первого крупного JSON в лог
                        if len(data.keys()) > 2:
                            logger.info(f"DEBUG JSON Keys found: {list(data.keys())}")
                        
                        found_items = self._extract_items_recursive(data)
                        if found_items:
                            items = found_items
                            break
                except (json_module.JSONDecodeError, TypeError):
                    continue

            if not json:
                return [Item(_item) for _item in items]
            else:
                return items

        except Exception as err:
            raise HTTPError(f"Error scraping HTML: {err}")

    def _extract_items_recursive(self, data):
        if isinstance(data, dict):
            # Проверяем расширенный список возможных ключей товаров
            for key in ['items', 'catalogItems', 'products', 'catalog_items', 'edges', 'nodes']:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    sample = data[key][0]
                    if isinstance(sample, dict) and any(k in sample for k in ['id', 'title', 'price', 'url']):
                        return data[key]
            for k, v in data.items():
                res = self._extract_items_recursive(v)
                if res:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = self._extract_items_recursive(item)
                if res:
                    return res
        return None

    def parse_url(
        self, url: str, nbr_items: int = 20, page: int = 1, time: Optional[int] = None
    ) -> Dict:
        queries = parse_qsl(urlparse(url).query)
        params = {
            "search_text": "+".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "search_text"])),
            "video_game_platform_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "video_game_platform_ids[]"])),
            "catalog_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "catalog[]"])),
            "color_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "color_ids[]"])),
            "brand_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "brand_ids[]"])),
            "size_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "size_ids[]"])),
            "material_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "material_ids[]"])),
            "status_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "status_ids[]"])),
            "country_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "country_ids[]"])),
            "city_ids": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "city_ids[]"])),
            "is_for_swap": ",".join(map(str, [1 for tpl in queries if tpl[0] == "disposal[]"])),
            "currency": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "currency"])),
            "price_to": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "price_to"])),
            "price_from": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "price_from"])),
            "page": page,
            "per_page": nbr_items,
            "order": ",".join(map(str, [tpl[1] for tpl in queries if tpl[0] == "order"])),
            "time": time,
        }
        return params

    parseUrl = parse_url
