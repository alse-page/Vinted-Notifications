from pyVintedVN.items.item import Item
from pyVintedVN.requester import requester
from urllib.parse import urlparse, parse_qsl
from requests.exceptions import HTTPError
from typing import List, Dict, Optional
from pyVintedVN.settings import Urls

class Items:
    """
    A class for searching and retrieving items from Vinted.
    """

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

        params = self.parse_url(url, nbr_items, page, time)

        base_domain = locale.replace("www.", "")
        api_url = f"https://api.{base_domain}/svc-catalogue/items"

        try:
            response = requester.get(url=api_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "items" in data:
                items = data["items"]
            elif "catalogItems" in data and "items" in data["catalogItems"]:
                items = data["catalogItems"]["items"]
            else:
                items = []

            if not json:
                return [Item(_item) for _item in items]
            else:
                return items
        except HTTPError as err:
            raise err

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
