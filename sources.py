import os, httpx, urllib.parse as u
from typing import List, Dict, Any

GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_KEY")
YELP_KEY = os.getenv("YELP_KEY")

async def google_places_leads(client: httpx.AsyncClient, query: str, location: str, radius_m: int = 10000) -> List[Dict[str,Any]]:
    if not GOOGLE_PLACES_KEY:
        return []
    url = ("https://maps.googleapis.com/maps/api/place/textsearch/json"
           f"?query={u.quote(query)}&location={u.quote(location)}&radius={radius_m}&key={GOOGLE_PLACES_KEY}")
    r = await client.get(url, timeout=20)
    out = []
    for p in r.json().get("results", []):
        place_id = p.get("place_id")
        if not place_id: continue
        d = await client.get(
            f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_phone_number,website,formatted_address,opening_hours,rating,types,geometry&key={GOOGLE_PLACES_KEY}",
            timeout=20)
        det = d.json().get("result",{})
        out.append({
            "full_name": det.get("name"),
            "phone": det.get("formatted_phone_number"),
            "email": None,
            "company": det.get("name"),
            "source": "google_places",
            "tags": det.get("types",[]),
            "meta": det
        })
    return out

async def yelp_leads(client: httpx.AsyncClient, term: str, location_text: str, limit: int = 20) -> List[Dict[str,Any]]:
    if not YELP_KEY:
        return []
    headers = {"Authorization": f"Bearer {YELP_KEY}"}
    url = f"https://api.yelp.com/v3/businesses/search?term={u.quote(term)}&location={u.quote(location_text)}&limit={limit}"
    r = await client.get(url, headers=headers, timeout=20)
    out = []
    for b in r.json().get("businesses", []):
        out.append({
            "full_name": b.get("name"),
            "phone": b.get("phone") or (b.get("display_phone") or "").replace(" ",""),
            "email": None,
            "company": b.get("name"),
            "source": "yelp",
            "tags": [c.get("alias") for c in b.get("categories",[]) if isinstance(c,dict)],
            "meta": b
        })
    return out