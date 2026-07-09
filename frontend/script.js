// En prod (Render) et en local via uvicorn, le frontend est servi par FastAPI :
// on appelle donc la MÊME origine (URL relative "").
// Seul cas particulier : frontend servi séparément en local (file:// ou http.server
// sur un autre port que 8000) -> on cible explicitement le backend local sur :8000.
const isLocalStatic =
  window.location.protocol === "file:" ||
  ((window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1") &&
    window.location.port !== "8000");
const DEFAULT_API = isLocalStatic ? "http://localhost:8000" : "";
const API_URL = localStorage.getItem("apiUrl") || DEFAULT_API;
const STORAGE_KEY = "lexsociale_threads";

const el = {
  form: document.getElementById("questionForm"),
  input: document.getElementById("questionInput"),
  submit: document.getElementById("submitBtn"),
  messages: document.getElementById("messages"),
  emptyState: document.getElementById("emptyState"),
  threadTitle: document.getElementById("threadTitle"),
  historyList: document.getElementById("historyList"),
  historyFilter: document.getElementById("historyFilter"),
  newSearch: document.getElementById("newSearchBtn"),
  suggestions: document.getElementById("suggestions"),
};

let threads = loadThreads();
let currentThreadId = null;

/* ---------- Persistence ---------- */
function loadThreads() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}
function saveThreads() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
}
function getThread(id) {
  return threads.find((t) => t.id === id);
}

/* ---------- Thread lifecycle ---------- */
function newThread() {
  currentThreadId = null;
  el.threadTitle.textContent = "Nouvelle recherche";
  el.messages.innerHTML = "";
  el.messages.appendChild(el.emptyState);
  el.emptyState.style.display = "";
  el.suggestions.style.display = "";
  renderHistory();
  el.input.focus();
}

function ensureThread(firstQuestion) {
  if (currentThreadId) return getThread(currentThreadId);
  const thread = {
    id: Date.now().toString(),
    title: firstQuestion,
    createdAt: Date.now(),
    messages: [],
  };
  threads.unshift(thread);
  currentThreadId = thread.id;
  el.threadTitle.textContent = truncate(firstQuestion, 60);
  return thread;
}

function openThread(id) {
  const thread = getThread(id);
  if (!thread) return;
  currentThreadId = id;
  el.threadTitle.textContent = truncate(thread.title, 60);
  el.messages.innerHTML = "";
  el.emptyState.style.display = "none";
  el.suggestions.style.display = "none";

  const wrap = document.createElement("div");
  wrap.className = "thread";
  el.messages.appendChild(wrap);

  thread.messages.forEach((m) => {
    if (m.role === "user") wrap.appendChild(renderUser(m.content));
    else wrap.appendChild(renderAssistant(m));
  });
  renderHistory();
  scrollBottom();
}

/* ---------- Rendering ---------- */
function getThreadWrap() {
  let wrap = el.messages.querySelector(".thread");
  if (!wrap) {
    el.emptyState.style.display = "none";
    el.suggestions.style.display = "none";
    wrap = document.createElement("div");
    wrap.className = "thread";
    el.messages.appendChild(wrap);
  }
  return wrap;
}

function renderUser(text) {
  const d = document.createElement("div");
  d.className = "msg-user";
  d.textContent = text;
  return d;
}

function renderAssistant(msg) {
  const d = document.createElement("div");
  d.className = "msg-assistant";

  const answerHtml = window.marked
    ? marked.parse(msg.content || "")
    : escapeHtml(msg.content || "");

  d.innerHTML = `
    <div class="assistant-avatar">§</div>
    <div class="assistant-body">
      <div class="assistant-head">
        <span class="assistant-name">Lex Sociale</span>
        <span class="assistant-tag">Réponse sourcée</span>
      </div>
      <div class="answer">${answerHtml}</div>
    </div>
  `;

  const body = d.querySelector(".assistant-body");
  const sources = buildSources(msg.documents || [], msg.metadatas || []);
  if (sources) body.appendChild(sources);
  return d;
}

function buildSources(documents, metadatas) {
  if (!documents.length) return null;
  const box = document.createElement("div");
  box.className = "sources";
  box.innerHTML = `<div class="sources-label">${documents.length} source${
    documents.length > 1 ? "s" : ""
  } citée${documents.length > 1 ? "s" : ""}</div>`;

  documents.forEach((doc, i) => {
    const m = metadatas[i] || {};
    const sim =
      m.similarity != null ? `${(m.similarity * 100).toFixed(0)}%` : "";
    const card = document.createElement("div");
    card.className = "source-card";
    card.innerHTML = `
      <div class="source-head">
        <div class="source-num">${i + 1}</div>
        <div class="source-meta">
          <span class="source-badge">${escapeHtml(
            m.source || "Code du travail"
          )}</span>
          <div class="source-title">${escapeHtml(m.num || "Article")}</div>
          <div class="source-sub">${escapeHtml(m.section_path || "")}</div>
        </div>
        ${sim ? `<div class="source-sim">${sim}</div>` : ""}
        <div class="source-caret">▾</div>
      </div>
      <div class="source-body">${escapeHtml(doc)}</div>
    `;
    card.querySelector(".source-head").addEventListener("click", () => {
      card.classList.toggle("open");
    });
    box.appendChild(card);
  });
  return box;
}

function renderHistory() {
  const filter = el.historyFilter.value.trim().toLowerCase();
  const groups = { "Aujourd'hui": [], Hier: [], "7 derniers jours": [], "Plus ancien": [] };
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayMs = 86400000;

  threads
    .filter((t) => !filter || t.title.toLowerCase().includes(filter))
    .forEach((t) => {
      if (t.createdAt >= startOfToday) groups["Aujourd'hui"].push(t);
      else if (t.createdAt >= startOfToday - dayMs) groups["Hier"].push(t);
      else if (t.createdAt >= startOfToday - 7 * dayMs) groups["7 derniers jours"].push(t);
      else groups["Plus ancien"].push(t);
    });

  el.historyList.innerHTML = "";
  Object.entries(groups).forEach(([label, items]) => {
    if (!items.length) return;
    const l = document.createElement("div");
    l.className = "history-group-label";
    l.textContent = label;
    el.historyList.appendChild(l);
    items.forEach((t) => {
      const b = document.createElement("button");
      b.className = "history-item" + (t.id === currentThreadId ? " active" : "");
      b.innerHTML = `<span class="dot">॥</span> <span>${escapeHtml(
        truncate(t.title, 34)
      )}</span>`;
      b.addEventListener("click", () => openThread(t.id));
      el.historyList.appendChild(b);
    });
  });
}

/* ---------- Ask flow ---------- */
async function askQuestion(question) {
  const thread = ensureThread(question);
  const wrap = getThreadWrap();
  wrap.appendChild(renderUser(question));

  thread.messages.push({ role: "user", content: question });
  saveThreads();
  renderHistory();
  scrollBottom();

  const pending = document.createElement("div");
  pending.className = "msg-assistant";
  pending.innerHTML = `
    <div class="assistant-avatar">§</div>
    <div class="assistant-body">
      <div class="assistant-head">
        <span class="assistant-name">Lex Sociale</span>
        <span class="assistant-tag">Recherche…</span>
      </div>
      <div class="typing"><span></span><span></span><span></span></div>
    </div>`;
  wrap.appendChild(pending);
  scrollBottom();

  setLoading(true);
  try {
    let res;
    try {
      res = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
    } catch (networkErr) {
      throw new Error(
        "Impossible de joindre le serveur. Vérifie que l'API tourne et ouvre l'app via http://localhost:8000/"
      );
    }

    if (!res.ok) {
      throw new Error(await parseError(res));
    }

    const data = await res.json();
    pending.remove();

    const assistantMsg = {
      role: "assistant",
      content: data.response,
      documents: data.documents || [],
      metadatas: data.metadatas || [],
    };
    wrap.appendChild(renderAssistant(assistantMsg));
    thread.messages.push(assistantMsg);
    saveThreads();
    scrollBottom();
  } catch (e) {
    pending.remove();
    const err = document.createElement("div");
    err.className = "msg-error";
    err.textContent = e.message || "Erreur inattendue";
    wrap.appendChild(err);
    scrollBottom();
  } finally {
    setLoading(false);
  }
}

async function parseError(res) {
  const raw = await res.text().catch(() => "");
  let detail;
  try {
    detail = JSON.parse(raw).detail;
  } catch {
    detail = raw;
  }
  if (Array.isArray(detail)) {
    detail = detail.map((d) => d.msg || JSON.stringify(d)).join(" · ");
  }
  if (detail && typeof detail === "object") detail = JSON.stringify(detail);
  const base = detail || "Erreur du serveur";
  if (res.status === 400) return base; // question hors périmètre / non sûre
  return `${base} (HTTP ${res.status})`;
}

/* ---------- Helpers ---------- */
function setLoading(on) {
  el.submit.disabled = on;
  el.input.disabled = on;
}
function scrollBottom() {
  el.messages.scrollTop = el.messages.scrollHeight;
}
function truncate(s, n) {
  s = s || "";
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* ---------- Events ---------- */
el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = el.input.value.trim();
  if (!q) return;
  el.input.value = "";
  el.input.style.height = "auto";
  askQuestion(q);
});

el.input.addEventListener("input", () => {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 160) + "px";
});
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    el.form.requestSubmit();
  }
});

el.newSearch.addEventListener("click", newThread);
el.historyFilter.addEventListener("input", renderHistory);

el.suggestions.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    askQuestion(chip.textContent.trim());
  });
});

window.setApiUrl = (url) => {
  localStorage.setItem("apiUrl", url);
  location.reload();
};

/* ---------- Init ---------- */
renderHistory();
