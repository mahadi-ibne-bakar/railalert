# railalert web app

Signup, login, "track a new train" form, bKash payment instructions,
dashboard with notification history, and the pages the worker's email
action links point to. Talks to the same Postgres database as `worker.py`.

## Environment variables

- `DATABASE_URL` -- same Supabase connection string the worker uses
- `SECRET_KEY` -- random string used to sign session cookies. Generate one with:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `BKASH_NUMBER` -- the number customers send payment to (default is a placeholder)
- `WATCH_FEE_BDT` -- the flat fee shown on the payment page (default `100`)

## Run it locally first

```bash
cd webapp
pip install -r requirements.txt
export DATABASE_URL="your-supabase-connection-string"
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export BKASH_NUMBER="01XXXXXXXXX"
export WATCH_FEE_BDT="100"
python3 app.py
```

Open `http://localhost:5000`. This connects to the **same Supabase database**
the worker uses, so:

1. Sign up with any email.
2. "Track a new train" -- use the same Mohanagar Express details we already
   validated (Chattogram -> Dhaka, train number `721`, a date within the
   booking window).
3. You'll land on a payment instructions page. The watch now exists in
   Supabase with `status = 'pending_payment'`, `is_paid = false`.
4. In Supabase's table editor, manually flip that row's `is_paid` to `true`
   and `status` to `active` -- this is standing in for you checking your
   bKash app and confirming a real payment.
5. Run the worker workflow manually (same as always). It should now pick up
   *this* watch alongside your test one.
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
- The "new watch" form makes you type the train name/number yourself
  (the same way you'd find it on the official site) -- there's no live
  train search built into this app.

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
