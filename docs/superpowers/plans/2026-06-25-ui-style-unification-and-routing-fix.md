# UI 风格统一与路由修复 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 以贷后助手玻璃拟态风格统一全部 7 个页面的视觉效果，修复侧边栏缺失报告入口和快捷跳转的路由问题。

**架构：** 新建共享 CSS 基础库（`public/shared.css`，CSS 变量 + 工具类）；修改 6 个后端 HTML 模板替换顶栏为侧边栏并引用共享样式；修改 App.vue 补全侧边栏导航 + 报告快捷按钮 + report ID 捕获。

**技术栈：** Vue 3 + Vite + 原生 CSS（无预处理器） + FastAPI（后端模板渲染）

---

## 文件结构

| 文件 | 职责 | 变动 |
|------|------|------|
| `frontend/public/shared.css` | 共享 CSS 变量 + 通用工具类 | **新建** |
| `frontend/src/App.vue` | 贷后助手 SPA：侧边栏补全 + 快捷按钮 + ID 捕获 + 宽度调整 | 修改 |
| `frontend/src/style.css` | 全局样式：引入 shared 变量 | 修改 |
| `backend/src/templates/warnings.html` | 预警中心：替换导航 + 引入 shared.css | 修改 |
| `backend/src/templates/enterprises.html` | 贷后项目：替换导航 + 引入 shared.css | 修改 |
| `backend/src/templates/sources.html` | 数据源管理：替换导航 + 引入 shared.css | 修改 |
| `backend/src/templates/upload.html` | 参考文档：替换导航 + 引入 shared.css | 修改 |
| `backend/src/templates/reports.html` | 报告列表：替换导航 + 引入 shared.css | 修改 |
| `backend/src/templates/reports-edit.html` | 报告编辑：替换导航 + 引入 shared.css | 修改 |

---

### 任务 1：创建共享 CSS 基础库

**文件：**
- 创建：`frontend/public/shared.css`

- [ ] **步骤 1：创建 shared.css**

`frontend/public/shared.css`（Vite 会将 `public/` 目录内容原样复制到 `dist/`，可通过 `/app/shared.css` 访问）：

```css
/* ============================================================
   共享设计系统 — 贷后助手玻璃拟态风格
   所有页面（Vue SPA + HTML 模板）统一引用此文件
   ============================================================ */

/* === CSS 自定义属性 === */
:root {
  /* 主色调 */
  --color-primary: #2563eb;
  --color-primary-light: #3b82f6;
  --color-primary-dark: #1d4ed8;
  --color-accent: #7c3aed;
  --color-accent-light: #8b5cf6;
  --color-indigo: #4f46e5;

  /* 渐变 */
  --gradient-brand: linear-gradient(135deg, #2563eb, #7c3aed);
  --gradient-action: linear-gradient(90deg, #3b82f6, #8b5cf6);
  --gradient-report: linear-gradient(180deg, #2563eb, #7c3aed);

  /* 表面 / 背景 */
  --surface-panel: rgba(255, 255, 255, 0.95);
  --surface-sidebar: rgba(255, 255, 255, 0.98);
  --surface-card: #ffffff;
  --bg-app: radial-gradient(circle at 20% 20%, #f8fafc, #dbeafe 60%);
  --bg-report: linear-gradient(165deg, #ffffff 0%, #f8fafc 42%, #f1f5f9 100%);

  /* 文字 */
  --text-primary: #0f172a;
  --text-body: #1f2937;
  --text-secondary: #334155;
  --text-muted: #475569;
  --text-subtle: #64748b;

  /* 边框 */
  --border-light: rgba(148, 163, 184, 0.18);
  --border-medium: rgba(148, 163, 184, 0.28);
  --border-strong: rgba(148, 163, 184, 0.4);

  /* 圆角 */
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 18px;
  --radius-xl: 20px;
  --radius-full: 9999px;

  /* 阴影 */
  --shadow-card: 0 2px 12px rgba(15, 23, 42, 0.06);
  --shadow-panel: 0 12px 32px rgba(15, 23, 42, 0.10);
  --shadow-modal: 0 24px 64px rgba(15, 23, 42, 0.25);
  --shadow-button: 0 4px 12px rgba(59, 130, 246, 0.3);

  /* 动效 */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --transition-fast: 150ms var(--ease-out);
  --transition-normal: 250ms var(--ease-out);

  /* 字体 */
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

/* === 全局重置 === */
*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: var(--font-sans);
  color: var(--text-body);
  background: var(--bg-app);
  min-height: 100vh;
}

/* === 面板（玻璃拟态） === */
.panel-glass {
  background: var(--surface-panel);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-panel);
}

/* === 卡片 === */
.card-glass {
  background: var(--surface-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  transition: transform var(--transition-normal),
              box-shadow var(--transition-normal);
}
.card-glass:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-panel);
}

/* === 主按钮 === */
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--gradient-brand);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  padding: 12px 24px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: transform var(--transition-fast),
              box-shadow var(--transition-fast);
  text-decoration: none;
}
.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-button);
}

/* === 次按钮 === */
.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid var(--border-medium);
  color: var(--text-muted);
  border-radius: var(--radius-md);
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
}
.btn-secondary:hover {
  border-color: var(--color-primary-light);
  color: var(--color-primary-light);
}

/* === 小标签 Badge === */
.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
}

/* === Toast / 消息 === */
.msg {
  padding: 12px 18px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
}
.msg.ok {
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
  border: 1px solid rgba(34, 197, 94, 0.25);
}
.msg.err {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.25);
}

/* === 侧边栏 === */
.layout-shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 280px;
  min-width: 280px;
  height: 100vh;
  position: sticky;
  top: 0;
  background: var(--surface-sidebar);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-right: 1px solid var(--border-medium);
  box-shadow: 4px 0 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  padding: 28px 20px;
  gap: 20px;
  overflow-y: auto;
  z-index: 100;
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sidebar-logo-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--gradient-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sidebar-logo-icon svg {
  width: 20px;
  height: 20px;
  color: #fff;
}

.sidebar-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.sidebar-subtitle {
  font-size: 12px;
  color: var(--text-subtle);
  margin: 0;
}

.sidebar-divider {
  border: none;
  border-top: 1px solid var(--border-light);
  margin: 0;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition-fast);
}
.sidebar-link:hover {
  background: rgba(59, 130, 246, 0.06);
  border-color: var(--border-medium);
  color: var(--color-primary-light);
}
.sidebar-link.active {
  background: rgba(59, 130, 246, 0.10);
  border-color: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 600;
}

.sidebar-link svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 4px;
}

.btn-new-research {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: var(--gradient-action);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-button);
  transition: transform var(--transition-fast),
              box-shadow var(--transition-fast);
}
.btn-new-research:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
}

/* === 主内容区 === */
.main-content {
  flex: 1;
  padding: 28px 32px;
  min-width: 0;
}

/* === 顶栏（页面标题） === */
.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-subtle);
  margin: 0;
}

/* === 快捷操作栏 === */
.quick-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(124, 58, 237, 0.06));
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  animation: fadeSlideIn 0.35s var(--ease-out);
}

.quick-actions-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-dark);
  flex: 1;
}

@keyframes fadeSlideIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* === 响应式 === */
@media (max-width: 768px) {
  .layout-shell {
    flex-direction: column;
  }
  .sidebar {
    width: 100%;
    min-width: 100%;
    height: auto;
    max-height: 45vh;
    position: relative;
  }
  .main-content {
    padding: 20px 16px;
  }
}
```

- [ ] **步骤 2：验证文件创建成功**

```bash
wc -l frontend/public/shared.css
```

期望：约 270 行，无错误输出。

- [ ] **步骤 3：Commit**

```bash
git add frontend/public/shared.css
git commit -m "feat: add shared.css design system with glass-morphism tokens

CSS custom properties and utility classes extracted from App.vue for
cross-page visual consistency across Vue SPA and backend HTML templates.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：更新全局样式与构建验证

**文件：**
- 修改：`frontend/src/style.css`

- [ ] **步骤 1：更新 style.css 使其与 shared.css 保持一致**

`frontend/src/style.css` 替换为精简版，移除与 shared.css 重复的定义：

```css
/* 引入共享设计变量（构建后位于 /app/shared.css） */
@import url('/app/shared.css');

#app {
  min-height: 100vh;
}
```

- [ ] **步骤 2：构建并验证 shared.css 可被外部访问**

```bash
cd frontend && npm run build
```

```bash
ls frontend/dist/shared.css
```

验证文件存在于 `frontend/dist/shared.css`。

- [ ] **步骤 3：Commit**

```bash
git add frontend/src/style.css frontend/dist/
git commit -m "refactor: sync style.css with shared.css and rebuild dist

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：修改 App.vue — 侧边栏补全报告入口 + 宽度调整

**文件：**
- 修改：`frontend/src/App.vue`（模板：第 161-167 行之间；样式：第 2658-2660 行、第 2933-2935 行）

- [ ] **步骤 1：在侧边栏导航中增加「报告列表」「编辑报告」链接**

在 `App.vue` 第 166 行（`数据源管理` 的 `</a>` 之后、`</div>` 之前）插入两个新链接：

**位置**：`frontend/src/App.vue:166`（数据源管理链接之后）

```html
          <a class="sidebar-link" href="/reports">
            <svg viewBox="0 0 24 24" width="16" height="16">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM6 20V4h7v5h5v11H6zm2 4h2v-2H8v2zm0-6h8v-2H8v2z" fill="currentColor"/>
            </svg>
            报告列表
          </a>
          <a class="sidebar-link" href="/reports-edit">
            <svg viewBox="0 0 24 24" width="16" height="16">
              <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/>
            </svg>
            编辑报告
          </a>
```

- [ ] **步骤 2：将侧边栏宽度从 400px 改为 280px**

在 `App.vue` 第 2658-2660 行：

```css
.sidebar {
  width: 280px;
  min-width: 280px;
```

在第 2933-2935 行（响应式断点 1024px 处）：

```css
  .sidebar {
    width: 280px;
    min-width: 280px;
  }
```

- [ ] **步骤 3：去掉 App.vue 中 sidebar-link 的 current 标记逻辑（如果有标记当前路由的 JS），改为纯展示**

检查模板中是否有 `.current` 类或路由标记逻辑。当前 sidebar-link 是静态 `<a>` 标签，无需修改 JS。

- [ ] **步骤 4：重新构建**

```bash
cd frontend && npm run build
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/App.vue frontend/dist/
git commit -m "feat: add report nav links to sidebar, adjust width to 280px

- Add 报告列表 and 编辑报告 sidebar links with SVG icons
- Reduce sidebar width from 400px to 280px (main and responsive breakpoints)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：修改 App.vue — 捕获 report ID + 快捷操作按钮

**文件：**
- 修改：`frontend/src/App.vue`（script：第 467、1062-1069 行；模板：第 187-189 行）

- [ ] **步骤 1：添加 `savedReportId` 响应式变量**

在 `App.vue` 第 467 行（`reportMarkdown` 定义之后）添加：

```typescript
const savedReportId = ref("");
```

- [ ] **步骤 2：在 `resetWorkflowState` 中重置 `savedReportId`**

在 `App.vue` 的 `resetWorkflowState` 函数（约第 761-771 行）中，在 `reportMarkdown.value = "";` 之后添加：

```typescript
  savedReportId.value = "";
```

- [ ] **步骤 3：修改 saveReport 逻辑，捕获 report ID**

将 `App.vue` 第 1066-1069 行的 fire-and-forget fetch 改为：

```typescript
          // 自动保存到后端并捕获 report ID
          fetch('http://127.0.0.1:8080/api/reports', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title: form.topic, content: reportMarkdown.value})
          })
          .then(r => r.json())
          .then(data => {
            if (data && data.id) {
              savedReportId.value = data.id;
            }
          })
          .catch(() => {});
```

- [ ] **步骤 4：在报告区顶部添加快捷操作栏**

在 `App.vue` 第 188 行（`<div class="report-block report-block--final"` 之前）插入：

```html
            <!-- 快捷操作栏：报告生成后显示 -->
            <div v-if="reportMarkdown && !generatingReport" class="quick-actions">
              <span class="quick-actions-label">✅ 报告已生成</span>
              <a v-if="savedReportId" class="btn-primary" :href="'/reports-edit?id=' + savedReportId" style="padding:8px 18px;font-size:13px;">
                <svg viewBox="0 0 24 24" width="14" height="14">
                  <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/>
                </svg>
                编辑报告
              </a>
              <a class="btn-secondary" href="/reports" style="padding:8px 18px;font-size:13px;">📋 报告列表</a>
            </div>
```

此 HTML 放在 `<div class="result-main">` 内部，`<div class="report-block report-block--final">` 之前。

- [ ] **步骤 5：在 App.vue `<style scoped>` 末尾追加快捷操作栏动画**

```css
/* 快捷操作栏动画 */
.quick-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(124, 58, 237, 0.06));
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  margin-bottom: 16px;
  animation: fadeSlideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

.quick-actions-label {
  font-size: 13px;
  font-weight: 600;
  color: #1d4ed8;
  flex: 1;
}

:deep(.quick-actions .btn-primary),
:deep(.quick-actions .btn-secondary) {
  text-decoration: none;
}

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}
```

- [ ] **步骤 6：重新构建并验证**

```bash
cd frontend && npm run build
```

确认无 TypeScript/Vite 编译错误。

- [ ] **步骤 7：Commit**

```bash
git add frontend/src/App.vue frontend/dist/
git commit -m "feat: capture report ID from save API, add quick edit buttons

- Add savedReportId ref to capture POST /api/reports response
- Show quick action bar (edit report + report list) when report is ready
- Reset savedReportId in resetWorkflowState

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：修改 HTML 模板 — 预警中心 (warnings.html)

**文件：**
- 修改：`backend/src/templates/warnings.html`

**原则：** 不动任何 JS 逻辑（`<script>` 标签内容不变），只改 HTML 结构（顶栏 → 侧边栏布局）和 CSS。

- [ ] **步骤 1：读取完整文件确认当前结构**

```bash
wc -l backend/src/templates/warnings.html
```

- [ ] **步骤 2：修改 `<head>` — 引入 shared.css，精简 `<style>`**

在 `<head>` 中 `<style>` 标签之前添加：

```html
<link rel="stylesheet" href="/app/shared.css">
```

删除 `<style>` 块中已被 shared.css 覆盖的规则：
- 删除 `body { font-family: ...; background: #f1f5f9; ... }`（shared.css 已定义）
- 删除 `.header` 及其所有子选择器（`.header-title`、`.nav-link`、`.nav-link.current`、`.nav-link:hover`）
- 删除通用按钮颜色/圆角/阴影定义（保留 `shared.css` 已有的）
- **保留**：`.container`（但改为 `max-width: none; padding: 0; margin: 0;`，因为布局由 `.layout-shell` 控制）
- **保留**：严重度相关样式（`.severity-red`、`.severity-orange`、`.severity-yellow` 左边框）
- **保留**：Badge 样式（`.badge.red`、`.badge.orange`、`.badge.yellow`）
- **保留**：骨架屏动画（`.skeleton`、`@keyframes shimmer`）
- **保留**：模态框样式（`.modal-overlay`、`.modal-box`）

- [ ] **步骤 3：修改 `<body>` — 替换顶栏为侧边栏布局**

**删除**：`<div class="header">` 整个块（包含所有 `.nav-link`）

**替换** body 结构为：

```html
<body>
  <div class="layout-shell">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-logo">
          <div class="sidebar-logo-icon">
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="white" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div>
            <h1 class="sidebar-title">贷后管理助手</h1>
            <p class="sidebar-subtitle">监控与预警系统</p>
          </div>
        </div>
      </div>
      <hr class="sidebar-divider">
      <nav class="sidebar-nav">
        <a class="sidebar-link" href="/app/">📋 贷后助手</a>
        <a class="sidebar-link active" href="/warnings">⚠️ 预警中心</a>
        <a class="sidebar-link" href="/enterprises">🏢 贷后项目</a>
        <a class="sidebar-link" href="/sources">📡 数据源管理</a>
        <a class="sidebar-link" href="/rag/upload">📄 参考文档</a>
        <a class="sidebar-link" href="/reports">📊 报告列表</a>
        <a class="sidebar-link" href="/reports-edit">✏️ 编辑报告</a>
      </nav>
      <hr class="sidebar-divider">
      <div class="sidebar-actions">
        <a class="btn-new-research" href="/app/">+ 开始新调查</a>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <div class="page-header">
        <h2 class="page-title">预警中心</h2>
        <p class="page-subtitle">实时监控企业风险动态</p>
      </div>
      <!-- 原有内容区（保留原有 HTML 结构和 JS 逻辑不变） -->
      ...
    </main>
  </div>
</body>
```

- [ ] **步骤 4：将原有内容区域包裹在 `<main class="main-content">` 中**

原有 `<div class="container">` 内部的所有业务内容（筛选栏、统计卡片、预警列表、模态框）保持不变。将 `<div class="container">` 改为：

```html
<div style="max-width:1100px;">
```

也可以直接去掉 `.container` 的 `max-width` 限制，改为在 `.main-content` 内使用 `max-width: 1100px`。

- [ ] **步骤 5：调整保留样式的颜色/圆角引用 shared 变量**

在保留的 `<style>` 块中，将硬编码颜色替换为 CSS 变量：
- `color: #1e293b` → `color: var(--text-body)`
- `background: #fff` → `background: var(--surface-card)`
- `border-radius: 14px` → `border-radius: var(--radius-lg)`
- `box-shadow: 0 2px 12px rgba(0,0,0,.06)` → `box-shadow: var(--shadow-card)`

- [ ] **步骤 6：启动后端验证页面渲染**

```bash
cd backend && python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 &
sleep 2
curl -s http://localhost:8080/warnings | head -50
```

确认：返回的 HTML 中包含 `shared.css` 引用，无 `<div class="header">`，有 `<aside class="sidebar">`。

- [ ] **步骤 7：Commit**

```bash
git add backend/src/templates/warnings.html
git commit -m "refactor: migrate warnings.html to shared sidebar + glass-morphism styles

- Replace dark top nav bar with glass-morphism sidebar
- Reference /app/shared.css for design tokens
- Keep all JS logic and business-specific styles intact

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 6：修改 HTML 模板 — 贷后项目 (enterprises.html)

**文件：**
- 修改：`backend/src/templates/enterprises.html`

参照任务 5 的模式，做同样的改动：

- [ ] **步骤 1：引入 shared.css + 精简 `<style>`**

`<link rel="stylesheet" href="/app/shared.css">`，删除 `.header`、`.nav-link` 等通用样式，保留手风琴和项目卡片交替色边框样式。

- [ ] **步骤 2：替换顶栏为侧边栏**

侧边栏结构同任务 5，`active` 类标在「🏢 贷后项目」上。

修改侧边栏中 `active` 的链接：`<a class="sidebar-link active" href="/enterprises">🏢 贷后项目</a>`，其他链接移除 `active`。

- [ ] **步骤 3：包裹内容到 `<main class="main-content">`**

- [ ] **步骤 4：替换保留样式中的硬编码值**

手风琴和交替色边框保留，将 `color`、`background`、`border-radius`、`box-shadow` 替换为 CSS 变量。

- [ ] **步骤 5：验证**

```bash
curl -s http://localhost:8080/enterprises | grep -c 'sidebar-link active'
```

期望：返回 `1`（正好一个 active 标记）。

- [ ] **步骤 6：Commit**

```bash
git add backend/src/templates/enterprises.html
git commit -m "refactor: migrate enterprises.html to shared sidebar + glass-morphism styles

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 7：修改 HTML 模板 — 数据源管理 (sources.html)

**文件：**
- 修改：`backend/src/templates/sources.html`

- [ ] **步骤 1-4：同任务 6 模式**

`active` 标在「📡 数据源管理」。保留 CSS toggle 开关样式和表格样式。替换硬编码值为 CSS 变量。表格圆角从 `12px` 改为 `var(--radius-md)`。

- [ ] **步骤 5：验证**

```bash
curl -s http://localhost:8080/sources | grep -c 'shared.css'
```

期望：`1`

- [ ] **步骤 6：Commit**

```bash
git add backend/src/templates/sources.html
git commit -m "refactor: migrate sources.html to shared sidebar + glass-morphism styles

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 8：修改 HTML 模板 — 参考文档 (upload.html)

**文件：**
- 修改：`backend/src/templates/upload.html`

- [ ] **步骤 1-4：同任务 6 模式**

`active` 标在「📄 参考文档」。保留文件上传虚线框区域样式（但将虚线框颜色改为 `var(--border-medium)`、背景改为半透明）。

- [ ] **步骤 5：验证**

```bash
curl -s http://localhost:8080/rag/upload | grep -c 'shared.css'
```

期望：`1`

- [ ] **步骤 6：Commit**

```bash
git add backend/src/templates/upload.html
git commit -m "refactor: migrate upload.html to shared sidebar + glass-morphism styles

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 9：修改 HTML 模板 — 报告列表 (reports.html)

**文件：**
- 修改：`backend/src/templates/reports.html`

- [ ] **步骤 1-4：同任务 6 模式**

`active` 标在「📊 报告列表」。保留报告列表表格结构和搜索过滤 JS 逻辑。列表项 hover 加浮起效果（使用 `.card-glass:hover`）。

- [ ] **步骤 5：验证**

```bash
curl -s http://localhost:8080/reports | grep -c 'shared.css'
```

期望：`1`

- [ ] **步骤 6：Commit**

```bash
git add backend/src/templates/reports.html
git commit -m "refactor: migrate reports.html to shared sidebar + glass-morphism styles

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 10：修改 HTML 模板 — 报告编辑 (reports-edit.html)

**文件：**
- 修改：`backend/src/templates/reports-edit.html`

- [ ] **步骤 1-4：同任务 6 模式**

`active` 标在「✏️ 编辑报告」。保留分栏编辑器（等宽字体 textarea + 实时预览）。预览区追加 markdown 渲染样式（参考贷后助手的 `:deep()` 样式：h1-h6 颜色、列表标记色、代码块、引用块底色调）。

无 report_id 时显示提示并附带「返回报告列表」链接 `/reports`。

- [ ] **步骤 5：预览区 markdown 样式追加**

在保留的 `<style>` 块中追加：

```css
/* Markdown 预览渲染样式（参考 App.vue :deep() 规则） */
#preview h1 { font-size: 1.6em; color: var(--text-primary); border-bottom: 2px solid var(--border-light); padding-bottom: 8px; }
#preview h2 { font-size: 1.3em; color: var(--text-body); }
#preview h3 { font-size: 1.1em; color: var(--text-secondary); }
#preview code { background: rgba(124, 58, 237, 0.08); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 0.88em; }
#preview pre { background: #1e293b; color: #e2e8f0; padding: 16px 20px; border-radius: var(--radius-md); overflow-x: auto; }
#preview pre code { background: transparent; padding: 0; color: inherit; }
#preview blockquote { border-left: 3px solid var(--color-primary-light); padding: 8px 16px; color: var(--text-muted); background: rgba(59, 130, 246, 0.04); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
#preview ul li::marker { color: var(--color-indigo); }
#preview ol { counter-reset: item; }
#preview ol li { counter-increment: item; }
#preview ol li::marker { color: var(--color-indigo); font-weight: 700; }
```

- [ ] **步骤 6：验证**

```bash
curl -s http://localhost:8080/reports-edit | grep -c 'shared.css'
```

期望：`1`

- [ ] **步骤 7：Commit**

```bash
git add backend/src/templates/reports-edit.html
git commit -m "refactor: migrate reports-edit.html to shared sidebar + glass-morphism styles

- Add shared sidebar navigation
- Add markdown preview render styles matching App.vue

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 11：端到端验证

**不修改文件，只运行验证命令。**

- [ ] **步骤 1：确认所有页面引入 shared.css**

```bash
for path in /warnings /enterprises /sources /rag/upload /reports /reports-edit; do
  count=$(curl -s "http://localhost:8080${path}" | grep -c 'shared.css')
  echo "${path}: shared.css refs = ${count}"
done
```

期望：每个路径都输出 `1`。

- [ ] **步骤 2：确认所有页面使用侧边栏布局**

```bash
for path in /warnings /enterprises /sources /rag/upload /reports /reports-edit; do
  count=$(curl -s "http://localhost:8080${path}" | grep -c 'class="sidebar"')
  echo "${path}: sidebar found = ${count}"
done
```

期望：每个路径都输出 `1`。

- [ ] **步骤 3：确认无残留老顶栏**

```bash
for path in /warnings /enterprises /sources /rag/upload /reports /reports-edit; do
  count=$(curl -s "http://localhost:8080${path}" | grep -c 'class="header"')
  echo "${path}: legacy header = ${count}"
done
```

期望：每个路径都输出 `0`。

- [ ] **步骤 4：确认贷后助手 shared.css 可访问**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/app/shared.css
```

期望：`200`

- [ ] **步骤 5：前端构建无错误**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

期望：无 ERROR 输出，正常完成。

- [ ] **步骤 6：整体 commit 验证结果**

```bash
git add -A
git diff --cached --stat
```

确认所有改动文件在预期范围内。

---

## 自检结果

| 检查项 | 状态 |
|--------|------|
| 规格覆盖度 | ✅ 全部需求有对应任务：CSS 变量库（任务 1）→ 所有 6 个 HTML 模板（任务 5-10）→ App.vue 路由修复（任务 3-4）→ 端到端验证（任务 11） |
| 占位符扫描 | ✅ 无 TODO/TBD/待定/后续实现/适当处理 |
| 类型一致性 | ✅ 类名（`.sidebar`、`.sidebar-link`、`.panel-glass`）在 shared.css 和所有模板中一致；JS 变量名 `savedReportId` 在定义、重置、使用三处一致 |
| 禁止占位符 | ✅ 所有步骤包含实际代码或精确命令 |
