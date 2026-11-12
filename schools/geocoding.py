import json
import urllib.parse
import urllib.request

# 国土地理院の住所検索API
GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"


def geocode(address):
    """住所から (緯度, 経度) を返す。見つからない・通信できないときは None を返す。"""
    url = f"{GSI_URL}?q={urllib.parse.quote(address)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            results = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None

    if not results:
        return None

    lng, lat = results[0]["geometry"]["coordinates"]  # 経度, 緯度 の順
    return lat, lng