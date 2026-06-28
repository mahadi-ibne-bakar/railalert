# railalert web app

Signup, login, a live train search (calls the real railway API the same way
`worker.py` does), bKash payment instructions, dashboard with notification
history, and the pages the worker's email action links point to. Talks to
the same Postgres database as `worker.py`.

## What's new in this version

The "track a new train" flow no longer makes customers type a train
name/number by hand. They enter from/to/date, the app calls the real
`search-trips-v2` endpoint live (same as the worker), and they pick a
specific train and specific seat class(es) from real, current results.

This means **the web app now needs the operator's railway credentials too**
(`RAIL_TOKEN`, `RAIL_DEVICE_ID`, `RAIL_DEVICE_KEY`) -- previously only
`worker.py` used them. The header-building and request logic lives in
`railway_api.py` in this folder, imported by both this app and (via a
sys.path adjustment) `worker.py`, so there's one source of truth instead of
two copies drifting apart.

**Operational consequence**: every ~12 hours when you refresh the railway
token, it now needs to be updated in **two** places, not one -- the GitHub
Secret (for the worker) and the Render environment variable (for this app).
Forgetting the second one doesn't crash anything; live search just shows a
"temporarily unavailable" message until it's updated.

`stations.json` is a seed list of station names (in the railway API's own
spelling, e.g. `Biman_Bandar` with an underscore) used to power autocomplete
suggestions on the from/to fields. It's a starting point, not guaranteed
complete or permanently accurate -- worth periodically cross-checking
against the live API (e.g. via `/v1.0/web/train-routes` per train) rather
than treated as a fixed source of truth.

## Environment variables

- `DATABASE_URL` -- same Supabase connection string the worker uses
- `RAIL_TOKEN`, `RAIL_DEVICE_ID`, `RAIL_DEVICE_KEY` -- same values as the
  worker's GitHub Secrets (see the note above about updating both places)
- `SECRET_KEY` -- random string used to sign session cookies. Generate one with:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `BKASH_NUMBER` -- the number customers send payment to (default is a placeholder)
- `WATCH_FEE_BDT` -- the flat fee shown on the payment page (default `100`)

## Run it locally first

```bash
cd webapp
pip install -r requirements.txt
export DATABASE_URL="your-supabase-connection-string"
export RAIL_TOKEN="your-current-token"
export RAIL_DEVICE_ID="your-device-id"
export RAIL_DEVICE_KEY="your-device-key"
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export BKASH_NUMBER="01XXXXXXXXX"
export WATCH_FEE_BDT="100"
python3 app.py
```

Open `http://localhost:5000`. This connects to the **same Supabase database**
the worker uses, so:

1. Sign up with any email.
2. "Track a new train" -- enter a real route and a date within the next ~9
   days, search, and confirm real trains with real seat counts come back.
3. Pick a train and seat class(es), submit. You'll land on a payment
   instructions page. The watch now exists in Supabase with
   `status = 'pending_payment'`, `is_paid = false`.
4. In Supabase's table editor, manually flip that row's `is_paid` to `true`
   and `status` to `active` -- this is standing in for you checking your
   bKash app and confirming a real payment.
5. Run the worker workflow manually (same as always). It should now pick up
   *this* watch alongside any others.
6. Back in the web app, open the watch's detail page -- you should see its
   live seat counts reflected and, once you force an alert the same way as
   before, a row appear in its notification history.
7. Try the action buttons on that page (the in-app equivalent of the email
   links): "bought everything," "bought some, need more," "couldn't buy,"
   "stop." Each should update the watch's status and you should see it
   reflected immediately.

## Known gaps in this version (fine for now, worth knowing)

- No CSRF protection on forms. Acceptable at this scale -- worth adding
  (e.g. Flask-WTF) before this has real volume.
- No password reset flow yet.
- `stations.json` is a seed list, not a verified-complete or
  permanently-accurate one (see note above).

## Deploying (once local testing looks right)

Render, free tier, same account you'd use for everything else here:

1. New Web Service -> connect this GitHub repo.
2. **Root Directory:** `webapp` (this is a subfolder of the same repo the
   worker lives in).
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `gunicorn app:app`
5. Add the same environment variables as above, as Render environment
   variables (not GitHub Secrets -- this is a separate system).
6. Deploy. Render gives you a free `https://something.onrender.com` URL.
7. Update the `APP_BASE_URL` secret in **GitHub** (the worker's repo) to
   that URL, so the email action links the worker sends actually point
   somewhere real.

Free-tier Render web services sleep after 15 minutes of no traffic and take
30-60 seconds to wake back up on the next request -- fine for now, easy to
remove later by upgrading that one service if it bothers real customers.

