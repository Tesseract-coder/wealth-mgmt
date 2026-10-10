# Google Sheets setup

The app can **import** your holdings from a Google Sheet and **export** its analysis back to one.

| | Service account (recommended) | Published CSV link |
|---|---|---|
| Import holdings | ✓ any tab, sheet stays private | ✓ one published tab per link |
| Export analysis | ✓ | ✗ (read-only) |
| Setup | ~10 minutes, once | ~1 minute |
| Who can read the tab | Only you and the people you share with | **Anyone with the link** |

**What the app never does**
- It never asks for your Google password or your Groww or broker login.
- A *service account* is a separate robot identity in Google Cloud. It can open only the sheets you explicitly share with it.
- It never writes to tabs other than the four export tabs, and it asks before replacing a tab with those names that it didn't create.

---

## 1. Prepare the sheet

Use one Google Sheet. For importing, give it a tab per holding type:

| Tab (default name) | Columns (same as a Groww export; header names are matched loosely) |
|---|---|
| `Holdings_Stocks` | Company/Stock name, Quantity, Average price. ISIN or NSE symbol helps matching. Optional: LTP, Current value, P&L, Buy date |
| `Holdings_MF` | Scheme name, Units (or Current value), Invested. Optional: Folio, ISIN, AMFI code, Category, NAV, Purchase date |

The easiest way to fill these tabs:
1. Download your holdings from Groww (see [GROWW_EXPORT_GUIDE.md](GROWW_EXPORT_GUIDE.md)).
2. Paste them into the tabs.

Title rows above the header and "Total" rows are skipped, just as with an uploaded file. If a header isn't recognised, the app shows the same column-matching screen as for a file upload, and it remembers your answer.

The tab names can be changed in **Settings → Google Sheets**.

## 2a. Service account (import and export)

You need a Google account. Google Cloud is free for this and needs no billing account.

1. Open <https://console.cloud.google.com/> and create a project, for example `portfolio-analyzer` (project picker at the top → **New project**).
2. Turn on the Sheets API: **APIs & Services → Library**, search **Google Sheets API**, then click **Enable**.
3. Create the robot: **IAM & Admin → Service accounts → Create service account**. Name it something like `portfolio-bot`, click **Create and continue**, then **Done**. It needs no roles.
4. Make a key: open the service account, go to **Keys → Add key → Create new key → JSON → Create**. A `.json` file downloads.
   - Treat it like a password: anyone with it can edit any sheet shared with the robot.
5. Give the key to the app. Use one of these:
   - **Settings → Google Sheets → Upload the key**. It is saved as `secrets/service-account.json` and only your user can read it.
   - Copy the file to `secrets/service-account.json` yourself.
   - Put it anywhere and set `GOOGLE_SERVICE_ACCOUNT_FILE=/full/path/key.json` in `.env`, then restart.

   `secrets/` and `.env` are gitignored. Delete the downloaded copy from your Downloads folder afterwards.
6. Share the sheet with the robot:
   - The settings page shows the robot's e-mail address (`…@….iam.gserviceaccount.com`). Click **Copy**.
   - In your sheet, click **Share**, paste the address, choose **Editor**, untick **Notify people**, and click **Share**.
   - Editor is needed for export. For import only, **Viewer** is enough, but then the connection test reports no write access.
7. In **Settings → Google Sheets**, paste the sheet's link from your browser's address bar (`https://docs.google.com/spreadsheets/d/…/edit`) and click **Save**.
8. Click **Test connection**. Every line should show ✓ (a tab you haven't created shows –).

If a work or school Google account blocks step 4 ("Service account key creation is disabled"), your organisation's policy forbids keys. Use a personal Google account instead, or use the published CSV link for import only.

## 2b. Published CSV link (import only, no Google Cloud)

1. In the sheet, go to **File → Share → Publish to web**.
2. Under **Link**, choose the tab (for example `Holdings_Stocks`) and **Comma-separated values (.csv)**, then click **Publish**.
3. Copy the link. It looks like `https://docs.google.com/spreadsheets/d/e/2PACX-…/pub?gid=0&single=true&output=csv`.
4. Paste it in either place:
   - **Settings → Google Sheets → "No service account?"**, under Stocks or Mutual funds;
   - directly in **Import → Google Sheet → A published CSV link**.
5. Repeat for the other tab if you want both.

> **Privacy:** a published tab can be read by anyone who has or guesses the link. Publish only what you're comfortable with. To stop it, go to **File → Share → Publish to web → Stop publishing**. The sheet's normal link also works if sharing is set to *Anyone with the link*, which has the same privacy trade-off.

The app accepts only `https://docs.google.com/spreadsheets/…` links, so a pasted link can't make it fetch anything else.

## 3. Import

Go to **Import → Google Sheet**. Choose **Stocks** or **Mutual funds**, then where to read from:
- **A tab of my sheet** (service account): type the tab name, which defaults to the saved one.
- **A published CSV link**.

Each import creates a new snapshot that replaces the previous one of that kind, exactly like uploading a file. Unmatched stocks and funds appear below for you to fix. A tab with more than 5,000 rows (`sheets.max_import_rows`) is refused.

## 4. Export

Click **Settings → Google Sheets → Export to Google Sheets** (also on **Settings → Export**). The app writes four tabs, creating any that are missing:

| Tab | Contents |
|---|---|
| `Summary` | Value, invested, P&L, XIRR, day change, signal counts, stops breached, red flags, stale prices, top actions, screener count, notes |
| `Analysis_Stocks` | Every stock: quantity, prices, P&L, weight, signal, composite / technical / fundamental scores, confidence, trailing stop, suggested action, rule, red flags, top reasons, price freshness |
| `Analysis_MF` | Every fund: units, value, P&L, XIRR, 1/3/5-year returns vs benchmark, expense ratio, Direct-plan gap, signal and reasons |
| `Screener` | The chosen screen run on your latest scan: rank, signal, scores, entry zone, stop, three targets, sector effect, filters met, reasons |

Every tab has the same layout:
1. **Row 1:** `Portfolio Analyzer · <title>`, `Updated <date, time> IST`, and the profile or scan used.
2. **Row 2:** the disclaimer.
3. **Row 3:** blank.
4. **Row 4:** column headers. Rows 1–4 are frozen.
5. **Row 5 onwards:** the data.

How values are written:
- Numbers are plain numbers, so formulas work on them.
- Rupee columns use Indian grouping (12,34,567.00). One limit of Sheets formats: negative amounts of a lakh or more show as −1,234,567.00.
- Everything is written as plain values. A stock name that starts with `=` is never run as a formula.

How tabs are handled:
- Each export clears and rewrites these four tabs, so don't type into them; put your own formulas on other tabs and reference these.
- If a tab with one of these names already holds content the app didn't write, export stops and asks before overwriting it.
- Tab names are set in `backend/config/profiles.yaml` under `sheets.export_tabs`.

The numbers come from data already downloaded (export doesn't download anything new), under your saved style and risk. The screen written to `Screener` is chosen in Settings and defaults to Top scores.

### Automatic export

Tick **Export automatically after the daily refresh** to export after the scheduled price refresh. That runs Mon–Fri at `data.refresh_time_ist` (16:00 IST by default), while the app is running.

The result appears under **Recent activity** and in the refresh job's log.

## Troubleshooting

| Message | Fix |
|---|---|
| *No service-account key found* | Do step 2a.5 |
| *This isn't a service-account key* | You downloaded an OAuth client or API key. Make a key under **Service accounts → Keys** |
| *Google refused the service-account key* | The key was deleted or disabled in Google Cloud. Create a new key and upload it |
| *The Google Sheets API isn't enabled* | Do step 2a.2, wait a minute, and test again |
| *The service account can't open this sheet. Share the sheet with …* | Do step 2a.6. For export, the role must be **Editor** |
| *Sheet not found* | Paste the sheet's normal link (from the address bar), not a link to a single published tab |
| *That is a 'Publish to web' link* | The service account needs the normal `…/d/<id>/edit` link. Published links go in the CSV fields |
| *Google returned a sign-in page instead of CSV* | The tab isn't published or shared. See 2b |
| *No tab named 'X'. Tabs in this sheet: …* | Fix the tab name in Settings, or rename the tab |
| *already has tab(s) named … with content this app didn't write* | Confirm the overwrite, or rename your tab or the export tab in `profiles.yaml` |
| *rate limit reached* | Wait a minute. The app paces itself at 50 requests a minute (`data.rate_limits_per_minute.google`), and an export uses about 7 |

## Revoking access

You can cut access in any of these ways:
- Remove the robot from the sheet's **Share** list.
- Delete the key in **Google Cloud → Service accounts → Keys**.
- Delete `secrets/service-account.json`.

Any one of them stops the app from reaching your sheet.
