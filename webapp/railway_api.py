"""
Shared client for Bangladesh Railway's ticketing backend.

Used by both worker.py (the polling worker, imports this via a sys.path
adjustment since it lives outside this folder) and the web app's live
train search (same folder, imports directly). One source of truth for the
headers and auth handling we reverse-engineered against the real API.
"""

import os

import requests

API_BASE = "https://railspaapi.shohoz.com/v1.0"
REQUEST_TIMEOUT = 20

RAIL_TOKEN = os.environ["RAIL_TOKEN"]
RAIL_DEVICE_ID = os.environ["RAIL_DEVICE_ID"]
RAIL_DEVICE_KEY = os.environ["RAIL_DEVICE_KEY"]

# Static header set validated against the real API. Only the three
# credential headers below change between login sessions.
STATIC_HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://eticket.railway.gov.bd",
    "priority": "u=1, i",
    "referer": "https://eticket.railway.gov.bd/",
    "sec-ch-ua": '"Chromium";v="125", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "sec-gpc": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}


def build_headers():
    return {
        **STATIC_HEADERS,
        "authorization": f"Bearer {RAIL_TOKEN}",
        "x-device-id": RAIL_DEVICE_ID,
        "x-device-key": RAIL_DEVICE_KEY,
    }


class TokenExpired(Exception):
    pass


def fetch_trains(from_city, to_city, date_of_journey_str, seat_class_param="S_CHAIR"):
    """date_of_journey_str must be DD-MMM-YYYY, e.g. '03-Jul-2026'."""
    resp = requests.get(
        f"{API_BASE}/web/bookings/search-trips-v2",
        params={
            "from_city": from_city,
            "to_city": to_city,
            "date_of_journey": date_of_journey_str,
            "seat_class": seat_class_param,
        },
        headers=build_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 401:
        raise TokenExpired(resp.text[:300])
    resp.raise_for_status()
    return resp.json()["data"]["trains"]


def find_train(trains, train_model):
    for t in trains:
        if t.get("train_model") == train_model:
            return t
    return None
