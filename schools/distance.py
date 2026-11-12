import math


def distance_km(lat1, lng1, lat2, lng2):
    """2地点の直線距離（km）を返す（ハーサイン公式）"""
    radius = 6371.0  # 地球の半径（km）
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))