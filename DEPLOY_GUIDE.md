# 🚀 Deployment Guide — Streamlit Cloud + Railway

**Time to deploy: ~15 minutes**

```
GitHub repo (source of truth)
     ├── Streamlit Community Cloud  →  Dashboard (app.py)
     └── Railway                    →  Telegram Bot (bot.py)
```

Both services pull directly from your GitHub repo. Push to `main` and both
auto-redeploy. No Docker, no servers to manage.

---

## Step 0 — Push your code to GitHub

If you haven't already:

```bash
# In your project folder
git init
git add .
git commit -m "Initial commit — Personal Life OS"

# Create a repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/personal-life-os.git
git branch -M main
git push -u origin main
```

> ⚠️  Double-check that `.env` and `.streamlit/secrets.toml` are NOT in the
> commit. Run `git status` and verify they're listed as "untracked" or
> in `.gitignore`.

---

## Part 1 — Deploy the Dashboard to Streamlit Cloud

### 1.1 — Create a Streamlit Cloud account

1. Go to **https://share.streamlit.io**
2. Click **"Sign up"** → sign in with your GitHub account
3. Authorize Streamlit to access your repositories

### 1.2 — Create a new app

1. Click **"New app"** (top-right)
2. Fill in the form:

   | Field | Value |
   |-------|-------|
   | **Repository** | `YOUR_USERNAME/personal-life-os` |
   | **Branch** | `main` |
   | **Main file path** | `app.py` |
   | **App URL** | choose a custom slug, e.g. `mylifeos` |

3. Click **"Advanced settings"**

### 1.3 — Add secrets

In the **Advanced settings → Secrets** box, paste:

```toml
SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "your-supabase-anon-key"
ANTHROPIC_API_KEY = "sk-ant-..."
ENVIRONMENT = "production"
```

> 💡 Get these from:
> - Supabase → Project → Settings → API
> - Anthropic → https://console.anthropic.com/settings/keys

### 1.4 — Deploy

Click **"Deploy!"**

Streamlit will install `requirements-dashboard.txt` and start the app.
First deploy takes ~2 minutes. Your dashboard will be live at:

```
https://YOUR_SLUG.streamlit.app
```

### 1.5 — Verify it works

Open the URL. Enter your Telegram ID in the sidebar.
If you see "Configuration error" — recheck the secrets in step 1.3.

---

## Part 2 — Deploy the Bot to Railway

### 2.1 — Create a Railway account

1. Go to **https://railway.app**
2. Click **"Start a New Project"** → sign in with GitHub
3. Authorize Railway to access your repositories

### 2.2 — Create a new project from GitHub

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Search for and select `personal-life-os`
4. Railway will detect the `Procfile` and `railway.toml` automatically

### 2.3 — Add environment variables

1. Click on your new service (the box that appears)
2. Go to the **"Variables"** tab
3. Click **"New Variable"** for each of the following:

   | Variable | Value |
   |----------|-------|
   | `SUPABASE_URL` | `https://xxxxxxxxxxxx.supabase.co` |
   | `SUPABASE_KEY` | `your-supabase-anon-key` |
   | `ANTHROPIC_API_KEY` | `sk-ant-...` |
   | `TELEGRAM_BOT_TOKEN` | `123456:ABC-your-bot-token` |
   | `ENVIRONMENT` | `production` |

   > 💡 **Pro tip:** Railway has a "RAW Editor" button — paste all variables at once:
   > ```
   > SUPABASE_URL=https://...
   > SUPABASE_KEY=...
   > ANTHROPIC_API_KEY=...
   > TELEGRAM_BOT_TOKEN=...
   > ENVIRONMENT=production
   > ```

### 2.4 — Confirm the start command

1. Go to the **"Settings"** tab
2. Under **"Deploy"**, confirm the start command shows:
   ```
   python bot.py
   ```
   If it's blank, type it in manually.

### 2.5 — Deploy

Railway deploys automatically after you add variables. Watch the
**"Deployments"** tab — you should see:

```
🚀 Personal Life OS bot running…
```

in the build logs within ~60 seconds.

### 2.6 — Verify the bot works

Open Telegram, find your bot, send `/start`. You should get the welcome message.
Then try:
- `Had eggs for breakfast` → should log food
- `How many calories in an avocado?` → should answer directly (not save)
- `/notes` → should list recent notes

---

## Ongoing Workflow

### Updating the code

```bash
# Make changes locally, then:
git add .
git commit -m "Your change description"
git push origin main
```

Both Streamlit Cloud and Railway watch the `main` branch and
**auto-redeploy within ~1 minute**.

### Checking bot logs (Railway)

Railway → Your project → Service → **Deployments** → click latest → **View Logs**

### Checking dashboard logs (Streamlit Cloud)

Streamlit Cloud → Your app → **"Manage app"** (bottom-right) → **Logs**

---

## Costs

| Service | Plan | Cost |
|---------|------|------|
| Streamlit Cloud | Community (free) | **$0/mo** |
| Railway | Hobby (free trial, then usage-based) | **~$0–5/mo** |
| Supabase | Free tier | **$0/mo** |
| Anthropic API | Pay per use | **~$1–5/mo** |

Railway's free trial gives you $5 credit. A constantly-running bot
(polling every few seconds) uses roughly **$2–4/month** on the Hobby plan.

---

## Troubleshooting

### Dashboard shows "Configuration error"
→ Check secrets in Streamlit Cloud → App → Settings → Secrets.
   Make sure there are no trailing spaces in the values.

### Bot doesn't respond on Telegram
→ Check Railway logs for errors.
→ Verify `TELEGRAM_BOT_TOKEN` is set correctly in Railway Variables.
→ Make sure only ONE instance of `bot.py` is running — two polling bots
   will conflict.

### "supabase" import error on Streamlit Cloud
→ Make sure Streamlit Cloud is using `requirements-dashboard.txt`.
   In App → Settings → Python packages file, set it to `requirements-dashboard.txt`.

### Railway build fails
→ Check that `requirements-bot.txt` exists in your repo root.
→ In Railway Settings → Build, confirm the install command is:
   `pip install -r requirements-bot.txt`

### Bot saves questions as notes
→ This means the updated `prompts.py` isn't deployed yet.
   Run `git push origin main` and wait for Railway to redeploy.

---

## File Reference

```
your-repo/
├── app.py                        ← Streamlit dashboard entry point
├── bot.py                        ← Telegram bot entry point
├── config.py                     ← Reads st.secrets OR env vars automatically
├── requirements-dashboard.txt    ← Used by Streamlit Cloud
├── requirements-bot.txt          ← Used by Railway
├── railway.toml                  ← Railway build + start config
├── Procfile                      ← Fallback process definition for Railway
├── .streamlit/
│   ├── config.toml               ← Theme + server settings (safe to commit)
│   └── secrets.toml.example      ← Template (DO NOT commit the real one)
├── .gitignore                    ← Protects .env and secrets.toml
└── schema.sql                    ← Run once in Supabase SQL editor
```
