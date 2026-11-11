# Plan: host Portfolio Analyzer for friends (multi-user)

*Written 2026-11-11. Status: **proposal, not started.***

Today the app runs on one laptop for one person. This plan turns it into a single hosted site that a few invited friends sign in to, where each person sees only their own portfolio. Market data (prices, NAVs, fundamentals, signals) is downloaded once and shared by everyone.

Like the UI redesign, the work is split into phases with a check after each one. Nothing gets bought or deployed until **Phase 0** shows that the data sources work from a cloud server.

---

## 1. Where the app is today

Each of these assumptions has to change before strangers' data can share a server:

| Area | Today | Why it blocks hosting |
|---|---|---|
| Users | None. `UserProfile` and `SheetSettings` are single rows (`id=1`). | Everyone would share, and overwrite, one portfolio. |
| Access | Bound to `127.0.0.1`; CORS allows only `localhost:5173`. | Fine on a laptop. Online, anyone with the URL could see everything. |
| Database | SQLite (`backend/var/app.db`, ~124 MB and growing with the nightly top-up). Upserts use `sqlalchemy.dialects.sqlite.insert` (`data/store.py`, `analysis/signals.py`, `analysis/checks.py`). Tables come from `create_all`, with no migrations. | SQLite holds up poorly when several users write at once, and there's no safe way to change the schema on a live database. |
| Background work | APScheduler and the job thread pool run inside the API process (`main.py` lifespan, `jobs/runner.py`). Only one job of each kind runs at a time, app-wide. | One friend's import would block another's, and running more than one web worker would start the scheduler twice. |
| Thresholds | Edits from Settings go to `var/profiles.local.yaml`, one file for the whole app. | One user's edits would change everyone's signals. |
| Google Sheets | Anyone can upload a service-account key in Settings; it is saved to `secrets/`. | Users' private keys would be stored on a shared server. |
| Frontend | Served by `vite` dev server; backend runs `uvicorn --reload`. | These are development servers: slow, and not safe on the open internet. |
| Heavy jobs | Anyone can start a whole-market scan (several hours) or a forced re-download. | One click could use up the shared Yahoo rate limit for everyone. |

---

## 2. Requirements

### 2.1 Functional

- **F1. Invite-only sign-in.** Only email addresses on an allowlist can get in. Sign-in uses Google; the app never stores passwords.
- **F2. Private portfolios.** Holdings, snapshots, imports, ticker/scheme fixes, watchlist, saved screens, Screener.in uploads, AMC portfolio uploads, Sheets settings and the investing profile (style, risk, edited thresholds) all belong to one user. No other user can see them, through any page, API endpoint, export or log.
- **F3. Shared market data.** Daily/intraday bars, NAVs, fundamentals, delivery stats, reference lists, signal/axis history and Nifty scan results are stored once and used by everyone.
- **F4. Same features as the laptop version.** Every page works per user: Overview, Holdings, a stock's page, Mutual funds, Compare, Screener, Watchlist, Import, Export (CSV/HTML/PDF) and Settings.
- **F5. Daily refresh covers everyone.** The scheduled jobs refresh the union of all users' holdings, plus the nightly top-up, once rather than once per user.
- **F6. Fair use.** Ordinary users can refresh their own holdings and run scans on cached data or an index up to the Nifty 500. Whole-market scans, forced re-downloads and changing data-source settings are **admin only**.
- **F7. Google Sheets without user keys.** The app has one service account of its own. A user shares their sheet with its email address, or uses a "Publish to web" CSV link. Users can't upload keys.
- **F8. Admin page.** For you: manage the allowlist, see who signed in when, see job status and source health, and remove a user.
- **F9. Your own data.** Users can download all their data (CSV/JSON) and delete their account. Deleting an account removes their rows within a day, and from backups once those expire.
- **F10. Disclaimer.** Every user accepts the "not investment advice" notice on first sign-in. It stays in the footer.

### 2.2 Non-functional

- **N1. Security.** HTTPS everywhere. Session cookies are `HttpOnly`, `Secure` and `SameSite=Lax`. CSRF protection on writes, upload size and type limits (already present for imports), and security headers. Secrets live in env vars or files outside the repo. The server firewall allows only ports 22, 80 and 443, and SSH accepts keys only.
- **N2. Isolation is tested.** An automated test signs in as user A and user B and calls **every** API route, failing if B ever gets A's data. It runs in CI on every push.
- **N3. Performance.** Pages respond about as fast as on the laptop for up to 20 users. Expected peak: 5 people at once.
- **N4. Availability.** Best effort, around 99%. Downtime for updates is acceptable at night. Data is never lost: nightly backups, kept for 14 days, stored off the server, and a restore tested once.
- **N5. Privacy.** Logs never contain holdings, quantities or values. Backups are encrypted, and only you (admin) can reach the server. A short privacy note says what's stored and why.
- **N6. Cost.** Under about ₹1,500 a month all-in for up to 20 users.
- **N7. Maintainability.** One `docker compose -f docker-compose.prod.yml up -d` runs everything. Schema changes go through migrations. Pushing to `main` with green CI deploys, or deploys after one manual approve. Laptop mode (`make dev`) keeps working, with no sign-in in single-user mode.
- **N8. Latency.** The server is in or near India: Mumbai, Bangalore or Singapore.

### 2.3 Out of scope

- Public sign-up, paid plans, or more than about 50 users.
- A native phone app. The site will work in a phone browser, which is a side benefit.
- Broker logins or placing orders. That stays out, as it is today.

---

## 3. Target design

```
               Internet (HTTPS only)
                      │
               ┌──────▼──────┐
               │    Caddy    │  automatic Let's Encrypt certificate,
               │ (reverse    │  serves the built frontend (static files),
               │  proxy)     │  forwards /api to the backend
               └──┬───────┬──┘
                  │       │
         static files   ┌─▼──────────────┐
         (vite build)   │  api           │  FastAPI, uvicorn (2 workers),
                        │                │  sign-in, per-user queries
                        └──┬─────────────┘
                           │
   ┌───────────────┐   ┌───▼──────────┐
   │  worker       │──▶│  Postgres 17 │  per-user tables carry user_id;
   │  APScheduler +│   │              │  market tables are shared
   │  job runner   │   └──────────────┘
   └───────────────┘          │ nightly pg_dump → encrypted → off-site storage
```

### Key decisions (recommended; open to change)

1. **Postgres instead of SQLite.** It handles several writers at once, works with Alembic migrations, and has proper backup tools. The three SQLite-only upserts become one helper that picks the right dialect, so laptop mode can stay on SQLite.
2. **`user_id` on per-user tables, not one database per user.** That's one schema, one migration path, and shared market data stays shared. Isolation is enforced by a `current_user` dependency that every query goes through, and checked by test N2.
3. **Sign-in: Google OAuth inside the app** (Authlib, with a session cookie). The alternative is **Cloudflare Access** in front of the site, which is free for up to 50 users, means almost no sign-in code, and has its allowlist in the Cloudflare dashboard. The app would then read and verify the `Cf-Access-Jwt-Assertion` header. That's less code but ties you to Cloudflare. *Open question Q2.*
4. **A separate worker process** runs the scheduler and the long jobs. The API only queues jobs, so it can run more than one worker without starting jobs twice. The "one job per kind" rule becomes "one per kind **per user**" for user jobs, and stays global for market jobs.
5. **Per-user thresholds in the database.** `profiles.local.yaml` becomes a `user_thresholds` row layered over `profiles.yaml`. Signal and axis records already have `style` and `risk` in their keys. A user with custom thresholds gets their own computed results, cached separately per user (`user_id` in the key, or no caching when overrides exist).
6. **Laptop mode stays.** `AUTH_MODE=single` (the default) keeps today's behaviour: no sign-in, one implicit user with `id=1`, SQLite.

### Which table is whose

| Becomes per-user (`user_id`) | Stays shared |
|---|---|
| `UserProfile` (one per user), `Snapshot` → `StockHolding`, `MFHolding` → `MFTransaction`, `ColumnMapping`, `TickerOverride`, `SchemeOverride`, `ScreenerUpload`, `ScreenerData`, `FundPortfolioUpload`, `FundPortfolioRow`, `SavedScreen`, `WatchItem` (key becomes `user_id + ticker`), `SheetSettings`, `SheetSync`, `Job` (nullable owner: none means a system job) | `DailyBar`, `IntradayBar`, `NavPoint`, `SeriesStatus`, `DeliveryStat`, `BhavcopyDay`, `FundamentalsRaw`, `GrowthGuidance`, `FundamentalMetrics`, `SignalRecord`, `AxisRecord`, `FundInfo`, `ScreenerScan` (results for the default thresholds), reference CSVs |
| **New:** `User` (email, name, role, created, last seen, disclaimer accepted), `Invite` (email allowlist), `UserThresholds` | |

---

## 4. Phases

Each phase ends with tests passing and a short report, then waits for your go-ahead. Effort assumes working with Claude Code. "Days" means focused sessions, not calendar days.

### Phase 0: Feasibility check (½ day, about ₹100)
Rent the cheapest server in the chosen region for an hour or two. Run a script that downloads from every source in `docs/DATA_SOURCES.md` (Yahoo daily + fundamentals, NSE archives, BSE bhavcopy, mfapi, AMFI) at the configured rate limits, then delete the server.
- **Go:** every source works, or Yahoo works with a few retries.
- **No-go:** Yahoo or NSE blocks the server's IP. Fallbacks: try another provider or region; route the fetches through a small home machine (a Raspberry Pi or an old laptop) that pushes data to the server; or stay on option 1 (everyone runs it locally).

### Phase 1: Postgres and migrations (2–3 days)
- Add Alembic. The first migration matches the current schema exactly.
- Replace the SQLite-only `insert … on_conflict` calls with a helper that picks the dialect.
- Run the test suite against both SQLite and Postgres in CI (Postgres as a GitHub Actions service).
- Add a script that copies an existing SQLite database into Postgres, checks row counts, and spot-checks values.
- **Done when:** all tests pass on both databases, and your real database, copied over, shows identical Overview numbers.

### Phase 2: Users and data ownership (3–4 days)
- Add the `User`, `Invite` and `UserThresholds` tables, plus `user_id` on the per-user tables from §3, with a migration that gives all existing rows to user 1 (you).
- Add a `current_user` dependency. Every route and every per-user query filters on it, including exports, PDF generation, Sheets sync and the importers.
- Thresholds come from `profiles.yaml` plus that user's overrides. Results are cached per user when overrides exist.
- Make user-started jobs one per kind per user.
- **The isolation test (N2)** covers every route in `app/api/*`.
- **Done when:** in `AUTH_MODE=single` everything behaves exactly as before, and with two test users the isolation test passes.

### Phase 3: Sign-in, roles and the admin page (2–3 days)
- Google OAuth (or Cloudflare Access, per Q2). Session cookie, logout, an "accept disclaimer" step, and roles `admin` and `user`.
- Frontend: a sign-in page, a "signed in as …" menu with sign-out, admin-only controls hidden for users, and server-side checks as well.
- Admin page: invites, users, last seen, remove user, and a jobs and source-health summary.
- "Download my data" and "Delete my account".
- **Done when:** a non-invited Google account can't get in, a user can't call admin endpoints (checked by tests), and deleting a user removes their rows.

### Phase 4: Shared jobs and fair use (1–2 days)
- Move the scheduler and job runner into a `worker` process. The API queues jobs and the worker runs them (the Job table already works as a queue).
- The daily refresh fetches the union of every user's holdings.
- Whole-market scans, forced re-downloads and data-source settings become admin only. Per-user rate limits: for example, 10 manual refreshes an hour and 1 scan running at a time.
- Google Sheets: remove key upload when `AUTH_MODE=multi`, and show the app's service-account email to share sheets with.
- **Done when:** two users importing and refreshing at the same time both finish, and the scheduler runs once.

### Phase 5: Production packaging (1–2 days)
- `docker-compose.prod.yml` with `caddy`, `api`, `worker`, `postgres` and `backup` services. The frontend is built into static files that Caddy serves. No `--reload` and no source mounts.
- Settings through `.env.prod`: `AUTH_MODE=multi`, the domain, OAuth client, secret key, database URL, backup target. A `.env.prod.example` documents each one.
- Security headers, upload limits, `/health` for monitoring, logs in JSON without portfolio data.
- Nightly `pg_dump`, compressed and encrypted (`age`), uploaded off-site and kept for 14 days, plus a restore script.
- **Done when:** the whole stack runs locally with production settings over HTTPS (Caddy's local CA), and a backup restores into an empty database.

### Phase 6: Go live (1 day)
- Buy a domain and point DNS at the server. Create the server: Ubuntu LTS, SSH keys only, `ufw` firewall, automatic security updates, Docker.
- Create the Google OAuth client, deploy, migrate your laptop database (Phase 1 script), and confirm your numbers match.
- Invite one or two friends first, fix what they find, then the rest.
- Update the README with a "Use the hosted version" section and keep the laptop install instructions.

### Phase 7: Running it (ongoing, about 1 hour a month)
- Uptime monitoring: a free UptimeRobot or Healthchecks.io ping, which emails you if the site or the nightly backup stops.
- A GitHub Actions deploy: tests, build images, then SSH to the server and `docker compose pull && up -d`, with a manual approve step.
- Monthly: apply updates, check disk use, and test one backup restore every quarter.

**Total: about 11–17 focused days of work, then roughly an hour a month.**

---

## 5. Pricing

*Approximate, checked online on 2026-11-11. Cloud prices changed several times in 2026 (Hetzner raised prices in April and June; Fly.io changed RAM pricing from 1 Oct 2026), so confirm on the provider's own page before buying. Conversions assume about ₹88 to US$1 and about ₹100 to €1.*

### What the app needs
- **RAM:** 2 GB at minimum, 4 GB to be comfortable. pandas and the indicator code run in both `api` and `worker`, plus Postgres and Caddy.
- **CPU:** 2 vCPU. Scans and backtests are CPU-heavy but rare.
- **Disk:** at least 40 GB SSD. The database is 124 MB today; with most of the ~4,500 stocks loaded (5 years of daily bars plus fundamentals), expect 1–3 GB, plus Docker images, logs and local backup copies.
- **Bandwidth:** small, well under 100 GB a month.

### Option A: one VPS (recommended)

| Item | Choice | Approx. monthly cost |
|---|---|---|
| Server | **DigitalOcean, Bangalore (BLR1)**: 1–2 vCPU, 2 GB, 50 GB SSD, about US$12–18. Best latency from India. | ₹1,050–1,600 |
| *or* Server | **Hetzner Cloud CX23-class** (2 vCPU, 4 GB, 40 GB), about €5.50 plus €0.50 for IPv4. Germany/Finland, so about 150 ms from India; Hetzner's Singapore region costs more. Best value per GB of RAM. | ₹600–700 |
| Off-site backups | Backblaze B2 or Cloudflare R2: well under 10 GB of encrypted dumps. | ₹0–50 |
| Domain | A `.in` or `.com` domain, about ₹800–1,200 a year. | ₹70–100 |
| HTTPS certificate | Let's Encrypt through Caddy. | ₹0 |
| Sign-in | Google OAuth (free) or Cloudflare Access (free up to 50 users). | ₹0 |
| Monitoring | UptimeRobot or Healthchecks.io free tier. | ₹0 |
| **Total** | | **about ₹700–1,750 a month** |

The provider's own server backups add about 20% of the server price. The off-site `pg_dump` covers the data, so they're optional.

### Option B: platform hosting (Fly.io / Railway / Render)
Fly.io from 1 Oct 2026: about US$6.70 a month per 1 GB shared-CPU machine, and volumes at US$0.15 per GB per month. This app needs about three machines (api, worker, Postgres, the last 2 GB+), so expect **about US$25–40 a month (₹2,200–3,500)**. Deploys are easier, but it costs more, there are more moving parts, and the same Yahoo IP risk applies. Not recommended at this size.

### Option C: managed Postgres
Neon or Supabase free tiers (about 0.5 GB) are too small once the full market is loaded; paid tiers start around US$19–25 a month. Not worth it. Run Postgres in Docker on the VPS and rely on the nightly encrypted dump.

Pricing pages to check before buying: [DigitalOcean Droplets](https://www.digitalocean.com/pricing/droplets), [Hetzner Cloud](https://www.hetzner.com/cloud), [Fly.io pricing](https://fly.io/docs/about/pricing/) and [2026 update](https://fly.io/pricing-update/), [Backblaze B2](https://www.backblaze.com/cloud-storage/pricing), [Cloudflare Zero Trust](https://www.cloudflare.com/plans/zero-trust-services/).

### One-off costs
- Phase 0 test server: about ₹100.
- Your time: about 11–17 focused days, as estimated above.

---

## 6. Risks

| Risk | Likelihood | Impact | What we do |
|---|---|---|---|
| Yahoo or NSE block or throttle cloud-server IPs | Medium–High | High: no fresh data | Phase 0 tests it before any spending. Fallback: a home machine fetches the data and pushes it to the server. |
| A bug shows one user another user's data | Low after N2 | Very high | `current_user` everywhere, the isolation test in CI, and a review of every route in Phase 2. |
| SEBI rules: Buy/Sell signals to other people could look like research or advice under the SEBI (Research Analysts) or (Investment Advisers) Regulations | Low for a free, private, invite-only tool | High | Keep it invite-only, free and unadvertised. Keep the disclaimer and require it to be accepted. Don't present it as advice or charge for it. *This is not legal advice; ask a professional before going beyond friends.* |
| India's DPDP Act 2023: you'd be processing friends' personal financial data | Certain (you hold the data) | Medium | Consent at sign-in, a short privacy note, store the minimum, export and delete-my-data (F9), encrypted backups, access limited to you. |
| The server is compromised | Low | High | SSH keys only, firewall, automatic security updates, no secrets in the repo, Postgres not exposed to the internet, regular image updates. |
| Costs creep up (bigger server, provider price rises) | Medium | Low | Size the server for the actual load, and review the bill monthly. |
| You become everyone's support desk | Medium | Medium | Keep the in-app feedback link (GitHub issues) and a short FAQ. |

---

## 7. Open questions for you

- **Q1. Server:** DigitalOcean Bangalore (lower latency, about ₹1,050–1,600 a month) or Hetzner (cheaper, more RAM, slower from India)? *Recommended: decide after Phase 0, and test DigitalOcean Bangalore first.*
- **Q2. Sign-in:** Google sign-in built into the app, or Cloudflare Access in front of it? *Recommended: Google in-app, since it doesn't tie you to Cloudflare and keeps a proper user model.*
- **Q3. Domain name:** do you have one, or should we pick one?
- **Q4. Friends:** about how many, and do they all have Google accounts?
- **Q5. Custom thresholds:** should friends be able to edit thresholds, or only pick style and risk (simpler, and everyone shares cached results)? *Recommended: style and risk only at first.*
- **Q6. Google Sheets:** do your friends need Sheets sync at all, or are file imports enough? If imports are enough, Sheets can be admin-only at first.
