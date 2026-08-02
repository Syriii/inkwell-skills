> 切换到阅读模式（`Cmd+E`）

---

## 内容库

```dataviewjs
const pages = dv.pages('"archived"').where(p => p.file.frontmatter && Object.keys(p.file.frontmatter).length > 0).sort(p => p.date, 'desc');
const container = dv.container;
container.innerHTML = '';

const style = document.createElement('style');
style.textContent = `
.iw-tabs {
    display: flex; flex-wrap: wrap; gap: 2px;
    border-bottom: 1px solid var(--background-modifier-border);
    margin-bottom: 14px;
}
.iw-tab {
    padding: 6px 16px;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    font-size: 0.9em;
    color: var(--text-muted);
    border: 1px solid transparent;
    user-select: none;
}
.iw-tab:hover { color: var(--text-normal); background: var(--background-modifier-hover); }
.iw-tab.is-active {
    color: var(--text-accent);
    background: var(--background-primary);
    border-color: var(--background-modifier-border);
    border-bottom-color: transparent;
    font-weight: 600;
}
.iw-panel { display: none; }
.iw-panel.is-active { display: block; }
`;
container.appendChild(style);

function buildItem(page) {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.textContent = page.file.name;
    a.className = 'internal-link';
    a.dataset.href = page.file.path;
    a.href = page.file.path;
    a.addEventListener('click', e => {
        e.preventDefault();
        app.workspace.openLinkText(page.file.path, '', false);
    });
    li.appendChild(a);
    if (page.date) {
        const span = document.createElement('span');
        let dateStr;
        try {
            const d = dv.date(page.date);
            dateStr = (d && d.isValid) ? d.toFormat('yyyy-MM-dd') : String(page.date);
        } catch (e) {
            dateStr = String(page.date);
        }
        span.textContent = `  —  ${dateStr}`;
        span.style.cssText = 'color: var(--text-faint); font-size: 0.85em;';
        li.appendChild(span);
    }
    return li;
}

const tabBar = document.createElement('div');
tabBar.className = 'iw-tabs';
const panels = {};

function addTab(id, label, buildPanel) {
    const tab = document.createElement('span');
    tab.className = 'iw-tab';
    tab.textContent = label;
    tab.addEventListener('click', () => {
        tabBar.querySelectorAll('.iw-tab').forEach(t => t.classList.remove('is-active'));
        Object.values(panels).forEach(p => p.classList.remove('is-active'));
        tab.classList.add('is-active');
        panels[id].classList.add('is-active');
    });
    tabBar.appendChild(tab);
    const panel = buildPanel();
    panel.className = 'iw-panel';
    panels[id] = panel;
}

// 分类
addTab('cat', '分类', () => {
    const div = document.createElement('div');
    const grouped = pages.groupBy(p => p.category || '未分类');
    // Dataview 的 sort 只接受 key 函数（不接受比较器）；'未分类' 映射到最大字符排最后
    grouped.sort(g => (g.key === '未分类' ? '￿' : g.key), 'asc');
    for (const g of grouped) {
        const det = document.createElement('details');
        const sum = document.createElement('summary');
        sum.innerHTML = `<b>${g.key}</b>（${g.rows.length}）`;
        det.appendChild(sum);
        const ul = document.createElement('ul');
        for (const p of g.rows) ul.appendChild(buildItem(p));
        det.appendChild(ul);
        div.appendChild(det);
    }
    return div;
});

// 标签
addTab('tag', '标签', () => {
    const div = document.createElement('div');
    const tagMap = new Map();
    for (const p of pages) {
        for (const t of (p.tags || [])) {
            if (!tagMap.has(t)) tagMap.set(t, []);
            tagMap.get(t).push(p);
        }
    }
    for (const tag of [...tagMap.keys()].sort()) {
        const items = tagMap.get(tag);
        const det = document.createElement('details');
        const sum = document.createElement('summary');
        sum.innerHTML = `<b>${tag}</b>（${items.length}）`;
        det.appendChild(sum);
        const ul = document.createElement('ul');
        for (const p of items) ul.appendChild(buildItem(p));
        det.appendChild(ul);
        div.appendChild(det);
    }
    return div;
});

tabBar.firstChild.classList.add('is-active');
panels['cat'].classList.add('is-active');

container.appendChild(tabBar);
for (const panel of Object.values(panels)) container.appendChild(panel);
```

---

## 动态

```dataviewjs
const container = dv.container;
container.innerHTML = '';

const style = document.createElement('style');
style.textContent = `
.iw-tabs2 {
    display: flex; flex-wrap: wrap; gap: 2px;
    border-bottom: 1px solid var(--background-modifier-border);
    margin-bottom: 14px;
}
.iw-tab2 {
    padding: 6px 16px;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    font-size: 0.9em;
    color: var(--text-muted);
    border: 1px solid transparent;
    user-select: none;
}
.iw-tab2:hover { color: var(--text-normal); background: var(--background-modifier-hover); }
.iw-tab2.is-active {
    color: var(--text-accent);
    background: var(--background-primary);
    border-color: var(--background-modifier-border);
    border-bottom-color: transparent;
    font-weight: 600;
}
.iw-panel2 { display: none; }
.iw-panel2.is-active { display: block; }
`;
container.appendChild(style);

function buildItem(page) {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.textContent = page.file.name;
    a.className = 'internal-link';
    a.dataset.href = page.file.path;
    a.href = page.file.path;
    a.addEventListener('click', e => {
        e.preventDefault();
        app.workspace.openLinkText(page.file.path, '', false);
    });
    li.appendChild(a);
    if (page.date) {
        const span = document.createElement('span');
        let dateStr;
        try {
            const d = dv.date(page.date);
            dateStr = (d && d.isValid) ? d.toFormat('yyyy-MM-dd') : String(page.date);
        } catch (e) {
            dateStr = String(page.date);
        }
        span.textContent = `  —  ${dateStr}`;
        span.style.cssText = 'color: var(--text-faint); font-size: 0.85em;';
        li.appendChild(span);
    }
    return li;
}

const tabBar = document.createElement('div');
tabBar.className = 'iw-tabs2';
const panels = {};

function addTab(id, label, buildPanel) {
    const tab = document.createElement('span');
    tab.className = 'iw-tab2';
    tab.textContent = label;
    tab.addEventListener('click', () => {
        tabBar.querySelectorAll('.iw-tab2').forEach(t => t.classList.remove('is-active'));
        Object.values(panels).forEach(p => p.classList.remove('is-active'));
        tab.classList.add('is-active');
        panels[id].classList.add('is-active');
    });
    tabBar.appendChild(tab);
    const panel = buildPanel();
    panel.className = 'iw-panel2';
    panels[id] = panel;
}

// 采集
addTab('recent', '采集', () => {
    const div = document.createElement('div');
    const ul = document.createElement('ul');
    const pages = dv.pages('"archived"').where(p => p.file.frontmatter && Object.keys(p.file.frontmatter).length > 0).sort(p => p.fetched_at, 'desc').slice(0, 15);
    for (const p of pages) ul.appendChild(buildItem(p));
    div.appendChild(ul);
    return div;
});

// 讨论
addTab('topics', '讨论', () => {
    const div = document.createElement('div');
    const ul = document.createElement('ul');
    const pages = dv.pages('"discussions"').where(p => p.file.frontmatter && Object.keys(p.file.frontmatter).length > 0).sort(p => p.date, 'desc').slice(0, 10);
    for (const p of pages) ul.appendChild(buildItem(p));
    div.appendChild(ul);
    return div;
});

// 创作
addTab('pub', '创作', () => {
    const div = document.createElement('div');
    const ul = document.createElement('ul');
    const pages = dv.pages('"creations"').sort(p => p.date, 'desc').slice(0, 10);
    for (const p of pages) ul.appendChild(buildItem(p));
    div.appendChild(ul);
    return div;
});

tabBar.firstChild.classList.add('is-active');
panels['recent'].classList.add('is-active');

container.appendChild(tabBar);
for (const panel of Object.values(panels)) container.appendChild(panel);
```
