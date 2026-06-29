# railalert web app

Signup, login, a live train search (calls the real railway API the same way
the cron job does), bKash payment instructions, dashboard with notification
history, and the pages the worker's email action links point to. Talks to
the same Postgres database as the cron job.

## Step: moving off GitHub Actions for reliability

The actual seat-checking logic now lives in `cron_logic.py`, called from
two places during this transition:

- `worker.py` (repo root) -- still run by GitHub Actions, unchanged behavior
- `/internal/cron` (this app) -- the new path, meant to be driven by
  cron-job.org instead

Both are safe to run at once: a Postgres advisory lock means if one is
already mid-run, the other just skips rather than double-processing and
sending duplicate emails. Once the new path has run reliably for a while,
`worker.py` and the GitHub Actions workflow get deleted and this becomes the
only path -- not yet, deliberately, so there's no gap in coverage while this
is being proven out.

### One-time setup for this step

1. **Run the migration.** Supabase -> SQL Editor -> paste the contents of
   `migrations/001_cron_health.sql` -> Run. (Purely additive -- adds columns,
   doesn't touch existing data or behavior.)
2. **Generate a cron secret** and add it as a new Render environment
   variable, `CRON_SECRET`:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
3. **Redeploy** so Render picks up the new env var and code.
4. **Test it by hand first.** Visit
   `https://your-app.onrender.com/internal/cron?key=YOUR_CRON_SECRET`
   directly in a browser. You should get back a short status line like
   `ok: 1 unique search(es), 2 watch(es), 0 alert(s) sent`. Then check
   Supabase's `worker_state` table -- `last_run_at` should be the current
   time, `last_run_ok` should be `true`.
5. **Set up cron-job.org**: create a free account, create a new cron job
   pointed at that same URL, interval every 5 minutes. Leave it running
   alongside GitHub Actions for now.
6. **Watch it for a while** (a day or so is plenty) before we retire the
   GitHub Actions workflow in a later step -- want to see it actually hit
   that 5-minute cadence reliably first.

## Environment variables

- `DATABASE_URL` -- same Supabase connection string the worker uses
- `RAIL_TOKEN`, `RAIL_DEVICE_ID`, `RAIL_DEVICE_KEY` -- same values as the
  worker's GitHub Secrets (update both places when you refresh the token)
- `CRON_SECRET` -- random string gating the `/internal/cron` route (new, see above)
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

