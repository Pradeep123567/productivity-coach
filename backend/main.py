"""
Productivity Coach v2 — FastAPI + Groq + Postgres
New in v2: auto subtask breakdown when a goal is created (agentic step),
subtask toggle endpoint, Railway-ready.
"""
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

import database as db

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set in .env")

client = Groq(api_key=GROQ_API_KEY)
MODEL = "llama-3.3-70b-versatile"

app = FastAPI(title="Productivity Coach v2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

SYSTEM_PROMPT = """You are Coach, a direct and encouraging productivity coach.
Your job is to help the user with time management, goal setting, and staying accountable.
You know frameworks like SMART goals, the Eisenhower matrix, time-blocking, and the 2-minute rule —
bring them up naturally when relevant, never just list jargon.

How you behave:
- Keep replies short and practical. No long lectures.
- When the user sets a goal, call create_goal first. Then ALWAYS follow it immediately
  with create_subtasks — break the goal into 3 to 5 concrete, actionable subtasks with
  realistic suggested deadlines. Do this automatically, the user doesn't need to ask.
- When the user reports progress or a setback, respond using their current goals below.
  If status changes, call update_goal.
- Be supportive but not soft — if someone is stalling, name it and suggest one next step.
- For general tips, just answer directly, no tool call needed.

The user's current goals:
{goals_block}
"""


def format_goals_for_prompt(goals):
    if not goals:
        return "(no goals yet)"
    lines = []
    for g in goals:
        deadline = g["deadline"] or "no deadline"
        note = f" | note: {g['latest_note']}" if g["latest_note"] else ""
        subtasks = g.get("subtasks", [])
        st_lines = ""
        if subtasks:
            st_lines = " | subtasks: " + ", ".join(
                f"{'[x]' if s['done'] else '[ ]'} {s['title']}" for s in subtasks
            )
        lines.append(
            f"- [id {g['id']}] \"{g['title']}\" (status: {g['status']}, deadline: {deadline}){note}{st_lines}"
        )
    return "\n".join(lines)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_goal",
            "description": "Save a new goal the user wants to work towards.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "deadline": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
                "required": ["title", "deadline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_subtasks",
            "description": (
                "Break a goal into 3-5 concrete subtasks. "
                "Always call this right after create_goal — never skip it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer", "description": "The id returned by create_goal"},
                    "subtasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "suggested_deadline": {"type": "string"},
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["goal_id", "subtasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal",
            "description": "Update an existing goal's status or add a progress note.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer"},
                    "status": {"type": "string", "enum": ["active", "stuck", "done"]},
                    "note": {"type": "string"},
                },
                "required": ["goal_id"],
            },
        },
    },
]


def run_tool(name, args):
    if name == "create_goal":
        goal_id = db.create_goal(
            title=args.get("title"),
            deadline=args.get("deadline"),
            why_it_matters=args.get("why_it_matters"),
        )
        return {"status": "created", "goal_id": goal_id}

    if name == "create_subtasks":
        db.create_subtasks(
            goal_id=args.get("goal_id"),
            subtasks=args.get("subtasks", []),
        )
        return {"status": "subtasks_created"}

    if name == "update_goal":
        ok = db.update_goal(
            goal_id=args.get("goal_id"),
            status=args.get("status"),
            note=args.get("note"),
        )
        return {"status": "updated" if ok else "not_found"}

    return {"status": "unknown_tool"}


def run_agent_loop(messages):
    """
    Keeps calling Groq until no more tool calls come back.
    This is what makes it agentic — the model can chain
    create_goal → create_subtasks in one turn automatically.
    """
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0].message

        if not choice.tool_calls:
            return choice.content

        # run all tool calls in this round
        messages.append({
            "role": "assistant",
            "content": choice.content or "",
            "tool_calls": [tc.model_dump() for tc in choice.tool_calls],
        })

        for tc in choice.tool_calls:
            args = json.loads(tc.function.arguments)
            result = run_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })
        # loop back — Groq may want to call another tool


class ChatRequest(BaseModel):
    message: str


class ToggleRequest(BaseModel):
    subtask_id: int


@app.post("/api/chat")
def chat(req: ChatRequest):
    db.add_message("user", req.message)

    goals = db.get_active_goals()
    system_prompt = SYSTEM_PROMPT.format(goals_block=format_goals_for_prompt(goals))

    history = db.get_recent_messages(limit=12)
    messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})

    reply = run_agent_loop(messages)

    db.add_message("assistant", reply)

    return {
        "reply": reply,
        "goals": db.get_all_goals(),
    }


@app.patch("/api/subtask/toggle")
def toggle_subtask(req: ToggleRequest):
    done = db.toggle_subtask(req.subtask_id)
    return {"subtask_id": req.subtask_id, "done": done, "goals": db.get_all_goals()}


@app.get("/api/goals")
def list_goals():
    return {"goals": db.get_all_goals()}


@app.get("/api/history")
def history():
    return {"messages": db.get_recent_messages(limit=50)}


frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
