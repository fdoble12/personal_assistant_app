# 🧠 Personal Life OS

A comprehensive life tracking system that uses AI to automatically categorize and log your daily activities through Telegram, with a beautiful Streamlit dashboard for analytics.

## Features

### 🤖 Intelligent Telegram Bot
- **Natural Language Processing**: Just text naturally - Claude AI figures out what you're logging
- **Automatic Classification**: Distinguishes between notes, food logs, and workouts
- **Macro Estimation**: Estimates calories, protein, carbs, and fat from food descriptions
- **Workout Tracking**: Extracts activity type, duration, and intensity
- **Daily Summaries**: Get instant reports on your day's progress

### 📊 Streamlit Dashboard
- **Analytics Dashboard**: Visualize your progress with interactive charts
- **Calorie Tracking**: Compare intake vs. goals over time
- **Workout Insights**: See workout frequency and activity distribution
- **Weight Progress**: Track your weight loss/gain journey
- **Journal View**: Browse and search through your notes
- **Manual Entry**: Add data manually when needed

## Tech Stack

- **Frontend**: Streamlit
- **Backend**: Supabase (PostgreSQL)
- **Bot**: python-telegram-bot (async)
- **AI**: Anthropic Claude 3.5 Sonnet
- **Data Validation**: Pydantic
- **Visualization**: Plotly

## Quick Start

### Prerequisites

- Python 3.9+
- A Supabase account
- An Anthropic API key
- A Telegram bot token from @BotFather

### 1. Clone and Install

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Set Up Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to the SQL Editor
3. Run the SQL from `schema.sql` to create all tables
4. Get your project URL and anon key from Settings > API

### 3. Configure Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your credentials
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
ANTHROPIC_API_KEY=your-anthropic-api-key
```

### 4. Create Your Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token and add it to your `.env` file

### 5. Get Your Telegram ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy your ID for use in the dashboard

### 6. Start the Bot

```bash
python bot.py
```

### 7. Launch the Dashboard

In a separate terminal:

```bash
streamlit run app.py
```

## Usage

### Telegram Bot Commands

- `/start` - Initialize the bot and see welcome message
- `/summary` - Get today's summary (calories, workouts, notes)
- `/profile` - View your profile settings
- `/setgoal [weight]` - Set your goal weight in kg
- `/settarget [calories]` - Set daily calorie target
- `/help` - Show help message

### Example Messages

**Food Logging:**
```
Had eggs and toast for breakfast
Chicken caesar salad for lunch
Just ate a protein bar
```

**Workout Logging:**
```
30 min run this morning
Gym session 45 mins - chest and back
Yoga class for an hour
5k run in 28 minutes
```

**Note Taking:**
```
Remember to call mom tomorrow
Idea for new feature: dark mode
Need to buy groceries this weekend
```

### Dashboard Usage

1. Enter your Telegram ID in the sidebar
2. Select a date range to view
3. Explore the three main tabs:
   - **Dashboard**: View analytics and charts
   - **Journal**: Browse and search your notes
   - **Data Entry**: Manually add food, workouts, or notes

## Project Structure

```
personal-life-os/
├── schema.sql              # Database schema
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── config.py              # Configuration management
├── models.py              # Pydantic data models
├── prompts.py             # LLM prompt templates
├── database.py            # Supabase operations
├── claude_client.py       # Anthropic API client
├── bot.py                 # Telegram bot (main ingestion)
├── app.py                 # Streamlit dashboard
└── README.md             # This file
```

## Architecture

### Data Flow

```
User Message → Telegram Bot → Claude API → Classification → Database
                                                              ↓
                                              Streamlit Dashboard
```

### Classification Logic

The system uses Claude with a carefully engineered prompt to:

1. **Classify** the message type (note, food, or workout)
2. **Extract** relevant data points:
   - **Notes**: content, summary, tags
   - **Food**: description, calories, protein, carbs, fat
   - **Workouts**: activity type, duration, distance, notes
3. **Validate** the data using Pydantic models
4. **Insert** into the appropriate Supabase table

### Database Schema

**users**
- telegram_id (unique identifier)
- goal_weight, current_weight
- daily_calorie_target
- created_at, updated_at

**notes**
- user_id (foreign key)
- content (full text)
- summary (one-sentence)
- tags (array)
- created_at

**food_logs**
- user_id (foreign key)
- food_description
- calories, protein, carbs, fat
- created_at

**workouts**
- user_id (foreign key)
- activity_type
- duration_mins, distance_km
- notes
- created_at

## Advanced Configuration

### Customizing Claude's Classification

Edit `prompts.py` to adjust:
- Classification confidence thresholds
- Macro estimation guidelines
- Tag extraction rules
- Summary generation style

### Extending the Database

To add new tables:
1. Add SQL to `schema.sql`
2. Create Pydantic model in `models.py`
3. Add database methods in `database.py`
4. Update bot handlers in `bot.py`
5. Add dashboard views in `app.py`

### Deployment

**Bot (24/7 running)**
- Deploy to a VPS, Heroku, or Railway
- Use process manager like PM2 or systemd
- Enable webhook mode for production

**Dashboard**
- Deploy to Streamlit Cloud (free tier available)
- Or use Docker + any cloud provider

## Troubleshooting

### Bot not responding
- Check if `bot.py` is running
- Verify your bot token in `.env`
- Ensure the bot is not banned by Telegram

### Claude returns errors
- Check your API key and credits
- Review the response in logs
- The system has fallbacks for malformed JSON

### Database connection issues
- Verify Supabase URL and key
- Check if tables are created
- Review Supabase logs for errors

### Dashboard shows no data
- Ensure you're using the correct Telegram ID
- Check if data exists in Supabase
- Verify date range selection

## Performance Optimization

- **Database**: Indexed columns are already optimized for queries
- **API Calls**: Responses are cached where appropriate
- **Dashboard**: Uses Streamlit caching for database operations

## Security Best Practices

1. **Never commit** your `.env` file
2. **Use row-level security** in Supabase for production
3. **Implement authentication** for the dashboard
4. **Rotate API keys** regularly
5. **Enable 2FA** on all services

## Roadmap

- [ ] Add voice message support
- [ ] Image recognition for food (via Claude Vision)
- [ ] Habit tracking and streaks
- [ ] Export data to CSV/PDF
- [ ] Mobile app wrapper
- [ ] Multi-user support with proper auth
- [ ] Integration with fitness trackers
- [ ] AI-powered insights and recommendations

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - feel free to use this for personal or commercial projects.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

---

Built with ❤️ using Claude, Streamlit, and Supabase
