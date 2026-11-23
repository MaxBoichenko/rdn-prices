/* Цены РДН — клиентская часть. Данные: data/meta.json + data/YYYY-MM.json (часы в UTC, EUR/MWh). */
(() => {
"use strict";

const ZONES = {
  PL: { color: "#d62839", ru: "Польша",   en: "Poland"   },
  RO: { color: "#1f5fbf", ru: "Румыния",  en: "Romania"  },
  SK: { color: "#7b4fb3", ru: "Словакия", en: "Slovakia" },
  HU: { color: "#22955a", ru: "Венгрия",  en: "Hungary"  },
  UA: { color: "#e3a300", ru: "Украина",  en: "Ukraine"  },
};
const ORDER = ["PL", "SK", "HU", "RO", "UA"];
const PEAK_FROM = 8, PEAK_TO = 20;

const T = {
  ru: {
    title: "Цены РДН", subtitle: "Рынок на сутки вперёд · EUR/MWh", tzKyiv: "Киев", tabDay: "День", tabPeriod: "Период",
    days: "дней", csv: "Скачать CSV", hourlyPrices: "Почасовые цены", table: "Таблица", spreads: "Спреды",
    baseMatrix: "Матрица спредов Base (строка − столбец)", dailyBase: "Цены по дням", monthly: "Средние по месяцам",
    footnote: "Base — среднее за сутки; Peak — 08:00–20:00 в выбранном часовом поясе; Off-peak — остальные часы. Для рынков с 15-минутным шагом часовая цена — среднее четырёх 15-минутных цен. Цены Украины, полученные в гривне, переведены в евро по официальному курсу НБУ на дату поставки. Информация носит справочный характер.",
    updated: "обновлено", hour: "Час", noData: "нет данных", vsPrev: "к пред. дню", min: "Мин", max: "Макс",
    avg: "Средний", maxSpread: "Макс", minSpread: "Мин", positive: "часов > 0", month: "Месяц",
    tzNoteCET: "Время: CET/CEST (Будапешт, Варшава, Братислава)", tzNoteKyiv: "Время: Киев / Кишинёв (EET/EEST)",
    loading: "Загрузка данных…", empty: "Данных пока нет. Они появятся после первого запуска сборщика.",
    noDay: "На эту дату данных нет.", sources: "Источники", wd: ["вс","пн","вт","ср","чт","пт","сб"],
    partial: "неполные сутки",
    uaVol: "Украина: спрос, предложение и акцепт на РДН", uaVolNote: "МВт·ч по часам, ОРЕЕ; линия — цена, €/MWh",
    anUAVol: "Объёмы торгов РДН Украины", anUAVolNote: "ГВт·ч, ОРЕЕ; линия — Base Украины, €/MWh",
    sell: "Предложение (SELL)", buy: "Спрос (BUY)", accepted: "Акцепт (объём торгов)", priceEur: "Цена, €/MWh",
    traded: "Объём торгов", deficitH: "Часов дефицита", surplusH: "Часов профицита", fillRate: "Удовлетворено спроса",
    avgDay: "В среднем за сутки", mwh: "МВт·ч", gwhU: "ГВт·ч",
    demoBanner: "ДЕМО-РЕЖИМ: все цифры на этой странице выдуманы и сгенерированы для проверки работы сайта. Это не рыночные данные.",
    xlsx: "Excel: все данные", xlsxBusy: "Готовлю файл…",
    tabAnalytics: "Аналитика", twelveTo: "12 месяцев по", anSummary: "Сводные показатели за 12 месяцев",
    anIndex: "Помесячная динамика индексов РДН", anSpread: "Межрыночные спреды Base: Украина − соседи",
    anSpreadNote: "€/MWh; «+» — Украина дороже", anFlowsUA: "Межгосударственные перетоки Украины",
    anFlowsNote: "ГВт·ч, физические перетоки; «+» — импорт в Украину, «−» — экспорт",
    anBalance: "Сальдо экспорта/импорта", anBalanceNote: "ГВт·ч; «+» — нетто-импорт, «−» — нетто-экспорт; по всем границам страны",
    country: "Страна", ratio: "Peak/Base", minH: "Мин. час", maxH: "Макс. час", negH: "Отриц. часов", sigma: "Волатильность σ",
    vsPrev12: "Base к пред. 12 мес.", coverage: "Покрытие", mom: "м/м", spreadAvg: "Спред", uaHigher: "UA дороже, % часов",
    total12: "Итого 12 мес.", avg12: "Среднее 12 мес.", imp: "Импорт", exp: "Экспорт", net: "Сальдо", border: "Граница",
    noFlows: "Данных по перетокам пока нет — они появятся после запуска сборщика.", partialMonth: "* неполный месяц",
    hlUA: "Украина, Base 12 мес.", hlSpread: "Спред UA − HU, 12 мес.", hlImport: "Сальдо Украины, 12 мес.", hlTop: "Самый дорогой рынок",
    netImport: "нетто-импорт", netExport: "нетто-экспорт", period: "Период",
  },
  en: {
    title: "Day-Ahead Prices", subtitle: "Day-ahead market · EUR/MWh", tzKyiv: "Kyiv", tabDay: "Day", tabPeriod: "Period",
    days: "days", csv: "Download CSV", hourlyPrices: "Hourly prices", table: "Table", spreads: "Spreads",
    baseMatrix: "Base spread matrix (row − column)", dailyBase: "Daily prices", monthly: "Monthly averages",
    footnote: "Base — daily average; Peak — 08:00–20:00 in the selected time zone; Off-peak — remaining hours. For 15-minute markets the hourly price is the average of four quarter-hour prices. Ukrainian prices published in UAH are converted to EUR at the official NBU rate for the delivery date. For information purposes only.",
    updated: "updated", hour: "Hour", noData: "no data", vsPrev: "vs prev. day", min: "Min", max: "Max",
    avg: "Average", maxSpread: "Max", minSpread: "Min", positive: "hours > 0", month: "Month",
    tzNoteCET: "Time: CET/CEST (Budapest, Warsaw, Bratislava)", tzNoteKyiv: "Time: Kyiv / Chișinău (EET/EEST)",
    loading: "Loading data…", empty: "No data yet. It will appear after the first collector run.",
    noDay: "No data for this date.", sources: "Sources", wd: ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"],
    partial: "incomplete day",
    uaVol: "Ukraine: DAM demand, supply and cleared volume", uaVolNote: "MWh per hour, OREE; line — price, €/MWh",
    anUAVol: "Ukraine DAM traded volumes", anUAVolNote: "GWh, OREE; line — Ukraine Base, €/MWh",
    sell: "Supply (SELL)", buy: "Demand (BUY)", accepted: "Cleared (traded volume)", priceEur: "Price, €/MWh",
    traded: "Traded volume", deficitH: "Deficit hours", surplusH: "Surplus hours", fillRate: "Demand cleared",
    avgDay: "Daily average", mwh: "MWh", gwhU: "GWh",
    demoBanner: "DEMO MODE: all figures on this page are made up to test the site. These are not market data.",
    xlsx: "Excel: all data", xlsxBusy: "Preparing file…",
    tabAnalytics: "Analytics", twelveTo: "12 months to", anSummary: "12-month summary",
    anIndex: "Monthly day-ahead index dynamics", anSpread: "Cross-market Base spreads: Ukraine − neighbours",
    anSpreadNote: "€/MWh; “+” — Ukraine more expensive", anFlowsUA: "Ukraine cross-border flows",
    anFlowsNote: "GWh, physical flows; “+” — import to Ukraine, “−” — export",
    anBalance: "Export/import balance", anBalanceNote: "GWh; “+” — net import, “−” — net export; all borders of the country",
    country: "Country", ratio: "Peak/Base", minH: "Min hour", maxH: "Max hour", negH: "Negative hours", sigma: "Volatility σ",
    vsPrev12: "Base vs prev. 12 m", coverage: "Coverage", mom: "m/m", spreadAvg: "Spread", uaHigher: "UA higher, % of hours",
    total12: "12-month total", avg12: "12-month average", imp: "Import", exp: "Export", net: "Net", border: "Border",
    noFlows: "No flow data yet — it will appear after the collector runs.", partialMonth: "* incomplete month",
    hlUA: "Ukraine, Base 12 m", hlSpread: "UA − HU spread, 12 m", hlImport: "Ukraine balance, 12 m", hlTop: "Most expensive market",
    netImport: "net import", netExport: "net export", period: "Period",
  },
};

// ---------------------------------------------------------------- state
const S = {
  lang: localGet("lang") || "ru",
  tz: localGet("tz") || "Europe/Budapest",
  view: "day",
  date: null,
  zones: new Set((localGet("zones") || ORDER.join(",")).split(",").filter(z => ZONES[z])),
  range: "90",
  metric: "base",
  pairA: "UA", pairB: "HU",
  meta: null,
  months: {},          // "YYYY-MM" -> {zone: {iso: price}}
  flows: {},           // "YYYY-MM" -> {"PL>UA": {day: MWh}}
  uaDam: {},           // "YYYY-MM" -> {price, buy, sell, accepted: {iso: value}}
  endMonth: null, anMetric: "base",
};
const charts = {};
const $ = id => document.getElementById(id);
const t = k => T[S.lang][k] ?? k;
const zname = z => ZONES[z][S.lang];

function localGet(k) { try { return localStorage.getItem("rdn_" + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("rdn_" + k, v); } catch { /* ignore */ } }

// ---------------------------------------------------------------- time zones
const dtfCache = {};
function parts(ms, tz) {
  const f = dtfCache[tz] ||= new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", weekday: "short",
  });
  const o = {};
  for (const p of f.formatToParts(new Date(ms))) o[p.type] = p.value;
  return { y: +o.year, m: +o.month, d: +o.day, h: +o.hour, min: +o.minute };
}
function offsetMs(ms, tz) {
  const p = parts(ms, tz);
  return Date.UTC(p.y, p.m - 1, p.d, p.h, p.min) - Math.floor(ms / 60000) * 60000;
}
function localMidnight(dateStr, tz) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const guess = Date.UTC(y, m - 1, d);
  let ms = guess - offsetMs(guess, tz);
  ms = guess - offsetMs(ms, tz);
  return ms;
}
function addDays(dateStr, n) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
function localDateOf(ms, tz) { const p = parts(ms, tz); return `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`; }
function isoKey(ms) { return new Date(ms).toISOString().slice(0, 16) + "Z"; }
function weekday(dateStr) { const [y, m, d] = dateStr.split("-").map(Number); return T[S.lang].wd[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]; }

/** Часы локальных суток: [{ms, label, h}] (23/24/25 часов при переходе времени). */
const _dhCache = {};
function dayHours(dateStr, tz) {
  const ck = tz + "|" + dateStr;
  if (_dhCache[ck]) return _dhCache[ck];
  const a = localMidnight(dateStr, tz), b = localMidnight(addDays(dateStr, 1), tz);
  const out = [];
  for (let ms = a; ms < b; ms += 3600e3) {
    const h = parts(ms, tz).h, h2 = parts(ms + 3600e3, tz).h;
    out.push({ ms, h, label: `${String(h).padStart(2, "0")}–${String(h2 === 0 ? 24 : h2).padStart(2, "0")}` });
  }
  return (_dhCache[ck] = out);
}

// ---------------------------------------------------------------- data
async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(url + ": " + r.status);
  return r.json();
}
async function ensureMonths(fromMs, toMs) {
  const need = new Set();
  for (let ms = fromMs - 86400e3; ms <= toMs + 86400e3; ms += 86400e3 * 27) need.add(new Date(ms).toISOString().slice(0, 7));
  need.add(new Date(toMs).toISOString().slice(0, 7));
  const avail = new Set(S.meta.months || []);
  await Promise.all([...need].filter(k => avail.has(k) && !S.months[k]).map(async k => {
    S.months[k] = (await getJSON(`data/${k}.json`)).prices || {};
  }));
}
function price(zone, ms) {
  const k = isoKey(ms);
  const m = S.months[k.slice(0, 7)];
  const v = m && m[zone] ? m[zone][k] : undefined;
  return v === undefined ? null : v;
}
function stats(vals, hours) {
  const all = [], pk = [], op = [];
  let min = null, max = null;
  vals.forEach((v, i) => {
    if (v == null) return;
    all.push(v);
    const h = hours[i].h;
    (h >= PEAK_FROM && h < PEAK_TO ? pk : op).push(v);
    if (!min || v < min.v) min = { v, i };
    if (!max || v > max.v) max = { v, i };
  });
  const avg = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
  return { base: avg(all), peak: avg(pk), offpeak: avg(op), min, max, n: all.length, total: hours.length };
}
function dayStats(zone, dateStr) {
  const hours = dayHours(dateStr, S.tz);
  const vals = hours.map(h => price(zone, h.ms));
  return { hours, vals, ...stats(vals, hours) };
}

// ---------------------------------------------------------------- formatting
const nf = (v, d = 2) => v == null || isNaN(v) ? "—" : v.toLocaleString(S.lang === "ru" ? "ru-RU" : "en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
const sign = v => (v > 0 ? "+" : "") + nf(v);
function heatColor(v, lo, hi) {
  if (v == null) return "#fff";
  const x = hi > lo ? Math.min(1, Math.max(0, (v - lo) / (hi - lo))) : .5;
  // зелёный -> белый -> красный
  const a = [46, 160, 100], m = [255, 255, 255], b = [214, 64, 69];
  const [c1, c2, k] = x < .5 ? [a, m, x * 2] : [m, b, (x - .5) * 2];
  const c = c1.map((ch, i) => Math.round(ch + (c2[i] - ch) * k));
  return `rgba(${c[0]},${c[1]},${c[2]},${x < .5 ? .55 : .7})`;
}
function divColor(v, lim) {
  if (v == null) return "#fff";
  const x = Math.max(-1, Math.min(1, v / (lim || 1)));
  return x >= 0 ? `rgba(214,64,69,${.08 + .5 * x})` : `rgba(46,160,100,${.08 + .5 * -x})`;
}

// ---------------------------------------------------------------- i18n / chrome
function applyI18n() {
  document.documentElement.lang = S.lang;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.title = `${t("title")} · PL RO SK HU UA`;
  segOn("langSeg", "lang", S.lang); segOn("tzSeg", "tz", S.tz);
  if (S.meta && S.meta.updated) {
    const u = new Date(S.meta.updated);
    $("updated").textContent = `${t("updated")} ${u.toLocaleString(S.lang === "ru" ? "ru-RU" : "en-GB", { timeZone: S.tz, dateStyle: "short", timeStyle: "short" })}`;
    $("demoBanner").textContent = t("demoBanner");
    const src = S.meta.sources || {};
    const byS = {};
    Object.entries(src).forEach(([z, s]) => (byS[s] ||= []).push(z));
    $("sources").innerHTML = `${t("sources")}: ` + Object.entries(byS).map(([s, zs]) => `${linkify(s)} (${zs.join(", ")})`).join("; ") +
      (S.lang === "ru" ? ". Курс EUR/UAH — НБУ." : ". EUR/UAH rate — NBU.");
  }
  renderChips();
  fillPairSelects();
}
function linkify(s) {
  const L = {
    "ENTSO-E Transparency Platform": "https://transparency.entsoe.eu/", "ОРЕЕ": "https://www.oree.com.ua/", "OKTE": "https://www.okte.sk/",
    "HUPX": "https://hupx.hu/", "OPCOM": "https://www.opcom.ro/", "Energy-Charts": "https://www.energy-charts.info/",
  };
  return s.split("; ").map(part => {
    for (const [k, url] of Object.entries(L)) if (part.startsWith(k)) return `<a href="${url}" target="_blank" rel="noopener">${k}</a>${part.slice(k.length)}`;
    return part;
  }).join(", ");
}
function segOn(id, key, val) { document.querySelectorAll(`#${id} button`).forEach(b => b.classList.toggle("on", b.dataset[key] === val)); }
function renderChips() {
  $("zoneChips").innerHTML = ORDER.map(z =>
    `<span class="chip ${S.zones.has(z) ? "" : "off"}" data-z="${z}" title="${zname(z)}"><i style="background:${ZONES[z].color}"></i>${z}</span>`).join("");
}
function fillPairSelects() {
  const opts = v => ORDER.map(z => `<option value="${z}" ${z === v ? "selected" : ""}>${z} · ${zname(z)}</option>`).join("");
  $("pairA").innerHTML = opts(S.pairA); $("pairB").innerHTML = opts(S.pairB);
}
function status(msg) { const el = $("status"); el.textContent = msg || ""; el.classList.toggle("hidden", !msg); }
function activeZones() { return ORDER.filter(z => S.zones.has(z)); }

// ---------------------------------------------------------------- charts
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 12;
Chart.defaults.color = "#5b6270";
function makeChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), cfg);
}
const gridY = { grid: { color: "#eef0f3" }, border: { display: false } };
const gridX = { grid: { display: false }, border: { color: "#e3e6eb" } };
const tooltipNum = { callbacks: { label: c => ` ${c.dataset.label}: ${nf(c.parsed.y)} €/MWh` } };

// ---------------------------------------------------------------- DAY VIEW
async function renderDay() {
  const d = S.date;
  $("dateInput").value = d;
  $("weekday").textContent = weekday(d);
  $("tzNote").textContent = S.tz === "Europe/Kyiv" ? t("tzNoteKyiv") : t("tzNoteCET");
  const hours = dayHours(d, S.tz);
  const prevHours = dayHours(addDays(d, -1), S.tz);
  await ensureMonths(prevHours[0].ms, hours[hours.length - 1].ms);

  const zs = activeZones();
  const data = {}; ORDER.forEach(z => { data[z] = dayStats(z, d); });
  const any = zs.some(z => data[z].n);
  status(any ? "" : t("noDay"));

  // next/prev buttons
  const lastDay = latestDate();
  $("nextDay").disabled = !lastDay || d >= lastDay;

  // KPI
  $("kpis").innerHTML = zs.map(z => {
    const s = data[z], p = dayStats(z, addDays(d, -1));
    const src = (S.meta.sources || {})[z] || "";
    if (s.n < s.total / 2) return `<div class="kpi empty" style="--c:${ZONES[z].color}"><div class="h"><span class="name">${zname(z)}</span><span class="src">${z}</span></div><div class="big">${t("noData")}</div></div>`;
    const dlt = p.base != null && s.n === s.total && p.n === p.total ? s.base - p.base : null;
    return `<div class="kpi" style="--c:${ZONES[z].color}">
      <div class="h"><span class="name">${zname(z)}</span><span class="src" title="${src}">${z}${s.n < s.total ? " · " + t("partial") : ""}</span></div>
      <div class="big">${nf(s.base)}<small>€/MWh Base</small></div>
      <div class="delta ${dlt > 0 ? "up" : dlt < 0 ? "down" : ""}">${dlt == null ? "&nbsp;" : `${dlt > 0 ? "▲" : "▼"} ${sign(dlt)} (${nf(dlt / p.base * 100, 1)}%) ${t("vsPrev")}`}</div>
      <dl><dt>Peak</dt><dd>${nf(s.peak)}</dd><dt>Off-peak</dt><dd>${nf(s.offpeak)}</dd>
      <dt>${t("min")}</dt><dd>${nf(s.min?.v)} <span class="muted">${s.min ? s.hours[s.min.i].label : ""}</span></dd>
      <dt>${t("max")}</dt><dd>${nf(s.max?.v)} <span class="muted">${s.max ? s.hours[s.max.i].label : ""}</span></dd></dl></div>`;
  }).join("");

  // line chart
  makeChart("dayChart", {
    type: "line",
    data: {
      labels: hours.map(h => h.label),
      datasets: zs.map(z => ({ label: zname(z), data: data[z].vals, borderColor: ZONES[z].color, backgroundColor: ZONES[z].color,
        borderWidth: 2.2, pointRadius: 0, pointHoverRadius: 4, stepped: "middle", spanGaps: false })),
    },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltipNum },
      scales: { x: gridX, y: { ...gridY, title: { display: true, text: "€/MWh" } } } },
  });

  // heat table
  const allV = zs.flatMap(z => data[z].vals).filter(v => v != null);
  const lo = Math.min(...allV), hi = Math.max(...allV);
  let html = `<thead><tr><th>${t("hour")}</th>${zs.map(z => `<th>${z}</th>`).join("")}</tr></thead><tbody>`;
  hours.forEach((h, i) => {
    html += `<tr><td>${h.label}</td>${zs.map(z => { const v = data[z].vals[i]; return `<td style="background:${heatColor(v, lo, hi)}">${nf(v)}</td>`; }).join("")}</tr>`;
  });
  for (const [k, lbl] of [["base", "Base"], ["peak", "Peak"], ["offpeak", "Off-peak"]])
    html += `<tr class="sum"><td>${lbl}</td>${zs.map(z => `<td>${nf(data[z][k])}</td>`).join("")}</tr>`;
  $("hourTable").innerHTML = html + "</tbody>";

  // spread
  const A = data[S.pairA].vals, B = data[S.pairB].vals;
  const sp = A.map((v, i) => v != null && B[i] != null ? +(v - B[i]).toFixed(2) : null);
  const spv = sp.filter(v => v != null);
  makeChart("spreadChart", {
    type: "bar",
    data: { labels: hours.map(h => h.label), datasets: [{ label: `${S.pairA} − ${S.pairB}`, data: sp,
      backgroundColor: sp.map(v => v >= 0 ? "rgba(214,64,69,.75)" : "rgba(46,160,100,.8)"), borderRadius: 2 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tooltipNum },
      scales: { x: gridX, y: { ...gridY, title: { display: true, text: "€/MWh" } } } },
  });
  $("spreadChart").parentElement.classList.toggle("hidden", !spv.length);
  const avg = spv.length ? spv.reduce((a, b) => a + b, 0) / spv.length : null;
  $("spreadSum").innerHTML = spv.length ? `
    <div>${t("avg")}: <b>${sign(avg)}</b></div>
    <div>${t("minSpread")}: <b>${sign(Math.min(...spv))}</b></div>
    <div>${t("maxSpread")}: <b>${sign(Math.max(...spv))}</b></div>
    <div>${t("positive")}: <b>${spv.filter(v => v > 0).length}/${spv.length}</b></div>` : `<span class="muted">${t("noData")}</span>`;

  // matrix
  const diffs = [];
  zs.forEach(a => zs.forEach(b => { if (a !== b && data[a].base != null && data[b].base != null) diffs.push(Math.abs(data[a].base - data[b].base)); }));
  const lim = Math.max(1, ...diffs);
  let mx = `<thead><tr><th></th>${zs.map(z => `<th>${z}</th>`).join("")}</tr></thead><tbody>`;
  zs.forEach(a => {
    mx += `<tr><td><b>${a}</b></td>` + zs.map(b => {
      if (a === b) return `<td class="diag">·</td>`;
      const v = data[a].base != null && data[b].base != null ? data[a].base - data[b].base : null;
      return `<td style="background:${divColor(v, lim)}">${v == null ? "—" : sign(v)}</td>`;
    }).join("") + "</tr>";
  });
  $("spreadMatrix").innerHTML = mx + "</tbody>";
  await renderUAVolDay(hours);
}


// ---------------------------------------------------------------- UA volumes (ОРЕЕ)
async function ensureUAMonths(fromMs, toMs) {
  const avail = new Set(S.meta.ua_dam_months || []);
  const need = new Set();
  for (let ms = fromMs - 86400e3; ms <= toMs + 86400e3; ms += 86400e3 * 27) need.add(new Date(ms).toISOString().slice(0, 7));
  need.add(new Date(toMs).toISOString().slice(0, 7));
  await Promise.all([...need].filter(k => avail.has(k) && !S.uaDam[k]).map(async k => { S.uaDam[k] = await getJSON(`data/ua_dam/${k}.json`); }));
}
function uaV(field, ms) {
  const k = isoKey(ms), m = S.uaDam[k.slice(0, 7)];
  const v = m && m[field] ? m[field][k] : undefined;
  return v === undefined ? null : v;
}
function uaAgg(hours) {
  const o = { acc: 0, buy: 0, sell: 0, n: 0, def: 0, sur: 0 };
  hours.forEach(h => {
    const a = uaV("accepted", h.ms), b = uaV("buy", h.ms), s2 = uaV("sell", h.ms);
    if (a == null) return;
    o.n++; o.acc += a; o.buy += b || 0; o.sell += s2 || 0;
    if (b != null && s2 != null) { if (b > s2) o.def++; else if (s2 > b) o.sur++; }
  });
  return o;
}

async function renderUAVolDay(hours) {
  const card = $("uaVolCard");
  if (!S.zones.has("UA") || !(S.meta.ua_dam_months || []).length) { card.classList.add("hidden"); return; }
  await ensureUAMonths(hours[0].ms, hours[hours.length - 1].ms);
  const sell = hours.map(h => uaV("sell", h.ms)), buy = hours.map(h => uaV("buy", h.ms)), acc = hours.map(h => uaV("accepted", h.ms));
  if (!acc.some(v => v != null)) { card.classList.add("hidden"); return; }
  card.classList.remove("hidden");
  const a = uaAgg(hours);
  $("uaVolSum").innerHTML = `
    <div>${t("traded")}: <b>${nf(a.acc, 1)}</b> ${t("mwh")}</div>
    <div>${t("sell")}: <b>${nf(a.sell, 1)}</b></div>
    <div>${t("buy")}: <b>${nf(a.buy, 1)}</b></div>
    <div>${t("fillRate")}: <b>${a.buy ? nf(a.acc / a.buy * 100, 0) + "%" : "—"}</b></div>
    <div>${t("deficitH")}: <b>${a.def}</b> · ${t("surplusH")}: <b>${a.sur}</b></div>`;
  makeChart("uaVolChart", {
    data: {
      labels: hours.map(h => h.label),
      datasets: [
        ...(hours.some(h => price("UA", h.ms) != null) ? [{ type: "line", label: t("priceEur"), data: hours.map(h => price("UA", h.ms)), yAxisID: "y1",
          borderColor: ZONES.UA.color, backgroundColor: ZONES.UA.color, borderWidth: 2.2, pointRadius: 0, stepped: "middle", order: 0 }] : []),
        { type: "bar", label: t("sell"), data: sell, backgroundColor: "rgba(66,133,214,.75)", order: 1 },
        { type: "bar", label: t("buy"), data: buy, backgroundColor: "rgba(240,128,60,.8)", order: 1 },
        { type: "bar", label: t("accepted"), data: acc, backgroundColor: "rgba(150,158,170,.6)", order: 1 },
      ],
    },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${nf(c.parsed.y, c.dataset.yAxisID === "y1" ? 2 : 1)}` } } },
      scales: { x: gridX, y: { ...gridY, title: { display: true, text: t("mwh") } },
        y1: { display: hours.some(h => price("UA", h.ms) != null), position: "right", grid: { display: false }, border: { display: false }, title: { display: true, text: "€/MWh" } } } },
  });
}

// ---------------------------------------------------------------- PERIOD VIEW
function periodDates() {
  const last = latestDate();
  const first = firstDate();
  if (!last) return [];
  let start = S.range === "all" ? first : addDays(last, -(+S.range - 1));
  if (first && start < first) start = first;
  const out = [];
  for (let d = start; d <= last; d = addDays(d, 1)) out.push(d);
  return out;
}
async function renderPeriod() {
  const dates = periodDates();
  if (!dates.length) { status(t("empty")); return; }
  await ensureMonths(localMidnight(dates[0], S.tz), localMidnight(addDays(dates[dates.length - 1], 1), S.tz));
  status("");
  const zs = activeZones();
  const daily = {}; zs.forEach(z => { daily[z] = dates.map(d => dayStats(z, d)); });

  makeChart("periodChart", {
    type: "line",
    data: { labels: dates, datasets: zs.map(z => ({ label: zname(z), data: daily[z].map(s => s.n ? +s[S.metric]?.toFixed(2) : null),
      borderColor: ZONES[z].color, backgroundColor: ZONES[z].color, borderWidth: 2, pointRadius: dates.length > 120 ? 0 : 2, tension: .15, spanGaps: true })) },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltipNum },
      scales: { x: { ...gridX, ticks: { maxTicksLimit: 12, callback(v) { const s = this.getLabelForValue(v); return s.slice(8, 10) + "." + s.slice(5, 7); } } },
        y: { ...gridY, title: { display: true, text: "€/MWh" } } } },
  });

  // monthly table (средние по дневным значениям, взвешенные по часам)
  const byM = {};
  dates.forEach((d, i) => {
    const m = d.slice(0, 7);
    zs.forEach(z => {
      const s = daily[z][i];
      s.vals.forEach((v, j) => {
        if (v == null) return;
        const o = ((byM[m] ||= {})[z] ||= { all: [0, 0], pk: [0, 0] });
        o.all[0] += v; o.all[1]++;
        if (s.hours[j].h >= PEAK_FROM && s.hours[j].h < PEAK_TO) { o.pk[0] += v; o.pk[1]++; }
      });
    });
  });
  const months = Object.keys(byM).sort().reverse();
  let html = `<thead><tr><th>${t("month")}</th>${zs.map(z => `<th>${z} Base</th><th>${z} Peak</th>`).join("")}</tr></thead><tbody>`;
  months.forEach(m => {
    html += `<tr><td class="grp">${m}</td>` + zs.map(z => {
      const o = byM[m][z];
      return o ? `<td>${nf(o.all[0] / o.all[1])}</td><td>${o.pk[1] ? nf(o.pk[0] / o.pk[1]) : "—"}</td>` : "<td>—</td><td>—</td>";
    }).join("") + "</tr>";
  });
  $("monthTable").innerHTML = html + "</tbody>";
}

// ---------------------------------------------------------------- ANALYTICS
const UA_NEIGHBOURS = ["PL", "SK", "HU", "RO"];
const UA_BORDERS = ["PL", "SK", "HU", "RO", "MD"];
const BAL_ZONES = ["PL", "SK", "HU", "RO", "UA"];
const BORDER_COLORS = { PL: "#d62839", SK: "#7b4fb3", HU: "#22955a", RO: "#1f5fbf", MD: "#8a8f98" };

function addMonths(ym, n) { const [y, m] = ym.split("-").map(Number); const d = new Date(Date.UTC(y, m - 1 + n, 1)); return d.toISOString().slice(0, 7); }
function monthsBack(endYm, n) { const out = []; for (let i = n - 1; i >= 0; i--) out.push(addMonths(endYm, -i)); return out; }
function daysOfMonth(ym) { const out = []; for (let d = ym + "-01"; d.startsWith(ym); d = addDays(d, 1)) out.push(d); return out; }
function fmtMonth(ym) {
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(S.lang === "ru" ? "ru-RU" : "en-GB", { month: "short", year: "2-digit", timeZone: "UTC" }).replace(" г.", "");
}

const _mcache = {};
/** Все часы месяца для зоны (в выбранном часовом поясе). */
function monthHours(zone, ym) {
  const key = `${S.tz}|${zone}|${ym}`;
  if (_mcache[key]) return _mcache[key];
  const hours = [], vals = [];
  for (const d of daysOfMonth(ym)) for (const h of dayHours(d, S.tz)) { hours.push(h); vals.push(price(zone, h.ms)); }
  return (_mcache[key] = { hours, vals });
}
function statsExt(vals, hours) {
  const s = stats(vals, hours);
  const v = vals.filter(x => x != null);
  s.neg = v.filter(x => x < 0).length;
  s.sd = s.base == null ? null : Math.sqrt(v.reduce((a, x) => a + (x - s.base) ** 2, 0) / v.length);
  s.cov = hours.length ? v.length / hours.length : 0;
  return s;
}
function concatMonths(zone, months) {
  const hours = [], vals = [];
  months.forEach(m => { const r = monthHours(zone, m); hours.push(...r.hours); vals.push(...r.vals); });
  return { hours, vals };
}
async function ensurePriceMonths(months) {
  const a = localMidnight(months[0] + "-01", S.tz);
  const b = localMidnight(addMonths(months[months.length - 1], 1) + "-01", S.tz);
  await ensureMonths(a, b);
}
async function ensureFlowMonths(months) {
  const avail = new Set(S.meta.flow_months || []);
  await Promise.all(months.filter(m => avail.has(m) && !S.flows[m]).map(async m => {
    S.flows[m] = (await getJSON(`data/flows/${m}.json`)).flows || {};
  }));
}
function flowSum(key, ym) {
  const f = S.flows[ym]?.[key];
  if (!f) return null;
  let s = 0, n = 0;
  for (const v of Object.values(f)) { s += v; n++; }
  return n ? s : null;
}
/** Импорт в страну C с границы N, экспорт из C в N (MWh за месяц). */
function borderIE(c, n, ym) {
  const imp = flowSum(`${n}>${c}`, ym), exp = flowSum(`${c}>${n}`, ym);
  return { imp, exp, net: imp == null && exp == null ? null : (imp || 0) - (exp || 0) };
}
function countryNet(c, ym) {
  let any = false, net = 0;
  for (const b of S.meta.borders || []) {
    const [x, y] = b.split("-");
    if (x !== c && y !== c) continue;
    const r = borderIE(c, x === c ? y : x, ym);
    if (r.net != null) { any = true; net += r.net; }
  }
  return any ? net : null;
}
const gwh = v => v == null ? null : v / 1000;
const cls = v => v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "";

function monthOptions() {
  const ms = (S.meta.months || []).slice().reverse();
  if (!S.endMonth || !ms.includes(S.endMonth)) S.endMonth = ms[0];
  $("endMonthSel").innerHTML = ms.map(m => `<option value="${m}" ${m === S.endMonth ? "selected" : ""}>${fmtMonth(m)}</option>`).join("");
}

async function renderAnalytics() {
  if (!S.meta.months?.length) { status(t("empty")); return; }
  monthOptions();
  const months = monthsBack(S.endMonth, 12);
  const prev = monthsBack(addMonths(S.endMonth, -12), 12);
  await ensurePriceMonths([...prev, ...months]);
  await ensureFlowMonths(months);
  status("");
  const zs = activeZones();

  // --- monthly stats
  const M = {};      // M[z][ym] = statsExt
  ORDER.forEach(z => { M[z] = {}; months.forEach(m => { const r = monthHours(z, m); M[z][m] = statsExt(r.vals, r.hours); }); });
  const partial = m => ORDER.some(z => M[z][m].n && M[z][m].cov < .95);
  const mLabel = m => fmtMonth(m) + (partial(m) ? "*" : "");
  $("anPeriodNote").textContent = `${fmtMonth(months[0])} — ${fmtMonth(months[11])}` + (months.some(partial) ? ` · ${t("partialMonth")}` : "");

  // --- 12m summary
  const Y = {}, P = {};
  ORDER.forEach(z => {
    const r = concatMonths(z, months); Y[z] = statsExt(r.vals, r.hours); Y[z].hours = r.hours;
    const q = concatMonths(z, prev); P[z] = statsExt(q.vals, q.hours);
  });
  const fmtHour = (s, k) => s[k] ? `${nf(s[k].v)} <span class="muted small">${new Date(s.hours[s[k].i].ms).toLocaleString(S.lang === "ru" ? "ru-RU" : "en-GB", { timeZone: S.tz, day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>` : "—";
  let html = `<thead><tr><th>${t("country")}</th><th>Base</th><th>Peak</th><th>Off-peak</th><th>${t("ratio")}</th><th>${t("minH")}</th><th>${t("maxH")}</th><th>${t("negH")}</th><th>${t("sigma")}</th><th>${t("vsPrev12")}</th><th>${t("coverage")}</th></tr></thead><tbody>`;
  zs.forEach(z => {
    const s = Y[z], p = P[z];
    const d = s.base != null && p.base != null && p.cov > .8 ? (s.base / p.base - 1) * 100 : null;
    html += `<tr><td class="zn"><i style="background:${ZONES[z].color}"></i>${zname(z)}</td>
      <td><b>${nf(s.base)}</b></td><td>${nf(s.peak)}</td><td>${nf(s.offpeak)}</td><td>${s.base ? nf(s.peak / s.base, 2) : "—"}</td>
      <td>${fmtHour(s, "min")}</td><td>${fmtHour(s, "max")}</td><td>${s.n ? s.neg : "—"}</td><td>${nf(s.sd)}</td>
      <td class="${cls(d)}">${d == null ? "—" : (d > 0 ? "+" : "") + nf(d, 1) + "%"}</td><td>${nf(s.cov * 100, 0)}%</td></tr>`;
  });
  $("anSummary").innerHTML = html + "</tbody>";

  // --- highlights
  const sp = n => { // среднее почасового спреда UA − n за 12 мес.
    const ua = concatMonths("UA", months).vals, nv = concatMonths(n, months).vals;
    let s = 0, c = 0, hi = 0;
    ua.forEach((v, i) => { if (v != null && nv[i] != null) { s += v - nv[i]; c++; if (v > nv[i]) hi++; } });
    return c ? { avg: s / c, share: hi / c } : { avg: null, share: null };
  };
  const uaNet12 = months.reduce((a, m) => { const v = countryNet("UA", m); return v == null ? a : (a ?? 0) + v; }, null);
  const top = ORDER.filter(z => Y[z].base != null).sort((a, b) => Y[b].base - Y[a].base)[0];
  const spHU = sp("HU");
  $("anHighlights").innerHTML = [
    [t("hlUA"), nf(Y.UA.base), "€/MWh", `Peak ${nf(Y.UA.peak)}`],
    [t("hlSpread"), spHU.avg == null ? "—" : sign(spHU.avg), "€/MWh", spHU.share == null ? "" : `UA > HU: ${nf(spHU.share * 100, 0)}% ${S.lang === "ru" ? "часов" : "of hours"}`],
    [t("hlImport"), uaNet12 == null ? "—" : nf(Math.abs(gwh(uaNet12)), 0), S.lang === "ru" ? "ГВт·ч" : "GWh", uaNet12 == null ? "" : uaNet12 >= 0 ? t("netImport") : t("netExport")],
    [t("hlTop"), top ? zname(top) : "—", "", top ? `Base ${nf(Y[top].base)} €/MWh` : ""],
  ].map(([h, v, u, n]) => `<div class="kpi"><div class="h"><span class="name">${h}</span></div><div class="big">${v}<small>${u}</small></div><div class="note">${n}</div></div>`).join("");

  // --- index dynamics
  const met = S.anMetric;
  makeChart("anIdxChart", {
    type: "line",
    data: { labels: months.map(mLabel), datasets: zs.map(z => ({ label: zname(z), data: months.map(m => M[z][m].n ? +M[z][m][met]?.toFixed(2) : null),
      borderColor: ZONES[z].color, backgroundColor: ZONES[z].color, borderWidth: 2.2, pointRadius: 3, tension: .2 })) },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltipNum },
      scales: { x: gridX, y: { ...gridY, title: { display: true, text: "€/MWh" } } } },
  });
  html = `<thead><tr><th rowspan="2">${t("month")}</th>${zs.map(z => `<th colspan="3" class="grp">${z}</th>`).join("")}</tr>
    <tr>${zs.map(() => `<th>Base</th><th>Peak</th><th>${t("mom")}</th>`).join("")}</tr></thead><tbody>`;
  months.slice().reverse().forEach(m => {
    html += `<tr><td class="grp">${mLabel(m)}</td>` + zs.map(z => {
      const s = M[z][m], pm = addMonths(m, -1);
      const p = M[z][pm] || (() => { const r = monthHours(z, pm); return statsExt(r.vals, r.hours); })();
      const d = s.base != null && p.base ? (s.base / p.base - 1) * 100 : null;
      return `<td>${nf(s.base)}</td><td>${nf(s.peak)}</td><td class="${cls(d)}">${d == null ? "—" : (d > 0 ? "+" : "") + nf(d, 1) + "%"}</td>`;
    }).join("") + "</tr>";
  });
  html += `<tr class="tot"><td>${t("avg12")}</td>${zs.map(z => `<td>${nf(Y[z].base)}</td><td>${nf(Y[z].peak)}</td><td></td>`).join("")}</tr>`;
  $("anIdxTable").innerHTML = html + "</tbody>";

  // --- spreads UA − neighbours (monthly, по часам где есть обе цены)
  const SP = {};
  UA_NEIGHBOURS.forEach(n => {
    SP[n] = months.map(m => {
      const a = monthHours("UA", m).vals, b = monthHours(n, m).vals;
      let s = 0, c = 0, hi = 0;
      a.forEach((v, i) => { if (v != null && b[i] != null) { s += v - b[i]; c++; if (v > b[i]) hi++; } });
      return c ? { avg: s / c, share: hi / c } : { avg: null, share: null };
    });
  });
  makeChart("anSpreadChart", {
    type: "bar",
    data: { labels: months.map(mLabel), datasets: UA_NEIGHBOURS.map(n => ({ label: `UA − ${n}`, data: SP[n].map(x => x.avg == null ? null : +x.avg.toFixed(2)),
      backgroundColor: ZONES[n].color, borderRadius: 2 })) },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltipNum },
      scales: { x: gridX, y: { ...gridY, title: { display: true, text: "€/MWh" } } } },
  });
  html = `<thead><tr><th rowspan="2">${t("month")}</th>${UA_NEIGHBOURS.map(n => `<th colspan="2" class="grp">UA − ${n}</th>`).join("")}</tr>
    <tr>${UA_NEIGHBOURS.map(() => `<th>${t("spreadAvg")}</th><th>${t("uaHigher")}</th>`).join("")}</tr></thead><tbody>`;
  months.map((m, i) => [m, i]).reverse().forEach(([m, i]) => {
    html += `<tr><td class="grp">${mLabel(m)}</td>` + UA_NEIGHBOURS.map(n => { const x = SP[n][i];
      return `<td class="${cls(x.avg)}">${x.avg == null ? "—" : sign(x.avg)}</td><td>${x.share == null ? "—" : nf(x.share * 100, 0) + "%"}</td>`; }).join("") + "</tr>";
  });
  html += `<tr class="tot"><td>${t("avg12")}</td>` + UA_NEIGHBOURS.map(n => { const x = sp(n);
    return `<td class="${cls(x.avg)}">${x.avg == null ? "—" : sign(x.avg)}</td><td>${x.share == null ? "—" : nf(x.share * 100, 0) + "%"}</td>`; }).join("") + "</tr>";
  $("anSpreadTable").innerHTML = html + "</tbody>";

  // --- UA traded volumes (ОРЕЕ)
  const hasUA = (S.meta.ua_dam_months || []).length > 0;
  $("anUACard").classList.toggle("hidden", !hasUA);
  const UV = {};
  if (hasUA) {
    await ensureUAMonths(localMidnight(months[0] + "-01", S.tz), localMidnight(addMonths(months[11], 1) + "-01", S.tz));
    months.forEach(m => { UV[m] = uaAgg(monthHours("UA", m).hours); });
    makeChart("anUAChart", {
      data: { labels: months.map(mLabel), datasets: [
        { type: "line", label: "Base UA, €/MWh", data: months.map(m => M.UA[m].n ? +M.UA[m].base.toFixed(2) : null), yAxisID: "y1",
          borderColor: ZONES.UA.color, backgroundColor: ZONES.UA.color, borderWidth: 2.2, pointRadius: 3, order: 0 },
        { type: "bar", label: t("traded"), data: months.map(m => UV[m].n ? +(UV[m].acc / 1000).toFixed(1) : null), backgroundColor: "rgba(150,158,170,.75)", order: 1 },
      ] },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } },
        scales: { x: gridX, y: { ...gridY, title: { display: true, text: t("gwhU") } },
          y1: { position: "right", grid: { display: false }, border: { display: false }, title: { display: true, text: "€/MWh" } } } },
    });
    html = `<thead><tr><th>${t("month")}</th><th>${t("traded")}, ${t("gwhU")}</th><th>${t("avgDay")}, ${t("mwh")}</th><th>${t("sell")}, ${t("gwhU")}</th><th>${t("buy")}, ${t("gwhU")}</th><th>${t("fillRate")}</th><th>${t("deficitH")}</th><th>${t("surplusH")}</th><th>Base UA</th></tr></thead><tbody>`;
    const row = (lbl, u, base, days, tot) => `<tr${tot ? ' class="tot"' : ""}><td class="grp">${lbl}</td>${u.n ? `<td><b>${nf(u.acc / 1000, 1)}</b></td><td>${nf(u.acc / Math.max(1, days), 0)}</td><td>${nf(u.sell / 1000, 1)}</td><td>${nf(u.buy / 1000, 1)}</td><td>${u.buy ? nf(u.acc / u.buy * 100, 0) + "%" : "—"}</td><td>${u.def}</td><td>${u.sur}</td>` : "<td>—</td>".repeat(7)}<td>${nf(base)}</td></tr>`;
    months.slice().reverse().forEach(m => { html += row(mLabel(m), UV[m], M.UA[m].base, UV[m].n / 24); });
    const tot = months.reduce((o, m) => { const u = UV[m]; ["acc", "buy", "sell", "n", "def", "sur"].forEach(k => o[k] += u[k]); return o; }, { acc: 0, buy: 0, sell: 0, n: 0, def: 0, sur: 0 });
    html += row(t("total12"), tot, Y.UA.base, tot.n / 24, true);
    $("anUATable").innerHTML = html + "</tbody>";
  }

  S._an = { months, M, SP, F: {}, B: {}, bordersWithData: [], UV };

  // --- flows
  const hasFlows = months.some(m => S.flows[m] && Object.keys(S.flows[m]).length);
  $("anFlowStatus").textContent = hasFlows ? "" : t("noFlows");
  $("anFlowStatus").classList.toggle("hidden", hasFlows);
  ["anFlowChart", "anBalChart"].forEach(id => $(id).parentElement.classList.toggle("hidden", !hasFlows));
  ["anFlowTable", "anBalTable"].forEach(id => $(id).parentElement.classList.toggle("hidden", !hasFlows));
  if (!hasFlows) return;

  const F = {}; UA_BORDERS.forEach(n => { F[n] = months.map(m => borderIE("UA", n, m)); });
  const bordersWithData = UA_BORDERS.filter(n => F[n].some(x => x.net != null));
  makeChart("anFlowChart", {
    type: "bar",
    data: { labels: months.map(mLabel), datasets: bordersWithData.map(n => ({ label: `${n} ⇄ UA`, data: F[n].map(x => x.net == null ? null : +gwh(x.net).toFixed(1)),
      backgroundColor: BORDER_COLORS[n], stack: "s" })) },
    options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${nf(c.parsed.y, 1)} GWh` } } },
      scales: { x: { ...gridX, stacked: true }, y: { ...gridY, stacked: true, title: { display: true, text: S.lang === "ru" ? "ГВт·ч" : "GWh" } } } },
  });
  html = `<thead><tr><th rowspan="2">${t("month")}</th>${bordersWithData.map(n => `<th colspan="3" class="grp">${n}</th>`).join("")}<th colspan="3" class="grp">${S.lang === "ru" ? "Всего" : "Total"}</th></tr>
    <tr>${[...bordersWithData, "T"].map(() => `<th>${t("imp")}</th><th>${t("exp")}</th><th>${t("net")}</th>`).join("")}</tr></thead><tbody>`;
  const row = (lbl, list, tot) => `<tr${tot ? ' class="tot"' : ""}><td class="grp">${lbl}</td>` + list.map(x =>
    `<td>${x.imp == null ? "—" : nf(gwh(x.imp), 1)}</td><td>${x.exp == null ? "—" : nf(gwh(x.exp), 1)}</td><td class="${cls(x.net)}">${x.net == null ? "—" : (x.net > 0 ? "+" : "") + nf(gwh(x.net), 1)}</td>`).join("") + "</tr>";
  const sumIE = arr => arr.reduce((a, x) => ({ imp: x.imp == null ? a.imp : (a.imp ?? 0) + x.imp, exp: x.exp == null ? a.exp : (a.exp ?? 0) + x.exp,
    net: x.net == null ? a.net : (a.net ?? 0) + x.net }), { imp: null, exp: null, net: null });
  months.map((m, i) => [m, i]).reverse().forEach(([m, i]) => {
    const list = bordersWithData.map(n => F[n][i]);
    html += row(mLabel(m), [...list, sumIE(list)]);
  });
  const totals = bordersWithData.map(n => sumIE(F[n]));
  html += row(t("total12"), [...totals, sumIE(totals)], true);
  $("anFlowTable").innerHTML = html + "</tbody>";

  // --- balances
  const B = {}; BAL_ZONES.forEach(c => { B[c] = months.map(m => countryNet(c, m)); });
  makeChart("anBalChart", {
    type: "bar",
    data: { labels: months.map(mLabel), datasets: BAL_ZONES.filter(c => S.zones.has(c)).map(c => ({ label: zname(c), data: B[c].map(v => v == null ? null : +gwh(v).toFixed(1)),
      backgroundColor: ZONES[c].color, borderRadius: 2 })) },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
      tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${nf(c.parsed.y, 1)} GWh` } } },
      scales: { x: gridX, y: { ...gridY, title: { display: true, text: S.lang === "ru" ? "ГВт·ч" : "GWh" } } } },
  });
  const bz = BAL_ZONES.filter(c => S.zones.has(c));
  html = `<thead><tr><th>${t("month")}</th>${bz.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>`;
  months.map((m, i) => [m, i]).reverse().forEach(([m, i]) => {
    html += `<tr><td class="grp">${mLabel(m)}</td>${bz.map(c => { const v = B[c][i]; return `<td class="${cls(v)}">${v == null ? "—" : (v > 0 ? "+" : "") + nf(gwh(v), 1)}</td>`; }).join("")}</tr>`;
  });
  html += `<tr class="tot"><td>${t("total12")}</td>${bz.map(c => { const v = B[c].reduce((a, x) => x == null ? a : (a ?? 0) + x, null);
    return `<td class="${cls(v)}">${v == null ? "—" : (v > 0 ? "+" : "") + nf(gwh(v), 1)}</td>`; }).join("")}</tr>`;
  $("anBalTable").innerHTML = html + "</tbody>";
  S._an = { months, M, SP, F, B, bordersWithData, UV };
}

// ---------------------------------------------------------------- EXCEL (все данные)
function loadScript(src) {
  return new Promise((ok, err) => { const el = document.createElement("script"); el.src = src; el.onload = ok; el.onerror = err; document.head.appendChild(el); });
}
async function exportExcel() {
  const btn = $("xlsxBtn");
  btn.disabled = true; btn.textContent = t("xlsxBusy");
  try {
    if (!window.XLSX) await loadScript("vendor/xlsx.mini.min.js");
    const ru = S.lang === "ru";
    const allM = S.meta.months || [];
    const first = firstDate(), last = latestDate();
    if (!first || !last) throw new Error(t("empty"));
    await ensureMonths(localMidnight(first, S.tz), localMidnight(addDays(last, 1), S.tz));
    await ensureFlowMonths(S.meta.flow_months || []);
    const tzName = S.tz === "Europe/Kyiv" ? (ru ? "Киев/Кишинёв (EET)" : "Kyiv/Chisinau (EET)") : "CET/CEST";
    const r2 = v => v == null || isNaN(v) ? null : Math.round(v * 100) / 100;
    const wb = XLSX.utils.book_new();
    const add = (name, rows, widths) => {
      const ws = XLSX.utils.aoa_to_sheet(rows);
      ws["!cols"] = (widths || rows[0].map(() => 11)).map(w => ({ wch: w }));
      if (rows.length > 1) ws["!autofilter"] = { ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: rows.length - 1, c: rows[0].length - 1 } }) };
      XLSX.utils.book_append_sheet(wb, ws, name);
    };

    // 1. Часовые цены
    const dates = []; for (let d = first; d <= last; d = addDays(d, 1)) dates.push(d);
    const hr = [[ru ? "Дата" : "Date", ru ? "Час" : "Hour", "UTC", ...ORDER.map(z => `${z}, €/MWh`)]];
    dates.forEach(d => dayHours(d, S.tz).forEach(h => {
      const v = ORDER.map(z => price(z, h.ms));
      if (v.some(x => x != null)) hr.push([d, h.label, isoKey(h.ms), ...v]);
    }));
    add(ru ? "Часовые цены" : "Hourly prices", hr, [11, 8, 18, 11, 11, 11, 11, 11]);

    // 2. Дневные индексы
    const dh = [[ru ? "Дата" : "Date", ...ORDER.flatMap(z => [`${z} Base`, `${z} Peak`, `${z} Off-peak`])]];
    dates.forEach(d => { const row = ORDER.flatMap(z => { const s = dayStats(z, d); return s.n ? [r2(s.base), r2(s.peak), r2(s.offpeak)] : [null, null, null]; });
      if (row.some(x => x != null)) dh.push([d, ...row]); });
    add(ru ? "Дневные индексы" : "Daily indices", dh, [11, ...ORDER.flatMap(() => [10, 10, 11])]);

    // 3. Месячные индексы
    const mh = [[ru ? "Месяц" : "Month", ...ORDER.flatMap(z => [`${z} Base`, `${z} Peak`, `${z} Off-peak`, `${z} ${ru ? "мин" : "min"}`, `${z} ${ru ? "макс" : "max"}`, `${z} σ`, `${z} ${ru ? "отриц. ч" : "neg. h"}`])]];
    const MS = {}; ORDER.forEach(z => { MS[z] = {}; allM.forEach(m => { const r = monthHours(z, m); MS[z][m] = statsExt(r.vals, r.hours); }); });
    const pushIf = (rows, row) => { if (row.slice(1).some(x => x != null)) rows.push(row); };
    allM.forEach(m => pushIf(mh, [m, ...ORDER.flatMap(z => { const s = MS[z][m]; return s.n ? [r2(s.base), r2(s.peak), r2(s.offpeak), r2(s.min?.v), r2(s.max?.v), r2(s.sd), s.neg] : [null, null, null, null, null, null, null]; })]));
    add(ru ? "Месячные индексы" : "Monthly indices", mh, [9, ...ORDER.flatMap(() => [9, 9, 10, 9, 9, 8, 9])]);

    // 4. Спреды Украина − соседи
    const sh = [[ru ? "Месяц" : "Month", ...UA_NEIGHBOURS.flatMap(n => [`UA−${n}, €/MWh`, `UA>${n}, % ${ru ? "часов" : "hours"}`])]];
    allM.forEach(m => pushIf(sh, [m, ...UA_NEIGHBOURS.flatMap(n => {
      const a = monthHours("UA", m).vals, b = monthHours(n, m).vals; let s = 0, c = 0, hi = 0;
      a.forEach((v, i) => { if (v != null && b[i] != null) { s += v - b[i]; c++; if (v > b[i]) hi++; } });
      return c ? [r2(s / c), r2(hi / c * 100)] : [null, null];
    })]));
    add(ru ? "Спреды UA" : "UA spreads", sh, [9, ...UA_NEIGHBOURS.flatMap(() => [13, 14])]);

    // 5–6. Перетоки
    const fm = S.meta.flow_months || [];
    if (fm.length) {
      const keys = [...new Set(fm.flatMap(m => Object.keys(S.flows[m] || {})))].sort();
      const fdays = [...new Set(fm.flatMap(m => Object.values(S.flows[m] || {}).flatMap(o => Object.keys(o))))].sort();
      const fh = [[ru ? "Дата (CET)" : "Date (CET)", ...keys.map(k => `${k.replace(">", " → ")}, MWh`)]];
      fdays.forEach(d => fh.push([d, ...keys.map(k => S.flows[d.slice(0, 7)]?.[k]?.[d] ?? null)]));
      add(ru ? "Перетоки по суткам" : "Daily flows", fh, [12, ...keys.map(() => 13)]);

      const bh = [[ru ? "Месяц" : "Month",
        ...UA_BORDERS.flatMap(n => [`${n}→UA, GWh`, `UA→${n}, GWh`, `${ru ? "Сальдо" : "Net"} UA/${n}, GWh`]),
        ...BAL_ZONES.map(c => `${ru ? "Сальдо" : "Net import"} ${c}, GWh`)]];
      fm.forEach(m => bh.push([m,
        ...UA_BORDERS.flatMap(n => { const x = borderIE("UA", n, m); return [x.imp, x.exp, x.net].map(v => v == null ? null : r2(v / 1000)); }),
        ...BAL_ZONES.map(c => { const v = countryNet(c, m); return v == null ? null : r2(v / 1000); })]));
      add(ru ? "Перетоки и сальдо" : "Flows & balances", bh, [9, ...UA_BORDERS.flatMap(() => [11, 11, 13]), ...BAL_ZONES.map(() => 14)]);
    }

    // UA: объёмы РДН (ОРЕЕ)
    const um = S.meta.ua_dam_months || [];
    if (um.length) {
      await ensureUAMonths(localMidnight(first, S.tz), localMidnight(addDays(last, 1), S.tz));
      const uh = [[ru ? "Дата" : "Date", ru ? "Час" : "Hour", "UTC", ru ? "Цена, грн/МВт·ч" : "Price, UAH/MWh", ru ? "Цена, €/MWh" : "Price, €/MWh",
        ru ? "Предложение (SELL), МВт·ч" : "Supply (SELL), MWh", ru ? "Спрос (BUY), МВт·ч" : "Demand (BUY), MWh", ru ? "Акцепт, МВт·ч" : "Cleared, MWh", ru ? "Дефицит(−)/профицит(+), МВт·ч" : "Deficit(−)/surplus(+), MWh"]];
      dates.forEach(d => dayHours(d, S.tz).forEach(h => {
        const a = uaV("accepted", h.ms); if (a == null) return;
        const b = uaV("buy", h.ms), s2 = uaV("sell", h.ms);
        uh.push([d, h.label, isoKey(h.ms), uaV("price", h.ms), price("UA", h.ms), s2, b, a, s2 != null && b != null ? r2(s2 - b) : null]);
      }));
      add(ru ? "UA объёмы (час)" : "UA volumes (hourly)", uh, [11, 8, 18, 13, 11, 15, 15, 12, 16]);
      const ums = [[ru ? "Месяц" : "Month", ru ? "Объём торгов, ГВт·ч" : "Traded, GWh", ru ? "Предложение, ГВт·ч" : "Supply, GWh", ru ? "Спрос, ГВт·ч" : "Demand, GWh",
        ru ? "Удовлетворено спроса, %" : "Demand cleared, %", ru ? "Часов дефицита" : "Deficit hours", ru ? "Часов профицита" : "Surplus hours", "Base UA, €/MWh"]];
      allM.forEach(m => { const u = uaAgg(monthHours("UA", m).hours); if (!u.n) return;
        ums.push([m, r2(u.acc / 1000), r2(u.sell / 1000), r2(u.buy / 1000), u.buy ? r2(u.acc / u.buy * 100) : null, u.def, u.sur, r2(MS.UA[m].base)]); });
      add(ru ? "UA объёмы (месяц)" : "UA volumes (monthly)", ums, [9, 14, 14, 12, 14, 12, 12, 12]);
    }

    // 7. Инфо
    const info = ru ? [
      ["Цены РДН: PL, SK, HU, RO, UA"],
      ["Сформировано", new Date().toLocaleString("ru-RU", { timeZone: S.tz })],
      ["Данные обновлены", new Date(S.meta.updated).toLocaleString("ru-RU", { timeZone: S.tz })],
      ["Часовой пояс дат и часов", tzName],
      ["Цены", "EUR/MWh; для 15-минутных рынков час = среднее четырёх 15-минуток"],
      ["Base / Peak / Off-peak", "среднее за сутки / 08:00–20:00 / остальные часы (в выбранном часовом поясе)"],
      ["Цены Украины в грн", "переведены в EUR по курсу НБУ на дату поставки"],
      ["Перетоки", "ENTSO-E, фактические физические перетоки; суммы за сутки по CET; сальдо «+» = нетто-импорт"],
      ["Объёмы РДН Украины", "ОРЕЕ: заявленные спрос (BUY) и предложение (SELL), акцептованный объём (= объём торгов), цена в грн"],
      ["Источники", Object.entries(S.meta.sources || {}).map(([z, s]) => `${z}: ${s}`).join("; ")],
    ] : [
      ["Day-ahead prices: PL, SK, HU, RO, UA"],
      ["Generated", new Date().toLocaleString("en-GB", { timeZone: S.tz })],
      ["Data updated", new Date(S.meta.updated).toLocaleString("en-GB", { timeZone: S.tz })],
      ["Time zone", tzName],
      ["Prices", "EUR/MWh; for 15-minute markets hour = average of four quarter-hours"],
      ["Base / Peak / Off-peak", "daily average / 08:00–20:00 / other hours (selected time zone)"],
      ["Ukrainian prices in UAH", "converted to EUR at the NBU rate for the delivery date"],
      ["Flows", "ENTSO-E physical flows; daily sums by CET day; net “+” = net import"],
      ["Ukraine DAM volumes", "OREE: declared demand (BUY) and supply (SELL), cleared volume (= traded volume), price in UAH"],
      ["Sources", Object.entries(S.meta.sources || {}).map(([z, s]) => `${z}: ${s}`).join("; ")],
    ];
    const wsI = XLSX.utils.aoa_to_sheet(info); wsI["!cols"] = [{ wch: 28 }, { wch: 90 }];
    XLSX.utils.book_append_sheet(wb, wsI, ru ? "Инфо" : "Info");
    wb.SheetNames.unshift(wb.SheetNames.pop());   // «Инфо» первым листом

    XLSX.writeFile(wb, `rdn_all_${first}_${last}.xlsx`, { compression: true });
  } catch (e) { console.error(e); alert(String(e.message || e)); }
  finally { btn.disabled = false; btn.textContent = t("xlsx"); }
}

// ---------------------------------------------------------------- CSV
function downloadCSV() {
  const zs = activeZones();
  let rows, name;
  if (S.view === "day") {
    const hours = dayHours(S.date, S.tz);
    rows = [["date", "hour", "utc_start", ...zs.map(z => `${z}_EUR_MWh`)]];
    hours.forEach(h => rows.push([S.date, h.label, isoKey(h.ms), ...zs.map(z => price(z, h.ms) ?? "")]));
    name = `rdn_${S.date}.csv`;
  } else if (S.view === "analytics" && S._an) {
    const A = S._an;
    rows = [["section", "month", ...ORDER.flatMap(z => [`${z}_base`, `${z}_peak`, `${z}_offpeak`])]];
    A.months.forEach(m => rows.push(["index_EUR_MWh", m, ...ORDER.flatMap(z => ["base", "peak", "offpeak"].map(k => A.M[z][m][k] == null ? "" : A.M[z][m][k].toFixed(2)))]));
    rows.push([]);
    rows.push(["section", "month", ...UA_NEIGHBOURS.flatMap(n => [`UA-${n}_spread`, `UA>${n}_share`])]);
    A.months.forEach((m, i) => rows.push(["spread_EUR_MWh", m, ...UA_NEIGHBOURS.flatMap(n => [A.SP[n][i].avg?.toFixed(2) ?? "", A.SP[n][i].share == null ? "" : A.SP[n][i].share.toFixed(3)])]));
    rows.push([]);
    rows.push(["section", "month", ...A.bordersWithData.flatMap(n => [`${n}>UA_MWh`, `UA>${n}_MWh`, `${n}_net_MWh`])]);
    A.months.forEach((m, i) => rows.push(["flows_UA", m, ...A.bordersWithData.flatMap(n => { const x = A.F[n][i]; return [x.imp, x.exp, x.net].map(v => v == null ? "" : v.toFixed(0)); })]));
    rows.push([]);
    rows.push(["section", "month", ...BAL_ZONES.map(c => `${c}_net_import_MWh`)]);
    A.months.forEach((m, i) => rows.push(["balance", m, ...BAL_ZONES.map(c => A.B[c]?.[i] == null ? "" : A.B[c][i].toFixed(0))]));
    name = `rdn_analytics_${A.months[0]}_${A.months[11]}.csv`;
  } else {
    const dates = periodDates();
    rows = [["date", ...zs.flatMap(z => [`${z}_base`, `${z}_peak`, `${z}_offpeak`])]];
    dates.forEach(d => rows.push([d, ...zs.flatMap(z => { const s = dayStats(z, d); return [s.base, s.peak, s.offpeak].map(v => v == null ? "" : v.toFixed(2)); })]));
    name = `rdn_daily_${dates[0]}_${dates[dates.length - 1]}.csv`;
  }
  const csv = "﻿" + rows.map(r => r.join(";")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// ---------------------------------------------------------------- dates available
function latestDate() {
  const l = Object.values(S.meta?.last || {});
  if (!l.length) return null;
  const max = l.sort().pop();
  return localDateOf(Date.parse(max), S.tz);
}
function firstDate() {
  const m = (S.meta?.months || [])[0];
  return m ? m + "-01" : null;
}

// ---------------------------------------------------------------- render / events
async function render() {
  $("dayView").classList.toggle("hidden", S.view !== "day");
  $("periodView").classList.toggle("hidden", S.view !== "period");
  $("analyticsView").classList.toggle("hidden", S.view !== "analytics");
  $("analyticsControls").classList.toggle("hidden", S.view !== "analytics");
  $("dayControls").classList.toggle("hidden", S.view !== "day");
  $("periodControls").classList.toggle("hidden", S.view !== "period");
  segOn("viewSeg", "view", S.view);
  try {
    if (S.view === "day") await renderDay();
    else if (S.view === "period") await renderPeriod();
    else await renderAnalytics();
  } catch (e) { console.error(e); status(String(e)); }
}

function bind() {
  $("langSeg").onclick = e => { const v = e.target.dataset.lang; if (!v) return; S.lang = v; localSet("lang", v); applyI18n(); render(); };
  $("tzSeg").onclick = e => { const v = e.target.dataset.tz; if (!v) return; S.tz = v; localSet("tz", v); applyI18n(); render(); };
  $("viewSeg").onclick = e => { const v = e.target.dataset.view; if (!v) return; S.view = v; render(); };
  $("metricSeg").onclick = e => { const v = e.target.dataset.metric; if (!v) return; S.metric = v; segOn("metricSeg", "metric", v); render(); };
  $("endMonthSel").onchange = e => { S.endMonth = e.target.value; render(); };
  $("anMetricSeg").onclick = e => { const v = e.target.dataset.metric; if (!v) return; S.anMetric = v; segOn("anMetricSeg", "metric", v); render(); };
  $("rangeSel").onchange = e => { S.range = e.target.value; render(); };
  $("zoneChips").onclick = e => {
    const c = e.target.closest(".chip"); if (!c) return;
    const z = c.dataset.z;
    if (S.zones.has(z) && S.zones.size > 1) S.zones.delete(z); else S.zones.add(z);
    localSet("zones", [...S.zones].join(",")); renderChips(); render();
  };
  $("dateInput").onchange = e => { if (e.target.value) { S.date = e.target.value; render(); } };
  $("prevDay").onclick = () => { S.date = addDays(S.date, -1); render(); };
  $("nextDay").onclick = () => { S.date = addDays(S.date, 1); render(); };
  $("pairA").onchange = e => { S.pairA = e.target.value; render(); };
  $("pairB").onchange = e => { S.pairB = e.target.value; render(); };
  $("csvBtn").onclick = downloadCSV;
  $("xlsxBtn").onclick = exportExcel;
  document.addEventListener("keydown", e => {
    if (S.view !== "day" || e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.key === "ArrowLeft") $("prevDay").click();
    if (e.key === "ArrowRight" && !$("nextDay").disabled) $("nextDay").click();
  });
}

// ---------------------------------------------------------------- DEMO (?demo=1): выдуманные данные, генерируются в браузере
function buildDemo() {
  let seed = 42;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const base = { PL: 98, SK: 106, HU: 112, RO: 115, UA: 122 };
  const now = Date.now();
  const tomorrowEnd = localMidnight(addDays(localDateOf(now, "Europe/Budapest"), 2), "Europe/Budapest");
  const nd = new Date(now);
  const from = Date.UTC(nd.getUTCFullYear() - 2, nd.getUTCMonth(), 1);
  const months = {};
  let shock = 0;
  for (let ms = from; ms < tomorrowEnd; ms += 3600e3) {
    const d = new Date(ms), k = isoKey(ms), m = k.slice(0, 7);
    const doy = (ms - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5;
    const h = parts(ms, "Europe/Budapest").h;
    const wd = parts(ms, "Europe/Budapest"); const dow = new Date(Date.UTC(wd.y, wd.m - 1, wd.d)).getUTCDay();
    const seas = 1 + .28 * Math.cos((doy - 15) / 365 * 2 * Math.PI);
    const solar = (1.6 - seas) * 55 * Math.exp(-((h - 13) ** 2) / 6);
    const shape = 30 * Math.exp(-((h - 19) ** 2) / 5) + 14 * Math.exp(-((h - 8) ** 2) / 3) - solar;
    if (h === 0) shock = gauss() * 14;
    const wkend = dow === 0 || dow === 6 ? -14 : 0;
    const yearTrend = (d.getUTCFullYear() - 2025) * -6;
    for (const [z, b] of Object.entries(base)) {
      if (z === "UA" && ms >= tomorrowEnd - 24 * 3600e3) continue;   // Украина «ещё не опубликована» на завтра
      const k2 = z === "HU" || z === "RO" ? 1.25 : z === "UA" ? .8 : 1;
      let v = b * seas + shape * k2 + shock + wkend + yearTrend + gauss() * 7;
      if (z === "UA") v = Math.min(v, 205);                           // «прайс-кэп»
      ((months[m] ||= {})[z] ||= {})[k] = Math.round(v * 100) / 100;
    }
  }
  // перетоки: суточные суммы MWh
  const fmean = { "HU>UA": 9000, "UA>HU": 1500, "SK>UA": 7000, "UA>SK": 1200, "PL>UA": 3500, "UA>PL": 800, "RO>UA": 4000, "UA>RO": 2500,
    "UA>MD": 6000, "MD>UA": 900, "DE>PL": 20000, "PL>DE": 8000, "CZ>PL": 6000, "PL>CZ": 3000, "SK>HU": 25000, "HU>SK": 3000, "CZ>SK": 15000,
    "SK>CZ": 4000, "AT>HU": 12000, "HU>AT": 3000, "HU>RO": 8000, "RO>HU": 7000, "RO>BG": 6000, "BG>RO": 8000, "RS>HU": 5000, "HU>RS": 4000,
    "RO>MD": 5000, "PL>LT": 3000, "LT>PL": 2000, "SE4>PL": 9000, "HR>HU": 3000, "HU>HR": 4000, "SI>HU": 1500, "HU>SI": 2500 };
  const flows = {};
  const lastFlowDay = addDays(localDateOf(now, "Europe/Budapest"), -1);
  for (let d = new Date(from).toISOString().slice(0, 10); d <= lastFlowDay; d = addDays(d, 1)) {
    const n = Date.parse(d) / 864e5;
    for (const [key, mean] of Object.entries(fmean))
      ((flows[d.slice(0, 7)] ||= {})[key] ||= {})[d] = Math.max(0, Math.round((mean * (1 + .3 * Math.sin(n / 40)) + gauss() * mean * .2) * 10) / 10);
  }
  const ms = Object.keys(months).sort();
  const last = {}; Object.keys(base).forEach(z => { last[z] = Object.keys(months[ms[ms.length - 1]][z] || months[ms[ms.length - 2]][z]).sort().pop(); });
  S.months = months; S.flows = flows;
  const uaDam = {};
  for (const [m, zz] of Object.entries(months)) for (const [k, p] of Object.entries(zz.UA || {})) {
    const h = parts(Date.parse(k), "Europe/Kyiv").h;
    const dem = 2600 + 1500 * Math.exp(-((h - 19) ** 2) / 10) + 900 * Math.exp(-((h - 9) ** 2) / 8) + gauss() * 150;
    const sup = 2800 + 1700 * Math.exp(-((h - 12) ** 2) / 12) + gauss() * 180;
    const o = (uaDam[m] ||= { price: {}, buy: {}, sell: {}, accepted: {} });
    o.price[k] = Math.round(p * 49.5); o.buy[k] = Math.round(dem * 10) / 10; o.sell[k] = Math.round(sup * 10) / 10;
    o.accepted[k] = Math.round(Math.min(dem, sup) * (0.9 + rnd() * 0.08) * 10) / 10;
  }
  S.uaDam = uaDam;
  return { updated: new Date().toISOString(), months: ms, flow_months: Object.keys(flows).sort(), ua_dam_months: Object.keys(S.uaDam).sort(), last, demo: true,
    borders: ["PL-DE","PL-CZ","PL-SK","PL-LT","PL-SE4","PL-UA","SK-CZ","SK-HU","SK-UA","HU-AT","HU-UA","HU-RO","HU-RS","HU-HR","HU-SI","RO-UA","RO-MD","RO-BG","RO-RS","UA-MD"],
    sources: Object.fromEntries(Object.keys(base).map(z => [z, "DEMO"])) };
}

async function init() {
  bind();
  status(t("loading"));
  const isDemo = new URLSearchParams(location.search).has("demo");
  if (isDemo) {
    S.meta = buildDemo();
    $("demoBanner").classList.remove("hidden");
  } else {
    try {
      S.meta = await getJSON("data/meta.json");
    } catch {
      S.meta = { months: [], last: {}, sources: {} };
    }
  }
  applyI18n();
  const params = new URLSearchParams(location.search);
  S.date = params.get("date") || latestDate() || localDateOf(Date.now(), S.tz);
  if (["day", "period", "analytics"].includes(params.get("view"))) S.view = params.get("view");
  if (!S.meta.months?.length) { status(t("empty")); return; }
  render();
}
init();
})();
