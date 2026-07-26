/* ═══════════════════════════════════════════════════════════
   SELFSHIP — simulated autonomous shipping pipeline
   everything client-side. no repos were harmed.
   ═══════════════════════════════════════════════════════════ */

"use strict";

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (a, b) => Math.round(a + Math.random() * (b - a));
const pick = (a) => a[Math.floor(Math.random() * a.length)];
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const PACE = REDUCED ? 0.35 : 1; // compress the drama if motion is reduced

const escapeHtml = (s) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ─────────────────────────────────────────────────────────
   particle field — drifting phosphor constellation
   ───────────────────────────────────────────────────────── */
(function particles() {
  const canvas = $("#particleCanvas");
  const ctx = canvas.getContext("2d");
  let W, H, pts = [];
  const COLORS = ["61,255,184", "88,196,255", "183,156,255"];

  function resize() {
    W = canvas.width = innerWidth;
    H = canvas.height = innerHeight;
    const n = Math.min(110, Math.floor((W * H) / 16000));
    pts = Array.from({ length: n }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.22,
      vy: (Math.random() - 0.5) * 0.22,
      r: Math.random() * 1.6 + 0.4,
      c: pick(COLORS),
      a: Math.random() * 0.5 + 0.15,
    }));
  }

  function frame() {
    ctx.clearRect(0, 0, W, H);
    for (const p of pts) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < -10) p.x = W + 10; if (p.x > W + 10) p.x = -10;
      if (p.y < -10) p.y = H + 10; if (p.y > H + 10) p.y = -10;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${p.c},${p.a})`;
      ctx.fill();
    }
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        const d = Math.hypot(dx, dy);
        if (d < 110) {
          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.strokeStyle = `rgba(120,160,200,${0.055 * (1 - d / 110)})`;
          ctx.stroke();
        }
      }
    }
    if (!REDUCED) requestAnimationFrame(frame);
  }

  addEventListener("resize", resize);
  resize();
  frame();
})();

/* cursor glow */
(function glow() {
  if (REDUCED) return;
  const g = $("#cursorGlow");
  addEventListener("pointermove", (e) => {
    g.style.transform = `translate(${e.clientX - 260}px, ${e.clientY - 260}px)`;
  }, { passive: true });
})();

/* ─────────────────────────────────────────────────────────
   the "deployed" to-do app — real, interactive, mutable
   ───────────────────────────────────────────────────────── */
const todo = {
  mounted: false,
  tasks: [],
  features: new Set(),
  query: "",
  nextId: 1,
};

const SEED_TASKS = [
  { text: "Design the landing hero", done: true },
  { text: "Wire up the pipeline animation", done: false },
  { text: "Ship the SelfShip demo", done: false },
];

function mountTodoApp() {
  const stage = $("#previewStage");
  todo.mounted = true;
  todo.features = new Set();
  todo.query = "";
  todo.nextId = 1;
  todo.tasks = SEED_TASKS.map((t) => ({
    id: todo.nextId++,
    text: t.text,
    done: t.done,
    priority: "none",
    due: "",
  }));

  stage.innerHTML = `
    <div class="todoapp" id="todoApp">
      <div class="pv-head">
        <div>
          <div class="pv-title">Tasks</div>
          <div class="pv-sub">ship day · todo-app v1.0</div>
        </div>
        <div class="pv-extras" id="pvExtras"></div>
      </div>
      <div id="pvBannerSlot"></div>
      <div id="pvProgressSlot"></div>
      <div id="pvSearchSlot"></div>
      <form class="pv-add" id="pvAddForm">
        <input id="pvAddInput" placeholder="Add a task…" maxlength="80" />
        <button type="submit">Add</button>
      </form>
      <ul class="pv-list" id="pvList"></ul>
      <div class="pv-foot" id="pvFoot"></div>
    </div>`;

  $("#pvAddForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#pvAddInput");
    const text = input.value.trim();
    if (!text) return;
    todo.tasks.push({ id: todo.nextId++, text, done: false, priority: "none", due: nextDue() });
    input.value = "";
    renderTodos();
  });

  $("#pvList").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const li = btn.closest(".pv-task");
    const task = todo.tasks.find((t) => t.id === Number(li.dataset.id));
    if (!task) return;

    if (btn.dataset.act === "toggle") {
      task.done = !task.done;
      if (task.done && todo.features.has("confetti")) {
        const r = btn.getBoundingClientRect();
        fireConfetti(r.left + r.width / 2, r.top + r.height / 2, 45, 3.2);
      }
      renderTodos();
    }
    if (btn.dataset.act === "flag") {
      task.priority = task.priority === "none" ? "high" : task.priority === "high" ? "low" : "none";
      renderTodos();
    }
    if (btn.dataset.act === "del") {
      li.classList.add("removing");
      setTimeout(() => {
        todo.tasks = todo.tasks.filter((t) => t.id !== task.id);
        renderTodos();
      }, 240);
    }
  });
}

let dueCycle = 0;
function nextDue() {
  return ["today", "tomorrow", "fri", "mon"][dueCycle++ % 4];
}

function rowHTML(t) {
  const f = (id) => todo.features.has(id);
  return `
    <li class="pv-task ${t.done ? "done" : ""} ${t.priority === "high" ? "prio-high" : ""}" data-id="${t.id}">
      ${f("priority") ? `<button class="pv-flag f-${t.priority}" data-act="flag" title="cycle priority">⚑</button>` : ""}
      <button class="pv-check" data-act="toggle" aria-label="toggle done">${t.done ? "✓" : ""}</button>
      <span class="pv-text">${escapeHtml(t.text)}</span>
      ${f("duedate") && t.due ? `<span class="pv-due">◷ ${t.due}</span>` : ""}
      ${f("delete") ? `<button class="pv-del" data-act="del" aria-label="delete">✕</button>` : ""}
    </li>`;
}

function renderTodos() {
  const list = $("#pvList");
  if (!list) return;
  const visible = todo.tasks.filter((t) => t.text.toLowerCase().includes(todo.query));
  list.innerHTML = visible.length
    ? visible.map(rowHTML).join("")
    : `<div class="pv-empty">${todo.query ? "no matches — the filter works." : "all clear. nothing to do."}</div>`;
  syncChrome();
}

function syncChrome() {
  const done = todo.tasks.filter((t) => t.done).length;
  const total = todo.tasks.length;
  const pct = total ? Math.round((done / total) * 100) : 0;

  const foot = $("#pvFoot");
  if (foot) foot.textContent = `${done} of ${total} completed`;

  const fill = $("#pvProgressFill");
  if (fill) {
    fill.style.width = pct + "%";
    const lbl = $("#pvProgressPct");
    if (lbl) lbl.textContent = pct + "%";
  }

  const counter = $("#pvCounterChip");
  if (counter) counter.textContent = `${total - done} open · ${done} done`;
}

function flashApp() {
  const app = $("#todoApp");
  if (!app) return;
  app.classList.remove("flash");
  void app.offsetWidth;
  app.classList.add("flash");
  const scan = $("#scanline");
  scan.classList.remove("sweep");
  void scan.offsetWidth;
  scan.classList.add("sweep");
}

function toast(msg) {
  const stage = $("#previewStage");
  stage.querySelectorAll(".pv-toast").forEach((t) => t.remove());
  const el = document.createElement("div");
  el.className = "pv-toast";
  el.textContent = msg;
  stage.appendChild(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  }, 2400);
}

/* ─────────────────────────────────────────────────────────
   feature engine — intent match → UI mutation + fake artifacts
   ───────────────────────────────────────────────────────── */
const FEATURES = [
  {
    id: "darkmode",
    match: /dark|night|light ?mode|theme|dim/i,
    intent: "ui.theme",
    title: "Dark mode toggle",
    hotLabel: "dark mode toggle",
    branch: "feat/dark-mode-toggle",
    commit: "feat: add dark mode toggle",
    files: [
      {
        path: "src/components/ThemeToggle.jsx", added: 18, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · ThemeToggle.jsx @@" },
          { t: "+", x: "import { useState } from \"react\";" },
          { t: "+", x: "" },
          { t: "+", x: "export function ThemeToggle() {" },
          { t: "+", x: "  const [dark, setDark] = useState(false);" },
          { t: "+", x: "" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <button" },
          { t: "+", x: "      className=\"pv-switch\"" },
          { t: "+", x: "      aria-label=\"toggle dark mode\"" },
          { t: "+", x: "      onClick={() => setDark((d) => !d)}" },
          { t: "+", x: "    >" },
          { t: "+", x: "      <span className=\"knob\" />" },
          { t: "+", x: "    </button>" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
      {
        path: "src/App.jsx", added: 4, removed: 1,
        diff: [
          { t: "h", x: "@@ -1,6 +1,9 @@" },
          { t: " ", x: "import { TaskList } from \"./TaskList\";" },
          { t: "+", x: "import { ThemeToggle } from \"./components/ThemeToggle\";" },
          { t: " ", x: "" },
          { t: " ", x: "export default function App() {" },
          { t: "-", x: "  return <main className=\"app\">" },
          { t: "+", x: "  const [dark] = useTheme();" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <main className={dark ? \"app pv-dark\" : \"app\"}>" },
          { t: "+", x: "      <ThemeToggle />" },
        ],
      },
    ],
    tests: [
      "ThemeToggle › renders the switch",
      "ThemeToggle › toggles .pv-dark on click",
      "ThemeToggle › persists preference",
      "TaskList › regression: seeded tasks render",
    ],
    apply() {
      todo.features.add("darkmode");
      const extras = $("#pvExtras");
      extras.insertAdjacentHTML("afterbegin", `<button class="pv-switch" id="pvThemeSwitch" title="toggle dark mode"><span class="knob">☾</span></button>`);
      const sw = $("#pvThemeSwitch");
      sw.addEventListener("click", () => {
        $("#todoApp").classList.toggle("pv-dark");
        sw.classList.toggle("on");
      });
      setTimeout(() => sw.click(), 650 * PACE);
    },
  },
  {
    id: "priority",
    match: /priorit|urgent|important|flag|star/i,
    intent: "data.priority",
    title: "Task priorities",
    hotLabel: "priority flags",
    branch: "feat/task-priorities",
    commit: "feat: add priority flags to tasks",
    files: [
      {
        path: "src/components/PriorityFlag.jsx", added: 14, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · PriorityFlag.jsx @@" },
          { t: "+", x: "const ORDER = [\"none\", \"high\", \"low\"];" },
          { t: "+", x: "" },
          { t: "+", x: "export function PriorityFlag({ value, onCycle }) {" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <button" },
          { t: "+", x: "      className={\"pv-flag f-\" + value}" },
          { t: "+", x: "      onClick={() => onCycle(next(ORDER, value))}" },
          { t: "+", x: "      title=\"cycle priority\"" },
          { t: "+", x: "    >" },
          { t: "+", x: "      ⚑" },
          { t: "+", x: "    </button>" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
      {
        path: "src/TaskRow.jsx", added: 5, removed: 1,
        diff: [
          { t: "h", x: "@@ -3,8 +3,12 @@" },
          { t: " ", x: "export function TaskRow({ task }) {" },
          { t: "-", x: "  const { text, done } = task;" },
          { t: "+", x: "  const { text, done, priority } = task;" },
          { t: " ", x: "  return (" },
          { t: "-", x: "    <li className={done ? \"done\" : \"\"}>" },
          { t: "+", x: "    <li className={cx({ done, \"prio-high\": priority === \"high\" })}>" },
          { t: "+", x: "      <PriorityFlag value={priority} onCycle={cycle} />" },
          { t: "+", x: "      <Checkbox checked={done} />" },
          { t: "+", x: "      <span>{text}</span>" },
        ],
      },
    ],
    tests: [
      "PriorityFlag › cycles none → high → low",
      "TaskRow › high priority shows red flag + border",
      "TaskRow › priority survives re-render",
      "TaskList › regression: toggle still works",
    ],
    apply() {
      todo.features.add("priority");
      const t = todo.tasks.find((x) => !x.done);
      if (t) t.priority = "high";
      renderTodos();
    },
  },
  {
    id: "progress",
    match: /progress|percent|completion|bar|track/i,
    intent: "ui.progress",
    title: "Completion progress bar",
    hotLabel: "progress bar",
    branch: "feat/progress-bar",
    commit: "feat: show completion progress bar",
    files: [
      {
        path: "src/components/ProgressBar.jsx", added: 16, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · ProgressBar.jsx @@" },
          { t: "+", x: "export function ProgressBar({ tasks }) {" },
          { t: "+", x: "  const done = tasks.filter((t) => t.done).length;" },
          { t: "+", x: "  const pct = tasks.length" },
          { t: "+", x: "    ? Math.round((done / tasks.length) * 100)" },
          { t: "+", x: "    : 0;" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <div className=\"pv-progress\">" },
          { t: "+", x: "      <div className=\"pv-progress-track\">" },
          { t: "+", x: "        <div style={{ width: pct + \"%\" }} />" },
          { t: "+", x: "      </div>" },
          { t: "+", x: "    </div>" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
      {
        path: "src/App.jsx", added: 3, removed: 0,
        diff: [
          { t: "h", x: "@@ -2,5 +2,8 @@" },
          { t: " ", x: "import { TaskList } from \"./TaskList\";" },
          { t: "+", x: "import { ProgressBar } from \"./components/ProgressBar\";" },
          { t: " ", x: "<Header />" },
          { t: "+", x: "<ProgressBar tasks={tasks} />" },
          { t: "+", x: "<TaskList tasks={tasks} />" },
        ],
      },
    ],
    tests: [
      "ProgressBar › computes percentage correctly",
      "ProgressBar › animates width on task toggle",
      "ProgressBar › handles empty list (0%)",
      "TaskList › regression: add task updates bar",
    ],
    apply() {
      todo.features.add("progress");
      $("#pvProgressSlot").innerHTML = `
        <div class="pv-progress">
          <div class="pv-progress-meta"><span>completion</span><span id="pvProgressPct">0%</span></div>
          <div class="pv-progress-track"><div class="pv-progress-fill" id="pvProgressFill"></div></div>
        </div>`;
      syncChrome();
    },
  },
  {
    id: "search",
    match: /search|filter|find|lookup/i,
    intent: "ui.search",
    title: "Search & filter",
    hotLabel: "search filter",
    branch: "feat/search-filter",
    commit: "feat: add live search filter",
    files: [
      {
        path: "src/components/SearchBar.jsx", added: 12, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · SearchBar.jsx @@" },
          { t: "+", x: "export function SearchBar({ onQuery }) {" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <input" },
          { t: "+", x: "      className=\"pv-search\"" },
          { t: "+", x: "      placeholder=\"Filter tasks…\"" },
          { t: "+", x: "      onChange={(e) => onQuery(e.target.value)}" },
          { t: "+", x: "    />" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
      {
        path: "src/TaskList.jsx", added: 4, removed: 1,
        diff: [
          { t: "h", x: "@@ -5,7 +5,10 @@" },
          { t: " ", x: "export function TaskList({ tasks }) {" },
          { t: "+", x: "  const [query, setQuery] = useState(\"\");" },
          { t: "-", x: "  const visible = tasks;" },
          { t: "+", x: "  const visible = tasks.filter((t) =>" },
          { t: "+", x: "    t.text.toLowerCase().includes(query.toLowerCase())" },
          { t: "+", x: "  );" },
        ],
      },
    ],
    tests: [
      "SearchBar › filters list as you type",
      "SearchBar › case-insensitive match",
      "SearchBar › empty state renders on no match",
      "TaskList › regression: all tasks visible by default",
    ],
    apply() {
      todo.features.add("search");
      $("#pvSearchSlot").innerHTML = `<div class="pv-search"><input id="pvSearchInput" placeholder="Filter tasks…" /></div>`;
      $("#pvSearchInput").addEventListener("input", (e) => {
        todo.query = e.target.value.toLowerCase();
        renderTodos();
      });
    },
  },
  {
    id: "delete",
    match: /delete|remove|trash|bin|clear/i,
    intent: "data.delete",
    title: "Delete tasks",
    hotLabel: "delete buttons",
    branch: "feat/delete-tasks",
    commit: "feat: allow deleting tasks",
    files: [
      {
        path: "src/TaskRow.jsx", added: 9, removed: 0,
        diff: [
          { t: "h", x: "@@ -6,6 +6,15 @@" },
          { t: " ", x: "<Checkbox checked={done} />" },
          { t: " ", x: "<span>{text}</span>" },
          { t: "+", x: "<button" },
          { t: "+", x: "  className=\"pv-del\"" },
          { t: "+", x: "  aria-label=\"delete task\"" },
          { t: "+", x: "  onClick={() => removeTask(id)}" },
          { t: "+", x: ">" },
          { t: "+", x: "  ✕" },
          { t: "+", x: "</button>" },
        ],
      },
      {
        path: "src/store.js", added: 5, removed: 0,
        diff: [
          { t: "h", x: "@@ -12,4 +12,9 @@" },
          { t: " ", x: "export const actions = {" },
          { t: "+", x: "  removeTask(id) {" },
          { t: "+", x: "    state.tasks = state.tasks.filter((t) => t.id !== id);" },
          { t: "+", x: "    persist(state);" },
          { t: "+", x: "  }," },
          { t: "+", x: "};" },
        ],
      },
    ],
    tests: [
      "TaskRow › delete button removes task",
      "TaskRow › removal animates out before unmount",
      "store › removeTask persists state",
      "TaskList › regression: remaining tasks unaffected",
    ],
    apply() {
      todo.features.add("delete");
      renderTodos();
    },
  },
  {
    id: "duedate",
    match: /due|deadline|date|calendar|schedule/i,
    intent: "data.due_date",
    title: "Due dates",
    hotLabel: "due date badges",
    branch: "feat/due-dates",
    commit: "feat: add due date badges",
    files: [
      {
        path: "src/components/DueDate.jsx", added: 11, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · DueDate.jsx @@" },
          { t: "+", x: "export function DueDate({ date }) {" },
          { t: "+", x: "  if (!date) return null;" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <span className=\"pv-due\">" },
          { t: "+", x: "      ◷ {formatRelative(date)}" },
          { t: "+", x: "    </span>" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
      {
        path: "src/TaskRow.jsx", added: 2, removed: 0,
        diff: [
          { t: "h", x: "@@ -7,4 +7,6 @@" },
          { t: " ", x: "<span>{text}</span>" },
          { t: "+", x: "<DueDate date={task.due} />" },
          { t: "+", x: "" },
        ],
      },
    ],
    tests: [
      "DueDate › renders relative label",
      "DueDate › hidden when task has no date",
      "TaskRow › badge aligns right of title",
      "TaskList › regression: dates survive toggle",
    ],
    apply() {
      todo.features.add("duedate");
      todo.tasks.forEach((t) => { if (!t.due) t.due = nextDue(); });
      renderTodos();
    },
  },
  {
    id: "counter",
    match: /count|total|stats|how many|number of/i,
    intent: "ui.counter",
    title: "Task counter",
    hotLabel: "task counter",
    branch: "feat/task-counter",
    commit: "feat: add live task counter",
    files: [
      {
        path: "src/components/Counter.jsx", added: 8, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · Counter.jsx @@" },
          { t: "+", x: "export function Counter({ tasks }) {" },
          { t: "+", x: "  const open = tasks.filter((t) => !t.done).length;" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <span className=\"pv-chip\">" },
          { t: "+", x: "      {open} open · {tasks.length - open} done" },
          { t: "+", x: "    </span>" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
    ],
    tests: [
      "Counter › shows open vs done split",
      "Counter › updates on add / toggle / delete",
      "TaskList › regression: header layout intact",
    ],
    apply() {
      todo.features.add("counter");
      $("#pvExtras").insertAdjacentHTML("beforeend", `<span class="pv-chip" id="pvCounterChip"></span>`);
      syncChrome();
    },
  },
  {
    id: "confetti",
    match: /confetti|celebrat|party|fun|delight/i,
    intent: "ux.delight",
    title: "Completion confetti",
    hotLabel: "confetti on complete",
    branch: "feat/celebrations",
    commit: "feat: celebrate completed tasks with confetti",
    files: [
      {
        path: "src/lib/confetti.js", added: 15, removed: 0,
        diff: [
          { t: "h", x: "@@ new file · confetti.js @@" },
          { t: "+", x: "export function burst(x, y, n = 45) {" },
          { t: "+", x: "  for (let i = 0; i < n; i++) {" },
          { t: "+", x: "    particles.push({" },
          { t: "+", x: "      x, y," },
          { t: "+", x: "      vx: rand(-4, 4)," },
          { t: "+", x: "      vy: rand(-7, -2)," },
          { t: "+", x: "      color: pick(PALETTE)," },
          { t: "+", x: "    });" },
          { t: "+", x: "  }" },
          { t: "+", x: "}" },
        ],
      },
      {
        path: "src/TaskRow.jsx", added: 3, removed: 1,
        diff: [
          { t: "h", x: "@@ -9,6 +9,8 @@" },
          { t: " ", x: "function onToggle(e) {" },
          { t: "-", x: "  toggle(task.id);" },
          { t: "+", x: "  toggle(task.id);" },
          { t: "+", x: "  if (!task.done) burst(e.clientX, e.clientY);" },
          { t: "+", x: "}" },
        ],
      },
    ],
    tests: [
      "confetti › burst spawns 45 particles",
      "TaskRow › fires only on complete, not un-complete",
      "TaskList › regression: no layout shift on burst",
    ],
    apply() {
      todo.features.add("confetti");
    },
  },
];

function makeCustomFeature(request) {
  const kebab = request.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32) || "custom";
  return {
    id: "custom",
    match: null,
    intent: "custom.module",
    title: `Custom module: “${request.length > 40 ? request.slice(0, 40) + "…" : request}”`,
    hotLabel: "custom module",
    branch: `feat/${kebab}`,
    commit: `feat: ${request.slice(0, 60)}`,
    requestText: request,
    files: [
      {
        path: `src/features/${kebab}.jsx`, added: 12, removed: 0,
        diff: [
          { t: "h", x: `@@ new file · ${kebab}.jsx @@` },
          { t: "+", x: "// generated from natural-language request:" },
          { t: "+", x: `// "${request.slice(0, 72)}"` },
          { t: "+", x: "" },
          { t: "+", x: "export function CustomFeature() {" },
          { t: "+", x: "  return (" },
          { t: "+", x: "    <div className=\"pv-banner\">" },
          { t: "+", x: "      ✨ AI-generated module wired in" },
          { t: "+", x: "    </div>" },
          { t: "+", x: "  );" },
          { t: "+", x: "}" },
        ],
      },
    ],
    tests: [
      "CustomFeature › module mounts without errors",
      "CustomFeature › banner renders request label",
      "TaskList › regression: base app unaffected",
    ],
    apply() {
      $("#pvBannerSlot").innerHTML = `<div class="pv-banner">✨ AI module wired in — “${escapeHtml(request.length > 52 ? request.slice(0, 52) + "…" : request)}”</div>`;
    },
  };
}

function detectFeatures(request) {
  const hits = FEATURES.filter((f) => f.match.test(request)).slice(0, 3);
  return hits.length ? hits : [makeCustomFeature(request)];
}

/* ─────────────────────────────────────────────────────────
   pipeline runner
   ───────────────────────────────────────────────────────── */
const STEPS = [
  { id: "parse", label: "Parsing intent" },
  { id: "gen", label: "Generating code" },
  { id: "pr", label: "Creating PR" },
  { id: "test", label: "Running tests" },
  { id: "deploy", label: "Deploying preview" },
  { id: "done", label: "Done" },
];

let runToken = 0;
let runStart = 0;

function timestamp() {
  const ms = Date.now() - runStart;
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
}

function log(msg, cls = "info") {
  const term = $("#terminal");
  const el = document.createElement("div");
  el.className = `tl tl-${cls}`;
  el.innerHTML = `<span class="ts">${timestamp()}</span>${msg}`;
  term.appendChild(el);
  term.scrollTop = term.scrollHeight;
  return el;
}

function buildSteps() {
  $("#stepsList").innerHTML = STEPS.map(
    (s, i) => `
    <li class="step" data-step="${s.id}">
      <div class="step-node"><span class="step-num">${i + 1}</span></div>
      <div class="step-body">
        <div class="step-label">${s.label}</div>
        <div class="step-sub">queued</div>
      </div>
      <div class="step-time"></div>
    </li>`
  ).join("");
}

function setStep(id, state, sub, timeMs) {
  const li = document.querySelector(`.step[data-step="${id}"]`);
  if (!li) return;
  li.classList.remove("active", "done");
  if (state) li.classList.add(state);
  if (sub !== undefined) li.querySelector(".step-sub").textContent = sub;
  if (state === "done") {
    li.querySelector(".step-node").innerHTML = '<span class="step-num">✓</span>';
    if (timeMs !== undefined) li.querySelector(".step-time").textContent = (timeMs / 1000).toFixed(1) + "s";
  }
}

function setPill(state, text) {
  const pill = $("#statusPill");
  pill.className = `pill pill-${state}`;
  pill.querySelector(".pill-text").textContent = text;
}

async function step(name, sub, fn) {
  const t0 = Date.now();
  setStep(name, "active", sub);
  await fn();
  setStep(name, "done", sub, Date.now() - t0);
}

/* ── individual pipeline stages ── */

async function runPipeline(request) {
  const token = ++runToken;
  const bail = () => { if (token !== runToken) throw new Error("cancelled"); };
  const wait = async (ms) => { await sleep(ms * PACE); bail(); };

  const features = detectFeatures(request);
  const composite = features.length > 1;
  const totals = features.reduce(
    (acc, f) => ({
      added: acc.added + f.files.reduce((a, x) => a + x.added, 0),
      removed: acc.removed + f.files.reduce((a, x) => a + x.removed, 0),
      files: acc.files + f.files.length,
    }),
    { added: 0, removed: 0, files: 0 }
  );
  const tests = [...features.flatMap((f) => f.tests), "build › bundle compiles clean"];
  const prNum = rand(1180, 9840);
  const slug = Math.random().toString(36).slice(2, 8);

  // reset UI
  runStart = Date.now();
  buildSteps();
  $("#terminal").innerHTML = "";
  $("#prCard").hidden = true;
  $("#prCard").classList.remove("revealed", "merged");
  $("#previewBadge").hidden = true;
  $("#previewUrl").textContent = "selfship.dev/preview/standby";
  $("#previewStage").innerHTML = `
    <div id="previewPlaceholder" class="preview-placeholder">
      <div class="ph-icon">◌</div>
      <div class="ph-text">awaiting deployment…</div>
      <div class="ph-sub">the preview mutates here when the hot update lands</div>
    </div>`;
  todo.mounted = false;
  setPill("running", "running");
  $("#runId").textContent = `run #${prNum}`;
  $("#reqEcho").textContent = request.length > 60 ? request.slice(0, 60) + "…" : request;

  try {
    /* ── 1 · parse ── */
    await step("parse", "tokenizing…", async () => {
      await wait(500);
      log(`$ selfship "${escapeHtml(request)}"`, "cmd");
      log("tokenizing input…", "info");
      await wait(550);
      if (composite) log(`composite request — ${features.length} intents detected`, "warn");
      for (const f of features) {
        log(`intent: <b>${f.intent}</b> · confidence 0.9${rand(4, 8)}`, "ok");
        await wait(300);
      }
      log(`target: embedded preview app (todo-app v1.0)`, "info");
      await wait(250);
    });
    setStep("parse", "done", `${features.length} intent${composite ? "s" : ""} locked`);

    /* ── 2 · generate ── */
    await step("gen", "writing code…", async () => {
      await wait(420);
      log(`planning changes… ${totals.files} file${totals.files > 1 ? "s" : ""} affected`, "info");
      await wait(500);
      for (const f of features) {
        for (const file of f.files) {
          log(`✎ ${file.removed === 0 ? "create" : "patch "} ${file.path} <span style="color:var(--phosphor)">+${file.added}</span>${file.removed ? ` <span style="color:var(--red)">−${file.removed}</span>` : ""}`, "file");
          await wait(rand(320, 520));
        }
      }
      log(`${totals.added} additions, ${totals.removed} deletions across ${totals.files} files`, "ok");
      await wait(300);
    });
    setStep("gen", "done", `+${totals.added} −${totals.removed}`);

    /* ── 3 · PR ── */
    await step("pr", "git ops…", async () => {
      const f0 = features[0];
      await wait(400);
      log(`$ git checkout -b ${f0.branch}`, "cmd");
      await wait(450);
      log(`$ git commit -m "${escapeHtml(f0.commit)}"`, "cmd");
      await wait(450);
      log("$ git push origin HEAD", "cmd");
      await wait(420);
      log(`opened PR <b>#${prNum}</b> · review requested from @selfship-bot`, "accent");
      await wait(250);
    });
    setStep("pr", "done", `PR #${prNum}`);

    /* ── 4 · tests ── */
    await step("test", "0 passing…", async () => {
      await wait(380);
      log("$ vitest run --reporter=verbose", "cmd");
      await wait(380);
      let passed = 0;
      for (const t of tests) {
        const line = log(`  ⠋ ${escapeHtml(t)}`, "info");
        await wait(rand(220, 380));
        line.className = "tl tl-ok";
        line.innerHTML = `<span class="ts">${timestamp()}</span>  ✓ ${escapeHtml(t)} <span style="color:var(--faint)">(${rand(18, 240)}ms)</span>`;
        passed++;
        setStep("test", "active", `${passed}/${tests.length} passing`);
      }
      log(`${passed} passed, 0 failed · ${(rand(140, 220) / 100).toFixed(2)}s`, "ok");
      await wait(280);
    });
    setStep("test", "done", `${tests.length}/${tests.length} green`);

    /* ── 5 · deploy ── */
    await step("deploy", "pushing to edge…", async () => {
      await wait(420);
      log(`bundling preview… ${rand(118, 186)} kB`, "info");
      await wait(480);
      log("pushing to edge (sfo1, iad1, fra1)…", "info");
      await wait(520);
      $("#previewUrl").textContent = `preview.selfship.run/${slug}`;
      log(`live → https://preview.selfship.run/${slug}`, "ok");
      mountTodoApp();
      renderTodos();
      $("#previewBadge").hidden = false;
      await wait(650);
      for (const f of features) {
        log(`hot update: ${f.hotLabel}`, "warn");
        f.apply();
        flashApp();
        toast(`⚡ hot update — ${f.hotLabel}`);
        await wait(800);
      }
      await wait(250);
    });
    setStep("deploy", "done", "preview live");

    /* ── 6 · done ── */
    await step("done", "wrapping up…", async () => {
      await wait(420);
      const total = ((Date.now() - runStart) / 1000).toFixed(1);
      log(`pipeline complete in ${total}s — ship it?`, "accent");
      await wait(200);
    });
    setStep("done", "done", "ready to merge");
    setPill("deployed", "deployed");

    showPrCard(features, totals, tests, prNum);
  } catch (e) {
    if (e.message !== "cancelled") throw e;
  }
}

/* ── PR card ── */

function showPrCard(features, totals, tests, prNum) {
  const f0 = features[0];
  $("#prNum").textContent = `#${prNum}`;
  $("#prTitle").textContent = features.length > 1
    ? `${f0.commit} (+${features.length - 1} more)`
    : f0.commit;
  $("#prBranch").textContent = f0.branch;
  $("#prStats").innerHTML = `
    <span class="stat-add">+${totals.added}</span>
    <span class="stat-del">−${totals.removed}</span>
    <span class="stat-files">${totals.files} files</span>`;
  $("#prChecks").innerHTML = [
    `✓ tests ${tests.length}/${tests.length}`,
    "✓ build",
    "✓ preview live",
    "✓ no conflicts",
  ].map((c) => `<span class="check">${c}</span>`).join("");

  $("#prDiff").innerHTML = features.flatMap((f) => f.files).map((file) => `
    <div class="diff-file">
      <div class="diff-fh">
        <span>${file.path}</span>
        <span class="fh-stats"><b class="a">+${file.added}</b> ${file.removed ? `<b class="d">−${file.removed}</b>` : ""}</span>
      </div>
      <pre>${file.diff.map((l) => {
        const cls = { "+": "dl-add", "-": "dl-del", " ": "dl-ctx", h: "dl-hunk" }[l.t];
        const g = { "+": "+", "-": "−", "": " ", h: " " }[l.t] || " ";
        return `<span class="dl ${cls}"><span class="dl-gutter">${g}</span>${escapeHtml(l.x) || " "}</span>`;
      }).join("")}</pre>
    </div>`).join("");

  const mergeBtn = $("#mergeBtn");
  mergeBtn.disabled = false;
  mergeBtn.innerHTML = "⎇ Merge pull request";
  $("#againBtn").hidden = true;

  const card = $("#prCard");
  card.hidden = false;
  requestAnimationFrame(() => {
    card.classList.add("revealed");
    card.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "nearest" });
  });
}

function wireMerge() {
  $("#mergeBtn").addEventListener("click", async () => {
    const btn = $("#mergeBtn");
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = "merging…";
    await sleep(850 * PACE);
    $("#prCard").classList.add("merged");
    btn.innerHTML = "✓ merged into main";
    $("#againBtn").hidden = false;
    setPill("merged", "merged");
    log("PR merged · preview promoted to production ✔", "accent");
    const r = btn.getBoundingClientRect();
    fireConfetti(r.left + r.width / 2, r.top + r.height / 2, 150, 9);
    setTimeout(() => fireConfetti(innerWidth * 0.22, innerHeight * 0.3, 90, 8), 220);
    setTimeout(() => fireConfetti(innerWidth * 0.78, innerHeight * 0.28, 90, 8), 380);
  });
}

/* ── confetti ── */

function fireConfetti(x, y, count = 120, power = 8) {
  if (REDUCED) return;
  const canvas = document.createElement("canvas");
  canvas.className = "confetti-canvas";
  canvas.width = innerWidth;
  canvas.height = innerHeight;
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  const colors = ["#3dffb8", "#58c4ff", "#b79cff", "#ffb454", "#ffffff"];
  const parts = Array.from({ length: count }, () => ({
    x, y,
    vx: (Math.random() - 0.5) * power,
    vy: (Math.random() - 0.85) * power,
    w: rand(4, 8), h: rand(3, 6),
    rot: Math.random() * Math.PI,
    vr: (Math.random() - 0.5) * 0.3,
    color: pick(colors),
    life: 1,
    decay: 0.008 + Math.random() * 0.01,
  }));

  (function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = false;
    for (const p of parts) {
      if (p.life <= 0) continue;
      alive = true;
      p.vy += 0.16; p.vx *= 0.99; p.vy *= 0.99;
      p.x += p.vx; p.y += p.vy;
      p.rot += p.vr; p.life -= p.decay;
      ctx.save();
      ctx.globalAlpha = Math.max(p.life, 0);
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx.restore();
    }
    if (alive) requestAnimationFrame(frame);
    else canvas.remove();
  })();
}

/* ── view switching & wiring ── */

function switchView(from, to) {
  from.classList.add("leaving");
  setTimeout(() => {
    from.hidden = true;
    from.classList.remove("leaving");
    to.hidden = false;
    to.classList.add("entering");
    setTimeout(() => to.classList.remove("entering"), 600);
  }, REDUCED ? 10 : 240);
}

function startRun(request) {
  const landing = $("#landingView");
  const pipeline = $("#pipelineView");
  switchView(landing, pipeline);
  setTimeout(() => runPipeline(request), REDUCED ? 20 : 260);
}

function resetToLanding() {
  runToken++; // cancel any in-flight pipeline
  const landing = $("#landingView");
  const pipeline = $("#pipelineView");
  switchView(pipeline, landing);
  const input = $("#requestInput");
  input.value = "";
  setTimeout(() => input.focus(), 350);
}

function init() {
  const form = $("#shipForm");
  const input = $("#requestInput");

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const request = input.value.trim();
    if (!request) {
      const bar = $(".shipbar");
      bar.classList.remove("shake");
      void bar.offsetWidth;
      bar.classList.add("shake");
      input.focus();
      return;
    }
    startRun(request);
  });

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      input.value = chip.dataset.prompt;
      form.requestSubmit();
    });
  });

  $("#backBtn").addEventListener("click", resetToLanding);
  $("#againBtn").addEventListener("click", resetToLanding);
  wireMerge();

  input.focus();
}

document.addEventListener("DOMContentLoaded", init);
