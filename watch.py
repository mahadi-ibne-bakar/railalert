"""
Bangladesh Railway seat watcher.

Checks a list of (train, route, date) watches against the live booking API,
compares the result to the last run, and emails when:
  - any seat type goes from 0 online seats to >0 (refund released, or a
    brand-new compartment showing up for the first time both count)
  - the access token has expired (sent once, not every run)

State is read from and written to state.json. This script does NOT commit
that file to git -- the GitHub Actions workflow does that as a separate step
after this script finishes, since this script only has filesystem access.
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText

import requests

API_BASE = "https://railspaapi.shohoz.com/v1.0"
WATCHES_FILE = "watches.json"
STATE_FILE = "state.json"
REQUEST_TIMEOUT = 20

# ---- credentials, injected as env vars by the GitHub Actions workflow ----
TOKEN = os.environ["RAIL_TOKEN"]
DEVICE_ID = os.environ["RAIL_DEVICE_ID"]
DEVICE_KEY = os.environ["RAIL_DEVICE_KEY"]

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_PASS"]
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

# Static headers copied from a real, working browser request. These mimic a
# real browser's fingerprint; only the three credential headers above change
# between login sessions.
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
        "authorization": f"Bearer {TOKEN}",
        "x-device-id": DEVICE_ID,
        "x-device-key": DEVICE_KEY,
    }


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [EMAIL_TO], msg.as_string())


class TokenExpired(Exception):
    pass


def fetch_trains(from_city, to_city, date_of_journey, seat_class_param):
    resp = requests.get(
        f"{API_BASE}/web/bookings/search-trips-v2",
        params={
            "from_city": from_city,
            "to_city": to_city,
            "date_of_journey": date_of_journey,
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


def check_one_watch(watch, state):
    """Returns (alerts_for_this_watch, updated_counts_or_None, auth_failed)."""
    key = watch["label"]
    try:
        trains = fetch_trains(
            watch["from_city"],
            watch["to_city"],
            watch["date_of_journey"],
            watch.get("seat_class_param", "S_CHAIR"),
        )
    except TokenExpired:
        return [], None, True
    except Exception as e:
        print(f"[{key}] fetch error: {e}", file=sys.stderr)
        return [], None, False

    train = find_train(trains, watch["train_model"])
    if train is None:
        # Train not present in this result set this round (could be a route/date
        # mismatch, a seat_class quirk, or it's just not running). Don't treat
        # this as "everything sold out" -- leave prior counts untouched so a
        # transient miss doesn't get reported as a drop to zero.
        print(f"[{key}] train_model {watch['train_model']} not found in response")
        return [], None, False

    prev_counts = state.get(key, {})
    new_counts = {}
    alerts = []

    for seat_type in train["seat_types"]:
        cls = seat_type["type"]
        online = seat_type["seat_counts"]["online"]
        fare = seat_type.get("fare")
        new_counts[cls] = online
        prev = prev_counts.get(cls, 0)
        if prev == 0 and online > 0:
            alerts.append(f"{key}\n  {cls}: {online} seat(s) now online (fare {fare})")

    return alerts, new_counts, False


def main():
    watches = load_json(WATCHES_FILE, [])
    state = load_json(STATE_FILE, {})

    all_alerts = []
    any_success = False
    any_auth_failure = False
    state_changed = False

    for watch in watches:
        alerts, new_counts, auth_failed = check_one_watch(watch, state)
        if auth_failed:
            any_auth_failure = True
            continue
        if new_counts is not None:
            any_success = True
            if new_counts != state.get(watch["label"], {}):
                state[watch["label"]] = new_counts
                state_changed = True
        all_alerts.extend(alerts)

    already_notified_expired = state.get("_token_expired_notified", False)

    if any_success and already_notified_expired:
        state["_token_expired_notified"] = False
        state_changed = True
    elif any_auth_failure and not already_notified_expired:
        send_email(
            "Rail watcher: token expired",
            "Your Bangladesh Railway access token has expired (or the "
            "device headers no longer match).\n\n"
            "Log into eticket.railway.gov.bd in a browser, grab a fresh "
            "token/x-device-id/x-device-key from dev tools, and update the "
            "RAIL_TOKEN (and RAIL_DEVICE_ID / RAIL_DEVICE_KEY if needed) "
            "secret in the GitHub repo.",
        )
        state["_token_expired_notified"] = True
        state_changed = True

    if all_alerts:
        send_email(
            "Seat available on your watched train",
            "A seat just opened up:\n\n" + "\n\n".join(all_alerts),
        )

    if state_changed:
        save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
