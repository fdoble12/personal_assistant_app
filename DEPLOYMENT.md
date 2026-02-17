# Deployment Guide - Personal Life OS

This guide covers various deployment options for your Personal Life OS.

## Table of Contents
1. [Local Development](#local-development)
2. [Docker Deployment](#docker-deployment)
3. [Cloud Deployment](#cloud-deployment)
4. [Production Best Practices](#production-best-practices)

---

## Local Development

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Run setup check
python setup_check.py

# Start bot (in one terminal)
python bot.py

# Start dashboard (in another terminal)
streamlit run app.py
```

---

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Build and start both services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Using Docker Individually

```bash
# Build image
docker build -t lifeos .

# Run bot
docker run -d --name lifeos-bot \
  --env-file .env \
  lifeos python bot.py

# Run dashboard
docker run -d --name lifeos-dashboard \
  --env-file .env \
  -p 8501:8501 \
  lifeos streamlit run app.py --server.port=8501 --server.address=0.0.0.0
```

---

## Cloud Deployment

### Option 1: Railway.app (Easiest)

**Bot Deployment:**
1. Create new project on [Railway](https://railway.app)
2. Connect your GitHub repo
3. Set environment variables in Railway dashboard
4. Deploy from `bot.py` as start command: `python bot.py`

**Dashboard Deployment:**
1. Create another service in same project
2. Use start command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
3. Railway will auto-assign PORT variable

### Option 2: Heroku

**Bot (Worker Dyno):**

Create `Procfile`:
```
worker: python bot.py
```

Deploy:
```bash
heroku create lifeos-bot
heroku config:set SUPABASE_URL=xxx SUPABASE_KEY=xxx ...
git push heroku main
heroku ps:scale worker=1
```

**Dashboard (Web Dyno):**

Create separate app:
```bash
heroku create lifeos-dashboard
heroku config:set SUPABASE_URL=xxx ...
git push heroku main
```

### Option 3: AWS EC2

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Clone repo and start
git clone your-repo
cd your-repo
cp .env.example .env
# Edit .env
docker-compose up -d
```

### Option 4: DigitalOcean App Platform

1. Create new app from GitHub repo
2. Configure two components:
   - **Worker**: `python bot.py`
   - **Web Service**: `streamlit run app.py --server.port=8080 --server.address=0.0.0.0`
3. Add environment variables
4. Deploy

### Option 5: Streamlit Cloud (Dashboard Only)

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect repo
4. Add secrets in Advanced Settings:
   ```toml
   SUPABASE_URL = "xxx"
   SUPABASE_KEY = "xxx"
   ```
5. Deploy

For bot, use a separate service (Railway, Heroku, etc.)

---

## Production Best Practices

### 1. Security

**Environment Variables:**
- Never commit `.env` to git
- Use secret management (AWS Secrets Manager, Vault)
- Rotate API keys regularly

**Supabase:**
```sql
-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE food_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE workouts ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY "Users can only access their own data"
ON users FOR ALL
USING (telegram_id = current_setting('app.user_id')::bigint);
```

**Bot Security:**
- Use webhook mode instead of polling in production
- Validate all inputs
- Implement rate limiting

### 2. Monitoring

**Logging:**
```python
# Add to bot.py and app.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
```

**Error Tracking:**
- Use Sentry for error monitoring
- Set up uptime monitoring (UptimeRobot, Pingdom)
- Configure alerts for bot downtime

### 3. Performance

**Database Optimization:**
- Already has indexes on key columns
- Consider adding composite indexes for complex queries
- Use connection pooling for high traffic

**Caching:**
```python
# Already implemented in app.py
@st.cache_resource
def get_database():
    return Database()
```

**API Rate Limits:**
- Anthropic: 50 requests/min (tier 1)
- Implement request queuing if needed
- Cache Claude responses for identical queries

### 4. Backups

**Supabase:**
- Daily automated backups (included in paid plan)
- Point-in-time recovery available
- Export data regularly:
  ```bash
  # Using Supabase CLI
  supabase db dump -f backup.sql
  ```

**Manual Backup Script:**
```python
import pandas as pd
from database import Database

db = Database()
telegram_id = YOUR_ID

# Export all data
notes = db.get_notes_by_date_range(telegram_id, start, end)
food = db.get_food_logs_by_date_range(telegram_id, start, end)
workouts = db.get_workouts_by_date_range(telegram_id, start, end)

pd.DataFrame(notes).to_csv('notes_backup.csv')
pd.DataFrame(food).to_csv('food_backup.csv')
pd.DataFrame(workouts).to_csv('workouts_backup.csv')
```

### 5. Scaling

**Bot (Horizontal Scaling):**
- Use webhook mode
- Deploy multiple instances behind load balancer
- Use Redis for shared state if needed

**Dashboard:**
- Streamlit Cloud auto-scales
- For self-hosted, use Nginx + multiple Streamlit instances
- Implement database connection pooling

### 6. Maintenance

**Update Dependencies:**
```bash
pip list --outdated
pip install --upgrade package-name
```

**Database Migrations:**
- Use Supabase migrations for schema changes
- Test on staging environment first
- Backup before major updates

**Health Checks:**
```python
# Add to bot.py
async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Health check endpoint"""
    await update.message.reply_text("✅ Bot is running!")

app.add_handler(CommandHandler("health", health_check))
```

---

## Troubleshooting

### Bot Not Receiving Messages
```bash
# Check if bot is running
docker-compose logs bot

# Test connection
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### Dashboard Not Loading
```bash
# Check logs
docker-compose logs dashboard

# Test locally
streamlit run app.py --server.headless true
```

### Database Connection Issues
```python
# Test connection
from database import Database
db = Database()
print(db.client.table('users').select('*').execute())
```

---

## Cost Estimation (Monthly)

- **Supabase**: $0 (free tier) - $25 (pro)
- **Anthropic API**: ~$3-10 (varies by usage)
- **Telegram Bot**: Free
- **Hosting**:
  - Railway: $5-10
  - Heroku: $7-14 (hobby dynos)
  - DigitalOcean: $12 (basic droplet)
  - Streamlit Cloud: Free (public repos)

**Total**: $5-50/month depending on choices

---

## Next Steps

1. Set up monitoring and alerts
2. Configure automated backups
3. Implement authentication for dashboard
4. Add SSL/TLS certificates
5. Set up CI/CD pipeline
6. Create staging environment

---

For questions or issues, refer to the main README.md or open an issue.
