# Ethiopian Airlines Careers Results — Telegram Monitor

Checks https://corporate.ethiopianairlines.com/AboutEthiopian/careers/results
every 5 minutes via GitHub Actions and posts any *new* announcement to a
Telegram chat. Runs entirely on GitHub's free tier — no server to host,
nothing to keep alive.

## How it works
- `monitor.py` runs once per invocation: fetch page → parse → compare
  against `seen_state.json` → notify Telegram for anything new → save state.
- `.github/workflows/monitor.yml` triggers that script every 5 minutes and
  commits the updated `seen_state.json` back to the repo, so state persists
  between runs.
- First-ever run seeds the state silently (so you don't get 30 messages
  for every announcement currently on the page) — only announcements that
  appear *after* that count as "new."

## Setup (10 minutes)

### 1. Create a Telegram bot
1. Open Telegram, message **@BotFather**.
2. Send `/newbot`, follow the prompts, name it whatever you like.
3. BotFather gives you a token like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   Save it — this is `TELEGRAM_BOT_TOKEN`.

### 2. Get your chat ID
1. Send any message to your new bot (search its username, hit Start, say "hi").
2. In a browser, visit:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":...}` in the response — that number is `TELEGRAM_CHAT_ID`.
   (If you want it posted to a group instead, add the bot to the group and
   do the same thing — group chat IDs are negative numbers, that's normal.)

### 3. Push this repo to GitHub
```bash
cd ea-results-bot
git init
git add .
git commit -m "Initial commit: EA careers results monitor"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

### 4. Add secrets in GitHub
Repo → **Settings → Secrets and variables → Actions → New repository secret**
- `TELEGRAM_BOT_TOKEN` → the token from step 1
- `TELEGRAM_CHAT_ID` → the chat ID from step 2

### 5. Enable and test
- Go to the **Actions** tab, you should see "EA Careers Results Monitor."
- Click into it → **Run workflow** to trigger it manually the first time
  (this does the silent baseline seed).
- After that it runs automatically every 5 minutes. Trigger it manually
  again any time from the Actions tab to test.

## Notes / limitations
- **GitHub disables scheduled workflows after 60 days of repo inactivity**
  (no commits/pushes). Since this workflow commits `seen_state.json` back
  to the repo whenever something new appears, it stays "active" as long as
  new announcements keep appearing. If the page goes quiet for 2+ months
  with zero changes, push any small commit (or just re-run manually) to
  keep it alive.
- Scheduled runs can be delayed a few minutes under GitHub's load — normal,
  not a bug.
- If Ethiopian Airlines changes the page's HTML structure, the position/
  location parsing (regex-based) may need adjusting — the candidate table
  parsing itself is more robust since it just reads whatever table headers
  exist.
- Only run this against your own name / for personal use of a public page.
  Don't repurpose it to scrape or republish other people's exam data at scale.

## Local testing
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python monitor.py
```
