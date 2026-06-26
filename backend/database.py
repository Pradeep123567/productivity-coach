"""
Postgres-backed storage using pg8000 (pure Python, works on Windows with zero build deps).
Tables: goals, subtasks, messages.
"""
import os
import pg8000.native
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")


def get_connection():
    url = urlparse(DATABASE_URL)
    conn = pg8000.native.Connection(
        host=url.hostname,
        port=url.port or 5432,
        database=url.path.lstrip("/"),
        user=url.username,
        password=url.password,
        ssl_context=True,  # Neon requires SSL
    )
    return conn


def init_db():
    conn = get_connection()
    conn.run("""
        CREATE TABLE IF NOT EXISTS goals (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            deadline TEXT,
            why_it_matters TEXT,
            status TEXT DEFAULT 'active',
            latest_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.run("""
        CREATE TABLE IF NOT EXISTS subtasks (
            id SERIAL PRIMARY KEY,
            goal_id INTEGER REFERENCES goals(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            suggested_deadline TEXT,
            done BOOLEAN DEFAULT FALSE,
            created_at TEXT NOT NULL
        )
    """)
    conn.run("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.close()


# ---------- Goals ----------

def create_goal(title, deadline=None, why_it_matters=None):
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    rows = conn.run(
        "INSERT INTO goals (title, deadline, why_it_matters, status, created_at, updated_at) "
        "VALUES (:title, :deadline, :why, 'active', :now, :now2) RETURNING id",
        title=title, deadline=deadline, why=why_it_matters, now=now, now2=now
    )
    goal_id = rows[0][0]
    conn.close()
    return goal_id


def update_goal(goal_id, status=None, note=None):
    conn = get_connection()
    rows = conn.run("SELECT status, latest_note FROM goals WHERE id = :id", id=goal_id)
    if not rows:
        conn.close()
        return False
    existing_status, existing_note = rows[0]
    new_status = status if status else existing_status
    new_note = note if note else existing_note
    now = datetime.utcnow().isoformat()
    conn.run(
        "UPDATE goals SET status = :status, latest_note = :note, updated_at = :now WHERE id = :id",
        status=new_status, note=new_note, now=now, id=goal_id
    )
    conn.close()
    return True


def _attach_subtasks(conn, goals):
    for goal in goals:
        rows = conn.run(
            "SELECT id, title, suggested_deadline, done FROM subtasks WHERE goal_id = :gid ORDER BY id ASC",
            gid=goal["id"]
        )
        goal["subtasks"] = [
            {"id": r[0], "title": r[1], "suggested_deadline": r[2], "done": r[3]}
            for r in rows
        ]
    return goals


def _rows_to_goals(rows):
    return [
        {
            "id": r[0], "title": r[1], "deadline": r[2],
            "why_it_matters": r[3], "status": r[4],
            "latest_note": r[5], "created_at": r[6], "updated_at": r[7],
            "subtasks": []
        }
        for r in rows
    ]


def get_all_goals():
    conn = get_connection()
    rows = conn.run("SELECT id,title,deadline,why_it_matters,status,latest_note,created_at,updated_at FROM goals ORDER BY created_at DESC")
    goals = _rows_to_goals(rows)
    goals = _attach_subtasks(conn, goals)
    conn.close()
    return goals


def get_active_goals():
    conn = get_connection()
    rows = conn.run("SELECT id,title,deadline,why_it_matters,status,latest_note,created_at,updated_at FROM goals WHERE status != 'done' ORDER BY created_at DESC")
    goals = _rows_to_goals(rows)
    goals = _attach_subtasks(conn, goals)
    conn.close()
    return goals


# ---------- Subtasks ----------

def create_subtasks(goal_id, subtasks):
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    for st in subtasks:
        conn.run(
            "INSERT INTO subtasks (goal_id, title, suggested_deadline, done, created_at) "
            "VALUES (:gid, :title, :deadline, FALSE, :now)",
            gid=goal_id, title=st.get("title"), deadline=st.get("suggested_deadline"), now=now
        )
    conn.close()


def toggle_subtask(subtask_id):
    conn = get_connection()
    rows = conn.run(
        "UPDATE subtasks SET done = NOT done WHERE id = :id RETURNING done",
        id=subtask_id
    )
    conn.close()
    return rows[0][0] if rows else None


# ---------- Messages ----------

def add_message(role, content):
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    conn.run(
        "INSERT INTO messages (role, content, created_at) VALUES (:role, :content, :now)",
        role=role, content=content, now=now
    )
    conn.close()


def get_recent_messages(limit=20):
    conn = get_connection()
    rows = conn.run(
        "SELECT role, content, created_at FROM messages ORDER BY id DESC LIMIT :limit",
        limit=limit
    )
    conn.close()
    msgs = [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]
    return list(reversed(msgs))
