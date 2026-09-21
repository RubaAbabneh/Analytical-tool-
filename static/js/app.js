/* ============================================================
   مرصد التقديرات السكانية — منطق الواجهة
   ============================================================ */
"use strict";

const STATE = { dataId: null, years: [], currentIntent: null };

// لوحة ألوان الرسوم (متناسقة مع الهوية)
const PALETTE = ["#2a8c9e", "#f2a93b", "#e0654a", "#6b5b95", "#4f9d69", "#0f4c5c"];
const FONT = "IBM Plex Sans Arabic, sans-serif";
const PLOT_CFG = { responsive: true, displayModeBar: false, locale: "ar" };

function baseLayout(title) {
  return {
    title: { text: title || "", font: { family: FONT, size: 15, color: "#14323b" } },
    font: { family: FONT, size: 12, color: "#14323b" },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { t: title ? 44 : 16, r: 16, b: 44, l: 64 },
    xaxis: { gridcolor: "#eef2f1", zeroline: false, automargin: true },
    yaxis: { gridcolor: "#eef2f1", zeroline: false, automargin: true, separatethousands: true },
    legend: { font: { family: FONT }, orientation: "h", y: -0.2 },
  };
}

const $ = (id) => document.getElementById(id);

/* ---------------- الرفع ---------------- */
const dropzone = $("dropzone");
const fileInput = $("fileInput");

$("pickBtn").addEventListener("click", (e) => { e.stopPropagation(); fileInput.click(); });
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => { if (fileInput.files[0]) uploadFile(fileInput.files[0]); });

["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]); });

function showError(msg) {
  const b = $("errorBanner");
  b.textContent = msg; b.hidden = false;
  b.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function uploadFile(file) {
  $("errorBanner").hidden = true;
  $("dzFile").hidden = false;
  $("dzFile").textContent = "جارٍ المعالجة: " + file.name;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!data.ok) { showError(data.error || "تعذّرت معالجة الملف."); $("dzFile").hidden = true; return; }
    STATE.dataId = data.data_id;
    STATE.years = data.brief.years;
    $("dzFile").textContent = "تم: " + file.name;
    renderBrief(data);
  } catch (err) {
    showError("حدث خطأ في الاتصال بالخادم. يُرجى التأكّد من تشغيل التطبيق.");
    $("dzFile").hidden = true;
  }
}

/* ---------------- الملخّص ---------------- */
function renderBrief(data) {
  $("fileChip").textContent = data.filename;

  $("statStrip").innerHTML = data.brief.stat_cards
    .map((c, i) =>
      `<div class="stat reveal" style="--reveal-delay:${i * 70}ms">` +
      `<div class="v">${c.value}</div><div class="l">${c.label}</div></div>`)
    .join("");

  const oc = data.brief.overview_chart;
  Plotly.newPlot("overviewChart", [{
    x: oc.years, y: oc.totals, type: "scatter", mode: "lines+markers",
    line: { color: PALETTE[0], width: 3, shape: "spline" },
    marker: { color: PALETTE[1], size: 8 },
    fill: "tozeroy", fillcolor: "rgba(42,140,158,.12)",
    hovertemplate: "%{x}: %{y:,.0f}<extra></extra>",
  }], baseLayout(""), PLOT_CFG);

  const t = data.brief.preview;
  $("previewTable").innerHTML =
    "<thead><tr>" + t.columns.map((c) => `<th>${c}</th>`).join("") + "</tr></thead>" +
    "<tbody>" + t.rows.map((r) => "<tr>" + r.map((v) => `<td>${v}</td>`).join("") + "</tr>").join("") + "</tbody>";

  $("briefSection").hidden = false;
  $("fab").hidden = false;
  $("briefSection").scrollIntoView({ behavior: "smooth", block: "start" });

  // تفعيل الظهور التدريجي عند التمرير
  observeReveals();
}

/* ---------------- الظهور التدريجي عند التمرير ---------------- */
let _revealObserver = null;

function observeReveals() {
  // احترام تفضيل تقليل الحركة
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // العناصر التي ستظهر تدريجياً داخل الملخّص
  const targets = [
    ...document.querySelectorAll("#statStrip .stat"),
    document.querySelector(".brief-grid .chart-card"),
    document.querySelector(".brief-grid .preview-card"),
    document.querySelector(".cta-row"),
  ].filter(Boolean);

  if (reduce) {
    // إظهار فوري دون حركة
    targets.forEach((el) => el.classList.add("reveal", "in"));
    return;
  }

  targets.forEach((el, i) => {
    el.classList.add("reveal");
    if (el.style.getPropertyValue("--reveal-delay") === "") {
      el.style.setProperty("--reveal-delay", `${Math.min(i, 6) * 70}ms`);
    }
  });

  if (!("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("in"));
    return;
  }

  if (_revealObserver) _revealObserver.disconnect();
  _revealObserver = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          obs.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
  );
  targets.forEach((el) => _revealObserver.observe(el));
}

/* ---------------- نافذة المساعد ---------------- */
$("openAssistantInline").addEventListener("click", () => openModal("text"));
$("openVoiceInline").addEventListener("click", () => openModal("voice"));
// الزر العائم يفتح المساعد الصوتي مباشرة
$("fab").addEventListener("click", () => openModal("voice"));
$("closeModal").addEventListener("click", closeModal);
$("overlay").addEventListener("click", (e) => { if (e.target === $("overlay")) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function openModal(mode) {
  STATE.mode = mode || "text";
  $("overlay").hidden = false;
  $("assistantTitle").textContent = STATE.mode === "voice" ? "المساعد التحليلي الصوتي" : "طرح الأسئلة حول بياناتك";
  if (STATE.mode === "voice") { showVoiceBar(); } else { showIntents(); }
}
function closeModal() { stopRecording(true); $("overlay").hidden = true; }

function showVoiceBar() {
  $("voiceBar").hidden = false;
  $("intents").hidden = true;
  $("config").hidden = true;
  $("results").hidden = true;
  $("voiceHeard").hidden = true;
  $("voiceStatus").textContent = "الضغط على الميكروفون ثم طرح السؤال صوتياً";
  $("micBtn").classList.remove("rec");
}

function showIntents() {
  $("voiceBar").hidden = true;
  $("intents").hidden = false;
  $("config").hidden = true;
  $("results").hidden = true;
}

$("backToIntents").addEventListener("click", () => {
  if (STATE.mode === "voice") showVoiceBar(); else showIntents();
});

document.querySelectorAll(".intent").forEach((btn) =>
  btn.addEventListener("click", () => selectIntent(btn.dataset.intent)));

const INTENT_TITLES = {
  by_governorate: "السكان حسب المحافظة",
  age_distribution: "التوزيع حسب الفئة العمرية",
  timeseries: "تطوّر السكان زمنياً",
  growth: "مقارنة النمو بين سنتين",
  custom: "عملية حسابية مخصّصة",
  forecast: "تنبؤ بعدد السكان باستخدام ARIMA",
};
// النوايا التي تستخدم المرشّحات المتتالية
const USES_FILTERS = ["age_distribution", "timeseries", "growth", "custom", "forecast"];

async function selectIntent(intent) {
  STATE.currentIntent = intent;
  $("voiceBar").hidden = true;
  $("intents").hidden = true;
  $("results").hidden = true;
  if (STATE.mode !== "voice") $("voiceNote").hidden = true;
  $("config").hidden = false;
  $("configTitle").textContent = INTENT_TITLES[intent];

  // إظهار/إخفاء المرشّحات
  document.querySelector(".filters").style.display = USES_FILTERS.includes(intent) ? "" : "none";
  if (USES_FILTERS.includes(intent)) await loadFilters();

  renderParams(intent);
}

/* ---------------- المرشّحات المتتالية ---------------- */
const ALL_VAL = "الكل";
const LEVEL_IDX = { gov: 0, reg: 1, nei: 2, age: 3 };

async function loadFilters(level) {
  const L = (level in LEVEL_IDX) ? LEVEL_IDX[level] : -1;
  // تُستخدم قيم المستويات الأعلى (المحفوظة)، وتُعامَل الأدنى منها كـ«الكل» لإعادة حسابها
  const body = {
    data_id: STATE.dataId,
    governorate: L >= 0 ? $("fGov").value : ALL_VAL,
    region: L >= 1 ? $("fReg").value : ALL_VAL,
    neighborhood: L >= 2 ? $("fNei").value : ALL_VAL,
  };
  const res = await fetch("/api/filters", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!data.ok) { showError(data.error); return; }
  const o = data.options;
  // يحفظ كل حقل اختياره عند مستواه أو أعلى، وتُعاد الحقول الأدنى إلى «الكل»
  fill($("fGov"), o.governorates, L >= 0);
  fill($("fReg"), o.regions, L >= 1);
  fill($("fNei"), o.neighborhoods, L >= 2);
  fill($("fAge"), o.ages, L >= 3);

  // في قائمة الفئات المتعدّدة: إن لم يبقَ أي اختيار، فعّل «الكل» افتراضياً
  const ageSel = $("fAge");
  if (ageSel.multiple && ageSel.selectedOptions.length === 0) {
    const allOpt = [...ageSel.options].find((o) => o.value === ALL_VAL);
    if (allOpt) allOpt.selected = true;
  }
}

function fill(sel, items, keep) {
  // إذا كان الحقل هو fAge نستخدم الـ custom dropdown
  if (sel && sel.id === "fAge") {
    fillAgeDropdown(items, keep);
    return;
  }
  const prevSelected = [sel.value];
  sel.innerHTML = items.map((v) => `<option value="${v}">${v}</option>`).join("");
  if (keep && items.includes(prevSelected[0])) {
    sel.value = prevSelected[0];
  }
}

/* ── Custom Age Dropdown ── */
let _selectedAges = new Set(["الكل"]);

function fillAgeDropdown(items, keep) {
  const dropdown = $("fAgeDropdown");
  if (!dropdown) return;

  // حفظ الاختيارات السابقة إن احتجنا
  const prevSelected = keep ? new Set(_selectedAges) : new Set(["الكل"]);

  dropdown.innerHTML = items.map((v) => {
    const checked = prevSelected.has(v) ||
      (!keep && v === "الكل") ? "checked" : "";
    return `<label>
      <input type="checkbox" value="${v}" ${checked} />
      ${v}
    </label>`;
  }).join("");

  // تحديث _selectedAges من checkboxes
  syncSelectedAges();
  updateAgeLabel();

  // ربط الأحداث
  dropdown.querySelectorAll("input[type='checkbox']").forEach((cb) => {
    cb.addEventListener("change", onAgeCheckboxChange);
  });
}

function onAgeCheckboxChange(e) {
  const cb = e.target;
  const val = cb.value;
  const ALL_VAL = "الكل";
  const dropdown = $("fAgeDropdown");
  const allCb = dropdown.querySelector(`input[value="${ALL_VAL}"]`);

  if (val === ALL_VAL && cb.checked) {
    // إذا اخترت «الكل» → ألغِ البقية
    dropdown.querySelectorAll("input[type='checkbox']").forEach((c) => {
      c.checked = c.value === ALL_VAL;
    });
  } else if (val !== ALL_VAL && cb.checked) {
    // إذا اخترت فئة محددة → ألغِ «الكل»
    if (allCb) allCb.checked = false;
  }

  // إذا لم يبقَ أي اختيار → عد لـ«الكل»
  const anyChecked = [...dropdown.querySelectorAll("input[type='checkbox']")]
    .some((c) => c.checked);
  if (!anyChecked && allCb) allCb.checked = true;

  syncSelectedAges();
  updateAgeLabel();
}

function syncSelectedAges() {
  const dropdown = $("fAgeDropdown");
  if (!dropdown) return;
  _selectedAges = new Set(
    [...dropdown.querySelectorAll("input[type='checkbox']:checked")]
      .map((c) => c.value)
  );
}

function updateAgeLabel() {
  const label = $("fAgeLabel");
  if (!label) return;
  if (_selectedAges.has("الكل") || _selectedAges.size === 0) {
    label.textContent = "الكل";
  } else if (_selectedAges.size === 1) {
    label.textContent = [..._selectedAges][0];
  } else {
    label.textContent = `${_selectedAges.size} فئات مختارة`;
  }
}

function toggleAgeDropdown() {
  const dropdown = $("fAgeDropdown");
  const btn = $("fAgeBtn");
  const isOpen = !dropdown.hidden;
  dropdown.hidden = isOpen;
  btn.setAttribute("aria-expanded", String(!isOpen));
}

// إغلاق الـ dropdown عند الضغط خارجه
document.addEventListener("click", (e) => {
  const wrapper = $("fAgeWrapper");
  if (wrapper && !wrapper.contains(e.target)) {
    $("fAgeDropdown").hidden = true;
    $("fAgeBtn").setAttribute("aria-expanded", "false");
  }
});


$("fGov").addEventListener("change", () => loadFilters("gov"));
$("fReg").addEventListener("change", () => loadFilters("reg"));
$("fNei").addEventListener("change", () => loadFilters("nei"));
$("fAgeBtn").addEventListener("click", toggleAgeDropdown);

// الفئة العمرية (اختيار متعدّد): «الكل» يتنافى مع اختيار فئات محدّدة
$("fAge").addEventListener("change", (e) => {
  const sel = e.target;
  const opts = [...sel.options];
  const allOpt = opts.find((o) => o.value === ALL_VAL);
  if (!allOpt) return;
  const specificSelected = opts.some((o) => o.value !== ALL_VAL && o.selected);
  if (allOpt.selected && specificSelected) {
    // إن كان آخر ما نُقر عليه هو «الكل» ألغِ البقية، وإلا ألغِ «الكل»
    // نستدلّ بأن «الكل» يبقى مفعّلاً فقط عند عدم وجود اختيار محدّد
    allOpt.selected = false;
  }
  if (sel.selectedOptions.length === 0) allOpt.selected = true;
});

/* ---------------- المُعاملات حسب النيّة ---------------- */
function renderParams(intent) {
  const p = $("params");
  const yearsOpts = STATE.years.map((y) => `<option value="${y}">${y}</option>`).join("");
  const last = STATE.years[STATE.years.length - 1];
  const first = STATE.years[0];

  if (intent === "by_governorate" || intent === "age_distribution") {
    p.innerHTML = `<label>السنة<select id="pYear">${yearsOpts}</select></label>`;
    $("pYear").value = last;
  } else if (intent === "growth") {
    p.innerHTML =
      `<label>من سنة<select id="pFrom">${yearsOpts}</select></label>` +
      `<label>إلى سنة<select id="pTo">${yearsOpts}</select></label>`;
    $("pFrom").value = first; $("pTo").value = last;
  } else if (intent === "custom") {
    p.innerHTML = `<label>العملية<select id="pOp">
      <option value="sum">المجموع</option><option value="mean">المتوسط</option>
      <option value="median">الوسيط</option><option value="max">القيمة العظمى</option>
      <option value="min">القيمة الصغرى</option><option value="std">الانحراف المعياري</option>
    </select></label>`;
  } else if (intent === "forecast") {
    p.innerHTML = `<label>عدد سنوات التنبؤ
      <input type="number" id="pHorizon" min="1" max="20" value="5" /></label>`;
  } else {
    p.innerHTML = "";
  }
}

/* ---------------- تنفيذ الاستعلام ---------------- */
$("runBtn").addEventListener("click", runQuery);

function getFilters() {
  let age;
  if (STATE.voiceAgeList && STATE.voiceAgeList.length > 0) {
    age = STATE.voiceAgeList;
  } else {
    const selected = [..._selectedAges];
    if (selected.length === 0 || selected.includes(ALL_VAL)) {
      age = ALL_VAL;
    } else {
      age = selected;
    }
  }
  STATE.voiceAgeList = null;
  return {
    governorate:  $("fGov").value,
    region:       $("fReg").value,
    neighborhood: $("fNei").value,
    age:          age,
  };
}
 
function getParams(intent) {
  if (intent === "by_governorate" || intent === "age_distribution") return { year: parseInt($("pYear").value) };
  if (intent === "growth") return { year_from: parseInt($("pFrom").value), year_to: parseInt($("pTo").value) };
  if (intent === "custom") return { op: $("pOp").value };
  if (intent === "forecast") return { horizon: parseInt($("pHorizon").value) || 5 };
  return {};
}

async function runQuery() {
  const intent = STATE.currentIntent;
  $("loading").hidden = false;
  $("results").hidden = true;
  const body = {
    data_id: STATE.dataId, intent,
    filters: USES_FILTERS.includes(intent) ? getFilters() : {},
    params: getParams(intent),
  };
  try {
    const res = await fetch("/api/query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    $("loading").hidden = true;
    if (!data.ok) { showError(data.error); return; }
    renderResult(data.result);
  } catch (err) {
    $("loading").hidden = true;
    showError("تعذّر تنفيذ العملية.");
  }
}

/* ---------------- عرض النتيجة ---------------- */
function renderResult(r) {
  $("results").hidden = false;
  $("reportText").textContent = r.report || "";

  // الجدول
  if (r.table && r.table.rows && r.table.rows.length) {
    $("tableBlock").style.display = "";
    $("resultTable").innerHTML =
      "<thead><tr>" + r.table.columns.map((c) => `<th>${c}</th>`).join("") + "</tr></thead>" +
      "<tbody>" + r.table.rows.map((row) => "<tr>" + row.map((v) => `<td>${fmt(v)}</td>`).join("") + "</tr>").join("") + "</tbody>";
  } else { $("tableBlock").style.display = "none"; }

  // الرسم
  if (r.chart) { $("chartBlock").style.display = ""; drawChart(r.chart); }
  else { $("chartBlock").style.display = "none"; }

  $("results").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function fmt(v) { return typeof v === "number" ? v.toLocaleString("en-US") : v; }

function drawChart(c) {
  const layout = baseLayout(c.title);
  let traces = [];

  if (c.type === "bar") {
    traces = [{ x: c.x, y: c.y, type: "bar", marker: { color: c.x.map((_, i) => PALETTE[i % PALETTE.length]) },
      hovertemplate: "%{x}: %{y:,.0f}<extra></extra>" }];
  } else if (c.type === "line") {
    traces = [{ x: c.x, y: c.y, type: "scatter", mode: "lines+markers",
      line: { color: PALETTE[0], width: 3, shape: "spline" }, marker: { color: PALETTE[1], size: 8 },
      fill: "tozeroy", fillcolor: "rgba(42,140,158,.10)", hovertemplate: "%{x}: %{y:,.0f}<extra></extra>" }];
  } else if (c.type === "pie") {
    traces = [{ labels: c.labels, values: c.values, type: "pie", hole: 0.5,
      marker: { colors: PALETTE }, textinfo: "label+percent", textfont: { family: FONT } }];
    layout.margin = { t: c.title ? 44 : 16, r: 16, b: 16, l: 16 };
  } else if (c.type === "forecast") {
    // شريط الثقة (مظلّل) + التاريخي + التنبؤ
    const band = {
      x: c.fc_years.concat(c.fc_years.slice().reverse()),
      y: c.fc_upper.concat(c.fc_lower.slice().reverse()),
      fill: "toself", fillcolor: "rgba(242,169,59,.18)", line: { color: "rgba(0,0,0,0)" },
      name: "فترة الثقة 95٪", hoverinfo: "skip", type: "scatter",
    };
    const hist = {
      x: c.hist_years, y: c.hist_values, type: "scatter", mode: "lines+markers",
      line: { color: PALETTE[5], width: 3 }, marker: { color: PALETTE[0], size: 7 },
      name: "البيانات الفعلية", hovertemplate: "%{x}: %{y:,.0f}<extra></extra>",
    };
    // وصل آخر نقطة فعلية ببداية التنبؤ
    const fxs = [c.hist_years[c.hist_years.length - 1], ...c.fc_years];
    const fys = [c.hist_values[c.hist_values.length - 1], ...c.fc_values];
    const fc = {
      x: fxs, y: fys, type: "scatter", mode: "lines+markers",
      line: { color: PALETTE[1], width: 3, dash: "dash" }, marker: { color: PALETTE[2], size: 7 },
      name: "التنبؤ", hovertemplate: "%{x}: %{y:,.0f}<extra></extra>",
    };
    traces = [band, hist, fc];
  }

  Plotly.newPlot("resultChart", traces, layout, PLOT_CFG);
}

/* ============================================================
   الإدخال الصوتي (faster-whisper عبر /api/voice)
   ============================================================ */
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

$("micBtn").addEventListener("click", toggleRecording);

// ── Web Speech API ──────────────────────────────────────────
let _recognition = null;

function _buildRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;

  const r = new SpeechRecognition();
  r.lang             = "ar-JO";   // اللهجة الأردنية
  r.continuous       = false;
  r.interimResults   = true;
  r.maxAlternatives  = 3;

  r.onstart = () => {
    isRecording = true;
    $("micBtn").classList.add("rec");
    $("voiceStatus").textContent = "جارٍ الاستماع… تكلّم الآن ثم اضغط مجدّداً للإيقاف";
    $("voiceHeard").hidden = true;
  };

  r.onresult = (event) => {
    let interim = "", final = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      event.results[i].isFinal ? (final += t) : (interim += t);
    }
    // عرض النص المؤقت أثناء الكلام
    if (interim) {
      $("voiceHeard").hidden = false;
      $("voiceHeard").textContent = "أسمع: " + interim;
    }
    // عند اكتمال الجملة → أرسل للسيرفر
    if (final) {
      $("voiceHeard").hidden = false;
      $("voiceHeard").textContent = "سمعت: " + final;
      $("voiceStatus").textContent = "جارٍ تحليل السؤال…";
      sendTextToServer(final);
    }
  };

  r.onerror = (event) => {
    isRecording = false;
    $("micBtn").classList.remove("rec");
    const msgs = {
      "not-allowed"  : "الرجاء السماح للموقع باستخدام الميكروفون.",
      "no-speech"    : "لم يُكتشف صوت، حاول مرة أخرى.",
      "network"      : "خطأ في الاتصال بالإنترنت.",
      "audio-capture": "لا يوجد ميكروفون متاح.",
    };
    $("voiceStatus").textContent = msgs[event.error] || "خطأ: " + event.error;
  };

  r.onend = () => {
    isRecording = false;
    $("micBtn").classList.remove("rec");
  };

  return r;
}

async function toggleRecording() {
  // ── هل المتصفح يدعم Web Speech API؟ ──
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    // ✅ المسار الأول: Web Speech API (Chrome/Edge/Safari)
    if (isRecording && _recognition) {
      _recognition.stop();
      return;
    }
    _recognition = _buildRecognition();
    _recognition.start();

  } else {
    // ⚠️ المسار الاحتياطي: MediaRecorder + Vosk (Firefox أو متصفح قديم)
    if (isRecording) { stopRecording(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      $("voiceStatus").textContent = "المتصفّح لا يدعم التسجيل الصوتي. يُرجى استخدام Chrome أو Edge.";
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => { if (e.data.size) audioChunks.push(e.data); };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const raw = new Blob(audioChunks, { type: "audio/webm" });
        if (raw.size === 0) { $("voiceStatus").textContent = "لم يُسجَّل صوت. يُرجى المحاولة مجدّداً."; return; }
        try { const wav = await blobToWav16k(raw); sendVoice(wav); }
        catch (e) { $("voiceStatus").textContent = "تعذّرت معالجة الصوت."; }
      };
      mediaRecorder.start();
      isRecording = true;
      $("micBtn").classList.add("rec");
      $("voiceStatus").textContent = "جارٍ الاستماع… اضغط مجدّداً عند الانتهاء";
      $("voiceHeard").hidden = true;
    } catch (err) {
      $("voiceStatus").textContent = "تعذّر الوصول للميكروفون. يُرجى التأكّد من منح الإذن.";
    }
  }
}




function stopRecording(silent) {
  if (mediaRecorder && isRecording) {
    isRecording = false;
    $("micBtn").classList.remove("rec");
    if (!silent) $("voiceStatus").textContent = "جارٍ تفريغ الصوت…";
    try { mediaRecorder.stop(); } catch (e) { /* ignore */ }
  }
}

async function sendVoice(blob) {
  const fd = new FormData();
  fd.append("audio", blob, "rec.wav");
  fd.append("data_id", STATE.dataId);
  try {
    const res = await fetch("/api/voice", { method: "POST", body: fd });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!data) {
      $("voiceStatus").textContent =
        `استجابة غير متوقّعة من الخادم (${res.status}). يُرجى فتح نافذة التشغيل (Terminal) لرؤية تفاصيل الخطأ.`;
      return;
    }
    if (!data.ok) { $("voiceStatus").textContent = data.error || "تعذّر تفريغ الصوت."; return; }
    if (data.text) {
      $("voiceHeard").hidden = false;
      $("voiceHeard").textContent = "سمعت: " + data.text;
    }
    $("voiceStatus").textContent = data.message || "";
    if (data.intent) applyVoiceResult(data);
  } catch (err) {
    $("voiceStatus").textContent =
      "تعذّر الاتصال بالخادم. يُرجى التأكّد من أن التطبيق يعمل. ملاحظة: أول استخدام صوتي قد يستغرق وقتاً لتنزيل نموذج الكلام (يحتاج إنترنت مرّة واحدة).";
  }
}



// ── إرسال النص المُعرَّف من Web Speech API مباشرة للسيرفر ──
async function sendTextToServer(text) {
  try {
    const res = await fetch("/api/voice_text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, data_id: STATE.dataId }),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }

    if (!data) {
      $("voiceStatus").textContent = "استجابة غير متوقّعة من الخادم.";
      return;
    }
    if (!data.ok) { $("voiceStatus").textContent = data.error || "تعذّر تحليل السؤال."; return; }

    $("voiceStatus").textContent = data.message || "";
    if (data.intent) applyVoiceResult(data);

  } catch (err) {
    $("voiceStatus").textContent = "تعذّر الاتصال بالخادم.";
  }
}




async function applyVoiceResult(data) {
  await selectIntent(data.intent);
  if (USES_FILTERS.includes(data.intent)) await applyVoiceFilters(data.filters || {});
  applyVoiceParams(data.intent, data.params || {});

  // ── عرض ما التقطه المعرّف الصوتي ──
  $("voiceNote").hidden = false;
  $("voiceNote").innerHTML =
    `<b>سمعت:</b> ${escapeHtml(data.text || "")}<br><b>${escapeHtml(data.message || "")}</b>`;

  // ── تشغيل الاستعلام مباشرة دون انتظار المستخدم ──
  await runQuery();
}

function setIfExists(id, val) {
  const s = $(id);
  if (val && [...s.options].some((o) => o.value === val)) s.value = val;
}

async function applyVoiceFilters(f) {
  setIfExists("fGov", f.governorate); await loadFilters("gov");
  setIfExists("fReg", f.region);      await loadFilters("reg");
  setIfExists("fNei", f.neighborhood);await loadFilters("nei");

  // age قد تكون قائمة (نطاق كامل) — نُظهر كل الفئات المطابقة في القائمة المتعدّدة
  const ageList = Array.isArray(f.age)
    ? f.age.filter((a) => a && a !== ALL_VAL)
    : (f.age && f.age !== ALL_VAL ? [f.age] : []);
  selectAges("fAge", ageList);

  // حفظ القائمة كاملة لاستخدامها في getFilters (الفلتر الحقيقي بالنطاق الكامل)
  STATE.voiceAgeList = ageList.length > 0 ? ageList : null;
}

function selectAges(id, values) {
  if (id !== "fAge") {
    const sel = $(id);
    if (!sel) return;
    const set = new Set(values);
    [...sel.options].forEach((o) => { o.selected = set.has(o.value); });
    return;
  }
  // custom dropdown
  const dropdown = $("fAgeDropdown");
  if (!dropdown) return;
  const set = new Set(values);
  const ALL_VAL = "الكل";
  let any = false;
  dropdown.querySelectorAll("input[type='checkbox']").forEach((cb) => {
    cb.checked = set.has(cb.value);
    if (cb.checked && cb.value !== ALL_VAL) any = true;
  });
  if (!any) {
    const allCb = dropdown.querySelector(`input[value="${ALL_VAL}"]`);
    if (allCb) allCb.checked = true;
  }
  syncSelectedAges();
  updateAgeLabel();
}



function applyVoiceParams(intent, p) {
  if ((intent === "by_governorate" || intent === "age_distribution") && p.year) {
    if ($("pYear")) setIfExists("pYear", String(p.year));
  } else if (intent === "growth") {
    if (p.year_from && $("pFrom")) setIfExists("pFrom", String(p.year_from));
    if (p.year_to && $("pTo")) setIfExists("pTo", String(p.year_to));
  } else if (intent === "custom" && p.op) {
    if ($("pOp")) setIfExists("pOp", p.op);
  } else if (intent === "forecast" && p.horizon) {
    if ($("pHorizon")) $("pHorizon").value = p.horizon;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ============================================================
   تحويل تسجيل المتصفّح إلى WAV أحادي القناة 16kHz / 16-بت
   (الصيغة التي يتوقّعها محرّك Vosk) — كل ذلك داخل المتصفّح
   ============================================================ */
async function blobToWav16k(blob) {
  const arrayBuf = await blob.arrayBuffer();
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioCtx();
  const decoded = await ctx.decodeAudioData(arrayBuf);
  if (ctx.close) ctx.close();

  const inRate = decoded.sampleRate;
  const length = decoded.length;
  const channels = decoded.numberOfChannels;

  // دمج القنوات إلى قناة واحدة (مونو)
  const mono = new Float32Array(length);
  for (let c = 0; c < channels; c++) {
    const d = decoded.getChannelData(c);
    for (let i = 0; i < length; i++) mono[i] += d[i] / channels;
  }

  // إعادة العيّنة إلى 16000Hz عبر OfflineAudioContext
  const targetRate = 16000;
  const outLen = Math.max(1, Math.ceil((length * targetRate) / inRate));
  const offline = new OfflineAudioContext(1, outLen, targetRate);
  const buffer = offline.createBuffer(1, length, inRate);
  buffer.copyToChannel(mono, 0);
  const src = offline.createBufferSource();
  src.buffer = buffer;
  src.connect(offline.destination);
  src.start(0);
  const rendered = await offline.startRendering();
  return encodeWav16(rendered.getChannelData(0), targetRate);
}

function encodeWav16(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);   // PCM
  view.setUint16(22, 1, true);   // قناة واحدة
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);  // 16-بت
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    off += 2;
  }
  return new Blob([view], { type: "audio/wav" });
}