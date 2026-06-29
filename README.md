# railalert

> **Note:** this file describes the original Postgres migration step. The
> project has grown a lot since -- a full web app now exists in `webapp/`,
> and `worker.py` is now a thin wrapper around `webapp/cron_logic.py` (see
> that folder's README for the current setup, including the move to
> cron-job.org for reliable scheduling). Kept here as a record of the
> original setup steps below.

Multi-tenant version: customers will eventually sign up through a web app
(not built yet), pick trains to watch, and pay a flat fee per watch. This
step replaces the single JSON-file state from the personal-use version with
a shared Postgres database, so the worker can serve many customers at once
and many customers watching the same train only cost one API call.

`watch.py`, `watches.json`, and `state.json` are retired -- delete them from
your repo (`git rm watch.py watches.json state.json`). `worker.py` replaces
all three.

## What changed from the personal-use version

- State lives in Postgres now, not in a file committed back to git. The
  workflow no longer needs a "commit updated state" step or write access to
  the repo.
- The worker can serve many customers' watches in one run. Identical
  (route, date, class) lookups across customers are deduped into a single
  API call.
- Two alerting modes per watch: `active` (only pings on a genuine 0 -> >0
  transition, same as before) and `reminder` (pings every ~30 minutes while
  seats remain available -- entered when a customer says "couldn't buy").
- No web app yet. For now, watches are created and managed by hand directly
  in Supabase's table editor. That's enough to prove the worker works
  end-to-end against the new database before building the actual signup
  flow on top of it.

## One-time setup

1. **Create a free Supabase project** at supabase.com. Free projects pause
   after 7 days of *inactivity* -- since our own worker queries the database
   every 5 minutes, that pause should never actually trigger in practice.

2. **Run the schema.** In the Supabase dashboard: SQL Editor -> paste the
   contents of `schema.sql` -> Run.

3. **Get your connection string.** Project Settings -> Database -> Connection
   string (URI format). This is your `DATABASE_URL`.

4. **Insert one test user and one test watch by hand**, reusing the exact
   train we already confirmed works, so this run validates the new
   Postgres-backed worker against data we already trust:
   ```sql
   INSERT INTO users (email, password_hash)
   VALUES ('you@example.com', 'placeholder')
   RETURNING id;
   -- note the id this returns, then:

   INSERT INTO watches (
     user_id, from_city, to_city, date_of_journey, train_model,
     train_label, seat_class_param, is_paid, status, action_token
   ) VALUES (
     1,                          -- the id from above
     'Chattogram', 'Dhaka',
     '2026-07-03',               -- pick a date still inside the ~10-day booking window
     '721', 'Mohanagar Express (721)',
     'S_CHAIR', true, 'active', 'test-token-123'
   );
   ```

5. **Update GitHub Secrets.** Add `DATABASE_URL` (from step 3). Your
   `RAIL_TOKEN` / `RAIL_DEVICE_ID` / `RAIL_DEVICE_KEY` / `SMTP_USER` /
   `SMTP_PASS` secrets stay the same as before. Add `OPERATOR_EMAIL` (where
   "token expired" alerts go -- can be the same as `SMTP_USER`). You can
   skip `APP_BASE_URL` for now; it only matters once the web app exists and
   the email action links need somewhere real to point.

6. **Test manually.** Actions tab -> "Rail Seat Watcher" -> "Run workflow".
   Then check, in Supabase's table editor:
   - `watches.last_counts` on your test row -- should now show real seat
     counts for train 721, same shape as what we saw from the live API
     earlier.
   - `ping_log` -- should be empty on this first run (cold-start baseline,
     same fix as before -- no alert on a watch's very first observation).

   To actually see an alert fire, edit `last_counts` in the table editor to
   set one class to `0`, then run the workflow again manually.

## What's next

The web app: signup/login, a form to create a watch, a dashboard showing
ping history, the bKash payment confirmation step, and the actual pages the
email action links point to. None of that exists yet -- this step only
proves the worker + database side works.
