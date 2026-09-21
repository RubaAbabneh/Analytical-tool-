/* ============================================================
   مرصد التقديرات السكانية — منطق الواجهة
   ============================================================ */
"use strict";

const STATE = { dataId: null, years: [], currentIntent: null, lastResult: null };

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
    showError("حدث خطأ في الاتصال بالخادم. تأكّدي من تشغيل التطبيق.");
    $("dzFile").hidden = true;
  }
}

/* ---------------- الملخّص ---------------- */
function renderBrief(data) {
  $("fileChip").textContent = data.filename;

  $("statStrip").innerHTML = data.brief.stat_cards
    .map((c) => `<div class="stat"><div class="v">${c.value}</div><div class="l">${c.label}</div></div>`)
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
}

/* ---------------- نافذة المساعد ---------------- */
$("openAssistantInline").addEventListener("click", openModal);
$("fab").addEventListener("click", openModal);
$("closeModal").addEventListener("click", closeModal);
$("overlay").addEventListener("click", (e) => { if (e.target === $("overlay")) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function openModal() {
  if (!STATE.dataId) {
    showError("يرجى رفع ملف البيانات أولاً قبل استخدام المساعد التحليلي.");
    $("uploadPanel").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  $("overlay").hidden = false;
  showIntents();
}
function closeModal() { $("overlay").hidden = true; }

function showIntents() {
  $("intents").hidden = false;
  $("config").hidden = true;
  $("results").hidden = true;
}

$("backToIntents").addEventListener("click", showIntents);

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
  $("intents").hidden = true;
  $("results").hidden = true;
  $("config").hidden = false;
  $("configTitle").textContent = INTENT_TITLES[intent];

  // إظهار/إخفاء المرشّحات
  document.querySelector(".filters").style.display = USES_FILTERS.includes(intent) ? "" : "none";
  if (USES_FILTERS.includes(intent)) await loadFilters();

  renderParams(intent);
}

/* ---------------- المرشّحات المتتالية ---------------- */
async function loadFilters(level) {
  const body = {
    data_id: STATE.dataId,
    governorate: $("fGov").value, region: $("fReg").value, neighborhood: $("fNei").value,
  };
  const res = await fetch("/api/filters", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json();
  if (!data.ok) { showError(data.error); return; }
  const o = data.options;
  fill($("fGov"), o.governorates, !!level);
  fill($("fReg"), o.regions, level === "reg" || level === "nei");
  fill($("fNei"), o.neighborhoods, level === "nei");
  fill($("fAge"), o.ages, false);
}

function fill(sel, items, keep) {
  const prev = sel.value;
  sel.innerHTML = items.map((v) => `<option value="${v}">${v}</option>`).join("");
  if (keep && items.includes(prev)) sel.value = prev;
}

$("fGov").addEventListener("change", () => loadFilters("gov"));
$("fReg").addEventListener("change", () => loadFilters("reg"));
$("fNei").addEventListener("change", () => loadFilters("nei"));

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
  return { governorate: $("fGov").value, region: $("fReg").value, neighborhood: $("fNei").value, age: $("fAge").value };
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
  STATE.lastResult = r;
  $("results").hidden = false;
  $("reportText").textContent = r.report || "";
  $("dlCsv").disabled = !(r.table && r.table.rows && r.table.rows.length);
  $("dlChart").disabled = !r.chart;

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

/* ---------------- تنزيل النتائج ---------------- */
$("dlCsv").addEventListener("click", () => {
  const r = STATE.lastResult;
  if (!r || !r.table || !r.table.rows.length) return;

  const escape = (v) => `"${String(v).replace(/"/g, '""')}"`;
  let csv = r.table.columns.map(escape).join(",") + "\n";
  csv += r.table.rows.map((row) => row.map(escape).join(",")).join("\n");
  if (r.report) csv += "\n\n" + escape("القراءة الكلامية") + "\n" + escape(r.report);

  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "نتائج_التحليل.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

$("dlChart").addEventListener("click", async () => {
  const r = STATE.lastResult;
  if (!r || !r.chart) return;
  const chartDiv = $("resultChart");
  const title = (r.chart.title || "رسم_التحليل").replace(/\s+/g, "_").replace(/[\/\\:*?"<>|]/g, "");
  await Plotly.relayout(chartDiv, { paper_bgcolor: "#ffffff", plot_bgcolor: "#f7fbfb" });
  try {
    await Plotly.downloadImage(chartDiv, {
      format: "png",
      filename: title,
      width: chartDiv.offsetWidth,
      height: chartDiv.offsetHeight,
    });
  } finally {
    await Plotly.relayout(chartDiv, { paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)" });
  }
});
