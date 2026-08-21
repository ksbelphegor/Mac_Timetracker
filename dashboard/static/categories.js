
let catsData = [];
let selectedId = null;
let editingId = null; // null = add, number = edit

function esc(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

// ── Tree rendering ──

function hasKids(c) { return c.children && c.children.length > 0; }

function renderTree(nodes, depth) {
  return nodes.map(c => {
    const hk = hasKids(c);
    const expanded = localStorage.getItem('cat-exp-'+c.id) !== '0';
    return `
      <div>
        <div class="tree-item depth-${depth} ${selectedId===c.id?'selected':''}"
             onclick="selectCat(${c.id})">
          <span class="tarrow ${hk?'expanded':''} ${hk?'':'empty'}" onclick="event.stopPropagation();toggleTree(${c.id})">${hk?'▶':''}</span>
          <span class="dot" style="background:${c.color}"></span>
          <span class="tname">${esc(c.name)}</span>
          <span class="tscore">+${c.score||0}</span>
        </div>
        ${hk ? `<div class="tree-children ${expanded?'open':''}" id="tch-${c.id}">${renderTree(c.children, depth+1)}</div>` : ''}
      </div>`;
  }).join('');
}

function toggleTree(id) {
  const el = document.getElementById('tch-'+id);
  if (!el) return;
  el.classList.toggle('open');
  localStorage.setItem('cat-exp-'+id, el.classList.contains('open') ? '1' : '0');
  // Update arrow
  const arrow = el.previousElementSibling?.querySelector('.tarrow');
  if (arrow) arrow.classList.toggle('expanded');
}

function selectCat(id) {
  selectedId = id;
  renderAll();
  showDetail(id);
}

function renderAll() {
  document.getElementById('tree').innerHTML = catsData.length === 0
    ? '<div style="padding:20px;text-align:center;color:#585e6a;font-size:12px;">카테고리가 없습니다</div>'
    : renderTree(catsData, 0);
}

// ── Detail panel ──

function showDetail(id) {
  const c = findCat(catsData, id);
  if (!c) return;
  const panel = document.getElementById('detail-panel');
  document.getElementById('detail-empty').style.display = 'none';
  document.getElementById('detail-content').style.display = 'flex';
  document.getElementById('detail-dot').style.background = c.color;
  document.getElementById('detail-name').textContent = c.name;
  document.getElementById('detail-badge').textContent = '점수 +' + (c.score||0) + (hasKids(c) ? ' · ' + c.children.length + '개 자식' : '');

  const rules = c.rules || [];
  const rulesEl = document.getElementById('rules-list');
  if (rules.length === 0) {
    rulesEl.innerHTML = '<div class="rule-empty">규칙이 없습니다 — 아래에 정규식을 입력하세요</div>';
  } else {
    rulesEl.innerHTML =
      `<div class="rules-header">📋 규칙 (${rules.length}개)</div>` +
      rules.map((r, i) =>
        `<div class="rule-item">
          <span class="rid">${i+1}</span>
          <span class="rpat">${esc(r.pattern)}</span>
          <span class="rci">${r.case_insensitive ? 'CI' : 'CS'}</span>
          <button class="btn btn-sm" onclick="editRule(${r.id},${c.id})">✏️</button>
          <button class="btn btn-sm btn-danger" onclick="delRule(${r.id})">✕</button>
        </div>`
      ).join('');
  }
}

// ── Rules CRUD ──

async function addRule() {
  const input = document.getElementById('rule-input');
  const pattern = input.value.trim();
  if (!pattern || !selectedId) return;
  const r = await fetch('/api/rules', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ category_id: selectedId, pattern })
  });
  if (r.ok) {
    input.value = '';
    await refresh();
  }
}

async function editRule(ruleId, catId) {
  const rules = findCat(catsData, catId)?.rules || [];
  const rule = rules.find(r => r.id === ruleId);
  if (!rule) return;
  const newPat = prompt('규칙 패턴:', rule.pattern);
  if (!newPat) return;
  const ci = prompt('Case insensitive? (y/n):', rule.case_insensitive ? 'y' : 'n') === 'y';
  const r = await fetch('/api/rules/' + ruleId, {
    method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ pattern: newPat.trim(), case_insensitive: ci })
  });
  if (r.ok) await refresh();
}

async function delRule(ruleId) {
  if (!confirm('규칙을 삭제할까요?')) return;
  const r = await fetch('/api/rules/' + ruleId, { method:'DELETE' });
  if (r.ok) await refresh();
}

// ── Category CRUD ──

function openAddModal() {
  editingId = null;
  document.getElementById('modal-title').textContent = '+ 카테고리 추가';
  document.getElementById('m-name').value = '';
  document.getElementById('m-color').value = '#58a6ff';
  document.getElementById('m-color-hex').value = '#58a6ff';
  document.getElementById('m-score').value = '10';
  document.getElementById('m-delete').style.display = 'none';
  updateParentSelect();
  document.getElementById('modal').classList.add('open');
}

function openEditModal(id) {
  const c = findCat(catsData, id);
  if (!c) return;
  editingId = id;
  document.getElementById('modal-title').textContent = '✏️ ' + c.name;
  document.getElementById('m-name').value = c.name;
  document.getElementById('m-color').value = c.color;
  document.getElementById('m-color-hex').value = c.color;
  document.getElementById('m-score').value = String(c.score || 0);
  document.getElementById('m-delete').style.display = '';
  updateParentSelect(c.parent_id);
  document.getElementById('modal').classList.add('open');
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
}

async function saveModal() {
  const name = document.getElementById('m-name').value.trim();
  const color = document.getElementById('m-color-hex').value.trim() || document.getElementById('m-color').value;
  const score = parseInt(document.getElementById('m-score').value) || 0;
  const parentId = document.getElementById('m-parent').value;
  const body = { name, color, score, regex: '' };
  if (parentId) body.parent_id = parseInt(parentId);

  if (editingId === null) {
    // Add
    const r = await fetch('/api/categories', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    if (r.ok) {
      closeModal();
      const created = await r.json();
      selectedId = created.id;
      await refresh();
    }
  } else {
    // Update
    const r = await fetch('/api/categories/' + editingId, {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
    });
    if (r.ok) {
      closeModal();
      await refresh();
    }
  }
}

async function deleteFromModal() {
  if (editingId === null) return;
  if (!confirm('정말 삭제할까요?')) return;
  const r = await fetch('/api/categories/' + editingId, { method:'DELETE' });
  if (r.ok) {
    closeModal();
    if (selectedId === editingId) selectedId = null;
    await refresh();
  }
}

async function delCat() {
  if (!selectedId) return;
  if (!confirm('삭제할까요? (규칙과 함께 삭제)')) return;
  const r = await fetch('/api/categories/' + selectedId, { method:'DELETE' });
  if (r.ok) {
    selectedId = null;
    document.getElementById('detail-content').style.display = 'none';
    document.getElementById('detail-empty').style.display = 'flex';
    await refresh();
  }
}

// ── Helpers ──

function findCat(nodes, id) {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) { const f=findCat(n.children,id); if(f) return f; }
  }
  return null;
}

function updateParentSelect(selectedParentId) {
  const sel = document.getElementById('m-parent');
  sel.innerHTML = '<option value="">없음 (루트)</option>';
  function addOpts(nodes, depth) {
    for (const n of nodes) {
      if (n.id === editingId) continue; // 자기 자신 제외
      const opt = document.createElement('option');
      opt.value = n.id;
      opt.textContent = '  '.repeat(depth) + n.name;
      sel.appendChild(opt);
      if (n.children) addOpts(n.children, depth+1);
    }
  }
  addOpts(catsData, 0);
  if (selectedParentId) sel.value = String(selectedParentId);
}

async function refresh() {
  const r = await fetch('/api/categories');
  catsData = await r.json();
  renderAll();
  if (selectedId && findCat(catsData, selectedId)) {
    showDetail(selectedId);
  } else {
    selectedId = null;
    document.getElementById('detail-content').style.display = 'none';
    document.getElementById('detail-empty').style.display = 'flex';
  }
}

// ── Init ──
async function load() {
  await refresh();
  // Auto-refresh rules list every 5s
  setInterval(async () => {
    const r = await fetch('/api/categories');
    catsData = await r.json();
    renderAll();
    if (selectedId && findCat(catsData, selectedId)) {
      showDetail(selectedId);
    }
  }, 5000);
}

// Color sync
document.getElementById('m-color').addEventListener('input', function() {
  document.getElementById('m-color-hex').value = this.value;
});
document.getElementById('m-color-hex').addEventListener('input', function() {
  const v = this.value.trim();
  if (/^#[0-9a-f]{6}$/i.test(v)) document.getElementById('m-color').value = v;
});

load();
