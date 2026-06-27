# railalert

Watches a specific train/route/date on Bangladesh Railway's e-ticketing
backend and emails you the moment a seat opens up (refund released, or a
newly added compartment). Runs on a free GitHub Actions schedule.

## How it works

Every 5 minutes, GitHub Actions runs `watch.py`, which calls the same
backend API the official site/app uses, compares the result to the last
run (saved in `state.json`, committed back to the repo each time), and
emails you if any seat type goes from 0 online seats to more than 0.

The API requires a personal access token tied to your account, and that
token expires roughly every 12 hours. Getting a fresh one means logging in
through a real browser (the login endpoint has a bot-check that this
project intentionally does not try to get around) and copying it out
manually. That's the one recurring manual step here.

## One-time setup

1. **Put this code in its own GitHub repo.**
   If you already have a local folder for this (e.g. the one you were
   testing in), copy these files into it, then:
   ```
   git init
   git add .
   git commit -m "initial commit"
   git branch -M main
   git remote add origin https://github.com/<you>/railalert.git
   git push -u origin main
   ```
   A **public** repo gets unlimited free Actions minutes; a **private** one
   gets ~2000 min/month free, which a 5-minute schedule can get close to
   over a full month. Nothing committed here is sensitive (your credentials
   never go into any file, only into GitHub Secrets below) — the only thing
   a public repo reveals is which route/date you're watching, in
   `watches.json`. Pick whichever trade-off you're comfortable with; switch
   to `*/10 * * * *` in the workflow file if you go private and want more
   headroom.

2. **Get a Gmail App Password** (or use any other SMTP provider):
   - Turn on 2-Step Verification on the Google account you want to send from.
   - Go to https://myaccount.google.com/apppasswords, create one for "Mail".
   - Copy the 16-character password it gives you.

3. **Add repository secrets.**
   In your repo: Settings → Secrets and variables → Actions → New repository secret.
   Add these:
   - `RAIL_TOKEN` — see step 4
   - `RAIL_DEVICE_ID` — see step 4
   - `RAIL_DEVICE_KEY` — see step 4
   - `SMTP_USER` — the Gmail address you created the app password for
   - `SMTP_PASS` — the 16-character app password from step 2
   - `EMAIL_TO` — where you want the alerts sent (can be the same as `SMTP_USER`)

4. **Get your token and device headers.**
   - Log into `eticket.railway.gov.bd` in a normal browser.
     (Since the token already shared in our earlier chat session is exposed,
     get a completely fresh one now — ideally after changing your password.)
   - Do any train search on the site so a request fires.
   - Open dev tools → Network tab → click the `search-trips-v2` request.
   - In its Request Headers, copy the values of `authorization` (just the
     part after `Bearer `), `x-device-id`, and `x-device-key`.
   - Paste each into the matching secret from step 3.

5. **Edit `watches.json`** with the train(s) you actually want to watch.
   - `from_city` / `to_city`: as used on the site (e.g. `"Dhaka"`, `"Chattogram"`)
   - `date_of_journey`: format is `DD-MMM-YYYY`, e.g. `"10-Jul-2026"`
   - `train_model`: the number in parentheses after the train's name on the
     site/app, e.g. for "MOHANAGAR EXPRESS (721)" this is `"721"`
   - `seat_class_param`: any class that train actually offers (this is a
     required search parameter, not a filter — the response still includes
     every class the train has). `S_CHAIR` is a safe default for most
     intercity trains.
   - `label`: anything readable — it's just used to identify this watch in
     emails and in `state.json`.

   You can list more than one watch in the array if you want to track
   several trains/dates at once.

6. **Test it manually before trusting the schedule.**
   Repo → Actions tab → "Rail Seat Watcher" → "Run workflow". Check the run
   log for errors, and check that `state.json` got updated with real seat
   counts afterward.

Once that run succeeds, the schedule takes over and you don't need to do
anything else until the token expires again in ~12 hours, at which point
you'll get an email telling you so.

## Known limitations

- **GitHub's cron isn't exact.** Scheduled runs can lag by a few minutes
  during platform load. This isn't a guarantee of a check every 300 seconds
  on the dot.
- **No fully automatic re-login.** That's by design — automating past the
  login bot-check isn't something this project does.
- **Single quota tracked.** This watches the *online* booking quota (what
  you can actually buy through the site/app), not the separate counter
  quota.
- If you change your account password, your current token will likely stop
  working immediately — refresh the secrets right after, not before.
