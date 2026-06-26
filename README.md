# Coach v2 — Productivity Chatbot

What's new in v2:
- Goals automatically get broken into 3-5 subtasks the moment you set one (agentic step)
- Subtasks have checkboxes + a progress bar per goal
- Postgres instead of SQLite (data survives redeployment)
- Railway-ready for public URL sharing

## Local setup

1. Get a free Postgres DB — easiest option: https://neon.tech (free tier, no credit card)
   After signing up, copy the connection string that looks like:
   postgresql://user:password@host/dbname

2. Install deps:
   cd backend
   pip install -r requirements.txt

3. Set up .env:
   cp .env.example .env
   Then open .env and fill in both values:
   GROQ_API_KEY=your_groq_key
   DATABASE_URL=your_postgres_connection_string

4. Run:
   uvicorn main:app --reload

5. Open http://127.0.0.1:8000

## Deploy to Railway (public URL)

1. Push this folder to a GitHub repo.
2. Go to https://railway.app → New Project → Deploy from GitHub repo → pick your repo.
3. In Railway dashboard → your service → Variables, add:
   GROQ_API_KEY = your key
   DATABASE_URL = (Railway gives you a free Postgres — click Add Service → Database → Postgres,
   then copy the DATABASE_URL from its Variables tab)
4. Railway auto-deploys. You get a URL like https://your-app.railway.app — share that link.

## Project structure

backend/
  main.py         FastAPI app, Groq agentic loop, all endpoints
  database.py     Postgres helpers (goals, subtasks, messages)
  requirements.txt
  .env.example

frontend/
  index.html      Chat UI + goals sidebar
  style.css       Styling + subtask + progress bar styles
  app.js          API calls, goal/subtask rendering, checkbox toggle

Procfile          Railway start command
railway.json      Railway build config
