"""Best-effort city → (lat, lng) lookup for plotting courier checkpoints.

The courier tracking API returns city-name checkpoints with no coordinates, so we
geocode against this static table of major Indian logistics hubs. Unknown cities
return None — the checkpoint is still recorded, it just isn't drawn on the map.
"""
from __future__ import annotations

# Lowercased city name → (lat, lng). Major couriers route through these hubs.
CITY_COORDS: dict[str, tuple[float, float]] = {
    "mumbai": (19.0760, 72.8777),
    "navi mumbai": (19.0330, 73.0297),
    "thane": (19.2183, 72.9781),
    "pune": (18.5204, 73.8567),
    "nagpur": (21.1458, 79.0882),
    "nashik": (19.9975, 73.7898),
    "aurangabad": (19.8762, 75.3433),
    "kolhapur": (16.7050, 74.2433),
    "delhi": (28.7041, 77.1025),
    "new delhi": (28.6139, 77.2090),
    "gurgaon": (28.4595, 77.0266),
    "gurugram": (28.4595, 77.0266),
    "noida": (28.5355, 77.3910),
    "faridabad": (28.4089, 77.3178),
    "ghaziabad": (28.6692, 77.4538),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867),
    "secunderabad": (17.4399, 78.4983),
    "kolkata": (22.5726, 88.3639),
    "howrah": (22.5958, 88.2636),
    "ahmedabad": (23.0225, 72.5714),
    "surat": (21.1702, 72.8311),
    "vadodara": (22.3072, 73.1812),
    "rajkot": (22.3039, 70.8022),
    "jaipur": (26.9124, 75.7873),
    "jodhpur": (26.2389, 73.0243),
    "udaipur": (24.5854, 73.7125),
    "lucknow": (26.8467, 80.9462),
    "kanpur": (26.4499, 80.3319),
    "agra": (27.1767, 78.0081),
    "varanasi": (25.3176, 82.9739),
    "patna": (25.5941, 85.1376),
    "ranchi": (23.3441, 85.3096),
    "bhopal": (23.2599, 77.4126),
    "indore": (22.7196, 75.8577),
    "raipur": (21.2514, 81.6296),
    "chandigarh": (30.7333, 76.7794),
    "ludhiana": (30.9010, 75.8573),
    "amritsar": (31.6340, 74.8723),
    "dehradun": (30.3165, 78.0322),
    "guwahati": (26.1445, 91.7362),
    "bhubaneswar": (20.2961, 85.8245),
    "cuttack": (20.4625, 85.8830),
    "visakhapatnam": (17.6868, 83.2185),
    "vijayawada": (16.5062, 80.6480),
    "coimbatore": (11.0168, 76.9558),
    "madurai": (9.9252, 78.1198),
    "tiruchirappalli": (10.7905, 78.7047),
    "kochi": (9.9312, 76.2673),
    "cochin": (9.9312, 76.2673),
    "ernakulam": (9.9816, 76.2999),
    "thiruvananthapuram": (8.5241, 76.9366),
    "trivandrum": (8.5241, 76.9366),
    "mangalore": (12.9141, 74.8560),
    "mysore": (12.2958, 76.6394),
    "mysuru": (12.2958, 76.6394),
    "goa": (15.2993, 74.1240),
    "panaji": (15.4909, 73.8278),
    "jamshedpur": (22.8046, 86.2029),
    "siliguri": (26.7271, 88.3953),
    "jammu": (32.7266, 74.8570),
    "srinagar": (34.0837, 74.7973),
}


def geocode(city: str | None) -> tuple[float, float] | None:
    """Return (lat, lng) for a checkpoint city name, or None if unknown."""
    if not city:
        return None
    # Normalize: lowercase, take the part before a comma (e.g. "Pune, MH"),
    # collapse whitespace.
    name = city.strip().lower().split(",")[0].strip()
    name = " ".join(name.split())
    if not name:
        return None
    if name in CITY_COORDS:
        return CITY_COORDS[name]
    # Loose fallback: a known hub appears as a token/substring of the location.
    for known, coords in CITY_COORDS.items():
        if known in name:
            return coords
    return None
