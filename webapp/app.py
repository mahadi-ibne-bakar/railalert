import json
import os
import secrets
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import railway_api
from db import get_conn, get_cursor

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

BKASH_NUMBER = os.environ.get("BKASH_NUMBER", "01XXXXXXXXX")
WATCH_FEE_BDT = os.environ.get("WATCH_FEE_BDT", "100")

# Same booking window the railway site itself enforces -- search dates
# further out than this won't return anything useful.
BOOKING_WINDOW_DAYS = 10

with open(os.path.join(os.path.dirname(__file__), "stations.json")) as f:
    STATIONS = json.load(f)


@app.before_request
def open_db():
    g.conn = get_conn()
    g.cur = get_cursor(g.conn)


@app.teardown_request
def close_db(exc):
    cur = g.pop("cur", None)
    conn = g.pop("conn", None)
    if cur:
        cur.close()
    if conn:
        conn.close()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    g.cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
    return g.cur.fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def get_owned_watch(watch_id):
    """Fetch a watch, but only if it belongs to the logged-in user."""
    user = current_user()
    g.cur.execute("SELECT * FROM watches WHERE id = %s AND user_id = %s", (watch_id, user["id"]))
    watch = g.cur.fetchone()
    if not watch:
        abort(404)
    return watch


def get_watch_by_token(watch_id, token):
    """Fetch a watch via its per-watch action token (used by email links, no login)."""
    g.cur.execute("SELECT * FROM watches WHERE id = %s AND action_token = %s", (watch_id, token))
    watch = g.cur.fetchone()
    if not watch:
        abort(404)
    return watch


def apply_action(watch_id, action, qty=None):
    if action == "done":
        g.cur.execute(
            "UPDATE watches SET status = 'done', updated_at = now() WHERE id = %s", (watch_id,)
        )
    elif action == "remind":
        g.cur.execute(
            "UPDATE watches SET status = 'reminder', updated_at = now() WHERE id = %s",
            (watch_id,),
        )
    elif action == "stop":
        g.cur.execute(
            "UPDATE watches SET status = 'stopped', updated_at = now() WHERE id = %s",
            (watch_id,),
        )
    elif action == "bought_some" and qty:
        g.cur.execute(
            """
            UPDATE watches SET tickets_acquired = tickets_acquired + %s, updated_at = now()
            WHERE id = %s
            RETURNING tickets_acquired, tickets_needed
            """,
            (qty, watch_id),
        )
        row = g.cur.fetchone()
        if row["tickets_acquired"] >= row["tickets_needed"]:
            g.cur.execute("UPDATE watches SET status = 'done' WHERE id = %s", (watch_id,))


# --- auth ---


@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user() else url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form["password"]
        if len(password) < 8:
            flash("Password needs to be at least 8 characters.")
            return render_template("signup.html")
        g.cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if g.cur.fetchone():
            flash("That email is already registered. Try logging in instead.")
            return render_template("signup.html")
        g.cur.execute(
            "INSERT INTO users (email, phone, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (email, phone, generate_password_hash(password)),
        )
        session["user_id"] = g.cur.fetchone()["id"]
        return redirect(url_for("dashboard"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        g.cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = g.cur.fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Incorrect email or password.")
            return render_template("login.html")
        session["user_id"] = user["id"]
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- watches (logged-in customer) ---


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    g.cur.execute(
        "SELECT * FROM watches WHERE user_id = %s ORDER BY created_at DESC", (user["id"],)
    )
    return render_template("dashboard.html", watches=g.cur.fetchall())


@app.route("/watches/new", methods=["GET", "POST"])
@login_required
def new_watch():
    today = date.today()
    max_date = today + timedelta(days=BOOKING_WINDOW_DAYS)

    if request.method == "POST":
        from_city = request.form["from_city"].strip()
        to_city = request.form["to_city"].strip()
        date_of_journey = request.form["date_of_journey"]  # ISO, e.g. 2026-07-03

        api_date = datetime.strptime(date_of_journey, "%Y-%m-%d").strftime("%d-%b-%Y")
        try:
            trains = railway_api.fetch_trains(from_city, to_city, api_date)
        except railway_api.TokenExpired:
            flash("Search is temporarily unavailable. Please try again shortly.")
            return redirect(url_for("new_watch"))
        except Exception:
            flash("Couldn't reach the railway search right now. Please try again.")
            return redirect(url_for("new_watch"))

        return render_template(
            "search_results.html",
            trains=trains,
            from_city=from_city,
            to_city=to_city,
            date_of_journey=date_of_journey,
            display_date=date.fromisoformat(date_of_journey).strftime("%d %b %Y"),
        )

    return render_template(
        "new_watch.html",
        stations=STATIONS,
        today=today.isoformat(),
        max_date=max_date.isoformat(),
    )


@app.route("/watches/create", methods=["POST"])
@login_required
def create_watch():
    user = current_user()
    available_classes = [c for c in request.form["available_classes"].split(",") if c]
    seat_classes = [c for c in available_classes if request.form.get(f"class_{c}")]
    # Pick a search parameter the train is confirmed to actually have (we
    # just saw its real seat_types). If the customer didn't narrow it down,
    # fall back to whichever class that train showed first.
    seat_class_param = seat_classes[0] if seat_classes else (available_classes or ["S_CHAIR"])[0]
    token = secrets.token_urlsafe(24)

    g.cur.execute(
        """
        INSERT INTO watches (
            user_id, from_city, to_city, date_of_journey, train_model,
            train_label, seat_classes, seat_class_param, tickets_needed,
            action_token, status, is_paid
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending_payment', false)
        RETURNING id
        """,
        (
            user["id"],
            request.form["from_city"].strip(),
            request.form["to_city"].strip(),
            request.form["date_of_journey"],
            request.form["train_model"].strip(),
            request.form["train_label"].strip(),
            seat_classes,
            seat_class_param,
            request.form.get("tickets_needed", default=1, type=int),
            token,
        ),
    )
    watch_id = g.cur.fetchone()["id"]
    return redirect(url_for("payment_instructions", watch_id=watch_id))


@app.route("/watches/<int:watch_id>/payment")
@login_required
def payment_instructions(watch_id):
    watch = get_owned_watch(watch_id)
    return render_template(
        "payment_instructions.html", watch=watch, bkash_number=BKASH_NUMBER, fee=WATCH_FEE_BDT
    )


@app.route("/watches/<int:watch_id>")
@login_required
def watch_detail(watch_id):
    watch = get_owned_watch(watch_id)
    g.cur.execute(
        "SELECT * FROM ping_log WHERE watch_id = %s ORDER BY created_at DESC", (watch_id,)
    )
    return render_template("watch_detail.html", watch=watch, pings=g.cur.fetchall())


@app.route("/watches/<int:watch_id>/act", methods=["POST"])
@login_required
def watch_act(watch_id):
    get_owned_watch(watch_id)  # ownership check; raises 404 if not yours
    apply_action(watch_id, request.form["action"], request.form.get("qty", type=int))
    return redirect(url_for("watch_detail", watch_id=watch_id))


# --- email action links: identified by a per-watch token, no login needed ---


@app.route("/watch/<int:watch_id>/action")
def email_action(watch_id):
    get_watch_by_token(watch_id, request.args.get("token", ""))
    action = request.args.get("action", "")
    if action not in ("done", "remind", "stop"):
        abort(400)
    apply_action(watch_id, action)
    return render_template("action_confirm.html", action=action)


@app.route("/watch/<int:watch_id>/bought-some", methods=["GET", "POST"])
def email_bought_some(watch_id):
    token = request.args.get("token", "")
    watch = get_watch_by_token(watch_id, token)
    if request.method == "POST":
        qty = request.form.get("qty", type=int) or 0
        apply_action(watch_id, "bought_some", qty)
        return render_template("action_confirm.html", action="bought_some")
    return render_template("bought_some.html", watch=watch, token=token)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
