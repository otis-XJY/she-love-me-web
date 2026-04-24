const state = {
  status: null,
  contacts: [],
  filtered: [],
  selected: null,
  busy: false,
  logs: [],
  latestReportUrl: "",
  pendingApiKey: "",
  quizIndex: 0,
  quizAnswers: [],
  quizDone: false,
  heroSlideIndex: 0,
};

const $ = (id) => document.getElementById(id);
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8765" : "";
const MASKED_KEY = "••••••••••••";
const PROVIDER_DEFAULTS = {
  openai: { baseUrl: "https://api.openai.com/v1", model: "gpt-4.1" },
  anthropic: { baseUrl: "https://api.anthropic.com/v1", model: "claude-3-5-sonnet-latest" },
  gemini: { baseUrl: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-1.5-pro" },
};
const PANE_META = {
  main: "TA回我了",
  archive: "角色档案",
  personality: "恋爱人格",
  settings: "设置",
};
const ROMAN = ["I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.", "IX.", "X."];
const QUIZ_QUESTIONS = [
  {
    question: "对方三个小时后回“刚忙完”，你的第一反应是？",
    options: [
      "松一口气。TA只是忙，逻辑合理。",
      "怀疑。谁会刚好忙到这个点？",
      "无所谓。我还没看手机。",
      "慌。先在备忘录写三版回复。",
    ],
  },
  {
    question: "连续两天都是你主动开启话题，你会怎么处理？",
    options: [
      "照常聊。关系需要稳定投入。",
      "停一下。我要看TA会不会主动找我。",
      "换个节奏。没必要把聊天当考核。",
      "反复检查上一句是不是说错了。",
    ],
  },
  {
    question: "TA发来一句很短的“嗯嗯”，你更容易读成什么？",
    options: [
      "只是简短确认，不代表态度变差。",
      "温度下降了，可能在敷衍。",
      "信息量太少，先不解读。",
      "我需要补一句，把场面救回来。",
    ],
  },
  {
    question: "你最舒服的恋爱沟通频率是？",
    options: [
      "每天有稳定交流，哪怕很短。",
      "最好频繁一点，不然会没有安全感。",
      "双方自然来，不需要固定打卡。",
      "取决于对方热不热，我会跟着调整。",
    ],
  },
  {
    question: "对方临时取消见面，你第一步会做什么？",
    options: [
      "问清原因，再一起改时间。",
      "判断是不是借口，先观察态度。",
      "接受变化，安排自己的事。",
      "忍住情绪，但心里已经排练很多句。",
    ],
  },
  {
    question: "看到TA在线但没回你，你通常会？",
    options: [
      "先做自己的事，晚点再看。",
      "开始推测TA在回谁。",
      "不太在意，在线不等于要回复。",
      "反复点开聊天框，又假装没事。",
    ],
  },
  {
    question: "你更希望关系里的主动权是什么状态？",
    options: [
      "互相主动，节奏清楚。",
      "TA多给一点确定性，我才放心。",
      "不用谈主动权，舒服就继续。",
      "我会主动，但希望看起来不太主动。",
    ],
  },
  {
    question: "发生误会时，你最自然的处理方式是？",
    options: [
      "直接说清楚，避免越想越乱。",
      "先看对方有没有解释意愿。",
      "冷静一会儿，等情绪降下来再谈。",
      "写很多话，但真正发出去会删掉一半。",
    ],
  },
  {
    question: "如果TA突然变得很热情，你会怎么感受？",
    options: [
      "开心，也会顺着回应。",
      "警觉。是不是有什么原因？",
      "看整体，不被一两天带着走。",
      "兴奋，但又怕自己表现得太明显。",
    ],
  },
  {
    question: "你最想从这段关系里确认什么？",
    options: [
      "我们是不是在认真靠近彼此。",
      "TA到底有没有把我放在重要位置。",
      "这段相处是否让我更自在。",
      "我该怎么回复，才不会失去优势。",
    ],
  },
];
const QUIZ_TYPES = [
  { name: "稳定靠近型", text: "你更看重持续投入和清楚表达，适合用稳定节奏推进关系。" },
  { name: "高敏侦测型", text: "你会快速捕捉温度变化，优势是敏锐，风险是过度解读。" },
  { name: "低卷观察型", text: "你更重视自洽和边界，不轻易被单次互动牵着走。" },
  { name: "预演回复型", text: "你擅长斟酌表达，但也容易在发送前消耗太多情绪。" },
];

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function log(message, data) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}`;
  const extra = data ? `\n${typeof data === "string" ? data : JSON.stringify(data, null, 2)}` : "";
  state.logs.unshift(`${line}${extra}`);
  state.logs = state.logs.slice(0, 80);
  if ($("logLatest")) $("logLatest").textContent = message;
  if ($("log")) $("log").textContent = state.logs.join("\n\n");
}

async function api(path, options = {}) {
  setBusy(true);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json" },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data.error || "请求失败"), { data });
    return data;
  } finally {
    setBusy(false);
  }
}

function setBusy(value) {
  state.busy = value;
  document.body.classList.toggle("busy", value);
  document.querySelectorAll("button").forEach((button) => {
    if (button.id !== "clearLog") button.toggleAttribute("aria-busy", value);
  });
}

function switchPane(name) {
  const aliases = { setup: "settings", decrypt: "main", contact: "main", analysis: "main", report: "main" };
  name = aliases[name] || name;
  document.body.dataset.pane = name;
  document.body.classList.remove("pane-changing");
  void document.body.offsetWidth;
  document.body.classList.add("pane-changing");
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.step === name));
  document.querySelectorAll(".pane").forEach((el) => el.classList.toggle("visible", el.id === `pane-${name}`));
  $("panelTitle").textContent = PANE_META[name] || PANE_META.main;
}

function scrollToPane(id) {
  requestAnimationFrame(() => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function renderStatus(status, options = {}) {
  const { loadLatestReport = true } = options;
  state.status = status;
  if ($("runtimePath")) $("runtimePath").textContent = status.runtime_root || "-";
  if ($("llmState")) $("llmState").textContent = status.llm_configured ? `${status.llm_provider || "openai"} · ${status.llm_model || "已配置"}` : "未配置";
  if ($("environmentBadge")) {
    $("environmentBadge").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");
    $("environmentBadge").classList.toggle("bad", !status.environment_ready);
  }
  document.body.classList.toggle("environment-ready", Boolean(status.environment_ready));
  if ($("heroStatusText")) {
    $("heroStatusText").textContent = status.environment_ready ? "环境就绪，可以向下开始" : "环境异常，请到设置页检查";
  }
  if ($("heroStatusBar")) {
    $("heroStatusBar").style.width = status.environment_ready ? "100%" : "42%";
  }

  if ($("llmProvider")) $("llmProvider").value = status.llm_provider || "openai";
  if ($("llmBaseUrl")) $("llmBaseUrl").value = status.llm_base_url || "";
  if ($("llmModel")) $("llmModel").value = status.llm_model || "";
  if ($("configHint")) {
    $("configHint").textContent = `当前：${status.llm_provider || "openai"} · ${status.llm_base_url || "未设置 BaseURL"} · ${status.llm_model || "未设置模型"} · ${status.llm_key_hint || "未设置"}`;
  }

  const strip = $("runtimeStatus");
  strip.querySelector("i").className = status.environment_ready ? "ok" : "bad";
  strip.querySelector("span").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");
  renderArchives(status.archives || []);
  if (loadLatestReport && status.latest_report) setReport(status.latest_report, { silent: true });
}

function clearMainAnalysis() {
  state.latestReportUrl = "";
  const openReport = $("openReport");
  if (openReport) {
    openReport.href = "#";
    delete openReport.dataset.href;
    openReport.setAttribute("aria-disabled", "true");
    openReport.classList.add("disabled");
  }
  if ($("reportSlot")) $("reportSlot").textContent = "暂无报告。";
  const stage = $("reportStage");
  if (stage) stage.classList.remove("has-report");
  const mount = $("reportMount");
  if (mount) {
    if (mount.shadowRoot) mount.shadowRoot.innerHTML = "";
    mount.innerHTML = "";
  }
  if ($("selectedHint")) $("selectedHint").textContent = "先选择一个联系人。";
}

function renderArchives(archives) {
  const el = $("archives");
  if (!el) return;
  if (!archives.length) {
    el.innerHTML = `<div class="archive-empty">暂无角色档案。完成一次识别并生成报告后，会自动存档在这里。</div>`;
    return;
  }
  el.innerHTML = archives.map((item, index) => {
    const contact = item.contact || "未命名";
    const count = item.message_count ? `${Number(item.message_count).toLocaleString()} 条消息 · ` : "";
    return `
      <article class="archive-card" data-index="${index}">
        <button class="archive-open" type="button">
          <span>${esc(item.relationship_type || "角色档案")}</span>
          <strong title="${esc(contact)}">${esc(contact)}</strong>
          <p>${count}${formatArchiveDate(item.created_at)}</p>
        </button>
        <button class="archive-delete" type="button" aria-label="删除 ${esc(contact)} 的档案">删除</button>
      </article>
    `;
  }).join("");
  el.querySelectorAll(".archive-open").forEach((button) => {
    button.addEventListener("click", () => {
      const item = archives[Number(button.closest(".archive-card").dataset.index)];
      if (item?.report_url) {
        setReport({ name: item.report_name || "报告", url: item.report_url });
        switchPane("main");
      }
    });
  });
  el.querySelectorAll(".archive-delete").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const item = archives[Number(button.closest(".archive-card").dataset.index)];
      deleteArchive(item).catch(handleError);
    });
  });
}

function formatArchiveDate(value) {
  if (!value) return "未知时间";
  return String(value).replace("T", " ").slice(0, 16);
}

async function deleteArchive(item) {
  if (!item) return;
  log(`删除角色档案：${item.contact || item.report_name || item.id}`);
  const data = await api("/api/archive/delete", {
    method: "POST",
    body: { id: item.id, report_name: item.report_name },
  });
  renderStatus(data.status, { loadLatestReport: false });
  clearMainAnalysis();
  log("角色档案已删除", data.deleted);
}

function setReport(report, options = {}) {
  const url = `${API_BASE}${encodeURI(report.url)}`;
  state.latestReportUrl = url;
  const openReport = $("openReport");
  if (openReport) {
    openReport.href = url;
    openReport.dataset.href = url;
    openReport.removeAttribute("aria-disabled");
    openReport.classList.remove("disabled");
  }
  $("reportSlot").innerHTML = `当前报告：<button class="inline-report-link" id="reloadReportBtn">${esc(report.name)}</button>`;
  $("reloadReportBtn")?.addEventListener("click", () => showReport(url));
  showReport(url).catch(handleError);
  if (!options.silent) log("报告已载入当前页面。");
}

async function loadScriptOnce(src) {
  if (document.querySelector(`script[data-report-src="${CSS.escape(src)}"]`)) return;
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.dataset.reportSrc = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function adaptReportCss(css, bodyClass) {
  return css
    .replaceAll(":root", ":host")
    .replaceAll("html", ":host")
    .replace(/body\.report-tone-/g, ".report-document.report-tone-")
    .replace(/body::/g, ".report-document::")
    .replace(/body\s*\{/g, ".report-document {")
    .concat(`
      :host { display:block; contain: content; }
      .report-document { min-height: 100%; overflow: visible; }
      .report-document::before,
      .report-document::after { position: absolute; }
    `);
}

function reportEnhancementCss() {
  return `
    .glass-title {
      position: relative;
      display: inline-block;
      isolation: isolate;
    }
    .glass-title::after {
      content: "";
      position: absolute;
      inset: -10% -4%;
      border-radius: 18px;
      background:
        radial-gradient(circle at var(--glass-x, 50%) var(--glass-y, 50%), rgba(255,255,255,.34), rgba(255,255,255,.1) 16%, transparent 34%),
        linear-gradient(110deg, transparent 0 38%, rgba(255,255,255,.26) 45%, transparent 54% 100%);
      mix-blend-mode: screen;
      opacity: .66;
      filter: blur(.2px);
      transform: translate3d(0, 0, 0);
      pointer-events: none;
      z-index: -1;
    }
    .glass-title::before {
      content: "";
      position: absolute;
      inset: -18% -8%;
      border-radius: 22px;
      border: 1px solid rgba(255,255,255,.14);
      backdrop-filter: blur(7px) saturate(1.35);
      -webkit-backdrop-filter: blur(7px) saturate(1.35);
      opacity: .38;
      pointer-events: none;
      z-index: -2;
    }
  `;
}

function applyGlassTitle(root) {
  const candidates = [
    ".result-hero h1",
    ".report-document h1",
    ".report-document h2",
    ".report-document .main-result",
  ];
  const title = candidates.map((selector) => root.querySelector(selector)).find(Boolean);
  if (!title) return;
  title.classList.add("glass-title");
  title.addEventListener("pointermove", (event) => {
    const rect = title.getBoundingClientRect();
    title.style.setProperty("--glass-x", `${((event.clientX - rect.left) / rect.width) * 100}%`);
    title.style.setProperty("--glass-y", `${((event.clientY - rect.top) / rect.height) * 100}%`);
  });
}

async function showReport(url) {
  const mount = $("reportMount");
  const stage = $("reportStage");
  if (!mount || !stage) return;
  stage.classList.add("has-report");
  const shadow = mount.shadowRoot || (mount.attachShadow ? mount.attachShadow({ mode: "open" }) : null);
  const root = shadow || mount;
  root.innerHTML = "";
  const html = await fetch(url).then((res) => {
    if (!res.ok) throw new Error("报告读取失败");
    return res.text();
  });
  const doc = new DOMParser().parseFromString(html, "text/html");
  const scripts = [...doc.querySelectorAll("script")];
  const styles = [...doc.querySelectorAll("style")].map((style) => style.textContent || "").join("\n");
  const externalScripts = scripts.map((script) => script.src).filter(Boolean);
  const inlineScripts = scripts.filter((script) => !script.src).map((script) => script.textContent || "");
  scripts.forEach((script) => script.remove());
  const bodyClass = doc.body.className || "";

  root.innerHTML = `
    <style>${adaptReportCss(styles, bodyClass)}${reportEnhancementCss()}</style>
    <div class="report-document ${esc(bodyClass)}">${doc.body.innerHTML}</div>
  `;
  applyGlassTitle(root);
  for (const src of externalScripts) await loadScriptOnce(src);
  for (const code of inlineScripts) {
    new Function("document", "window", "Chart", code)(root, window, window.Chart);
  }
}

function renderContacts() {
  const search = $("contactSearch");
  const list = $("contactList");
  if (!search || !list) return;
  const q = search.value.trim().toLowerCase();
  state.filtered = state.contacts.filter((item) => {
    const text = `${item.display_name || ""} ${item.nick_name || ""} ${item.remark || ""} ${item.username || ""}`.toLowerCase();
    return !q || text.includes(q);
  }).slice(0, 120);

  if (!state.filtered.length) {
    list.innerHTML = `<div class="contact-empty">没有联系人。点击“开始读取联系人”，或换个关键词。</div>`;
    return;
  }

  list.innerHTML = state.filtered.map((item, index) => {
    const name = item.display_name || item.username;
    const selected = state.selected && state.selected.username === item.username;
    return `
      <button class="contact ${selected ? "selected" : ""}" data-index="${index}">
        <strong title="${esc(name)}">${esc(name)}</strong>
        <span>${Number(item.message_count || 0).toLocaleString()} 条 · ${esc(item.username)}</span>
      </button>
    `;
  }).join("");
}

async function refreshStatus() {
  renderStatus(await api("/api/status"));
}

async function runSetup() {
  log("开始环境检查");
  const data = await api("/api/setup", { method: "POST" });
  renderStatus(data.status);
  log("环境检查完成", data.result.json || data.result.stderr || data.result.stdout);
}

async function saveConfig() {
  const inputValue = $("llmApiKey").value.trim();
  const body = {
    provider: $("llmProvider").value,
    base_url: $("llmBaseUrl").value.trim(),
    model: $("llmModel").value.trim(),
    api_key: state.pendingApiKey || (inputValue === MASKED_KEY ? "" : inputValue),
  };
  log("保存模型接口配置");
  const data = await api("/api/config", { method: "POST", body });
  renderStatus(data.status);
  state.pendingApiKey = "";
  $("llmApiKey").value = "";
  log("模型配置已保存", data.config);
}

function applyProviderDefaults(provider) {
  const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.openai;
  $("llmBaseUrl").value = defaults.baseUrl;
  $("llmModel").value = defaults.model;
}

const UI_THEMES = ["neon", "cyan", "ember"];

function normalizeUiTheme(theme) {
  return UI_THEMES.includes(theme) ? theme : "ember";
}

function applyUiTheme(theme) {
  const selected = normalizeUiTheme(theme);
  document.body.classList.remove("ui-neon", "ui-cyan", "ui-ember", "ui-rose", "ui-blue", "ui-graphite", "ui-gold", "ui-minimal");
  document.body.classList.add(`ui-${selected}`);
  localStorage.setItem("ta-ui-theme", selected);
  document.querySelectorAll(".theme-choice").forEach((button) => {
    button.classList.toggle("active", button.dataset.theme === selected);
  });
}

function maskApiKeyFromPaste(event) {
  event.preventDefault();
  const pasted = event.clipboardData?.getData("text")?.trim() || "";
  if (!pasted) return;
  state.pendingApiKey = pasted;
  $("llmApiKey").value = MASKED_KEY;
  $("llmApiKey").blur();
  log("API Key 已粘贴并隐藏。");
}

async function loadContacts() {
  log("开始读取联系人：检查环境、解密并扫描微信");
  if ($("contactSummary")) $("contactSummary").textContent = "正在读取联系人...";
  const data = await api("/api/discover", { method: "POST" });
  renderStatus(data.status);
  state.contacts = data.contacts || [];
  state.selected = null;
  if ($("reportBtn")) $("reportBtn").disabled = true;
  renderContacts();
  switchPane("main");
  if ($("contactSummary")) $("contactSummary").textContent = `已读取 ${state.contacts.length} 个联系人。`;
  log(`读取到 ${state.contacts.length} 个联系人`);
}

async function discoverWechat() {
  log("开始识别微信：检查环境、解密数据库、扫描联系人");
  const data = await api("/api/discover", { method: "POST" });
  renderStatus(data.status);
  state.contacts = data.contacts || [];
  state.selected = null;
  if ($("reportBtn")) $("reportBtn").disabled = true;
  renderContacts();
  switchPane("main");
  log(`微信识别完成，读取到 ${state.contacts.length} 个联系人`);
}

async function extractAndStats() {
  if (!state.selected) return;
  const contact = state.selected.display_name || state.selected.username;
  log(`提取联系人：${contact}`);
  const extracted = await api("/api/extract", { method: "POST", body: { contact } });
  log("消息提取完成", extracted.result.json || extracted.result.stderr);
  const stats = await api("/api/stats", { method: "POST" });
  log("统计完成", stats.stats.scores || stats.result.stdout);
}

async function runSubtextScan() {
  log("调用模型生成潜台词扫描");
  const data = await api("/api/analyze", { method: "POST", body: { use_llm: true } });
  renderStatus(data.status);
  log("analysis.json 已生成", { mode: data.analysis._analysis_mode });
  return data;
}

async function analyze() {
  await runSubtextScan();
}

async function report() {
  if (!state.selected) return;
  log("提取聊天并生成报告");
  await extractAndStats();
  await runSubtextScan();
  const data = await api("/api/report", { method: "POST" });
  renderStatus(data.status);
  setReport(data.report);
  log("报告已生成", data.report);
}

function renderQuiz() {
  const step = $("quizStep");
  const count = $("quizCount");
  const bar = $("quizBar");
  const question = $("quizQuestion");
  const options = $("quizOptions");
  const prev = $("quizPrevBtn");
  const next = $("quizNextBtn");
  if (!step || !count || !bar || !question || !options || !prev || !next) return;

  if (state.quizDone) {
    const scores = [0, 0, 0, 0];
    state.quizAnswers.forEach((answer) => {
      if (Number.isInteger(answer)) scores[answer] += 1;
    });
    const top = scores.reduce((best, value, index) => (value > scores[best] ? index : best), 0);
    const profile = QUIZ_TYPES[top];
    step.textContent = "完成";
    count.textContent = `${QUIZ_QUESTIONS.length} / ${QUIZ_QUESTIONS.length}`;
    bar.style.width = "100%";
    question.textContent = profile.name;
    question.classList.add("glass-title");
    options.classList.add("result-mode");
    options.innerHTML = `
      <article class="quiz-result">
        <p>${esc(profile.text)}</p>
        <dl>
          ${QUIZ_TYPES.map((type, index) => `
            <div>
              <dt>${esc(type.name)}</dt>
              <dd>${scores[index]} 题</dd>
            </div>
          `).join("")}
        </dl>
      </article>
    `;
    prev.hidden = true;
    next.disabled = false;
    next.textContent = "重新测试";
    return;
  }

  const item = QUIZ_QUESTIONS[state.quizIndex];
  const selected = state.quizAnswers[state.quizIndex];
  question.classList.remove("glass-title");
  step.textContent = `第 ${ROMAN[state.quizIndex].replace(".", "")} 题`;
  count.textContent = `${state.quizIndex + 1} / ${QUIZ_QUESTIONS.length}`;
  bar.style.width = `${((state.quizIndex + 1) / QUIZ_QUESTIONS.length) * 100}%`;
  question.textContent = item.question;
  options.classList.remove("result-mode");
  options.innerHTML = item.options.map((option, index) => `
    <button class="secondary quiz-option ${selected === index ? "selected" : ""}" data-index="${index}" type="button">
      <span>${ROMAN[index]}</span>
      ${esc(option)}
    </button>
  `).join("");
  prev.hidden = false;
  prev.disabled = state.quizIndex === 0;
  prev.textContent = "上一题";
  next.disabled = selected === undefined;
  next.textContent = state.quizIndex === QUIZ_QUESTIONS.length - 1 ? "查看结果" : "下一题";
}

function selectQuizOption(index) {
  state.quizAnswers[state.quizIndex] = index;
  renderQuiz();
}

function nextQuiz() {
  if (state.quizDone) {
    state.quizIndex = 0;
    state.quizAnswers = [];
    state.quizDone = false;
    renderQuiz();
    return;
  }
  if (state.quizAnswers[state.quizIndex] === undefined) return;
  if (state.quizIndex >= QUIZ_QUESTIONS.length - 1) {
    state.quizDone = true;
  } else {
    state.quizIndex += 1;
  }
  renderQuiz();
}

function prevQuiz() {
  if (state.quizIndex <= 0) return;
  state.quizIndex -= 1;
  renderQuiz();
}

function initReveals() {
  const nodes = document.querySelectorAll(".workflow-card, .report-panel, .archive-card, .archive-empty, .personality-panel, .config-panel, .theme-panel, .console-wrap");
  if (!("IntersectionObserver" in window)) {
    nodes.forEach((node) => node.classList.add("is-visible"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
  nodes.forEach((node) => {
    node.classList.add("reveal-item");
    observer.observe(node);
  });
}

function initHeroSlides() {
  const slides = [...document.querySelectorAll(".hero-slide")];
  if (slides.length < 2) return;
  window.setInterval(() => {
    if (document.body.dataset.pane !== "main") return;
    state.heroSlideIndex = (state.heroSlideIndex + 1) % slides.length;
    slides.forEach((slide, index) => slide.classList.toggle("active", index === state.heroSlideIndex));
  }, 5200);
}

function initCursorParticles() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (window.matchMedia("(pointer: coarse)").matches) return;
  const layer = document.createElement("div");
  layer.className = "cursor-particles";
  document.body.appendChild(layer);
  let last = 0;
  window.addEventListener("pointermove", (event) => {
    const now = performance.now();
    if (now - last < 16) return;
    last = now;
    const dot = document.createElement("i");
    const angle = Math.random() * Math.PI * 2;
    const distance = 26 + Math.random() * 42;
    dot.style.left = `${event.clientX}px`;
    dot.style.top = `${event.clientY}px`;
    dot.style.setProperty("--dx", `${Math.cos(angle) * distance}px`);
    dot.style.setProperty("--dy", `${Math.sin(angle) * distance}px`);
    dot.style.setProperty("--size", `${6 + Math.random() * 8}px`);
    layer.appendChild(dot);
    window.setTimeout(() => dot.remove(), 900);
  }, { passive: true });
}

function bind() {
  const on = (id, event, handler) => {
    const el = $(id);
    if (el) el.addEventListener(event, handler);
  };

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchPane(button.dataset.step));
  });
  on("heroScrollCue", "click", () => scrollToPane("pane-main"));
  on("saveConfigBtn", "click", () => saveConfig().catch(handleError));
  on("llmProvider", "change", (event) => applyProviderDefaults(event.target.value));
  on("llmApiKey", "paste", maskApiKeyFromPaste);
  on("llmApiKey", "input", () => {
    if ($("llmApiKey")?.value !== MASKED_KEY) state.pendingApiKey = "";
  });
  on("setupBtn", "click", () => runSetup().catch(handleError));
  on("loadContactsBtn", "click", () => loadContacts().catch(handleError));
  on("reportBtn", "click", () => report().catch(handleError));
  on("quizOptions", "click", (event) => {
    const button = event.target.closest(".quiz-option");
    if (!button) return;
    selectQuizOption(Number(button.dataset.index));
  });
  on("quizPrevBtn", "click", prevQuiz);
  on("quizNextBtn", "click", nextQuiz);
  on("consoleHead", "click", (event) => {
    if (event.target.closest("#clearLog")) return;
    $("consoleWrap").classList.toggle("expanded");
  });
  on("clearLog", "click", () => {
    state.logs = [];
    $("log").textContent = "";
    $("logLatest").textContent = "日志已清空。";
  });
  on("contactSearch", "input", renderContacts);
  on("contactList", "click", (event) => {
    const button = event.target.closest(".contact");
    if (!button) return;
    state.selected = state.filtered[Number(button.dataset.index)];
    if ($("reportBtn")) $("reportBtn").disabled = false;
    if ($("selectedHint")) {
      const label = state.selected.display_name || state.selected.username;
      $("selectedHint").textContent = `将分析：${label}`;
    }
    renderContacts();
  });
  document.querySelectorAll(".theme-choice").forEach((button) => {
    button.addEventListener("click", () => applyUiTheme(button.dataset.theme));
  });
  renderQuiz();
  initReveals();
  initHeroSlides();
  initCursorParticles();
}

function handleError(error) {
  const detail = error.data?.details || error.message;
  log(`失败：${error.message}`, detail);
}

const savedTheme = localStorage.getItem("ta-ui-theme");
const initialTheme = normalizeUiTheme(savedTheme || "ember");
localStorage.setItem("ta-ui-theme-v4", "ember-stage");
applyUiTheme(initialTheme);
bind();
switchPane("main");
refreshStatus().catch(handleError);
