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

/* 折叠块：覆盖 Obsidian 默认 details/summary 样式，统一箭头，去边框 */
.iw-panel details, .iw-panel2 details {
    margin: 2px 0;
    padding: 0;
    border: none;
    background: transparent;
}
.iw-panel summary, .iw-panel2 summary {
    cursor: pointer;
    padding: 3px 4px;
    border-radius: 4px;
    list-style: none;
    user-select: none;
}
.iw-panel summary::-webkit-details-marker, .iw-panel2 summary::-webkit-details-marker { display: none; }
.iw-panel summary::before, .iw-panel2 summary::before {
    content: '';
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 0.42em solid currentColor;
    border-top: 0.3em solid transparent;
    border-bottom: 0.3em solid transparent;
    margin-right: 0.55em;
    vertical-align: middle;
    transition: transform .12s;
}
.iw-panel details[open] > summary::before, .iw-panel2 details[open] > summary::before { transform: rotate(90deg); }
.iw-panel summary:hover, .iw-panel2 summary:hover { background: var(--background-modifier-hover); }

/* 列表：日期固定右列不换行，标题可换行，整体对齐 */
.iw-panel ul {
    list-style: none;
    margin: 2px 0 8px;
    padding-left: 0.4em;
}
.iw-panel2 ul {
    list-style: none;
    margin: 2px 0 8px;
    padding-left: 0;
}
.iw-panel li, .iw-panel2 li {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin: 2px 0;
    line-height: 1.5;
}
.iw-panel li a, .iw-panel2 li a {
    flex: 1 1 auto;
    min-width: 0;
    text-decoration: none;
}
.iw-panel li .iw-date, .iw-panel2 li .iw-date {
    flex: 0 0 auto;
    white-space: nowrap;
    color: var(--text-faint);
    font-size: 0.85em;
}
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
        span.className = 'iw-date';
        span.textContent = `  —  ${dateStr}`;
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
    // Dataview 的 sort 只接受 key 函数（码点序，非拼音）；转原生数组用 localeCompare 得拼音序
    const grouped = pages.groupBy(p => p.category || '未分类').array().sort((a, b) => {
        if (a.key === '未分类') return 1;
        if (b.key === '未分类') return -1;
        return a.key.localeCompare(b.key);
    });
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

/* 折叠块：覆盖 Obsidian 默认 details/summary 样式，统一箭头，去边框 */
.iw-panel details, .iw-panel2 details {
    margin: 2px 0;
    padding: 0;
    border: none;
    background: transparent;
}
.iw-panel summary, .iw-panel2 summary {
    cursor: pointer;
    padding: 3px 4px;
    border-radius: 4px;
    list-style: none;
    user-select: none;
}
.iw-panel summary::-webkit-details-marker, .iw-panel2 summary::-webkit-details-marker { display: none; }
.iw-panel summary::before, .iw-panel2 summary::before {
    content: '';
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 0.42em solid currentColor;
    border-top: 0.3em solid transparent;
    border-bottom: 0.3em solid transparent;
    margin-right: 0.55em;
    vertical-align: middle;
    transition: transform .12s;
}
.iw-panel details[open] > summary::before, .iw-panel2 details[open] > summary::before { transform: rotate(90deg); }
.iw-panel summary:hover, .iw-panel2 summary:hover { background: var(--background-modifier-hover); }

/* 列表：日期固定右列不换行，标题可换行，整体对齐 */
.iw-panel ul {
    list-style: none;
    margin: 2px 0 8px;
    padding-left: 0.4em;
}
.iw-panel2 ul {
    list-style: none;
    margin: 2px 0 8px;
    padding-left: 0;
}
.iw-panel li, .iw-panel2 li {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin: 2px 0;
    line-height: 1.5;
}
.iw-panel li a, .iw-panel2 li a {
    flex: 1 1 auto;
    min-width: 0;
    text-decoration: none;
}
.iw-panel li .iw-date, .iw-panel2 li .iw-date {
    flex: 0 0 auto;
    white-space: nowrap;
    color: var(--text-faint);
    font-size: 0.85em;
}
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
        span.className = 'iw-date';
        span.textContent = `  —  ${dateStr}`;
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

// 讨论 —— 只显示讨论总结（type: summary），过滤 rounds/ 过程文件和 references
addTab('topics', '讨论', () => {
    const div = document.createElement('div');
    const ul = document.createElement('ul');
    const pages = dv.pages('"discussions"').where(p => p.file.frontmatter && Object.keys(p.file.frontmatter).length > 0 && p.type === 'summary').sort(p => p.date, 'desc').slice(0, 10);
    if (pages.length === 0) {
        const span = document.createElement('span');
        span.style.color = 'var(--text-faint)';
        span.textContent = '（暂无讨论总结）';
        div.appendChild(span);
    }
    for (const p of pages) ul.appendChild(buildItem(p));
    div.appendChild(ul);
    return div;
});

// 创作 —— 只显示定稿（type: article，creations/{slug}/{slug}.md），过滤 outline 和 drafts/
addTab('pub', '创作', () => {
    const div = document.createElement('div');
    const ul = document.createElement('ul');
    const pages = dv.pages('"creations"').where(p => p.file.frontmatter && Object.keys(p.file.frontmatter).length > 0 && p.type === 'article').sort(p => p.date, 'desc').slice(0, 10);
    if (pages.length === 0) {
        const span = document.createElement('span');
        span.style.color = 'var(--text-faint)';
        span.textContent = '（暂无定稿）';
        div.appendChild(span);
    }
    for (const p of pages) ul.appendChild(buildItem(p));
    div.appendChild(ul);
    return div;
});

tabBar.firstChild.classList.add('is-active');
panels['recent'].classList.add('is-active');

container.appendChild(tabBar);
for (const panel of Object.values(panels)) container.appendChild(panel);
```
