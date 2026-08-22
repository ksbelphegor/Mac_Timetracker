
/* ═══════════ 공통 ═══════════ */
let selectedDate = todayLocal(); // YYYY-MM-DD (로컬 시간대)

function todayLocal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function fmt(secs) {
  const h = Math.floor(secs / 3600), m = Math.floor((secs%3600)/60), s = Math.floor(secs%60);
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}
function fmtDur(secs) {
  const h = Math.floor(secs / 3600), m = Math.floor((secs%3600)/60), s = Math.floor(secs%60);
  if (h > 0) return `${h}시간 ${m}분 ${s}초`;
  if (m > 0) return `${m}분 ${s}초`;
  return `${s}초`;
}
function fmtTime(ts) {
  return new Date(ts*1000).toLocaleTimeString('ko-KR', {hour:'2-digit',minute:'2-digit'});
}
function fmtTimePrecise(ts) {
  const d = new Date(ts*1000);
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}
function esc(s) {
  const d = document.createElement('div'); d.textContent = s; return d.innerHTML;
}
function escAttr(s) {
  // HTML escape first, then make it safe for onclick='...' attribute value
  // Must handle: \ (backslash first!), ', ", \n, \r
  return esc(s)
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/"/g, '&quot;')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
}
function countNodes(nodes) {
  let c = 0;
  for (const n of nodes) { c += 1; if (n.children) c += countNodes(n.children); }
  return c;
}

/* ═══════════ 날짜 ═══════════ */
function initDatePicker() {
  document.getElementById('date-picker').value = selectedDate;
}

function onDateChange() {
  selectedDate = document.getElementById('date-picker').value;
  expandedTitles = new Set();
  homeSelected = null;
  refreshAll();
}

function changeDate(delta) {
  expandedTitles = new Set();
  homeSelected = null;
  // Parse selectedDate as local date, add delta, re-format as local YYYY-MM-DD
  const parts = selectedDate.split('-').map(Number);
  const d = new Date(parts[0], parts[1] - 1, parts[2]);
  d.setDate(d.getDate() + delta);
  selectedDate = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  document.getElementById('date-picker').value = selectedDate;
  refreshAll();
}

function goToday() {
  expandedTitles = new Set();
  homeSelected = null;
  selectedDate = todayLocal();
  document.getElementById('date-picker').value = selectedDate;
  refreshAll();
}

function refreshAll() {
  pingServer();
  if (document.getElementById('tab-home').classList.contains('active')) loadHome();
  if (document.getElementById('tab-browser').classList.contains('active')) loadBrowserSessions();
  if (document.getElementById('tab-tags').classList.contains('active')) {
    if (window._tagLoaded) refreshTagStats();
    // (미로드 시: 탭 전환 때 loadTags가 담당 — 여기서 return하면
    //  아래 권한 패널 갱신을 건너뛰는 버그 → return 제거)
  }
  if (permPanelOpen) loadPermissions();
}

/* ═══════════ 서버 연결 상태 (DB 없는 초경량 ping) ═══════════ */
function pingServer() {
  const badge = document.getElementById('status-badge');
  if (!badge) return;
  fetch('/api/ping').then(r => {
    badge.innerHTML = r.ok
      ? `<span class="status-dot status-on"></span>연결됨`
      : `<span class="status-dot status-off"></span>연결 오류`;
  }).catch(() => {
    badge.innerHTML = `<span class="status-dot status-off"></span>연결 오류`;
  });
}

/* ═══════════ 권한 설정 패널 ═══════════ */
let permPanelOpen = false;
function togglePermPanel() {
  permPanelOpen = !permPanelOpen;
  document.getElementById('perm-panel').style.display = permPanelOpen ? 'block' : 'none';
  if (permPanelOpen) loadPermissions();
}

async function loadPermissions() {
  try {
    const r = await fetch('/api/permissions');
    if (!r.ok) return;
    renderPerm(await r.json());
  } catch (e) { /* 서버 중지 상태 */ }
}

function renderPerm(p) {
  const gear = document.getElementById('perm-gear');
  const dot = document.getElementById('perm-dot');
  gear.style.opacity = p.app_found ? 1 : 0.4;
  dot.style.display = p.all_ok ? 'none' : 'inline-block';
  const set = (id, ok) => {
    const el = document.getElementById(id);
    el.textContent = ok ? '✅ 허용됨' : '⚠️ 미부여';
    el.className = ok ? 'perm-state-ok' : 'perm-state-missing';
  };
  set('perm-sr-state', p.screen_recording);
  const srNote = document.getElementById('perm-sr-note');
  if (srNote) srNote.textContent = (p.sr_required === false) ? ' (macOS 26+ 필수 아님)' : '';
  set('perm-ax-state', p.accessibility);
  if (p.checked_at > 0) {
    document.getElementById('perm-updated').textContent =
      '확인 ' + new Date(p.checked_at * 1000).toLocaleTimeString('ko-KR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  }
}

async function permAction(action, which) {
  try {
    await fetch(`/api/permissions?action=${action}&which=${which}`, { method: 'POST' });
  } catch (e) {}
  // prompt은 사용자가 시스템 창에서 처리해야 하므로 넉넉히 기다리고 재확인
  setTimeout(loadPermissions, action === 'prompt' ? 6000 : 1500);
}

function dateParam() {
  return selectedDate !== todayLocal() ? `?target_date=${selectedDate}` : '';
}

/* ═══════════ 탭 전환 ═══════════ */
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-'+name));
  if (name === 'browser') loadBrowserSessions();
  if (name === 'tags') { window._tagLoaded = false; loadTags(); }
}

/* ═══════════ 홈 탭 ═══════════ */
let homeSelected = null;
let sgSortBy = 'end';
let sgSortDir = 'desc';
let expandedTitles = new Set();

function sgId(title) { return 'sg-' + title.replace(/[^a-z0-9가-힣\s_-]/gi, '').slice(0, 60).replace(/\s/g, '_'); }

function sortSG(col) {
  if (sgSortBy === col) sgSortDir = sgSortDir === 'asc' ? 'desc' : 'asc';
  else { sgSortBy = col; sgSortDir = 'desc'; }
  if (homeSelected) loadHomeSessions(homeSelected);
}

function getSGSorter() {
  const { by, dir } = { by: sgSortBy, dir: sgSortDir };
  const mult = dir === 'desc' ? -1 : 1;
  return (a, b) => {
    let va, vb;
    if (by === 'title') { va = a.title; vb = b.title; return va < vb ? -mult : va > vb ? mult : 0; }
    if (by === 'start') { va = a.sessions[0].start; vb = b.sessions[0].start; }
    else if (by === 'end') { va = a.sessions[a.sessions.length-1].end; vb = b.sessions[b.sessions.length-1].end; }
    else { va = a.total; vb = b.total; }
    return (va - vb) * mult;
  };
}

function sortArrow(col) {
  if (sgSortBy !== col) return '';
  return sgSortDir === 'asc' ? ' ▲' : ' ▼';
}

async function loadHome() {
  // in-flight 중복 방지 (setInterval 3s + user click race 방지)
  if (window._homeInFlight) { window._homePending = true; return; }
  window._homeInFlight = true;
  try {
    const res = await fetch('/api/today' + dateParam());
    const data = await res.json();
    document.getElementById('status-badge').innerHTML =
      `<span class="status-dot status-on"></span>연결됨`;

    const listEl = document.getElementById('home-app-list');
    const existing = listEl.children;

    // 구조가 같으면 DOM 갈아엎지 않고 시간만 업데이트 (깜빡임 방지)
    let same = existing.length === data.apps.length;
    if (same) {
      for (let i = 0; i < data.apps.length; i++) {
        const nameEl = existing[i]?.querySelector('.app-item-name');
        if (!nameEl || nameEl.textContent !== data.apps[i].name) {
          same = false;
          break;
        }
      }
    }

    if (same) {
      for (let i = 0; i < data.apps.length; i++) {
        const a = data.apps[i];
        const item = existing[i];
        item.querySelector('.app-item-time').textContent = fmt(a.seconds);
        item.classList.toggle('active', homeSelected === a.name);
      }
    } else {
      listEl.innerHTML = data.apps.map(a =>
        `<div class="app-item ${homeSelected === a.name ? 'active' : ''}"
             onclick="selectHomeApp('${escAttr(a.name)}')">
          <img class="app-icon-img" src="/api/app-icon/${encodeURIComponent(a.name)}"
               alt="" loading="lazy"
               onerror="this.style.display='none'">
          <span class="app-item-name">${esc(a.name)}</span>
          <span class="app-item-time">${fmt(a.seconds)}</span>
        </div>`
      ).join('');
    }

    if (homeSelected) {
      const exists = data.apps.some(a => a.name === homeSelected);
      if (!exists) { homeSelected = null; showHomeEmpty(); }
      else loadHomeSessions(homeSelected);
    }
  } catch(e) {
    document.getElementById('status-badge').innerHTML =
      `<span class="status-dot status-off"></span>연결 오류`;
    console.error('loadHome:', e);
  } finally {
    window._homeInFlight = false;
    if (window._homePending) { window._homePending = false; loadHome(); }
  }
}

function selectHomeApp(name) {
  homeSelected = name;
  document.getElementById('home-content').style.display = 'flex';
  document.getElementById('home-empty').style.display = 'none';
  document.getElementById('home-app-name').textContent = name;
  // 클릭 즉시 active 클래스 적용
  document.querySelectorAll('#home-app-list .app-item').forEach(el => {
    el.classList.toggle('active', el.textContent.trim().startsWith(name));
  });
  loadHomeSessions(name);
}

function showHomeEmpty() {
  homeSelected = null;
  document.getElementById('home-content').style.display = 'none';
  document.getElementById('home-empty').style.display = 'flex';
}

async function loadHomeSessions(name) {
  try {
    const res = await fetch(`/api/sessions/${encodeURIComponent(name)}?target_date=${selectedDate}`);
    const data = await res.json();
    const listEl = document.getElementById('home-sessions');
    let total = 0;

    // 같은 사이트 이름 또는 도메인 기준 그룹핑
    const groups = {};
    for (const s of data.sessions) {
      total += s.duration;
      const key = extractGroupName(s) || '(알 수 없음)';
      // 타이틀 미확정(앱명으로 폴백) 세션은 아예 표시하지 않음 —
      // 앱 목록 행에 총 시간이 이미 있고, 내용도 앱 이름뿐이라 중복
      if (key.toLowerCase() === name.toLowerCase()) continue;
      // '알 수 없음' = 타이틀만 포착(URL 없음) — 앱 목록에 이미 합산된 시간이라 중복
      if (key === '(알 수 없음)') continue;
      if (!groups[key]) groups[key] = { title: key, sessions: [], total: 0 };
      groups[key].sessions.push(s);
      groups[key].total += s.duration;
      // ⚠️ total 재가산 금지 — 루프 상단(278행)에서 전량 세션 1회 합산 완료
      // (이전 버그: 표시 대상 세션만 한 번 더 → 앱 총시간이 ~2배로 부풀림)
    }

    // 그룹핑 + 정렬 + 상위 30개
    const sorter = getSGSorter();
    const sorted = Object.values(groups).sort(sorter).slice(0, 30);

    listEl.innerHTML = `
      <div class="sg-list-header">
        <span class="lh-title lh-btn ${sgSortBy==='title'?'active':''}" onclick="sortSG('title')">사이트${sortArrow('title')}</span>
        <span class="lh-start lh-btn ${sgSortBy==='start'?'active':''}" onclick="sortSG('start')">시작${sortArrow('start')}</span>
        <span class="lh-end lh-btn ${sgSortBy==='end'?'active':''}" onclick="sortSG('end')">종료${sortArrow('end')}</span>
        <span class="lh-dur lh-btn ${sgSortBy==='duration'?'active':''}" onclick="sortSG('duration')">활성화${sortArrow('duration')}</span>
        <span class="lh-spacer"></span>
      </div>
      ${sorted.length === 0 ? '<div style="padding:8px 4px;color:#585e6a;font-size:11px;">타이틀 미확정 기록만 있어 표시할 항목 없음 (보조제어 권한 부여 시 채워짐)</div>' : ''}
      ${sorted.map((g, gi) => {
        const first = g.sessions[0];
        const last = g.sessions[g.sessions.length - 1];
        const durSec = Math.round(g.total);
        const durStr = durSec >= 60 ? `${Math.floor(durSec/60)}분 ${durSec%60}초` : `${durSec}초`;
        const id = sgId(g.title);
        const isOpen = expandedTitles.has(g.title);
        return `<div class="sg-group">
        <div class="sg-header" onclick="toggleSG('${escAttr(g.title)}')">
          <span class="sg-title">${/^(알 수 없음)$/.test(g.title) ? '❓' : '🌐'} ${esc(g.title)}</span>
          <span class="sg-hdr-start">${fmtTimePrecise(first.start)}</span>
          <span class="sg-hdr-end">${fmtTimePrecise(last.end)}</span>
          <span class="sg-hdr-dur">${durStr}</span>
          <span class="sg-arrow" id="arr-${id}">${isOpen?'▼':'▶'}</span>
        </div>
        <div class="sg-body" id="${id}" style="display:${isOpen?'':'none'}">
          <div class="sg-inner-header">
            <span class="ih-spacer" style="flex:1;font-size:10px;color:#585e6a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">페이지</span>
            <span class="ih-start">시작</span>
            <span class="ih-end">종료</span>
            <span class="ih-dur">활성화</span>
            <span class="ih-empty"></span>
          </div>
          ${g.sessions.sort((a, b) => b.end - a.end).map(s => {
            const sDurSec = Math.round(s.duration);
            const sDurStr = sDurSec >= 60 ? `${Math.floor(sDurSec/60)}분 ${sDurSec%60}초` : `${sDurSec}초`;
            return `<div class="sg-item">
              <span class="sg-item-title">📄 ${esc(s.title||'')}</span>
              <span class="sg-item-start">${fmtTimePrecise(s.start)}</span>
              <span class="sg-item-end">${fmtTimePrecise(s.end)}</span>
              <span class="sg-item-dur">${sDurStr}</span>
              <span class="sg-item-arrow"></span>
            </div>`;
          }).join('')}
        </div>
      </div>`;
      }).join('')}
    `;

    document.getElementById('home-total-time').textContent = fmt(total);
  } catch(e) { console.error('loadHomeSessions:', e); }
}

function toggleSG(title) {
  const id = sgId(title);
  const body = document.getElementById(id);
  const arr = document.getElementById('arr-' + id);
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  if (arr) arr.textContent = open ? '▶' : '▼';
  if (open) expandedTitles.delete(title);
  else expandedTitles.add(title);
}

/* ═══════════ 브라우저 탭 ═══════════ */
let browserFilter = '__all__';
let groupBySite = false;

function extractSite(title, app) {
  // 탭 제목에서 사이트명 추출
  // 패턴: "title - site" 또는 "title | site" (마지막 구분자)
  const patterns = [/ \| ([^|]+)$/, / — ([^—]+)$/, / - ([^-]+)$/, / – ([^–]+)$/];
  for (const p of patterns) {
    const m = title.match(p);
    if (m) return m[1].trim();
  }
  // 구분자가 없으면 앱명 반환
  return app;
}
function extractDomain(url) {
  if (!url) return null;
  try {
    let h = new URL(url).hostname.toLowerCase();
    // 서브도메인 정리 (www, m, mobile, page-N, series 등)
    h = h.replace(/^(www|m|mobile|web|blog|mail|page(?:-\d+)?|series|read|board|bbs|cafe|game|news?|shop|docs|support|help|stage|dev|api|login|account|en|ko|ja|zh|cn|jp)\./, '');
    return h;
  }
  catch(e) { return null; }
}

// 자주 쓰는 사이트: 도메인 → 표시용 한글명
const siteNames = {
  'newtoki.com': '뉴토끼', 'newtoki.net': '뉴토끼',
  'newtoki.org': '뉴토끼', 'newtoki1.com': '뉴토끼',
  'newtoki2.com': '뉴토끼', 'newtoki3.com': '뉴토끼',
  'naver.com': '네이버', 'daum.net': '다음', 'kakao.com': '카카오',
  'youtube.com': 'YouTube', 'github.com': 'GitHub',
  'google.com': 'Google', 'twitter.com': 'Twitter',
  'x.com': 'X', 'reddit.com': 'Reddit', 'discord.com': 'Discord',
  'namu.wiki': '나무위키', 'fmkorea.com': '에펨코리아',
  'dcinside.com': '디시인사이드', 'ppomppu.co.kr': '뽐뿌',
  'clien.net': '클리앙', 'ruliweb.com': '루리웹',
  'inven.co.kr': '인벤',
};

function extractGroupName(s) {
  // 1. URL이 있으면 도메인으로 그룹핑 (가장 정확 — YouTube, 에펨코리아 모두 해결)
  if (s.url) {
    const d = extractDomain(s.url);
    if (d) return siteNames[d] || d;
  }
  // 2. URL이 없으면 타이틀 기반 fallback
  //    (AppleScript 실패 등으로 URL 미캡처된 경우)
  let title = s.title || '';
  if (!title) return null;
  const patterns = [
    / [\-–—|] /,           // "title - site"
    /[\-–—]\s*/,            // "title-site"
    /\s*\|+\s*/,            // "title | site"
    / :: /,                 // "title :: site"
    /\s*·\s*/,              // "title · site"
    /\s*◆\s*/,              // "title ◆ site"
  ];
  for (const sep of patterns) {
    const segments = title.split(sep).map(s => s.trim()).filter(Boolean);
    if (segments.length > 1) {
      // 첫 번째 세그먼트 = 사이트명 (에펨코리아, 디시, 네이버 등 한국 커뮤니티)
      // URL 기반이 YouTube 등 국제사이트를 커버하므로,
      // title-only fallback에서는 한국형 패턴(사이트명-first)을 우선
      return segments[0];
    }
  }
  return title;
}

function filterBrowser(app) {
  browserFilter = app;
  document.querySelectorAll('.browser-filter-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.app === app));
  loadBrowserSessions();
}

function toggleSiteGroup() {
  groupBySite = !groupBySite;
  document.getElementById('browser-group-toggle').classList.toggle('active');
  loadBrowserSessions();
}

function expandSite(siteKey) {
  const el = document.getElementById('bs-' + siteKey);
  if (el) el.style.display = el.style.display === 'none' ? '' : 'none';
}

async function loadBrowserSessions() {
  const search = (document.getElementById('browser-search-input').value || '').toLowerCase();
  const statusEl = document.getElementById('browser-status');
  const listEl = document.getElementById('browser-list');
  const filterEl = document.getElementById('browser-filters');
  try {
    const res = await fetch('/api/browser-sessions?target_date=' + selectedDate);
    const data = await res.json();
    let sessions = data.sessions;

    // 브라우저 필터 버튼 생성 (1회)
    if (!filterEl.dataset.initialized) {
      const apps = [...new Set(sessions.map(s => s.app))];
      filterEl.innerHTML =
        `<button class="browser-filter-btn active" data-app="__all__" onclick="filterBrowser('__all__')">전체</button>`
        + apps.map(a => `<button class="browser-filter-btn" data-app="${esc(a)}" onclick="filterBrowser('${esc(a)}')">${esc(a)}</button>`).join('')
        + `<button class="browser-filter-btn" id="browser-group-toggle" onclick="toggleSiteGroup()">📁 사이트별</button>`;
      filterEl.dataset.initialized = '1';
    }

    // 필터
    if (browserFilter !== '__all__') sessions = sessions.filter(s => s.app === browserFilter);
    if (search) sessions = sessions.filter(s => s.title.toLowerCase().includes(search));

    if (groupBySite) {
      // 사이트별 그룹화
      const groups = {};
      for (const s of sessions) {
        const site = extractSite(s.title, s.app);
        // 위와 동일: 사이트명 = 앱 이름(제목 미확정)이면 표시하지 않음
        if (site.toLowerCase() === s.app.toLowerCase()) continue;
        if (!groups[site]) groups[site] = { site, apps: new Set(), total: 0, sessions: [] };
        groups[site].apps.add(s.app);
        groups[site].total += s.duration;
        groups[site].sessions.push(s);
      }
      const sorted = Object.values(groups).sort((a, b) => b.total - a.total);
      statusEl.textContent = `📁 ${sorted.length}개 사이트 · 총 ${sessions.length}개 탭 기록`;
      listEl.innerHTML = sorted.slice(0, 50).map((g, i) => {
        const siteKey = esc(g.site).replace(/\s/g, '_') + i;
        const appsList = [...g.apps].map(a => a.replace(' Browser','')).join(', ');
        return `<div class="browser-group">
          <div class="browser-group-header" onclick="expandSite('${siteKey}')">
            <span class="browser-group-name">📁 ${esc(g.site)}</span>
            <span class="browser-group-meta">${appsList} · ${fmtDur(g.total)}</span>
            <span class="browser-group-arrow">▶</span>
          </div>
          <div class="browser-group-items" id="bs-${siteKey}" style="display:none">
            ${g.sessions.map(s => `
              <div class="browser-item">
                <span class="browser-item-time">${fmtTime(s.start)}</span>
                <span class="browser-item-app">${esc(s.app.replace(' Browser',''))}</span>
                <span class="browser-item-title">${esc(s.title)}</span>
                <span class="browser-item-dur">${fmtDur(s.duration)}</span>
              </div>
            `).join('')}
          </div>
        </div>`;
      }).join('');
    } else {
      // 기본: 시간순 목록
      statusEl.textContent = `총 ${sessions.length}개 탭 기록`;
      listEl.innerHTML = sessions.slice(0, 100).map(s =>
        `<div class="browser-item">
          <span class="browser-item-time">${fmtTime(s.start)}</span>
          <span class="browser-item-app">${esc(s.app.replace(' Browser',''))}</span>
          <span class="browser-item-title">${esc(s.title)}</span>
          <span class="browser-item-dur">${fmtDur(s.duration)}</span>
        </div>`
      ).join('');
    }
  } catch(e) {
    statusEl.textContent = '로딩 실패';
    console.error('loadBrowserSessions:', e);
  } finally {
    window._browserInFlight = false;
    if (window._browserPending) { window._browserPending = false; loadBrowserSessions(); }
  }
}

/* ═══════════ 태그 탭 (v2) ═══════════ */
let tagsData = [];
let statsData = [];
let matchCache = {};  // {__all__: categoryMatchesData}
let cachedDate = '';
let breakdownBuilt = false;


function renderTodayBreakdown(stats) {
  const el = document.getElementById('tag-today-bar');
  const legend = document.getElementById('tag-today-legend');
  const section = document.getElementById('tag-today-section');
  const empty = document.getElementById('tag-today-empty');
  const breakdown = document.getElementById('tag-today-breakdown');
  const tagged = stats.filter(s => s.tag !== '__untagged__');
  const total = tagged.reduce((s, t) => s + (t.seconds || 0), 0);
  if (total < 1) { section.style.display = 'none'; empty.style.display = ''; return; }
  section.style.display = ''; empty.style.display = 'none';

  // Stacked bar (proportional view) — 항상 카테고리명 표시
  el.innerHTML = tagged.map(t => {
    const pct = (t.seconds / total) * 100;
    const label = pct > 12 ? esc(t.tag) + ' ' + fmt(t.seconds) : esc(t.tag);
    return `<div style="flex:${pct};background:${t.color};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#fff;min-width:0;overflow:hidden;white-space:nowrap;text-shadow:0 1px 2px #00000066;" title="${esc(t.tag)} ${fmt(t.seconds)}">${label}</div>`;
  }).join('');

  // Legend — 이름 + 퍼센트만 (시간은 카드/막대 title에 이미 있음)
  legend.innerHTML = tagged.map(t => {
    const pct = ((t.seconds / total) * 100).toFixed(0);
    return `<span style="display:flex;align-items:center;gap:3px;font-size:10px;color:#8b949e;"><span style="width:8px;height:8px;border-radius:2px;background:${t.color};flex-shrink:0;"></span>${esc(t.tag)} <span style="color:#585e6a;">(${pct}%)</span></span>`;
  }).join('');

  // ⬅ 날짜 체크를 먼저 (breakdownBuilt 리셋이 card build보다 앞서도록)
  const todayKey = selectedDate;
  if (todayKey !== cachedDate) {
    matchCache = {};
    cachedDate = todayKey;
    breakdownBuilt = false;
  }

  // Inline per-tag breakdown — 최초 1회만 빌드 (또는 날짜 변경 시)
  if (!breakdownBuilt) {
    breakdown.innerHTML = tagged.map(t => {
      const pct = ((t.seconds / total) * 100).toFixed(0);
      return `<div class="tag-breakdown-card" style="background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:5px 8px;">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
        <span style="width:8px;height:8px;border-radius:50%;background:${t.color};flex-shrink:0;"></span>
        <span style="font-size:12px;font-weight:600;color:#c9d1d9;">${esc(t.tag)}</span>
        <span style="font-size:12px;font-weight:500;color:${t.color};">${fmt(t.seconds)}</span>
        <span style="font-size:10px;color:#585e6a;">(${pct}%)</span>
      </div>
      <div id="tag-apps-${cssId(t.tag)}" class="tag-apps-list" data-rendered="0"></div>
    </div>`;
    }).join('');
    breakdownBuilt = true;
    // Load from cache (loadTags에서 미리 fetch한 __all__ 데이터)
    if (matchCache['__all__']) {
      for (const [cidStr, info] of Object.entries(matchCache['__all__'])) {
        const cat = findCatById(tagsData, parseInt(cidStr));
        if (!cat) continue;
        const listEl = document.getElementById(`tag-apps-${cssId(cat.name)}`);
        if (!listEl) continue;
        renderAppList(listEl, info.matches || [], info.color || '#58a6ff');
      }
    }
  } else {
    // 이후 리프레시: 시간 숫자만 업데이트
    breakdown.querySelectorAll('.tag-breakdown-card').forEach(card => {
      const tagName = card.querySelector('span:nth-child(2)')?.textContent;
      if (!tagName) return;
      const s = tagged.find(t => t.tag === tagName);  // API 필드는 tag (name 아님)
      if (!s) return;
      const sp = card.querySelector('span:nth-child(3)');
      const pctEl = card.querySelector('span:nth-child(4)');
      if (sp) sp.textContent = fmt(s.seconds);
      const totalPct = ((s.seconds / total) * 100).toFixed(0);
      if (pctEl) pctEl.textContent = `(${totalPct}%)`;
    });
  }

  // (all-matches는 loadTags에서 미리 로드, 여기서는 fetch 안 함)
  }

  function renderAppList(listEl, matches, color) {
    // 이미 렌더링된 경우 스킵
    if (listEl.children.length > 0 && listEl.dataset.rendered) return;
    if (!matches || matches.length === 0) {
      listEl.innerHTML = '<div style="padding:2px 0;color:#585e6a;font-size:10px;">매칭 없음</div>';
      listEl.dataset.rendered = '1';
      return;
    }
    // Group by app, sum durations
    const appMap = {};
    matches.forEach(m => {
      const key = m.app || '(기타)';
      if (!appMap[key]) appMap[key] = { app: key, seconds: 0 };
      appMap[key].seconds += (m.seconds || m.duration || 0);
    });
    const apps = Object.values(appMap).sort((a,b) => b.seconds - a.seconds);
    const maxAppSecs = apps[0]?.seconds || 1;
    listEl.innerHTML = apps.map(a => {
      const apct = (a.seconds / maxAppSecs) * 100;
      return `<div style="display:flex;align-items:center;gap:5px;padding:1px 0;font-size:10px;">
        <div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8b949e;">${esc(a.app)}</div>
        <div style="width:60px;height:6px;background:#21262d;border-radius:3px;overflow:hidden;flex-shrink:0;">
          <div style="width:${apct}%;height:100%;background:${color};border-radius:3px;"></div>
        </div>
        <span style="color:#c9d1d9;min-width:32px;text-align:right;font-family:monospace;">${fmt(a.seconds)}</span>
      </div>`;
    }).join('');
    listEl.dataset.rendered = '1';
  }

function findCatById(nodes, id) {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) { const f = findCatById(n.children, id); if (f) return f; }
  }
  return null;
}

function cssId(name) {
  return 'cat-' + name.replace(/[^a-zA-Z0-9\uAC00-\uD7AF-]/g, '_').substring(0, 40);
}

async function loadTags() {
  // in-flight dedup (setInterval 3s + user click race 방지)
  if (window._tagInFlight) { window._tagPending = true; return; }
  window._tagInFlight = true;
  try {
    // 한 번에 3개 API를 모두 병렬 호출
    const [tagsRes, statsRes, allRes] = await Promise.all([
      fetch('/api/categories'),
      fetch('/api/tag-stats' + dateParam()),
      fetch('/api/category-all-matches')
    ]);
    tagsData = await tagsRes.json();
    statsData = await statsRes.json();
    const allData = await allRes.json();

    // 1. 오늘 활동 브레이크다운 (renderTodayBreakdown 내부에서 matchCache 리셋됨)
    renderTodayBreakdown(statsData);
    // 2. all-matches는 renderTodayBreakdown 이후에 설정 (리셋 방지)
    matchCache['__all__'] = allData || {};
    // 2. 각 카드에 all-matches 결과 분배
    for (const [cidStr, info] of Object.entries(matchCache['__all__'])) {
      const cat = findCatById(tagsData, parseInt(cidStr));
      if (!cat) continue;
      const listEl = document.getElementById(`tag-apps-${cssId(cat.name)}`);
      if (!listEl) continue;
      renderAppList(listEl, info.matches || [], info.color || '#58a6ff');
    }
    // 3. 카테고리 목록 + 상태
    renderMiniCategoryList();
    document.getElementById('tag-status').textContent = `${countNodes(tagsData)}개 카테고리`;

  } catch(e) { console.error('loadTags:', e); }
  window._tagInFlight = false;
  window._tagLoaded = true;
  if (window._tagPending) { window._tagPending = false; loadTags(); }
}

// 3초 리프레시용 — stats만 업데이트, 카드 건드리지 않음
async function refreshTagStats() {
  // in-flight dedup (setInterval 3s + loadTags race 방지)
  if (window._tagRefreshInFlight) return;
  window._tagRefreshInFlight = true;
  try {
    const res = await fetch('/api/tag-stats' + dateParam());
    const fresh = await res.json();
    if (!fresh || fresh.length === 0) return;
    statsData = fresh;
    const el = document.getElementById('tag-today-bar');
    const legend = document.getElementById('tag-today-legend');
    if (!el || !legend) return;
    const tagged = fresh.filter(s => s.tag !== '__untagged__');
    const total = tagged.reduce((s, t) => s + (t.seconds || 0), 0);
    if (total < 1) return;
    // 🔹 막대 segment 업데이트 — dirty check (flashes 방지: 1초 미만 변경이면 skip)
    const segs = el.children;
    let dirty = false;
    if (segs.length === tagged.length) {
      for (let i = 0; i < tagged.length; i++) {
        const t = tagged[i];
        const prev = segs[i]._prevSecs;
        if (prev === undefined || Math.abs(t.seconds - prev) >= 1) { dirty = true; }
      }
    } else {
      dirty = true;  // segs 개수 변경이면 항상 update
    }
    if (!dirty) { window._tagRefreshInFlight = false; return; }  // 아무 변경도 없으면 DOM 건드리지 않음
    // in-place: segs append/remove + update
    if (segs.length < tagged.length) {
      for (let i = segs.length; i < tagged.length; i++) {
        const t = tagged[i];
        const pct = (t.seconds / total) * 100;
        const seg = document.createElement('div');
        seg.style.cssText = `flex:${pct};background:${t.color};display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#fff;min-width:0;overflow:hidden;white-space:nowrap;text-shadow:0 1px 2px #00000066;`;
        seg.textContent = pct > 12 ? t.tag + ' ' + fmt(t.seconds) : t.tag;
        seg.title = t.tag + ' ' + fmt(t.seconds);
        seg._prevSecs = t.seconds;
        el.appendChild(seg);
      }
    } else if (segs.length > tagged.length) {
      for (let i = segs.length - 1; i >= tagged.length; i--) segs[i].remove();
    }
    for (let i = 0; i < tagged.length; i++) {
      const t = tagged[i];
      const pct = (t.seconds / total) * 100;
      segs[i].style.flex = pct;
      segs[i].style.background = t.color;
      segs[i].textContent = pct > 12 ? t.tag + ' ' + fmt(t.seconds) : t.tag;
      segs[i].title = t.tag + ' ' + fmt(t.seconds);
      segs[i]._prevSecs = t.seconds;
    }
    // 🔹 범례 업데이트 — dirty check (flashes 방지)
    const legItems = legend.children;
    // in-place: legItems append/remove + update
    if (legItems.length < tagged.length) {
      for (let i = legItems.length; i < tagged.length; i++) {
        const t = tagged[i];
        const pct = ((t.seconds / total) * 100).toFixed(0);
        const item = document.createElement('span');
        item.style.cssText = 'display:flex;align-items:center;gap:3px;font-size:10px;color:#8b949e;';
        item.innerHTML = `<span style="width:8px;height:8px;border-radius:2px;background:${t.color};flex-shrink:0;"></span>${esc(t.tag)} <span style="color:#585e6a;">(${pct}%)</span>`;
        item._prevSecs = t.seconds;
        legend.appendChild(item);
      }
    } else if (legItems.length > tagged.length) {
      for (let i = legItems.length - 1; i >= tagged.length; i--) legItems[i].remove();
    }
    for (let i = 0; i < tagged.length; i++) {
      const t = tagged[i];
      const pct = ((t.seconds / total) * 100).toFixed(0);
      const legItem = legend.children[i];
      if (!legItem) continue;
      const prev = legItem._prevSecs;
      if (prev !== undefined && Math.abs(t.seconds - prev) < 1) continue;  // 1초 미만 변경이면 skip
      const dot = legItem.querySelector('span:first-child');
      if (dot) dot.style.background = t.color;
      const textNodes = [];
      legItem.childNodes.forEach(n => { if (n.nodeType === 3) textNodes.push(n); });
      if (textNodes[0]) textNodes[0].textContent = t.tag + ' ';
      const pctSpan = legItem.querySelector('span:last-child');
      if (pctSpan) pctSpan.textContent = `(${pct}%)`;
      legItem._prevSecs = t.seconds;
    }
    // 🔹 카드 내 시간 텍스트 갱신 — dirty check (flashes 방지)
    document.querySelectorAll('.tag-breakdown-card').forEach(card => {
      const nameEl = card.querySelector('span:nth-child(2)');
      if (!nameEl) return;
      const tagName = nameEl.textContent;
      const s = tagged.find(t => t.tag === tagName);  // API 필드는 tag (name 아님)
      if (!s) return;
      const prev = card._prevSecs;
      if (prev !== undefined && Math.abs(s.seconds - prev) < 1) return;  // 1초 미만 변경이면 skip
      const sp = card.querySelector('span:nth-child(3)');
      const pctEl = card.querySelector('span:nth-child(4)');
      if (sp) sp.textContent = fmt(s.seconds);
      const totalPct = ((s.seconds / total) * 100).toFixed(0);
      if (pctEl) pctEl.textContent = `(${totalPct}%)`;
      card._prevSecs = s.seconds;
    });
  } catch(e) { /* 조용히 */ } finally {
    window._tagRefreshInFlight = false;
  }
}

function openCategoriesPopup() {
  const feat = 'width=550,height=520,scrollbars=yes,resizable=yes';
  window.open('/static/categories.html', 'categories', feat);
}

/* ── 미니 카테고리 목록 (시간 포함, 계층형) ── */
function renderMiniCategoryList() {
  // statsData에서 카테고리별 시간 lookup
  const timeMap = {};
  for (const s of statsData) {
    timeMap[s.tag] = s.seconds;
  }

  function renderNode(nodes, depth) {
    return nodes.map(t => {
      const secs = timeMap[t.name] || 0;
      const tagColor = t.color;
      const hasKids = t.children && t.children.length > 0;
      const isGroup = hasKids || (!t.regex || t.regex === '');
      const indent = depth * 12;
      return `
        <div class="tag-mgmt-item" style="padding:4px 6px;padding-left:${indent + 8}px;">
          <span class="tag-mgmt-color" style="background:${tagColor};width:8px;height:8px;border-radius:50%;flex-shrink:0;"></span>
          <span class="tag-mgmt-name" style="font-size:13px;flex:none;min-width:50px;${isGroup ? 'font-weight:600;' : ''}">${esc(t.name)}</span>
          <span class="tag-app-time" style="font-size:13px;color:${tagColor};margin-right:4px;">${fmt(secs)}</span>
          <span style="font-size:10px;color:#585e6a;font-family:monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(t.regex || (hasKids ? '' : '그룹'))}</span>
        </div>
        ${hasKids ? renderNode(t.children, depth + 1) : ''}
      `;
    }).join('');
  }

  document.getElementById('tag-cat-mini').innerHTML = renderNode(tagsData, 0);

  // 미분류 시간도 표시
  const untaggedSecs = statsData.find(s => s.tag === '__untagged__')?.seconds || 0;
  if (untaggedSecs > 0) {
    document.getElementById('tag-cat-mini').insertAdjacentHTML('beforeend',
      `<div class="tag-mgmt-item" style="padding:4px 6px 4px 8px;opacity:0.5;">
        <span style="width:8px;height:8px;border-radius:50%;background:#8b949e;flex-shrink:0;"></span>
        <span style="font-size:13px;flex:none;min-width:40px;color:#8b949e;">❓ 미분류</span>
        <span style="font-size:13px;color:#8b949e;font-weight:600;">${fmt(untaggedSecs)}</span>
      </div>`
    );
  }
}



/* ═══════════ 뽀모도로 ═══════════ */
let pomo = {
  state: 'idle', // idle | work | break
  workSec: 25*60, breakSec: 5*60,
  remaining: 25*60, count: 0,
  timerId: null,
};

function pomoUpdateSettings() {
  pomo.workSec = parseInt(document.getElementById('pomo-work-min').value) * 60;
  pomo.breakSec = parseInt(document.getElementById('pomo-break-min').value) * 60;
  if (pomo.state === 'idle') {
    pomo.remaining = pomo.workSec;
    pomoRender();
  }
}

function pomoStart() {
  const isPaused = pomo.state === 'paused-work' || pomo.state === 'paused-break';
  if (pomo.state === 'idle' || isPaused) {
    if (pomo.state === 'idle') {
      pomo.remaining = pomo.workSec;
      pomo.state = 'work';
    } else {
      pomo.state = pomo.state === 'paused-work' ? 'work' : 'break';
    }
    document.getElementById('pomo-start').style.display = 'none';
    document.getElementById('pomo-pause').style.display = '';
    document.getElementById('pomo-stop').style.display = '';
    pomo.timerId = setInterval(pomoTick, 1000);
    pomoRender();
  }
}

function pomoPause() {
  if (pomo.state === 'work') pomo.state = 'paused-work';
  else if (pomo.state === 'break') pomo.state = 'paused-break';
  clearInterval(pomo.timerId);
  document.getElementById('pomo-start').style.display = '';
  document.getElementById('pomo-start').textContent = '▶ 재개';
  document.getElementById('pomo-pause').style.display = 'none';
  pomoRender();
}

function pomoStop() {
  clearInterval(pomo.timerId);
  pomo.state = 'idle';
  pomo.remaining = pomo.workSec;
  document.getElementById('pomo-start').style.display = '';
  document.getElementById('pomo-start').textContent = '▶ 시작';
  document.getElementById('pomo-pause').style.display = 'none';
  document.getElementById('pomo-stop').style.display = 'none';
  pomoRender();
}

function pomoReset() {
  clearInterval(pomo.timerId);
  pomo.state = 'idle';
  pomo.remaining = pomo.workSec;
  document.getElementById('pomo-start').style.display = '';
  document.getElementById('pomo-start').textContent = '▶ 시작';
  document.getElementById('pomo-pause').style.display = 'none';
  pomoRender();
}

function pomoTick() {
  pomo.remaining--;
  if (pomo.remaining <= 0) {
    clearInterval(pomo.timerId);
    if (pomo.state === 'work') {
      pomo.count++;
      pomo.state = 'break';
      pomo.remaining = pomo.breakSec;
      document.getElementById('pomo-count').textContent = pomo.count;
      playNotification('🍅 작업 완료! 휴식 시간!');
    } else {
      pomo.state = 'work';
      pomo.remaining = pomo.workSec;
      playNotification('☕ 휴식 끝! 다시 작업 시작!');
    }
    document.getElementById('pomo-start').style.display = '';
    document.getElementById('pomo-start').textContent = '▶ 시작';
    document.getElementById('pomo-pause').style.display = 'none';
    document.getElementById('pomo-stop').style.display = 'none';
    pomo.timerId = setInterval(pomoTick, 1000);
  }
  pomoRender();
}

function playNotification(msg) {
  if (Notification.permission === 'granted') {
    new Notification('🍅 Mac Time Tracker', { body: msg });
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission();
  }
}

function pomoRender() {
  const timer = document.getElementById('pomo-timer');
  const label = document.getElementById('pomo-label');
  const progress = document.getElementById('pomo-progress');

  const m = Math.floor(pomo.remaining / 60);
  const s = pomo.remaining % 60;
  timer.textContent = `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;

  const isWork = pomo.state === 'work' || pomo.state === 'paused-work' || pomo.state === 'idle';
  timer.className = 'pomodoro-timer ' + (isWork ? 'work' : 'break');
  progress.className = 'pomodoro-progress-fill ' + (isWork ? '' : 'break');

  const total = isWork ? pomo.workSec : pomo.breakSec;
  progress.style.width = (total > 0 ? (pomo.remaining / total * 100) : 0) + '%';

  if (pomo.state === 'idle') label.textContent = '🍅 준비 완료';
  else if (isWork) label.textContent = '🔥 작업 중...';
  else label.textContent = '☕ 휴식 중...';
}

/* ═══════════ 새로고침 ═══════════ */
function refresh() { refreshAll(); }
initDatePicker();
refresh();
setInterval(refresh, 10000);  // 3s → 10s (flashes 빈도 1/3으로 감소)
// 권한 상태: 패널 닫혀있어도 30s마다 점(dot) 갱신
let permTick = 0;
setInterval(() => { if (++permTick % 3 === 0) loadPermissions(); }, 10000);

// 알림 권한 요청
if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
