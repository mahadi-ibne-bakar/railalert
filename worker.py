"""
Multi-tenant Bangladesh Railway seat watcher worker.

Run on a schedule (GitHub Actions, same as before). Reads every active, paid
watch from Postgres, groups identical (route, date, class) lookups so many
customers watching the same train cost ONE API call rather than one each,
checks each watch's own criteria against the result, emails the matching
customer, and logs every notification.

This still only ever uses ONE Bangladesh Railway account -- yours, the
operator's. Customers never provide their own Railway credentials; seat
availability is the same regardless of whose token checks for it.
"""

import os
import smtplib
import sys
from collections import defaultdict
from datetime import date
from email.mime.text import MIMEText

import psycopg2
import psycopg2.extras

# railway_api.py lives in webapp/, shared with the web app's live search.
# GitHub Actions checks out the whole repo, so this folder is reachable even
# though this script itself sits at the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp"))
from railway_api import TokenExpired, fetch_trains, find_train  # noqa: E402

REMINDER_INTERVAL_MINUTES = 30  # how often to re-ping a watch in "reminder" mode

DATABASE_URL = os.environ["DATABASE_URL"]

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_PASS"]
OPERATOR_EMAIL = os.environ.get("OPERATOR_EMAIL", SMTP_USER)

# Placeholder until the web app has a real domain -- update this secret later.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://your-app-domain.example")


def send_email(to_addr, subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_addr
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [to_addr], msg.as_string())


def action_links(watch_id, token):
    base = f"{APP_BASE_URL}/watch/{watch_id}/action?token={token}"
    return (
        f"  Bought everything I needed:    {base}&action=done\n"
        f"  Bought some, still need more:  {APP_BASE_URL}/watch/{watch_id}/bought-some?token={token}\n"
        f"  Couldn't buy, keep reminding:  {base}&action=remind\n"
        f"  Stop watching this train:      {base}&action=stop\n"
    )


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Stop watching trains whose journey date has already passed.
    cur.execute(
        "UPDATE watches SET status = 'done', updated_at = now() "
        "WHERE status IN ('active', 'reminder') AND date_of_journey < %s",
        (date.today(),),
    )

    cur.execute(
        "SELECT w.*, u.email "
        "FROM watches w JOIN users u ON u.id = w.user_id "
        "WHERE w.is_paid = true AND w.status IN ('active', 'reminder')"
    )
    watches = cur.fetchall()

    # Group identical lookups: many customers watching the same train+date+class
    # cost exactly one API call, not one per customer.
    groups = defaultdict(list)
    for w in watches:
        key = (w["from_city"], w["to_city"], w["date_of_journey"], w["seat_class_param"])
        groups[key].append(w)

    # Guarantee this row exists rather than assuming schema.sql's seed insert
    # landed -- if it's ever missing (or gets deleted later), this heals it
    # instead of crashing every single run.
    cur.execute("INSERT INTO worker_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    cur.execute("SELECT token_expired_notified FROM worker_state WHERE id = 1")
    already_notified_expired = cur.fetchone()["token_expired_notified"]
    any_success = False
    any_auth_failure = False

    for (from_city, to_city, date_of_journey, seat_class_param), group in groups.items():
        try:
            trains = fetch_trains(
                from_city, to_city, date_of_journey.strftime("%d-%b-%Y"), seat_class_param
            )
            any_success = True
        except TokenExpired:
            any_auth_failure = True
            continue
        except Exception as e:
            print(f"fetch error for {from_city}->{to_city} {date_of_journey}: {e}")
            continue

        for w in group:
            train = find_train(trains, w["train_model"])
            if train is None:
                print(f"[watch {w['id']}] train_model {w['train_model']} not found")
                continue

            prev_counts = w["last_counts"] or {}
            is_first_observation = prev_counts == {}
            wanted_classes = set(w["seat_classes"]) or None  # None = any class
            new_counts = {}
            matched = []

            for seat_type in train["seat_types"]:
                cls = seat_type["type"]
                online = seat_type["seat_counts"]["online"]
                fare = seat_type.get("fare")
                new_counts[cls] = online

                if wanted_classes is not None and cls not in wanted_classes:
                    continue
                if online <= 0:
                    continue

                if w["status"] == "reminder":
                    matched.append((cls, online, fare))
                elif not is_first_observation and prev_counts.get(cls, 0) == 0:
                    matched.append((cls, online, fare))

            cur.execute(
                "UPDATE watches SET last_counts = %s, updated_at = now() WHERE id = %s",
                (psycopg2.extras.Json(new_counts), w["id"]),
            )

            should_ping = bool(matched) and not is_first_observation
            if not should_ping:
                continue

            if w["status"] == "reminder":
                cur.execute(
                    "SELECT (last_pinged_at IS NULL OR now() - last_pinged_at > interval %s) AS due "
                    "FROM watches WHERE id = %s",
                    (f"{REMINDER_INTERVAL_MINUTES} minutes", w["id"]),
                )
                if not cur.fetchone()["due"]:
                    continue

            lines = [f"  {c}: {n} seat(s) online (fare {f})" for c, n, f in matched]
            body = (
                f"{w['train_label']}, {from_city} to {to_city}, "
                f"{date_of_journey.strftime('%d %b %Y')}\n\n"
                + "\n".join(lines)
                + "\n\nWhat would you like to do?\n\n"
                + action_links(w["id"], w["action_token"])
            )
            send_email(w["email"], "Seat available on your watched train", body)

            for cls, online, fare in matched:
                cur.execute(
                    "INSERT INTO ping_log (watch_id, seat_class, seats_online, fare) "
                    "VALUES (%s, %s, %s, %s)",
                    (w["id"], cls, online, fare),
                )
            cur.execute("UPDATE watches SET last_pinged_at = now() WHERE id = %s", (w["id"],))

    if any_success and already_notified_expired:
        cur.execute("UPDATE worker_state SET token_expired_notified = false WHERE id = 1")
    elif any_auth_failure and not already_notified_expired:
        send_email(
            OPERATOR_EMAIL,
            "Rail watcher: token expired",
            "Your Bangladesh Railway access token has expired. Refresh "
            "RAIL_TOKEN / RAIL_DEVICE_ID / RAIL_DEVICE_KEY in GitHub Secrets.",
        )
        cur.execute("UPDATE worker_state SET token_expired_notified = true WHERE id = 1")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
