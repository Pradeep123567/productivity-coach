const messagesEl = document.getElementById("messages");
const goalsListEl = document.getElementById("goals-list");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-input");

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function addBubble(role, text, isThinking) {
  const bubble = document.createElement("div");
  bubble.className = "bubble " + role + (isThinking ? " thinking" : "");
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

function renderGoals(goals) {
  if (!goals || goals.length === 0) {
    goalsListEl.innerHTML = '<p class="empty-state">Nothing saved yet — tell Coach what you are working towards.</p>';
    return;
  }

  goalsListEl.innerHTML = goals.map(function (g) {
    const deadline = g.deadline ? g.deadline : "no deadline";
    const note = g.latest_note
      ? '<div class="goal-note">' + escapeHtml(g.latest_note) + "</div>"
      : "";

    const subtasks = g.subtasks || [];
    const subtasksHtml = subtasks.length > 0
      ? '<div class="subtasks">' +
        subtasks.map(function (s) {
          return (
            '<label class="subtask' + (s.done ? " done" : "") + '">' +
            '<input type="checkbox" ' + (s.done ? "checked" : "") +
            ' data-id="' + s.id + '" onchange="handleSubtaskToggle(this)" />' +
            '<span>' + escapeHtml(s.title) + "</span>" +
            (s.suggested_deadline
              ? '<span class="subtask-deadline">' + escapeHtml(s.suggested_deadline) + "</span>"
              : "") +
            "</label>"
          );
        }).join("") +
        "</div>"
      : "";

    const doneCount = subtasks.filter(function (s) { return s.done; }).length;
    const progressHtml = subtasks.length > 0
      ? '<div class="progress-bar"><div class="progress-fill" style="width:' +
        Math.round((doneCount / subtasks.length) * 100) + '%"></div></div>'
      : "";

    return (
      '<div class="goal-card ' + g.status + '">' +
      '<div class="goal-title">' + escapeHtml(g.title) + "</div>" +
      '<div class="goal-meta">' +
      "<span>" + escapeHtml(deadline) + "</span>" +
      '<span class="goal-status ' + g.status + '">' + escapeHtml(g.status) + "</span>" +
      "</div>" +
      note +
      progressHtml +
      subtasksHtml +
      "</div>"
    );
  }).join("");
}

async function handleSubtaskToggle(checkbox) {
  const subtaskId = parseInt(checkbox.dataset.id);
  checkbox.disabled = true;
  try {
    const res = await fetch("/api/subtask/toggle", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subtask_id: subtaskId }),
    });
    const data = await res.json();
    renderGoals(data.goals);
  } catch (err) {
    checkbox.disabled = false;
  }
}

async function loadInitial() {
  try {
    const historyRes = await fetch("/api/history");
    const goalsRes = await fetch("/api/goals");
    const history = await historyRes.json();
    const goals = await goalsRes.json();

    history.messages.forEach(function (m) {
      addBubble(m.role, m.content);
    });
    renderGoals(goals.goals);

    if (history.messages.length === 0) {
      addBubble(
        "assistant",
        "Hey — I'm Coach. Tell me a goal you're working towards and I'll break it into steps for you automatically."
      );
    }
  } catch (err) {
    addBubble("assistant", "Couldn't reach the backend. Is the server running?");
  }
}

form.addEventListener("submit", async function (e) {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  addBubble("user", text);
  input.value = "";
  input.disabled = true;

  const thinkingBubble = addBubble("assistant", "thinking...", true);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    thinkingBubble.remove();
    addBubble("assistant", data.reply);
    renderGoals(data.goals);
  } catch (err) {
    thinkingBubble.remove();
    addBubble("assistant", "Something went wrong talking to the server.");
  } finally {
    input.disabled = false;
    input.focus();
  }
});

loadInitial();
