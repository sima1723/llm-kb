/* ═══════════════════════════════════════════════════════════
   LLM 知识库 — 前端主逻辑
   架构：无框架 Vanilla JS，d3-force 图谱，marked.js 渲染
   ═══════════════════════════════════════════════════════════ */

'use strict';

// ── 全局状态 ──────────────────────────────────────────────────
const state = {
  graphData: { nodes: [], edges: [] },
  simulation: null,
  selectedNode: null,
  sidebarMode: null,   // 'entry' | 'search' | 'ask'
  compileRunning: false,
  statusPollTimer: null,
};

// ── API 工具 ──────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api' + path, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}
const GET  = (path)        => api('GET',  path);
const POST = (path, body)  => api('POST', path, body);

// ── 入口 ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await checkSetup();
  bindUI();
  await loadGraph();
  startStatusPoll();
});

// ── 首次配置检测 ──────────────────────────────────────────────
async function checkSetup() {
  try {
    const cfg = await GET('/config');
    if (!cfg.api_key_set) showSetupOverlay();
    else loadSettingsIntoDrawer(cfg);
  } catch (e) {
    showSetupOverlay();
  }
}

function showSetupOverlay() {
  document.getElementById('setup-overlay').style.display = 'flex';
}

document.getElementById('btn-test-key').addEventListener('click', async () => {
  const key = document.getElementById('setup-api-key').value.trim();
  const baseUrl = document.getElementById('setup-base-url').value.trim();
  const resultEl = document.getElementById('test-result');
  if (!key) { resultEl.textContent = '请输入 API Key'; resultEl.className = 'err'; return; }

  resultEl.textContent = '连接中…';
  resultEl.className = '';

  try {
    await POST('/config', { api_key: key, base_url: baseUrl });
    const r = await POST('/config/test', {});
    if (r.ok) {
      resultEl.textContent = `✓ 连接成功 — ${r.model}（${r.latency_ms}ms）`;
      resultEl.className = 'ok';
      setTimeout(() => {
        document.getElementById('setup-overlay').style.display = 'none';
        loadSettingsIntoDrawer({ model: r.model });
        loadGraph();
        startStatusPoll();
      }, 800);
    } else {
      resultEl.textContent = '✗ ' + (r.error || '连接失败');
      resultEl.className = 'err';
    }
  } catch (e) {
    resultEl.textContent = '✗ ' + e.message;
    resultEl.className = 'err';
  }
});

// ── 绑定 UI 事件 ──────────────────────────────────────────────
function bindUI() {
  // 搜索框
  const searchInput = document.getElementById('search-input');
  const modeBadge   = document.getElementById('search-mode-badge');
  let searchTimer;
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    modeBadge.textContent = q.length > 15 ? '问答' : 'TF-IDF';
    clearTimeout(searchTimer);
    if (!q) { closeSidebar(); return; }
    searchTimer = setTimeout(() => doSearch(q), 350);
  });
  searchInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { clearTimeout(searchTimer); doSearch(searchInput.value.trim()); }
  });

  // 添加内容抽屉
  document.getElementById('btn-add').addEventListener('click', () => openDrawer('ingest'));
  document.getElementById('ingest-close').addEventListener('click', () => closeDrawers());

  // 设置抽屉
  document.getElementById('btn-settings').addEventListener('click', () => openDrawer('settings'));
  document.getElementById('settings-close').addEventListener('click', () => closeDrawers());
  document.getElementById('btn-save-settings').addEventListener('click', saveSettings);

  // 侧边栏关闭
  document.getElementById('sidebar-close').addEventListener('click', closeSidebar);

  // 抽屉内 Tabs
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const name = tab.dataset.tab;
      document.getElementById('tab-url').style.display = name === 'url' ? '' : 'none';
      document.getElementById('tab-pdf').style.display = name === 'pdf' ? '' : 'none';
    });
  });

  // URL 抓取
  document.getElementById('btn-clip').addEventListener('click', doClip);

  // PDF 上传
  const dropZone = document.getElementById('drop-zone');
  const pdfInput = document.getElementById('pdf-input');
  dropZone.addEventListener('click', () => pdfInput.click());
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('dragover');
    uploadPDFs(e.dataTransfer.files);
  });
  pdfInput.addEventListener('change', () => uploadPDFs(pdfInput.files));

  // 背景遮罩
  document.getElementById('backdrop').addEventListener('click', closeDrawers);
}

// ── 搜索 / 问答 ───────────────────────────────────────────────
async function doSearch(q) {
  if (!q) return;
  const isQuestion = q.length > 15;
  if (isQuestion) {
    showSidebar('ask', '思考中…');
    try {
      const r = await POST('/ask', { question: q, save: true, deep: false });
      renderAskResult(q, r);
    } catch (e) {
      document.getElementById('sidebar-body').innerHTML =
        `<p style="color:var(--red)">错误：${e.message}</p>`;
    }
  } else {
    showSidebar('search', '搜索中…');
    try {
      const r = await GET(`/search?q=${encodeURIComponent(q)}&mode=tfidf&top=8`);
      renderSearchResults(r);
    } catch (e) {
      document.getElementById('sidebar-body').innerHTML =
        `<p style="color:var(--red)">错误：${e.message}</p>`;
    }
  }
}

function renderSearchResults(r) {
  const body = document.getElementById('sidebar-body');
  document.getElementById('sidebar-title').textContent = `搜索结果（${r.results.length}）`;
  if (!r.results.length) {
    body.innerHTML = '<p style="color:var(--text2);padding-top:12px">未找到匹配条目</p>';
    return;
  }
  body.innerHTML = r.results.map(res => `
    <div class="search-result" onclick="loadEntry('${esc(res.filename.replace('.md',''))}')">
      <div class="result-title">${esc(res.title)}</div>
      <div class="result-snippet">${esc(res.snippet)}</div>
      <div class="result-score">相关度 ${res.score}</div>
    </div>`).join('');
}

function renderAskResult(question, r) {
  document.getElementById('sidebar-title').textContent = '知识库问答';
  const sourcesHtml = (r.sources || []).map(s => {
    const name = s.replace('answers/', '').replace('.md', '');
    return `<div class="source-card" onclick="loadEntry('${esc(name)}')">${esc(name)}</div>`;
  }).join('');

  document.getElementById('sidebar-body').innerHTML = `
    <div class="answer-wrap">
      <div class="answer-question">Q: ${esc(question)}</div>
      <div class="answer-body entry-body" id="answer-content"></div>
      ${sourcesHtml ? `<div class="answer-sources"><h4>引用来源</h4>${sourcesHtml}</div>` : ''}
      <div class="answer-cost">花费 $${(r.cost_usd || 0).toFixed(5)}</div>
    </div>`;

  const content = document.getElementById('answer-content');
  content.innerHTML = renderMarkdown(r.answer_md || r.answer_html || '');
  bindWikiLinks(content);
}

// ── 条目阅读 ──────────────────────────────────────────────────
async function loadEntry(name) {
  showSidebar('entry', '加载中…');
  try {
    const entry = await GET(`/wiki/entry/${encodeURIComponent(name)}`);
    renderEntry(entry);
    highlightNode(name);
  } catch (e) {
    document.getElementById('sidebar-body').innerHTML =
      `<p style="color:var(--red)">找不到条目：${esc(name)}</p>`;
  }
}

function renderEntry(entry) {
  document.getElementById('sidebar-title').textContent = entry.name;
  const fm = entry.frontmatter || {};
  const typeLabel = fm.tags?.includes('stub') ? 'stub'
    : fm.source_type === 'answer' ? 'answer' : 'entry';

  const linksHtml = (entry.links || []).map(l =>
    `<span class="link-chip" onclick="loadEntry('${esc(l)}')">${esc(l)}</span>`
  ).join('');
  const backlinksHtml = (entry.backlinks || []).map(l =>
    `<span class="link-chip" onclick="loadEntry('${esc(l)}')">${esc(l)}</span>`
  ).join('');

  const body = document.getElementById('sidebar-body');
  body.innerHTML = `
    <div class="entry-meta">
      <span class="badge ${typeLabel}">${typeLabel}</span>
      ${fm.last_updated ? `<span class="badge" style="border-color:var(--border);color:var(--text2)">${fm.last_updated}</span>` : ''}
    </div>
    <div class="entry-body" id="entry-content"></div>
    ${linksHtml ? `<div class="links-section"><h4>链出</h4><div class="link-chips">${linksHtml}</div></div>` : ''}
    ${backlinksHtml ? `<div class="links-section" style="margin-top:12px"><h4>链入</h4><div class="link-chips">${backlinksHtml}</div></div>` : ''}
  `;

  const content = document.getElementById('entry-content');
  content.innerHTML = renderMarkdown(entry.body_md || '');
  bindWikiLinks(content);
}

function bindWikiLinks(container) {
  container.querySelectorAll('.wiki-link').forEach(el => {
    el.addEventListener('click', () => loadEntry(el.dataset.entry));
  });
}

function renderMarkdown(md) {
  if (!md) return '';
  // [[链接]] → span
  const processed = md.replace(/\[\[(.+?)\]\]/g,
    (_, name) => `<span class="wiki-link" data-entry="${name}">[[${name}]]</span>`);
  if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true });
    return marked.parse(processed);
  }
  return `<pre>${processed}</pre>`;
}

// ── 知识图谱 ──────────────────────────────────────────────────
async function loadGraph() {
  try {
    const data = await GET('/wiki/graph');
    state.graphData = data;
    renderGraph(data);
    const empty = document.getElementById('empty-hint');
    empty.style.display = data.nodes.length === 0 ? 'block' : 'none';
  } catch (e) {
    console.warn('loadGraph error', e);
  }
}

function renderGraph(data) {
  const container = document.getElementById('graph-container');
  const svg = d3.select('#graph-canvas');
  svg.selectAll('*').remove();

  const W = container.clientWidth;
  const H = container.clientHeight;
  svg.attr('width', W).attr('height', H);

  // 颜色映射
  const colorOf = node => {
    if (node.type === 'answer') return '#3fb950';
    if (node.type === 'stub')   return '#484f58';
    return '#58a6ff';
  };

  // 节点大小：基于关联数
  const sizeOf = node => {
    const base = 7;
    const bonus = Math.min((node.cited_count || 0) + (node.link_count || 0), 20);
    return base + bonus * 0.6;
  };

  const g = svg.append('g');

  // 缩放 + 平移
  svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

  // 边
  const link = g.append('g').attr('stroke', '#30363d').attr('stroke-width', 1.2)
    .selectAll('line')
    .data(data.edges)
    .join('line')
    .attr('stroke-opacity', 0.6);

  // 节点
  const node = g.append('g')
    .selectAll('g')
    .data(data.nodes)
    .join('g')
    .attr('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) state.simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => { if (!e.active) state.simulation.alphaTarget(0); d.fx = null; d.fy = null; }))
    .on('click', (e, d) => { e.stopPropagation(); loadEntry(d.id); state.selectedNode = d.id; updateNodeHighlight(); })
    .on('mouseover', (e, d) => showTooltip(e, d))
    .on('mousemove', (e)    => moveTooltip(e))
    .on('mouseout',  ()     => hideTooltip());

  node.append('circle')
    .attr('r', sizeOf)
    .attr('fill', colorOf)
    .attr('fill-opacity', 0.85)
    .attr('stroke', '#161b22')
    .attr('stroke-width', 1.5);

  node.append('text')
    .text(d => d.label.length > 10 ? d.label.slice(0, 9) + '…' : d.label)
    .attr('x', d => sizeOf(d) + 4)
    .attr('y', 4)
    .attr('fill', '#8b949e')
    .attr('font-size', 11)
    .attr('pointer-events', 'none');

  // 力模拟
  state.simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(80).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-180))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide().radius(d => sizeOf(d) + 8))
    .on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

  // 点击空白取消选中
  svg.on('click', () => { closeSidebar(); state.selectedNode = null; });

  state._nodeSelection = node;
}

function highlightNode(name) {
  state.selectedNode = name;
  updateNodeHighlight();
}

function updateNodeHighlight() {
  if (!state._nodeSelection) return;
  state._nodeSelection.select('circle')
    .attr('stroke', d => d.id === state.selectedNode ? '#fff' : '#161b22')
    .attr('stroke-width', d => d.id === state.selectedNode ? 2.5 : 1.5);
}

// ── Tooltip ──────────────────────────────────────────────────
const tooltip = document.getElementById('graph-tooltip');
function showTooltip(e, d) {
  tooltip.querySelector('.tip-name').textContent = d.label;
  tooltip.querySelector('.tip-desc').textContent = d.description || '';
  tooltip.classList.add('visible');
  moveTooltip(e);
}
function moveTooltip(e) {
  tooltip.style.left = (e.clientX + 14) + 'px';
  tooltip.style.top  = (e.clientY - 10) + 'px';
}
function hideTooltip() { tooltip.classList.remove('visible'); }

// ── 侧边栏控制 ───────────────────────────────────────────────
function showSidebar(mode, title) {
  state.sidebarMode = mode;
  document.getElementById('sidebar').classList.remove('collapsed');
  document.getElementById('sidebar-title').textContent = title;
  document.getElementById('sidebar-body').innerHTML =
    '<div style="padding-top:24px;text-align:center"><span class="spinner"></span></div>';
}

function closeSidebar() {
  document.getElementById('sidebar').classList.add('collapsed');
  state.sidebarMode = null;
  state.selectedNode = null;
  updateNodeHighlight();
}

// ── 抽屉控制 ─────────────────────────────────────────────────
function openDrawer(name) {
  closeDrawers();
  document.getElementById(name + '-drawer').classList.add('open');
  document.getElementById('backdrop').classList.add('visible');
}

function closeDrawers() {
  ['ingest', 'settings'].forEach(n => {
    document.getElementById(n + '-drawer').classList.remove('open');
  });
  document.getElementById('backdrop').classList.remove('visible');
}

// ── URL 抓取 ─────────────────────────────────────────────────
async function doClip() {
  const raw = document.getElementById('url-input').value.trim();
  if (!raw) return;
  const urls = raw.split('\n').map(u => u.trim()).filter(Boolean);
  const resultEl = document.getElementById('clip-result');
  const btn = document.getElementById('btn-clip');

  btn.disabled = true;
  btn.textContent = '抓取中…';
  resultEl.style.display = 'none';

  const results = [];
  for (const url of urls) {
    try {
      const r = await POST('/ingest/clip', { url });
      if (r.skipped) results.push(`⚠ 已存在：${url}`);
      else results.push(`✓ ${r.title}（${r.chars} 字符）`);
    } catch (e) {
      results.push(`✗ 失败：${url} — ${e.message}`);
    }
  }

  resultEl.textContent = results.join('\n');
  resultEl.style.display = 'block';
  btn.disabled = false;
  btn.textContent = '抓取并编译';
  document.getElementById('url-input').value = '';

  // 自动触发编译
  await triggerCompile();
}

// ── PDF 上传 ─────────────────────────────────────────────────
async function uploadPDFs(files) {
  const resultEl = document.getElementById('pdf-result');
  const results  = [];
  for (const file of Array.from(files)) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch('/api/ingest/upload', { method: 'POST', body: fd });
      const r = await res.json();
      results.push(`✓ ${r.filename}（${r.chars} 字符）`);
    } catch (e) {
      results.push(`✗ ${file.name}: ${e.message}`);
    }
  }
  resultEl.textContent = results.join('\n');
  resultEl.style.display = 'block';
  await triggerCompile();
}

// ── 编译控制 ─────────────────────────────────────────────────
async function triggerCompile() {
  if (state.compileRunning) return;
  try {
    await POST('/compile', { mode: 'incremental' });
    state.compileRunning = true;
    startSSE();
  } catch (e) {
    console.warn('compile trigger failed', e);
  }
}

function startSSE() {
  const logBox = document.getElementById('compile-log-box');
  logBox.style.display = 'block';
  logBox.innerHTML = '';
  document.getElementById('compile-indicator').style.display = '';

  const es = new EventSource('/api/compile/stream');
  es.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'log') {
      const p = document.createElement('p');
      p.textContent = msg.line;
      p.className = msg.line.includes('✓') ? 'ok' : msg.line.includes('✗') ? 'err' : '';
      logBox.appendChild(p);
      logBox.scrollTop = logBox.scrollHeight;
    } else if (msg.type === 'done') {
      es.close();
      state.compileRunning = false;
      document.getElementById('compile-indicator').style.display = 'none';
      // 重新加载图谱
      setTimeout(() => { loadGraph(); updateStatus(); }, 500);
    }
  };
  es.onerror = () => {
    es.close();
    state.compileRunning = false;
    document.getElementById('compile-indicator').style.display = 'none';
  };
}

// ── 状态栏 ───────────────────────────────────────────────────
function startStatusPoll() {
  updateStatus();
  state.statusPollTimer = setInterval(updateStatus, 8000);
}

async function updateStatus() {
  try {
    const s = await GET('/compile/status');
    document.getElementById('stat-entries').textContent =
      `${(state.graphData.nodes.filter(n => n.type === 'entry').length || 0)} 条目`;
    document.getElementById('stat-answers').textContent =
      `${state.graphData.nodes.filter(n => n.type === 'answer').length || 0} 个答案`;
    document.getElementById('stat-pending').textContent =
      s.files_pending > 0 ? `待编译 ${s.files_pending}` : '已同步';
    document.getElementById('stat-compile').textContent =
      s.last_run ? `上次编译 ${timeAgo(s.last_run)}` : '尚未编译';
    document.getElementById('stat-cost').textContent =
      s.cost_total_usd > 0 ? `累计 $${s.cost_total_usd.toFixed(4)}` : '';

    if (s.running && !state.compileRunning) {
      state.compileRunning = true;
      document.getElementById('compile-indicator').style.display = '';
    } else if (!s.running && state.compileRunning) {
      state.compileRunning = false;
      document.getElementById('compile-indicator').style.display = 'none';
      loadGraph();
    }
  } catch (e) { /* ignore */ }
}

function timeAgo(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff/60)}分钟前`;
  return `${Math.floor(diff/3600)}小时前`;
}

// ── 设置抽屉 ─────────────────────────────────────────────────
async function loadSettingsIntoDrawer(cfg) {
  if (!cfg) {
    cfg = await GET('/config').catch(() => ({}));
  }
  const el = id => document.getElementById(id);
  if (cfg.budget_limit !== undefined) el('s-budget').value = cfg.budget_limit;
  if (cfg.git_auto_commit !== undefined) el('s-git-commit').checked = cfg.git_auto_commit;
  if (cfg.base_url !== undefined) el('s-base-url').value = cfg.base_url;
}

async function saveSettings() {
  const body = {
    budget_limit: parseFloat(document.getElementById('s-budget').value) || 5,
    git_auto_commit: document.getElementById('s-git-commit').checked,
    base_url: document.getElementById('s-base-url').value.trim(),
  };
  const keyInput = document.getElementById('s-api-key').value.trim();
  if (keyInput) body.api_key = keyInput;

  const msg = document.getElementById('settings-msg');
  try {
    await POST('/config', body);
    msg.textContent = '✓ 已保存';
    msg.style.color = 'var(--green)';
  } catch (e) {
    msg.textContent = '✗ ' + e.message;
    msg.style.color = 'var(--red)';
  }
  setTimeout(() => { msg.textContent = ''; }, 2000);
}

// ── 工具函数 ─────────────────────────────────────────────────
function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// 窗口大小变化时重绘图谱
window.addEventListener('resize', () => {
  if (state.graphData.nodes.length > 0) renderGraph(state.graphData);
});
