/* ---------------- theme ---------------- */
const SUN_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>';
const MOON_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  document.getElementById('themeToggle').innerHTML = theme === 'dark' ? SUN_ICON : MOON_ICON;
}
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  applyTheme(current === 'dark' ? 'light' : 'dark');
}
applyTheme(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');

function applyPalette(palette) {
  document.documentElement.setAttribute('data-palette', palette);
}
applyPalette('aurora');

/* ---------------- tabs ---------------- */
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });

  const panel = document.getElementById('tab-' + name);
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  panel.classList.add('active');
  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');

  // Move focus to the panel's heading so screen reader users get an
  // announcement that the section changed, not just a silent DOM swap.
  const heading = panel.querySelector('h2');
  if (heading) heading.focus();

  if (name === 'jobs') loadJobPostings();
  if (name === 'kb') loadStatus();
}

/* ---------------- shared helpers ---------------- */
const apiUrlInput = document.getElementById('apiUrlInput');
// Opening the files directly uses the original local API. When the dashboard
// is served by Docker, use nginx's same-origin /api proxy so the API
// container never needs to expose a host port.
const defaultApiBase = window.location.protocol === 'file:'
  ? apiUrlInput.dataset.fileApiUrl
  : window.location.origin;
apiUrlInput.value = defaultApiBase;
let apiBase = apiUrlInput.value.replace(/\/$/, '');
let currentJob = null;
let currentMatchReport = '';
let currentJobSaved = false; // whether currentJob exists in data/job_postings/ — decided by match confidence

apiUrlInput.addEventListener('change', (e) => {
  apiBase = e.target.value.replace(/\/$/, '');
  checkHealth();
});

function setMsg(id, text, kind) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'inline-msg' + (kind ? ' ' + kind : '');
  el.classList.toggle('hidden', !text);
  // aria-live="polite" is set in the HTML for all of these; for errors we
  // additionally set role="alert", which implies assertive announcement —
  // a screen reader user shouldn't have to be already focused on this
  // element to hear that something went wrong.
  if (kind === 'error') {
    el.setAttribute('role', 'alert');
  } else {
    el.removeAttribute('role');
  }
}

function friendlyError(e) {
  const msg = String(e && e.message || e);
  if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('Load failed')) {
    return `Couldn't reach the API at ${apiBase}. Make sure it's running (uvicorn src.api:app --reload --port 8000) and try again.`;
  }
  return msg;
}

async function safeJson(res) {
  try { return await res.json(); } catch { return null; }
}

async function apiFetch(path, options) {
  const res = await fetch(apiBase + path, options);
  if (!res.ok) {
    const err = await safeJson(res);
    throw new Error(err && err.detail ? err.detail : `Request failed (${res.status})`);
  }
  return res.json();
}

async function checkHealth() {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('statusText');
  try {
    await apiFetch('/api/health');
    dot.className = 'dot on';
    text.textContent = 'Connected';
  } catch {
    dot.className = 'dot off';
    text.textContent = 'Not connected';
  }
}
checkHealth();
setInterval(checkHealth, 10000);

/* ---------------- Match tab ---------------- */
async function findMatch() {
  const jobInputEl = document.getElementById('jobInput');
  const source = jobInputEl.value.trim();
  if (!source) {
    setMsg('matchMsg', 'Paste a job description or URL first.', 'error');
    jobInputEl.setAttribute('aria-invalid', 'true');
    return;
  }
  jobInputEl.removeAttribute('aria-invalid');
  const btn = document.getElementById('matchBtn');
  btn.disabled = true;
  btn.textContent = 'Finding match…';
  setMatchLoading();
  setMsg('matchMsg', 'Looking for a match — this can take a little while on local hardware…', 'loading');

  try {
    const data = await apiFetch('/api/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_source: source }),
    });
    currentJob = data.job;
    currentMatchReport = data.match_report;
    renderMatch(data);
    setMsg('matchMsg', '', null);
  } catch (e) {
    setMsg('matchMsg', friendlyError(e), 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Find match';
  }
}

async function matchSavedJob(job) {
  switchTab('match');
  document.getElementById('jobInput').value = job.raw_description || '';
  const btn = document.getElementById('matchBtn');
  btn.disabled = true;
  btn.textContent = 'Finding match…';
  setMatchLoading();
  setMsg('matchMsg', 'Re-matching this saved posting…', 'loading');
  try {
    const data = await apiFetch('/api/match', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job }),
    });
    currentJob = data.job;
    currentMatchReport = data.match_report;
    renderMatch(data);
    setMsg('matchMsg', '', null);
  } catch (e) {
    setMsg('matchMsg', friendlyError(e), 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Find match';
  }
}

function setMatchLoading() {
  const section = document.getElementById('matchSection');
  const report = document.getElementById('reportText');
  section.classList.remove('hidden');
  report.classList.add('is-loading');
  report.setAttribute('aria-live', 'polite');
  report.innerHTML = '<span class="match-loader" aria-label="Finding match"></span>';
}

function renderMatch(data) {
  document.getElementById('matchSection').classList.remove('hidden');
  document.getElementById('jobTitle').textContent = data.job.title || 'Untitled role';
  document.getElementById('jobCompany').textContent = data.job.company || 'Unknown company';
  const report = document.getElementById('reportText');
  report.classList.remove('is-loading');
  report.removeAttribute('aria-live');
  report.textContent = data.match_report;
  currentJobSaved = !!data.saved;

  const badge = document.getElementById('confidenceBadge');
  const c = data.confidence;
  badge.textContent = `Match confidence: ${c}/100`;
  badge.className = 'badge ' + (c >= 70 ? 'good' : c >= 50 ? 'mid' : 'low');

  const banner = document.getElementById('cautionBanner');
  if (data.below_threshold) {
    banner.textContent = `Confidence is below the usual threshold (${data.confidence_threshold}/100), so this job wasn't saved to your Job Postings board. You can still generate a resume or cover letter below for a second opinion, but it won't be attached to a saved posting.`;
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
  }

  document.getElementById('resumeBtn').disabled = false;
  document.getElementById('coverBtn').disabled = false;
  ['resumeResult','coverResult'].forEach(id => document.getElementById(id).classList.add('hidden'));
  ['resumeActions','coverActions'].forEach(id => document.getElementById(id).classList.add('hidden'));

  buildMatchMaps(data.match_report).catch(() => {
    document.getElementById('skillsMap').innerHTML = '<p class="map-caption">Could not build the map.</p>';
    document.getElementById('experienceMap').innerHTML = '<p class="map-caption">Could not build the map.</p>';
  });
}

async function generateResume() {
  await generateArtifact({
    endpoint: '/api/resume', btnId: 'resumeBtn', msgId: 'resumeMsg',
    resultId: 'resumeResult', actionsId: 'resumeActions',
    loadingLabel: 'Generating resume…', idleLabel: 'Generate resume', responseKey: 'resume',
    patchField: 'resume_text',
  });
}

async function generateCoverLetter() {
  await generateArtifact({
    endpoint: '/api/cover-letter', btnId: 'coverBtn', msgId: 'coverMsg',
    resultId: 'coverResult', actionsId: 'coverActions',
    loadingLabel: 'Generating cover letter…', idleLabel: 'Generate cover letter', responseKey: 'cover_letter',
    patchField: 'cover_letter_text',
  });
}

async function generateArtifact(cfg) {
  if (!currentJob) return;
  const btn = document.getElementById(cfg.btnId);
  btn.disabled = true;
  btn.textContent = cfg.loadingLabel;
  setMsg(cfg.msgId, 'This can take a while on local hardware — please wait…', 'loading');
  document.getElementById(cfg.resultId).classList.add('hidden');
  document.getElementById(cfg.actionsId).classList.add('hidden');

  try {
    const data = await apiFetch(cfg.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job: currentJob, match_report: currentMatchReport }),
    });
    const resultEl = document.getElementById(cfg.resultId);
    resultEl.textContent = data[cfg.responseKey];
    resultEl.classList.remove('hidden');
    document.getElementById(cfg.actionsId).classList.remove('hidden');
    setMsg(cfg.msgId, '', null);

    // Persist onto the saved job posting so its Kanban card's detail view
    // shows this later. Skipped entirely for a match that wasn't saved
    // (below confidence threshold) — there's no posting record to attach it to.
    if (currentJobSaved && currentJob && currentJob.id) {
      try {
        await apiFetch(`/api/job-postings/${encodeURIComponent(currentJob.id)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [cfg.patchField]: data[cfg.responseKey] }),
        });
      } catch {
        // Non-fatal: the result is still shown above; it just won't be
        // saved onto the Kanban card. Don't block the UI on this.
      }
    }
  } catch (e) {
    setMsg(cfg.msgId, friendlyError(e), 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = cfg.idleLabel;
  }
}

function copyResult(id, btn) {
  const text = document.getElementById(id).textContent;
  const original = btn.textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied';
    setTimeout(() => { btn.textContent = original; }, 1500);
  }).catch(() => {
    btn.textContent = 'Select text to copy';
    setTimeout(() => { btn.textContent = original; }, 2000);
  });
}

/* ---------------- Match maps (skills / experience scatter charts) ---------------- */
let profileDataCache = null;

async function ensureProfileData() {
  if (!profileDataCache) {
    profileDataCache = await apiFetch('/api/profile-data');
  }
  return profileDataCache;
}

function splitReportSections(report) {
  const headerRe = /(strong matches|partial matches|gaps)\s*:?\s*/gi;
  const found = [...report.matchAll(headerRe)];
  const sections = { strong: '', partial: '', gap: '' };
  for (let i = 0; i < found.length; i++) {
    const label = found[i][1].toLowerCase();
    const start = found[i].index + found[i][0].length;
    const end = i + 1 < found.length ? found[i + 1].index : report.length;
    const text = report.slice(start, end).trim();
    if (label.startsWith('strong')) sections.strong = text;
    else if (label.startsWith('partial')) sections.partial = text;
    else if (label.startsWith('gap')) sections.gap = text;
  }
  return sections;
}

function extractItems(sectionText) {
  if (!sectionText) return [];
  const lines = sectionText.split(/\n+/).map(l => l.trim()).filter(Boolean);
  const bulletLines = lines.filter(l => /^[-*•]|^\d+[.)]/.test(l));
  let raw;
  if (bulletLines.length >= 1) {
    raw = bulletLines.map(l => l.replace(/^[-*•]\s*|^\d+[.)]\s*/, ''));
  } else {
    raw = sectionText.split(/[,;]|\.\s+(?=[A-Z])/).map(s => s.trim());
  }
  return raw.map(s => s.replace(/\.$/, '')).filter(s => s.length >= 3 && s.length <= 140);
}

function nameAliases(name) {
  const aliases = [name];
  const m = /\(([^)]+)\)/.exec(name);
  if (m) aliases.push(m[1]);
  const base = name.replace(/\([^)]*\)/g, '').replace(/\s+/g, ' ').trim();
  if (base && base !== name) aliases.push(base);
  return aliases;
}

function containsPhrase(haystack, needle) {
  if (needle.length < 3) return false;
  const esc = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  try { return new RegExp('\\b' + esc + '\\b', 'i').test(haystack); }
  catch { return haystack.toLowerCase().includes(needle.toLowerCase()); }
}

function classifyItem(itemText, profile) {
  for (const s of profile.skills) {
    for (const alias of nameAliases(s.name)) {
      if (containsPhrase(itemText, alias)) return { type: 'skill', label: s.name };
    }
  }
  for (const e of profile.experience) {
    if (containsPhrase(itemText, e.company)) return { type: 'experience', label: `${e.title} — ${e.company}` };
    for (const alias of nameAliases(e.title)) {
      if (alias.length > 4 && containsPhrase(itemText, alias)) return { type: 'experience', label: `${e.title} — ${e.company}` };
    }
  }
  return { type: 'unclassified', label: itemText };
}

async function buildMatchMaps(report) {
  const profile = await ensureProfileData();
  const sections = splitReportSections(report);
  const buckets = { skill: { strong: [], partial: [], gap: [] }, experience: { strong: [], partial: [], gap: [] } };

  ['strong', 'partial', 'gap'].forEach((sectionKey) => {
    extractItems(sections[sectionKey]).forEach((item) => {
      const { type, label } = classifyItem(item, profile);
      if (type === 'skill') buckets.skill[sectionKey].push(label);
      else if (type === 'experience') buckets.experience[sectionKey].push(label);
    });
  });

  renderScatterChart('skillsMap', buckets.skill, 'Skills match map');
  renderScatterChart('experienceMap', buckets.experience, 'Experience match map');
}

function escapeXml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderScatterChart(containerId, itemsBySection, chartLabel) {
  const width = 420, height = 190, bandWidth = width / 3;
  const columns = [
    { key: 'strong', label: 'Strong', color: '#16a34a', x0: 0 },
    { key: 'partial', label: 'Partial', color: '#d97706', x0: bandWidth },
    { key: 'gap', label: 'Gaps', color: '#dc2626', x0: bandWidth * 2 },
  ];
  let total = 0;
  let svg = `<svg viewBox="0 0 ${width} ${height + 26}" role="img" aria-label="${escapeXml(chartLabel)}">`;
  columns.forEach((col) => {
    const items = itemsBySection[col.key] || [];
    total += items.length;
    const cx = col.x0 + bandWidth / 2;
    if (col.x0 > 0) svg += `<line x1="${col.x0}" y1="0" x2="${col.x0}" y2="${height}" stroke="currentColor" stroke-opacity="0.12"/>`;
    svg += `<text x="${cx}" y="${height + 18}" text-anchor="middle" font-size="11" fill="currentColor" fill-opacity="0.55">${col.label} (${items.length})</text>`;
    const n = items.length;
    items.forEach((label, i) => {
      const ySpacing = height / (n + 1);
      const jitterX = (pseudoRandom(label + i) - 0.5) * (bandWidth * 0.55);
      const jitterY = (pseudoRandom(i + label) - 0.5) * (ySpacing * 0.4);
      const x = cx + jitterX;
      const y = ySpacing * (i + 1) + jitterY;
      svg += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6.5" fill="${col.color}" fill-opacity="0.82" stroke="${col.color}" stroke-width="1.2"><title>${escapeXml(label)}</title></circle>`;
    });
  });
  svg += `</svg>`;

  const container = document.getElementById(containerId);
  if (total === 0) {
    container.innerHTML = '<p class="map-caption">No clearly categorized items found in the report for this map.</p>';
    return;
  }

  // The SVG's dots are only reachable by hovering, which excludes screen
  // reader and motor-impaired users entirely — this table carries the
  // same strong/partial/gap categorization as real, non-visual content.
  let table = `<table class="sr-only"><caption>${escapeXml(chartLabel)}</caption><thead><tr><th>Category</th><th>Item</th></tr></thead><tbody>`;
  columns.forEach((col) => {
    const items = itemsBySection[col.key] || [];
    items.forEach((label) => {
      table += `<tr><td>${escapeXml(col.label)}</td><td>${escapeXml(label)}</td></tr>`;
    });
  });
  table += `</tbody></table>`;

  container.innerHTML = svg + table;
}

// Deterministic pseudo-random in [0,1) from a string seed, so re-rendering
// the same match doesn't jitter the dots to a new position each time.
function pseudoRandom(seed) {
  let h = 0;
  const s = String(seed);
  for (let i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) >>> 0; }
  return (h % 1000) / 1000;
}

/* ---------------- Ask tab ---------------- */
let lastAskContext = '';
let lastAskAnswerRaw = '';

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inlineFormat(s) {
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/`([^`]+?)`/g, '<code>$1</code>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  s = s.replace(/_(.+?)_/g, '<em>$1</em>');
  return s;
}

function renderBlockLines(lines) {
  const out = [];
  let i = 0;
  while (i < lines.length) {
    if (/^[-*•]\s+/.test(lines[i])) {
      const items = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i])) {
        items.push(`<li>${inlineFormat(lines[i].replace(/^[-*•]\s+/, ''))}</li>`);
        i++;
      }
      out.push('<ul>' + items.join('') + '</ul>');
    } else if (/^\d+[.)]\s+/.test(lines[i])) {
      const items = [];
      while (i < lines.length && /^\d+[.)]\s+/.test(lines[i])) {
        items.push(`<li>${inlineFormat(lines[i].replace(/^\d+[.)]\s+/, ''))}</li>`);
        i++;
      }
      out.push('<ol>' + items.join('') + '</ol>');
    } else {
      const paraLines = [];
      while (i < lines.length && !/^[-*•]\s+/.test(lines[i]) && !/^\d+[.)]\s+/.test(lines[i])) {
        paraLines.push(lines[i]);
        i++;
      }
      out.push(`<p>${paraLines.map(inlineFormat).join('<br>')}</p>`);
    }
  }
  return out.join('');
}

// Minimal, safe markdown -> HTML: paragraphs, single-newline line breaks,
// bold/italic/code, and bullet/numbered lists — including a lead-in line
// immediately followed by list items with no blank line between them
// (a common real-world LLM output pattern). Escapes HTML first so any
// literal <, >, & in the answer can't break the page or inject markup.
function markdownToHtml(text) {
  const blocks = escapeHtml(text).trim().split(/\n\s*\n/);
  return blocks.map((block) => {
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
    return lines.length ? renderBlockLines(lines) : '';
  }).join('');
}

async function askQuestion() {
  const askInputEl = document.getElementById('askInput');
  const query = askInputEl.value.trim();
  if (!query) {
    setMsg('askMsg', 'Type or paste a question first.', 'error');
    askInputEl.setAttribute('aria-invalid', 'true');
    return;
  }
  askInputEl.removeAttribute('aria-invalid');
  const entityType = document.getElementById('askType').value || null;
  const btn = document.getElementById('askBtn');
  btn.disabled = true;
  btn.textContent = 'Asking…';
  setMsg('askMsg', 'Retrieving and answering — please wait…', 'loading');
  document.getElementById('askPanel').classList.add('hidden');
  document.getElementById('askContext').classList.add('hidden');

  try {
    const data = await apiFetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, entity_type: entityType }),
    });
    document.getElementById('askAnswer').innerHTML = markdownToHtml(data.answer);
    lastAskAnswerRaw = data.answer;
    lastAskContext = data.context || '';
    document.getElementById('askPanel').classList.remove('hidden');
    document.getElementById('askContextToggle').textContent = 'Show retrieved context';
    setMsg('askMsg', '', null);
  } catch (e) {
    setMsg('askMsg', friendlyError(e), 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Ask';
  }
}

function copyAskAnswer(btn) {
  const original = btn.textContent;
  navigator.clipboard.writeText(lastAskAnswerRaw).then(() => {
    btn.textContent = 'Copied';
    setTimeout(() => { btn.textContent = original; }, 1500);
  }).catch(() => {
    btn.textContent = 'Select text to copy';
    setTimeout(() => { btn.textContent = original; }, 2000);
  });
}

function toggleAskContext() {
  const el = document.getElementById('askContext');
  const btn = document.getElementById('askContextToggle');
  const showing = !el.classList.contains('hidden');
  if (showing) {
    el.classList.add('hidden');
    btn.textContent = 'Show retrieved context';
  } else {
    el.textContent = lastAskContext;
    el.classList.remove('hidden');
    btn.textContent = 'Hide retrieved context';
  }
}

/* ---------------- Job postings tab (Kanban board) ---------------- */
const KANBAN_STATUSES = [
  { key: 'saved', label: 'Saved' },
  { key: 'application_sent', label: 'Application Sent / Waiting' },
  { key: 'initial_interview', label: 'Initial Interview' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'failed', label: 'Failed' },
];
const KANBAN_STATUS_KEYS = KANBAN_STATUSES.map(s => s.key);

let jobPostingsCache = [];
let currentModalJobId = null;

function normalizeStatus(status) {
  return KANBAN_STATUS_KEYS.includes(status) ? status : 'saved';
}

function statusLabel(key) {
  const found = KANBAN_STATUSES.find(s => s.key === key);
  return found ? found.label : key;
}

async function updateJobStatus(jobId, newStatus) {
  const job = jobPostingsCache.find(j => j.id === jobId);
  if (!job || normalizeStatus(job.status) === newStatus) return;

  const previousStatus = job.status;
  job.status = newStatus; // optimistic UI update
  renderKanbanBoard(jobPostingsCache);
  if (currentModalJobId === jobId) {
    document.getElementById('modalStatusSelect').value = newStatus;
  }

  try {
    await apiFetch(`/api/job-postings/${encodeURIComponent(jobId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus }),
    });
  } catch (err) {
    job.status = previousStatus; // roll back on failure
    renderKanbanBoard(jobPostingsCache);
    if (currentModalJobId === jobId) {
      document.getElementById('modalStatusSelect').value = normalizeStatus(previousStatus);
    }
    setMsg('jobsMsg', friendlyError(err), 'error');
  }
}

async function loadJobPostings() {
  setMsg('jobsMsg', 'Loading…', 'loading');
  try {
    const data = await apiFetch('/api/job-postings');
    jobPostingsCache = data.postings || [];
    renderKanbanBoard(jobPostingsCache);
    setMsg('jobsMsg', '', null);
  } catch (e) {
    setMsg('jobsMsg', friendlyError(e), 'error');
  }
}

function elFromHtml(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstChild;
}

function renderKanbanBoard(postings) {
  const board = document.getElementById('kanbanBoard');
  board.innerHTML = '';

  const countEl = document.getElementById('jobsCount');
  countEl.textContent = String(postings.length);
  countEl.classList.toggle('hidden', postings.length === 0);

  if (postings.length === 0) {
    board.appendChild(elFromHtml('<div class="empty-state">No saved job postings yet — a match needs to score high enough confidence to be saved here. Run one from the Match tab.</div>'));
    return;
  }

  KANBAN_STATUSES.forEach(({ key, label }) => {
    const columnPostings = postings.filter(j => normalizeStatus(j.status) === key);

    const column = document.createElement('div');
    column.className = 'kanban-column glass';
    column.dataset.status = key;
    column.addEventListener('dragover', onColumnDragOver);
    column.addEventListener('dragleave', onColumnDragLeave);
    column.addEventListener('drop', onColumnDrop);

    const header = document.createElement('div');
    header.className = 'kanban-column-header';
    header.innerHTML = '<span></span><span class="count"></span>';
    header.querySelector('span').textContent = label;
    header.querySelector('.count').textContent = String(columnPostings.length);
    column.appendChild(header);

    const cardsWrap = document.createElement('div');
    cardsWrap.className = 'kanban-cards';
    if (columnPostings.length === 0) {
      cardsWrap.appendChild(elFromHtml('<div class="kanban-empty">No jobs here</div>'));
    } else {
      columnPostings.forEach(job => cardsWrap.appendChild(buildKanbanCard(job)));
    }
    column.appendChild(cardsWrap);

    board.appendChild(column);
  });
}

function buildKanbanCard(job) {
  const card = document.createElement('div');
  card.className = 'kanban-card';
  card.draggable = true;
  card.dataset.jobId = job.id;
  card.tabIndex = 0;
  card.setAttribute('role', 'button');

  const conf = job.last_match_confidence;
  const confClass = conf == null ? '' : (conf >= 70 ? 'good' : conf >= 50 ? 'mid' : 'low');
  const statusLbl = statusLabel(normalizeStatus(job.status));

  card.setAttribute('aria-label',
    `${job.title || 'Untitled role'} at ${job.company || 'Unknown company'}, status: ${statusLbl}` +
    (conf != null ? `, match confidence ${conf} of 100` : '') +
    '. Press Enter to view details.');

  card.innerHTML = `
    <div class="title"></div>
    <div class="company"></div>
    <div class="meta-row">
      <span class="date"></span>
      <span class="badge conf-badge"></span>
    </div>
  `;
  card.querySelector('.title').textContent = job.title || 'Untitled role';
  card.querySelector('.company').textContent = job.company || 'Unknown company';
  card.querySelector('.date').textContent = job.date_saved || '';
  const badge = card.querySelector('.conf-badge');
  if (conf == null) {
    badge.remove();
  } else {
    badge.textContent = `${conf}/100`;
    badge.classList.add(confClass);
  }

  // Per-card status control: a real, always-reachable alternative to
  // dragging — needed for keyboard users, and for anyone who finds drag
  // interactions error-prone (WCAG 2.5.7 requires a non-drag path; the
  // modal's dropdown alone doesn't count if the card itself can't be
  // reached without a mouse).
  const statusSelect = document.createElement('select');
  statusSelect.className = 'kanban-card-status';
  statusSelect.setAttribute('aria-label', `Change status for ${job.title || 'this job'}`);
  statusSelect.innerHTML = KANBAN_STATUSES.map(s => `<option value="${s.key}">${s.label}</option>`).join('');
  statusSelect.value = normalizeStatus(job.status);
  statusSelect.addEventListener('click', (e) => e.stopPropagation());
  statusSelect.addEventListener('keydown', (e) => e.stopPropagation());
  statusSelect.addEventListener('change', (e) => {
    e.stopPropagation();
    updateJobStatus(job.id, statusSelect.value);
  });
  card.appendChild(statusSelect);

  card.addEventListener('dragstart', (e) => {
    card.classList.add('dragging');
    e.dataTransfer.setData('text/plain', job.id);
    e.dataTransfer.effectAllowed = 'move';
  });
  card.addEventListener('dragend', () => card.classList.remove('dragging'));
  card.addEventListener('click', () => openJobModal(job.id, card));
  card.addEventListener('keydown', (e) => {
    if (e.target !== card) return; // let the status select handle its own keys
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      openJobModal(job.id, card);
    }
  });

  return card;
}

function onColumnDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('drag-over');
}
function onColumnDragLeave(e) {
  e.currentTarget.classList.remove('drag-over');
}

async function onColumnDrop(e) {
  e.preventDefault();
  const column = e.currentTarget;
  column.classList.remove('drag-over');
  const jobId = e.dataTransfer.getData('text/plain');
  await updateJobStatus(jobId, column.dataset.status);
}

let modalTriggerElement = null;
let modalKeydownHandler = null;

function getFocusableInModal() {
  const modal = document.getElementById('jobModal');
  const selector = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';
  return Array.from(modal.querySelectorAll(selector)).filter(el => !el.disabled);
}

function openJobModal(jobId, triggerEl) {
  const job = jobPostingsCache.find(j => j.id === jobId);
  if (!job) return;
  currentModalJobId = jobId;
  modalTriggerElement = triggerEl || document.activeElement;

  document.getElementById('modalJobTitle').textContent = job.title || 'Untitled role';
  document.getElementById('modalJobCompany').textContent = job.company || 'Unknown company';

  const select = document.getElementById('modalStatusSelect');
  select.innerHTML = KANBAN_STATUSES.map(s => `<option value="${s.key}">${s.label}</option>`).join('');
  select.value = normalizeStatus(job.status);

  fillModalTextField('modalResumeText', 'modalResumeActions', job.resume_text);
  fillModalTextField('modalCoverText', 'modalCoverActions', job.cover_letter_text);

  document.getElementById('jobModalBackdrop').classList.remove('hidden');

  // Focus management: move focus into the dialog (2.4.3 Focus Order),
  // trap Tab within it while open, and close on Escape — all required
  // for a modal to be usable by keyboard/screen reader users at all.
  document.getElementById('modalJobTitle').focus();

  modalKeydownHandler = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeJobModal();
      return;
    }
    if (e.key === 'Tab') {
      const focusable = getFocusableInModal();
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };
  document.addEventListener('keydown', modalKeydownHandler);
}

function fillModalTextField(textId, actionsId, value) {
  const el = document.getElementById(textId);
  const actions = document.getElementById(actionsId);
  if (value) {
    el.textContent = value;
    actions.classList.remove('hidden');
  } else {
    el.textContent = 'Not generated yet for this job.';
    actions.classList.add('hidden');
  }
}

function closeJobModal() {
  document.getElementById('jobModalBackdrop').classList.add('hidden');
  currentModalJobId = null;
  if (modalKeydownHandler) {
    document.removeEventListener('keydown', modalKeydownHandler);
    modalKeydownHandler = null;
  }
  // Return focus to whatever opened the modal — without this, a keyboard
  // user's focus silently drops to the top of the page (2.4.3).
  if (modalTriggerElement && typeof modalTriggerElement.focus === 'function') {
    modalTriggerElement.focus();
  }
  modalTriggerElement = null;
}

function closeJobModalIfBackdrop(e) {
  if (e.target.id === 'jobModalBackdrop') closeJobModal();
}

async function onModalStatusChange() {
  if (!currentModalJobId) return;
  const newStatus = document.getElementById('modalStatusSelect').value;
  await updateJobStatus(currentModalJobId, newStatus);
}

function goToMatchTabForModalJob() {
  const job = jobPostingsCache.find(j => j.id === currentModalJobId);
  closeJobModal();
  if (job) matchSavedJob(job);
}

/* ---------------- Knowledge base tab ---------------- */
async function loadStatus() {
  setMsg('kbMsg', 'Loading…', 'loading');
  try {
    const data = await apiFetch('/api/status');
    renderStats(data.indexed || {});
    setMsg('kbMsg', '', null);
  } catch (e) {
    setMsg('kbMsg', friendlyError(e), 'error');
  }
}

function renderStats(indexed) {
  const grid = document.getElementById('statGrid');
  grid.innerHTML = '';
  const entries = Object.entries(indexed);
  if (entries.length === 0) {
    grid.appendChild(elFromHtml('<div class="empty-state">Nothing indexed yet — click "Re-index now" below.</div>'));
    return;
  }
  entries.forEach(([type, count]) => {
    const card = document.createElement('div');
    card.className = 'stat-card glass';
    card.innerHTML = `<div class="num"></div><div class="label"></div>`;
    card.querySelector('.num').textContent = count;
    card.querySelector('.label').textContent = type.replace(/_/g, ' ') + (count === 1 ? '' : 's');
    grid.appendChild(card);
  });
}

async function runIngest() {
  const btn = document.getElementById('ingestBtn');
  btn.disabled = true;
  btn.textContent = 'Re-indexing…';
  setMsg('kbMsg', "This only affects the Ask tab — match/resume/cover-letter don't need it. Please wait…", 'loading');
  try {
    const data = await apiFetch('/api/ingest', { method: 'POST' });
    renderStats(data.indexed || {});
    const s = data.stats || {};
    setMsg('kbMsg', `Done — added ${s.added||0}, updated ${s.updated||0}, unchanged ${s.unchanged||0}, deleted ${s.deleted||0}.`, null);
  } catch (e) {
    setMsg('kbMsg', friendlyError(e), 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Re-index now';
  }
}
