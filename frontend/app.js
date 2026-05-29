const state = { sessionId: null, style: "friendly", reviewStarted: false };

const $ = (sel) => document.querySelector(sel);
const views = ["config", "interview", "feedback", "review", "wiki"];

function showView(name) {
  views.forEach((v) => {
    const el = $("#view-" + v);
    if (el) el.hidden = v !== name;
  });
  document.querySelectorAll(".nav-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });
  if (name === "wiki") loadWiki();
}

document.querySelectorAll(".nav-btn").forEach((b) => {
  b.addEventListener("click", () => showView(b.dataset.view));
});

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => (t.hidden = true), ms);
}

// ---- 流式请求:逐行解析 ndjson ----
async function streamPost(url, body, onObj) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onObj(JSON.parse(line));
    }
  }
  if (buf.trim()) onObj(JSON.parse(buf.trim()));
}

// ================= 配置屏 =================
$("#cfg-style").addEventListener("click", (e) => {
  if (!e.target.dataset.style) return;
  document.querySelectorAll("#cfg-style .seg-btn").forEach((b) => b.classList.remove("active"));
  e.target.classList.add("active");
  state.style = e.target.dataset.style;
});

$("#btn-start").addEventListener("click", async () => {
  const job = $("#cfg-job").value.trim() || "通用岗位";
  const persona = $("#cfg-persona").value.trim();
  $("#btn-start").disabled = true;
  $("#iv-messages").innerHTML = "";
  $("#iv-monologue").innerHTML = "";
  $("#iv-observer").innerHTML = "";
  $("#iv-job-tag").textContent = job + " · 面试中";
  updateSwitchBtn();
  showView("interview");

  const bot = appendMsg("iv-messages", "bot", "");
  const monoEl = $("#iv-monologue");
  try {
    await streamPost("/api/session/start", { job, style: state.style, persona }, (o) => {
      if (o.type === "session") state.sessionId = o.session_id;
      else if (o.type === "monologue") monoEl.textContent += o.text;
      else if (o.type === "reply") { bot.textContent += o.text; scrollChat("iv-messages"); }
      else if (o.type === "error") { bot.textContent = "（" + o.text + "）"; }
    });
  } catch (e) {
    bot.textContent = "（连接失败,请检查后端与 API Key）";
  }
  $("#btn-start").disabled = false;
});

// ================= 面试屏 =================
function appendMsg(containerId, cls, text) {
  const div = document.createElement("div");
  div.className = "msg " + cls;
  div.textContent = text;
  $("#" + containerId).appendChild(div);
  scrollChat(containerId);
  return div;
}
function scrollChat(id) { const c = $("#" + id); c.scrollTop = c.scrollHeight; }

function updateSwitchBtn() {
  $("#btn-switch").textContent =
    state.style === "friendly" ? "切换为高压模式" : "切换为友善模式";
}

async function sendInterview() {
  const input = $("#iv-input");
  const text = input.value.trim();
  if (!text || !state.sessionId) return;
  input.value = "";
  appendMsg("iv-messages", "user", text);
  const bot = appendMsg("iv-messages", "bot", "");
  $("#iv-monologue").innerHTML = "";
  const monoEl = $("#iv-monologue");
  try {
    await streamPost("/api/interview/message", { session_id: state.sessionId, message: text }, (o) => {
      if (o.type === "monologue") monoEl.textContent += o.text;
      else if (o.type === "reply") { bot.textContent += o.text; scrollChat("iv-messages"); }
      else if (o.type === "observer") renderObserver(o.record);
      else if (o.type === "error") { bot.textContent += "（" + o.text + "）"; }
    });
  } catch (e) {
    bot.textContent += "（连接中断）";
  }
}

$("#iv-send").addEventListener("click", sendInterview);
$("#iv-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendInterview(); }
});

function renderObserver(rec) {
  const box = $("#iv-observer");
  if (box.querySelector(".muted")) box.innerHTML = "";
  const groups = [
    ["经历", "exp", (rec.experiences || []).map((e) => `${e.title || ""}：${e.detail || ""}`)],
    ["能力信号", "sig", (rec.competency_signals || []).map((s) => `${s.competency || ""}（${s.level || ""}）：${s.signal || ""}`)],
    ["薄弱点", "weak", rec.weak_points || []],
    ["矛盾", "contra", rec.contradictions || []],
  ];
  groups.forEach(([label, cls, items]) => {
    if (!items.length) return;
    const g = document.createElement("div");
    g.className = "rec-group";
    g.innerHTML = `<h4>${label}</h4>`;
    items.forEach((it) => {
      const d = document.createElement("div");
      d.className = "rec-item " + cls;
      d.textContent = it;
      g.appendChild(d);
    });
    box.appendChild(g);
  });
  box.scrollTop = box.scrollHeight;
}

$("#btn-switch").addEventListener("click", async () => {
  if (!state.sessionId) return;
  const next = state.style === "friendly" ? "pressure" : "friendly";
  await fetch("/api/interview/switch_persona", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId, style: next }),
  });
  state.style = next;
  updateSwitchBtn();
  toast(next === "pressure" ? "已切换为高压模式" : "已切换为友善模式");
});

$("#btn-end").addEventListener("click", async () => {
  if (!state.sessionId) return;
  $("#btn-end").disabled = true;
  const fb = $("#fb-content");
  fb.textContent = "面试官正在整理点评…";
  showView("feedback");
  let started = false;
  try {
    await streamPost("/api/interview/end", { session_id: state.sessionId }, (o) => {
      if (o.type === "reply") {
        if (!started) { fb.textContent = ""; started = true; }
        fb.textContent += o.text;
      } else if (o.type === "error") {
        fb.textContent = "（" + o.text + "）";
      }
    });
    if (started && !fb.textContent.trim()) fb.textContent = "（无反馈）";
  } catch (e) {
    fb.textContent = "（连接失败,请检查后端与 API Key）";
  }
  $("#btn-end").disabled = false;
});

// ================= 复盘屏 =================
$("#btn-to-review").addEventListener("click", () => {
  showView("review");
  if (!state.reviewStarted) {
    state.reviewStarted = true;
    startReview("");
  }
});

async function startReview(text) {
  const bot = appendMsg("rv-messages", "coach", "");
  try {
    await streamPost("/api/review/message", { session_id: state.sessionId, message: text }, (o) => {
      if (o.type === "reply") { bot.textContent += o.text; scrollChat("rv-messages"); }
      else if (o.type === "error") { bot.textContent += "（" + o.text + "）"; }
    });
  } catch (e) {
    bot.textContent += "（连接中断）";
  }
}

async function sendReview() {
  const input = $("#rv-input");
  const text = input.value.trim();
  if (!text || !state.sessionId) return;
  input.value = "";
  appendMsg("rv-messages", "user", text);
  await startReview(text);
}

$("#rv-send").addEventListener("click", sendReview);
$("#rv-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReview(); }
});

$("#btn-commit").addEventListener("click", async () => {
  if (!state.sessionId) return;
  const btn = $("#btn-commit");
  btn.disabled = true;
  btn.textContent = "整理中…";
  showView("wiki");
  showWikiPane("content");
  const box = $("#wiki-content");
  box.innerHTML = '<h2>正在整理画像…</h2><div class="activity" id="ingest-activity"></div>';
  const act = $("#ingest-activity");
  let errored = false, summary = "";
  try {
    await streamPost("/api/wiki/commit", { session_id: state.sessionId }, (o) => {
      if (o.type === "activity") { appendActivity(act, o.text); }
      else if (o.type === "error") { errored = true; appendActivity(act, "⚠ " + o.text); }
      else if (o.type === "done") { summary = o.summary; }
    });
  } catch (e) { errored = true; toast("整理失败,请重试"); }
  btn.disabled = false;
  btn.textContent = "整理并写入 Wiki";
  if (!errored) {
    appendActivity(act, "✓ " + (summary || "已写入 Wiki"));
    toast(summary || "已写入 Wiki");
  }
  await loadWiki();
});

function appendActivity(container, text) {
  const d = document.createElement("div");
  d.className = "act-line";
  d.textContent = text;
  container.appendChild(d);
  container.scrollTop = container.scrollHeight;
}

// ================= Wiki 屏 =================
const wikiPanes = ["content", "query", "lint"];
function showWikiPane(name) {
  $("#wiki-content").hidden = name !== "content";
  $("#wiki-query").hidden = name !== "query";
  $("#wiki-lint").hidden = name !== "lint";
}

async function loadWiki() {
  const r = await fetch("/api/wiki/tree");
  const data = await r.json();
  $("#wiki-meta").textContent = `已积累 ${data.interviews} 次面试`;
  const ul = $("#wiki-tree");
  ul.innerHTML = "";
  state.wikiFiles = [];

  const fileLi = (node) => {
    const li = document.createElement("li");
    li.className = "wt-file";
    li.textContent = "› " + node.label;
    li.addEventListener("click", () => {
      ul.querySelectorAll("li").forEach((x) => x.classList.remove("active"));
      li.classList.add("active");
      openWikiFile(node.path);
    });
    state.wikiFiles.push({ label: node.label, path: node.path });
    return li;
  };

  data.tree.forEach((node) => {
    if (node.type === "dir") {
      const head = document.createElement("li");
      head.className = "wt-dir";
      head.textContent = node.label + ` (${(node.children || []).length})`;
      ul.appendChild(head);
      (node.children || []).forEach((c) => ul.appendChild(fileLi(c)));
    } else {
      ul.appendChild(fileLi(node));
    }
  });
}

async function openWikiFile(path) {
  showWikiPane("content");
  const r = await fetch("/api/wiki/file?path=" + encodeURIComponent(path));
  const data = await r.json();
  $("#wiki-content").innerHTML = renderMarkdown(stripFrontmatter(data.content || "（暂无内容）"));
}

function stripFrontmatter(md) {
  const m = md.match(/^---\s*\n[\s\S]*?\n---\s*\n?/);
  return m ? md.slice(m[0].length) : md;
}

// 解析 [[标题]] 互链:在已知文件里找匹配的页面,点击跳转
function resolveWikiLink(title) {
  const files = state.wikiFiles || [];
  const t = title.trim().toLowerCase();
  return (
    files.find((f) => f.label.toLowerCase() === t) ||
    files.find((f) => f.label.toLowerCase().includes(t) || t.includes(f.label.toLowerCase()))
  );
}

// 点击渲染区里的 [[链接]]
document.addEventListener("click", (e) => {
  const a = e.target.closest(".wikilink");
  if (!a) return;
  const hit = resolveWikiLink(a.dataset.link);
  if (hit) {
    const ul = $("#wiki-tree");
    ul.querySelectorAll("li").forEach((x) => x.classList.remove("active"));
    openWikiFile(hit.path);
  } else {
    toast("还没有「" + a.dataset.link + "」这一页");
  }
});

// 极简 markdown 渲染(标题/列表/粗体/代码/分隔线/[[互链]])
function renderMarkdown(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (line) =>
    line
      .replace(/\[\[(.+?)\]\]/g, (_, t) => `<a class="wikilink" data-link="${t}">${t}</a>`)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`(.+?)`/g, "<code>$1</code>");
  const lines = md.split("\n");
  let html = "", inList = false, inCode = false, code = "";
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (let raw of lines) {
    if (/^```/.test(raw)) {
      if (inCode) { html += "<pre><code>" + esc(code) + "</code></pre>"; code = ""; inCode = false; }
      else { closeList(); inCode = true; }
      continue;
    }
    if (inCode) { code += raw + "\n"; continue; }
    let line = inline(esc(raw));
    if (/^###\s+/.test(raw)) { closeList(); html += "<h3>" + line.replace(/^###\s+/, "") + "</h3>"; }
    else if (/^##\s+/.test(raw)) { closeList(); html += "<h2>" + line.replace(/^##\s+/, "") + "</h2>"; }
    else if (/^#\s+/.test(raw)) { closeList(); html += "<h1>" + line.replace(/^#\s+/, "") + "</h1>"; }
    else if (/^---+\s*$/.test(raw)) { closeList(); html += "<hr>"; }
    else if (/^\s*[-*]\s+/.test(raw)) { if (!inList) { html += "<ul>"; inList = true; } html += "<li>" + line.replace(/^\s*[-*]\s+/, "") + "</li>"; }
    else if (raw.trim() === "") { closeList(); }
    else { closeList(); html += "<p>" + line + "</p>"; }
  }
  if (inCode) html += "<pre><code>" + esc(code) + "</code></pre>";
  closeList();
  return html;
}

// ---- Query: 问问画像 ----
state.queryHistory = [];
$("#btn-query").addEventListener("click", () => showWikiPane("query"));
document.querySelectorAll("[data-close]").forEach((b) =>
  b.addEventListener("click", () => showWikiPane("content"))
);

async function sendQuery() {
  const input = $("#q-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  appendMsg("q-messages", "user", text);
  const bot = appendMsg("q-messages", "coach", "");
  bot.classList.add("thinking");
  bot.textContent = "查阅画像中…";
  let reply = "";
  try {
    await streamPost("/api/wiki/query", { history: state.queryHistory, message: text }, (o) => {
      if (o.type === "activity") { bot.textContent = "· " + o.text; }
      else if (o.type === "reply") { reply = o.text; bot.classList.remove("thinking"); bot.innerHTML = renderMarkdown(reply); scrollChat("q-messages"); }
      else if (o.type === "error") { bot.classList.remove("thinking"); bot.textContent = "（" + o.text + "）"; }
    });
  } catch (e) { bot.classList.remove("thinking"); bot.textContent = "（连接中断）"; }
  if (reply) {
    state.queryHistory.push({ role: "user", content: text });
    state.queryHistory.push({ role: "assistant", content: reply });
  }
}
$("#q-send").addEventListener("click", sendQuery);
$("#q-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQuery(); }
});

// ---- Lint: 体检 + 下场提纲 ----
$("#btn-lint").addEventListener("click", async () => {
  showWikiPane("lint");
  const act = $("#lint-activity");
  const rep = $("#lint-report");
  const qWrap = $("#lint-questions");
  act.innerHTML = "";
  rep.innerHTML = "";
  qWrap.hidden = true;
  let report = "", questions = [];
  try {
    await streamPost("/api/wiki/lint", {}, (o) => {
      if (o.type === "activity") { appendActivity(act, o.text); }
      else if (o.type === "report") { report = o.text; questions = o.questions || []; }
      else if (o.type === "error") { appendActivity(act, "⚠ " + o.text); }
    });
  } catch (e) { appendActivity(act, "⚠ 体检失败"); }
  if (report) {
    act.innerHTML = "";
    // 报告里末尾的 json 代码块不展示
    rep.innerHTML = renderMarkdown(report.replace(/```(?:json)?\s*\{[\s\S]*?\}\s*```/g, ""));
  }
  if (questions.length) {
    const list = $("#lint-q-list");
    list.innerHTML = "";
    questions.forEach((q) => {
      const li = document.createElement("li");
      li.textContent = q;
      list.appendChild(li);
    });
    state.nextQuestions = questions;
    qWrap.hidden = false;
  }
});

$("#btn-use-questions").addEventListener("click", () => {
  const qs = state.nextQuestions || [];
  if (qs.length) {
    $("#cfg-persona").value =
      "本场请重点追问以下方向(基于上次画像体检):\n" + qs.map((q, i) => `${i + 1}. ${q}`).join("\n");
  }
  showView("config");
  toast("已把体检提纲带入新面试配置");
});

showView("config");
