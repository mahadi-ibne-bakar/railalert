"""
Quick test script for Bangladesh Railway's ticketing backend API.

WHAT THIS DOES
1. Logs in with your eticket.railway.gov.bd / Rail Sheba account (mobile number +
   password) to get an auth token -- the same account you already use to buy tickets.
2. Uses that token to ask for seat availability on one route/date/class.
3. Prints the raw response so we can see exactly what data comes back, and also
   tries the same search WITHOUT a token so we can confirm the 401 behavior.

NOTES
- This hits the real, live Bangladesh Railway backend (same one the official Rail
  Sheba app uses). Run it once or twice while we're exploring -- don't loop it yet.
- Your password is sent only to the real sign-in endpoint, nowhere else.
- Don't want to type your password into a script? Log into the website normally,
  open browser dev tools -> Network tab, find any request to railspaapi.shohoz.com,
  copy the value of its 'Authorization' header, paste it into EXISTING_TOKEN below,
  and set USE_EXISTING_TOKEN = True.
- When you paste the output back into chat, the token is already truncated to 12
  characters below for safety -- you don't need to share the full token or password.
"""

import json
import requests

BASE = "https://railspaapi.shohoz.com/v1.0"

MOBILE_NUMBER = "01866655727"   # your Rail Sheba / eticket account mobile number
PASSWORD = "AB12cd,."

USE_EXISTING_TOKEN = True
EXISTING_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6ImF0K2p3dCJ9.eyJuYmYiOjE3ODI1NzE0NTksImV4cCI6MTc4MjYxNDY1OSwiaXNzIjoiaHR0cDovL3RyYWluLWlhbS5zaG9ob3ouY29tIiwiYXVkIjoic2hvaG96LmlhbS50cmFpbiIsImNsaWVudF9pZCI6InRyYWluLXRpY2tldC11c2VyIiwiY2xpZW50X3RlbmFudF9pZCI6IjY3YTUxNjNjLTU2NWQtNGNhMC1iMTE3LTg3YzcwMWY2NTRmOSIsImNsaWVudF92ZXJ0aWNhbF9pZCI6IjA2OGU4MDRmLTJkYjctNDQ4OS05OTYzLTc4OWZiN2UwMmJkZiIsInN1YiI6IjcwODllM2NlLTU2NzEtNDRjOC04MzA0LWM5ZTY2NDNiODE4ZSIsImF1dGhfdGltZSI6MTc4MjU3MTQ1OSwiaWRwIjoibG9jYWwiLCJwaG9uZV9udW1iZXIiOiIwMTg2NjY1NTcyNyIsImVtYWlsIjoibWFoYWRpZW1haWw5OUBnbWFpbC5jb20iLCJ1c2VybmFtZSI6IjAxODY2NjU1NzI3IiwiZGlzcGxheV9uYW1lIjoiTUFIQURJIElCTkUgQkFLQVIiLCJsb2NhbGUiOiJibi1CRCIsIm5pZG4iOiI5NTkwODM3MDI4IiwibmlkbnQiOiJOSUQiLCJyb2xlIjpbInVzZXIiLCJhbm9ueW1vdXMiXSwic2NvcGUiOlsic2hvaG96LmlhbS50cmFpbiIsIm9mZmxpbmVfYWNjZXNzIl0sImFtciI6WyJwd2QiXX0.cV26DrBIq7-VFpo8du9ZTidOC7z9zZeBAkdUVDOhLdO5xI73eSlKB93ACilJLUio3vXRQ4X7WdNw3XYgnN1fSp0yF7xmrbo7VtfigJW3qEWvE4MSyAgKkR0ZS7X5zlLpxZt_UUilIMG8cWVEqLMU8gcR-8XRw0-5-LHCH9XbACEfKj06lmmVuSLgAGwcO-EgaMgYSkf8-FemL6aqyGDUuIS-MvPINAE5X7po2ekvsoaO3aeZVVxlWYW_Xl3h09HGshEYYQIULMNwzuF3AnX_gMbcgA-GunEh7jutMCet6BUdTWeCtifWF5wnvQraeZPLLOPv6VZNKMOQhKVRHGdgpg"


# ---- route/date/class to test with ----
FROM_CITY = "Dhaka"
TO_CITY = "Chattogram"
DATE_OF_JOURNEY = "2026-07-10"   # YYYY-MM-DD, must be within the bookable window
SEAT_CLASS = "S_CHAIR"          # also try: SNIGDHA, AC_S, AC_B, F_BERTH, F_SEAT...


COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://eticket.railway.gov.bd",
    "Referer": "https://eticket.railway.gov.bd/",
}


def get_token():
    if USE_EXISTING_TOKEN:
        return EXISTING_TOKEN

    headers = {**COMMON_HEADERS, "Content-Type": "application/json"}
    resp = requests.post(
        f"{BASE}/app/auth/sign-in",
        json={"mobile_number": MOBILE_NUMBER, "password": PASSWORD},
        headers=headers,
        timeout=15,
    )
    print("LOGIN status:", resp.status_code)
    print("LOGIN body:", resp.text[:1000])
    resp.raise_for_status()
    data = resp.json()

    token = None
    if isinstance(data.get("data"), dict):
        token = data["data"].get("token")
    if not token:
        token = data.get("token")

    print("\nExtracted token (first 12 chars):", (token or "")[:12], "...")
    return token


def search_trips(token, label):
    headers = dict(COMMON_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {
        "from_city": FROM_CITY,
        "to_city": TO_CITY,
        "date_of_journey": DATE_OF_JOURNEY,
        "seat_class": SEAT_CLASS,
    }
    resp = requests.get(
        f"{BASE}/web/bookings/search-trips-v2",
        params=params,
        headers=headers,
        timeout=15,
    )
    print(f"\n--- {label} ---")
    print("SEARCH status:", resp.status_code)
    try:
        print("SEARCH body:\n", json.dumps(resp.json(), indent=2)[:4000])
    except Exception:
        print("SEARCH raw body:", resp.text[:2000])


RUN_CONTROL_TEST = False  # flip to True later once we're past the current rate limit

if __name__ == "__main__":
    token = get_token()
    search_trips(token, "WITH auth token")
    if RUN_CONTROL_TEST:
        search_trips(None, "WITHOUT auth token (control)")
