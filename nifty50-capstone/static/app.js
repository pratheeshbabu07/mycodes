/* Nifty 50 predictor - the page's API client.
   Plain fetch + DOM, no framework, so there is nothing to build or install. */

const $ = (id) => document.getElementById(id);

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/* --- helpers ------------------------------------------------------------- */

async function call(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try { body = await res.json(); } catch (e) { /* non-JSON error page */ }
  if (!res.ok) {
    throw new Error((body && (body.detail || body.error)) || `${res.status} ${res.statusText}`);
  }
  return body;
}

// Text only - never innerHTML with server data.
const text = (el, value) => { el.textContent = value; };

const fmtProb = (p) => Number(p).toFixed(4);

// '2026-09-22' + 'Tue' -> 'Tue 22 Sep'. Parsed by hand so no timezone can shift it.
function fmtDate(iso, day) {
  const [, m, d] = iso.split('-');
  return `${day} ${Number(d)} ${MONTHS[Number(m) - 1]}`;
}

/* Direction as three channels at once: a triangle (shape), the word (text), and
   colour last. Green/red separate poorly for deuteranopes, so the shape and the
   word are what actually carry it. */
function directionEl(direction, { chip = false } = {}) {
  const up = direction === 'Up';
  const el = document.createElement('span');
  el.className = (chip ? 'chip ' : 'dir ') + (up ? 'up' : 'down');
  const mark = document.createElement('span');
  mark.className = 'mark';
  mark.textContent = up ? '▲' : '▼';   // filled triangle up / down
  mark.setAttribute('aria-hidden', 'true');
  el.append(mark, document.createTextNode(direction));
  return el;
}

function cell(row, value, { num = false } = {}) {
  const td = document.createElement('td');
  if (num) td.classList.add('num');
  if (value instanceof Node) td.append(value); else td.textContent = value;
  row.append(td);
  return td;
}

function busy(button, on, label) {
  button.disabled = on;
  if (on) { button.dataset.label = button.textContent; button.textContent = label; }
  else if (button.dataset.label) { button.textContent = button.dataset.label; }
}

/* --- status bar ---------------------------------------------------------- */

async function loadHealth() {
  const h = await call('/health');

  const model = $('st-model');
  model.textContent = '';
  const dot = document.createElement('span');
  dot.className = 'dot ' + (h.model_loaded ? 'ok' : 'bad');
  model.append(dot, document.createTextNode(
    h.model_loaded ? (h.model_type || 'loaded') : 'not loaded'));

  text($('st-features'), String(h.features.length));
  text($('st-today'), h.today_label);
  text($('st-market'), h.market_open ? 'open' : 'shut (weekend)');
  text($('st-week'), h.week_label || '—');
}

/* --- the hero figure ----------------------------------------------------- */

/* The one number the page leads with: the next session still to open. On a Friday
   every session has already traded, so fall back to the most recent one. */
function renderHero(records) {
  const next = records.find((r) => r.Horizon === 'Forecast');
  const rec = next || records[records.length - 1];
  if (!rec) return;

  const prob = Number(rec['Predicted Probability']);
  const up = rec['Nifty 50 Open Direction'] === 'Up';

  text($('hero-label'), next ? 'Next session' : 'Latest session');
  text($('hero-date'), fmtDate(rec.Date, rec.Day));
  text($('hero-prob'), fmtProb(prob));
  text($('hero-class'), String(rec['Predicted Class']));

  const dir = $('hero-dir');
  dir.textContent = '';
  dir.append(directionEl(rec['Nifty 50 Open Direction'], { chip: true }));

  const meter = $('hero-meter');
  meter.className = 'fill ' + (up ? 'up' : 'down');
  meter.style.width = Math.max(1, Math.min(100, prob * 100)) + '%';

  $('hero').classList.remove('hidden');
}

/* --- the week ------------------------------------------------------------ */

async function runWeek() {
  const note = $('week-note');
  note.className = 'note';
  text(note, 'Topping up data and predicting…');
  busy($('btn-week'), true, 'Running…');

  try {
    const r = await call('/predict/week', { method: 'POST' });

    const body = $('week-rows');
    body.textContent = '';
    for (const rec of r.records) {
      const tr = document.createElement('tr');
      const traded = rec.Horizon !== 'Forecast';
      if (traded) tr.className = 'traded';

      cell(tr, rec.Date);
      cell(tr, rec.Day);

      const h = document.createElement('span');
      h.className = 'horizon' + (traded ? '' : ' forecast');
      h.textContent = traded ? 'Traded' : 'Forecast';
      cell(tr, h);

      cell(tr, fmtProb(rec['Predicted Probability']), { num: true });
      cell(tr, String(rec['Predicted Class']), { num: true });
      cell(tr, directionEl(rec['Nifty 50 Open Direction']));
      body.append(tr);
    }

    renderHero(r.records);

    // Cache-bust so a rerun shows the new chart rather than the old one.
    $('week-img').src = '/chart/week.png?t=' + Date.now();

    $('empty').classList.add('hidden');
    $('week-chart').classList.remove('hidden');
    $('week-tablewrap').classList.remove('hidden');

    text(note, `${r.week_label} · ${r.n_traded} already traded, ${r.n_forecast} forecast`
                + (r.weekend_run ? ' · market shut, whole week is forecast' : ''));

    const dl = $('week-download');
    dl.textContent = '';
    const a = document.createElement('a');
    a.href = '/outputs/' + encodeURIComponent(r.csv_name);
    a.textContent = 'Download ' + r.csv_name;
    dl.append(document.createTextNode('Saved to the output folder. '), a);
    dl.classList.remove('hidden');
  } catch (err) {
    note.className = 'note error';
    text(note, err.message);
  } finally {
    busy($('btn-week'), false);
  }
}

/* --- wire up ------------------------------------------------------------- */

$('btn-week').onclick = runWeek;

loadHealth().catch((err) => text($('st-model'), 'API unreachable: ' + err.message));
