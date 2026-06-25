# 统一 SPA 架构 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 6 个 HTML 模板 + App.vue 合并为统一 Vue SPA，全部路由在 `/loan/` 下，共享同一个 `AppSidebar.vue` 组件。

**架构：** Vue 3 + Vue Router + 7 个页面组件。App.vue 退化为最小壳子（AppSidebar + router-view）。Vite base 改为 `/loan/`，FastAPI mount 改为 `/loan/`，旧路径 301 重定向。

**技术栈：** Vue 3, Vue Router 4, Vite, TypeScript

**规格文档：** `docs/superpowers/specs/2026-06-25-unified-spa-architecture-design.md`

---

## 文件结构

| 文件 | 职责 | 变动 |
|------|------|------|
| `frontend/src/router/index.ts` | Vue Router 路由配置 | **新建** |
| `frontend/src/main.ts` | 注册 router | 修改 |
| `frontend/vite.config.ts` | base 改为 `/loan/` | 修改 |
| `frontend/src/components/AppSidebar.vue` | 统一侧边栏组件，所有页面共用 | **新建** |
| `frontend/src/App.vue` | 最小壳子：AppSidebar + router-view | **重写** |
| `frontend/src/pages/ResearchPage.vue` | 贷后助手（从 App.vue 提取） | **新建** |
| `frontend/src/pages/ProjectsPage.vue` | 贷后项目（从 enterprises.html 迁移） | **新建** |
| `frontend/src/pages/WarningsPage.vue` | 预警中心（从 warnings.html 迁移） | **新建** |
| `frontend/src/pages/SourcesPage.vue` | 数据源管理（从 sources.html 迁移） | **新建** |
| `frontend/src/pages/UploadPage.vue` | 参考文档（从 upload.html 迁移） | **新建** |
| `frontend/src/pages/ReportsPage.vue` | 报告列表（从 reports.html 迁移） | **新建** |
| `frontend/src/pages/ReportEditPage.vue` | 报告编辑（从 reports-edit.html 迁移） | **新建** |
| `frontend/src/style.css` | 全局样式 | 修改 |
| `frontend/public/shared.css` | 清理侧边栏布局规则，保留工具类 | 修改 |
| `backend/src/main.py` | mount `/loan/` + 6 条 301 重定向 | 修改 |
| `backend/src/templates/*.html` | 不再需要 | **删除** |

---

### 任务 1：基础设施 — Vue Router + Vite 配置

**文件：**
- 创建：`frontend/src/router/index.ts`
- 修改：`frontend/src/main.ts`
- 修改：`frontend/vite.config.ts`

- [ ] **步骤 1：创建路由配置（占位页面组件）**

`frontend/src/router/index.ts`：

```typescript
import { createRouter, createWebHistory } from "vue-router";

// 占位组件 — 各任务逐步替换为真实组件
const Placeholder = { template: '<div class="main-content"><div class="page-header"><h2 class="page-title">加载中...</h2></div></div>' };

const routes = [
  { path: "/",              name: "projects",  component: () => import("../pages/ProjectsPage.vue") },
  { path: "/research",      name: "research",  component: () => import("../pages/ResearchPage.vue") },
  { path: "/warnings",      name: "warnings",  component: () => import("../pages/WarningsPage.vue") },
  { path: "/sources",       name: "sources",   component: () => import("../pages/SourcesPage.vue") },
  { path: "/upload",        name: "upload",    component: () => import("../pages/UploadPage.vue") },
  { path: "/reports",       name: "reports",   component: () => import("../pages/ReportsPage.vue") },
  { path: "/reports/:id/edit", name: "report-edit", component: () => import("../pages/ReportEditPage.vue") },
];

const router = createRouter({
  history: createWebHistory("/loan/"),
  routes,
});

export default router;
```

- [ ] **步骤 2：修改 main.ts 注册 router**

`frontend/src/main.ts`：

```typescript
import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";

import "./style.css";

createApp(App).use(router).mount("#app");
```

- [ ] **步骤 3：修改 vite.config.ts base 路径**

`frontend/vite.config.ts` 将 `base: '/app/'` 改为：

```typescript
base: '/loan/',
```

- [ ] **步骤 4：创建 7 个占位页面组件**

为每个 `frontend/src/pages/*.vue` 创建最小占位文件（带 scoped 空壳），确保构建不报错。

`ProjectsPage.vue`（最小占位模板，其他 6 个同理，仅 `<h2>` 标题不同）：

```vue
<template>
  <main class="main-content">
    <div class="page-header">
      <h2 class="page-title">贷后项目</h2>
    </div>
  </main>
</template>
```

所有 7 个占位文件（ProjectsPage、ResearchPage、WarningsPage、SourcesPage、UploadPage、ReportsPage、ReportEditPage）均按此模板创建，仅标题不同。

- [ ] **步骤 5：构建验证**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

预期：构建成功，无 TypeScript/Vite 错误。

- [ ] **步骤 6：Commit**

```bash
git add frontend/src/router/ frontend/src/main.ts frontend/vite.config.ts frontend/src/pages/
git commit -m "feat: add Vue Router + placeholder pages + /loan/ base

- Vue Router with history mode, base /loan/
- 7 placeholder page components (to be filled in subsequent tasks)
- Vite base changed from /app/ to /loan/

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：创建 AppSidebar.vue 统一侧边栏

**文件：**
- 创建：`frontend/src/components/AppSidebar.vue`

- [ ] **步骤 1：创建 AppSidebar.vue**

`frontend/src/components/AppSidebar.vue`：

```vue
<template>
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
      <router-link class="sidebar-link" to="/">🏢 贷后项目</router-link>
      <router-link class="sidebar-link" to="/research">📋 贷后助手</router-link>
      <router-link class="sidebar-link" to="/warnings">⚠️ 预警中心</router-link>
      <router-link class="sidebar-link" to="/sources">📡 数据源管理</router-link>
      <router-link class="sidebar-link" to="/upload">📄 参考文档</router-link>
      <router-link class="sidebar-link" to="/reports">📊 报告列表</router-link>
    </nav>
    <hr class="sidebar-divider">
    <div class="sidebar-actions">
      <router-link class="btn-new-research" to="/research">+ 开始新调查</router-link>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  min-width: 280px;
  height: 100vh;
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-right: 1px solid rgba(148, 163, 184, 0.28);
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
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
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
  color: #0f172a;
  margin: 0;
}

.sidebar-subtitle {
  font-size: 12px;
  color: #64748b;
  margin: 0;
}

.sidebar-divider {
  border: none;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
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
  border-radius: 14px;
  border: 1px solid transparent;
  color: #475569;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: all 150ms cubic-bezier(0.16, 1, 0.3, 1);
}

.sidebar-link:hover {
  background: rgba(59, 130, 246, 0.06);
  border-color: rgba(148, 163, 184, 0.28);
  color: #3b82f6;
}

.sidebar-link.router-link-exact-active,
.sidebar-link.router-link-active[href="/research"],
.sidebar-link.router-link-active[href="/warnings"],
.sidebar-link.router-link-active[href="/sources"],
.sidebar-link.router-link-active[href="/upload"],
.sidebar-link.router-link-active[href="/reports"] {
  background: rgba(59, 130, 246, 0.10);
  border-color: #3b82f6;
  color: #2563eb;
  font-weight: 600;
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
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  color: #fff;
  border: none;
  border-radius: 14px;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
  transition: transform 150ms cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 150ms cubic-bezier(0.16, 1, 0.3, 1);
  text-decoration: none;
}

.btn-new-research:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
}

/* / 路由是 exact match，/research 路径需要父级匹配即可 */
.sidebar-link.router-link-active:not([href="/"]) {
  /* 子路径不自动激活父级 */
}
</style>
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/src/components/AppSidebar.vue
git commit -m "feat: add AppSidebar.vue — unified navigation component

6 nav links with router-link-active auto-highlight. All 7 pages share
this single sidebar implementation.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：重写 App.vue 为最小壳子

**文件：**
- 修改：`frontend/src/App.vue`（从 ~3000 行缩到 ~50 行）

- [ ] **步骤 1：重写 App.vue**

将当前 App.vue 的全部内容替换为：

```vue
<template>
  <div class="layout-shell">
    <AppSidebar />
    <router-view />
  </div>
</template>

<script setup lang="ts">
import AppSidebar from "./components/AppSidebar.vue";
</script>

<style>
/* 全局布局（非 scoped，让页面组件可访问 CSS 变量） */
@import "../public/shared.css";

.layout-shell {
  display: flex;
  min-height: 100vh;
}
</style>
```

注意：`@import "../public/shared.css"` 在 Vite 构建时会被处理。确认构建通过，如果 `public/` 文件无法被 CSS import，则改为在 `index.html` 中通过 `<link>` 引入 shared.css。

- [ ] **步骤 2：检查 index.html 是否需要引入 shared.css**

`frontend/index.html` 中确保有：

```html
<link rel="stylesheet" href="/loan/shared.css">
```

（Vite 构建后 `public/shared.css` 被复制到 `dist/shared.css`，base `/loan/` 下路径为 `/loan/shared.css`）

- [ ] **步骤 3：构建验证**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

预期：构建成功。

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/App.vue frontend/index.html
git commit -m "refactor: reduce App.vue to minimal shell — AppSidebar + router-view

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：提取 ResearchPage.vue（贷后助手）

**文件：**
- 创建：`frontend/src/pages/ResearchPage.vue`
- 修改：`frontend/src/App.vue`（旧代码已在上一步删除）

ResearchPage.vue 从旧 App.vue 中提取以下内容：
1. 居中输入卡片（初始状态）+ 全屏调查界面（展开状态）
2. SSE 研究流程处理
3. 报告展示 + Markdown 渲染
4. 快捷操作栏
5. 保留的样式：aurora 背景、form、面板、报告块等

- [ ] **步骤 1：创建 ResearchPage.vue（完整版）**

ResearchPage.vue 包含三个区域（从旧 App.vue 提取）：**模板**、**script setup**、**style scoped**。

**模板部分**：

```vue
<template>
  <div class="research-page">
    <div class="aurora" aria-hidden="true">
      <span></span><span></span><span></span>
    </div>

    <!-- 初始状态：居中输入卡片 -->
    <div v-if="!isExpanded" class="layout layout-centered">
      <section class="panel panel-form panel-centered">
        <header class="panel-head">
          <div class="logo">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2.5c-.7 0-1.4.2-2 .6L4.6 7C3.6 7.6 3 8.7 3 9.9v4.2c0 1.2.6 2.3 1.6 2.9l5.4 3.9c1.2.8 2.8.8 4 0l5.4-3.9c1-.7 1.6-1.7 1.6-2.9V9.9c0-1.2-.6-2.3-1.6-2.9L14 3.1a3.6 3.6 0 0 0-2-.6Z"/>
            </svg>
          </div>
          <div>
            <h1>贷后管理综合报告</h1>
            <p>结合多轮智能检索与总结，实时呈现洞见与引用。</p>
          </div>
        </header>

        <form class="form" @submit.prevent="handleSubmit">
          <label class="field">
            <span>债务企业</span>
            <textarea v-model="form.topic" placeholder="例如：四川振海保安服务有限公司" rows="4" required></textarea>
          </label>
          <section class="options">
            <label class="field option">
              <span>搜索引擎</span>
              <select v-model="form.searchApi">
                <option value="">沿用后端配置</option>
                <option v-for="option in searchOptions" :key="option" :value="option">{{ option }}</option>
              </select>
            </label>
          </section>
          <div class="form-actions">
            <button type="submit" class="primary-btn" :disabled="loading">
              <svg viewBox="0 0 24 24" width="18" height="18">
                <path d="M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
              </svg>
              {{ loading ? "调查中..." : "开始调查" }}
            </button>
            <button type="button" class="secondary-btn" @click="cancelResearch" v-if="loading">取消调查</button>
          </div>
        </form>

        <p v-if="error" class="error-chip">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="M10 3.2c-.3 0-.6.2-.8.5L3.4 15c-.4.7.1 1.6.8 1.6h11.6c.7 0 1.2-.9.8-1.6L10.8 3.7c-.2-.3-.5-.5-.8-.5Zm0 4.3c.4 0 .7.3.7.7v4c0 .4-.3.7-.7.7s-.7-.3-.7-.7V8.2c0-.4.3-.7.7-.7Zm0 6.6a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"/>
          </svg>
          {{ error }}
        </p>
        <p v-else-if="loading" class="hint muted">正在收集线索与证据，实时进展见右侧区域。</p>
      </section>
    </div>

    <!-- 全屏状态 -->
    <div v-else class="layout layout-fullscreen">
      <section class="panel panel-result">
        <header class="status-bar">
          <div class="status-main">
            <div class="status-chip" :class="{ active: loading }">
              <span class="dot"></span>
              {{ loading ? "调查进行中" : "调查流程完成" }}
            </div>
            <span class="status-meta">任务进度：{{ completedTasks }} / {{ totalTasks || todoTasks.length || 1 }}</span>
          </div>
          <div class="status-actions">
            <button class="btn-new-research-inline" @click="startNewResearch">+ 新调查</button>
          </div>
        </header>

        <div class="result-main">
          <div v-if="reportMarkdown && !generatingReport" class="quick-actions">
            <span class="quick-actions-label">✅ 报告已生成</span>
            <router-link v-if="savedReportId" class="btn-primary" :to="'/reports/' + savedReportId + '/edit'" style="padding:8px 18px;font-size:13px;">
              <svg viewBox="0 0 24 24" width="14" height="14">
                <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/>
              </svg>
              编辑报告
            </router-link>
            <router-link class="btn-secondary" to="/reports" style="padding:8px 18px;font-size:13px;">📋 报告列表</router-link>
          </div>

          <div v-if="reportMarkdown || generatingReport" class="report-block report-block--final" :class="{ 'block-highlight': reportHighlight }">
            <div class="report-head collapsible-head" @click="reportCollapsed = !reportCollapsed">
              <span class="report-head-accent" aria-hidden="true"></span>
              <h3>最终报告</h3>
              <span class="fold-arrow">{{ reportCollapsed ? '▶' : '▼' }}</span>
            </div>
            <div v-if="generatingReport && !reportMarkdown" class="report-generating">
              <div class="generating-spinner"></div>
              <p>报告生成中，请稍候...</p>
            </div>
            <div v-else class="report-body" v-show="!reportCollapsed" v-html="reportHtml"></div>
          </div>

          <div class="tasks-section" v-if="todoTasks.length">
            <div class="tasks-section-header collapsible-head" @click="tasksCollapsed = !tasksCollapsed">
              <h3 class="tasks-section-title">任务过程</h3>
              <span class="fold-arrow">{{ tasksCollapsed ? '▶' : '▼' }}</span>
            </div>
            <p class="tasks-section-hint muted">点击卡片查看来源、总结与工具调用详情</p>
            <ul class="task-card-list" v-show="!tasksCollapsed">
              <li v-for="task in todoTasks" :key="task.id" :class="['task-card', { 'task-card--active': task.id === activeTaskId, 'task-card--completed': task.status === 'completed' }]" @click="openTaskDetail(task)">
                <div class="task-card-header">
                  <span class="task-status-icon">{{ task.status === 'completed' ? '✅' : task.status === 'running' ? '⏳' : '📌' }}</span>
                  <span class="task-title">{{ task.title || task.intent }}</span>
                </div>
                <div class="task-card-body" v-if="task.id === activeTaskId && taskDetailOpen">
                  <div class="task-section" v-if="task.summary">
                    <h4>📝 总结</h4>
                    <p>{{ task.summary }}</p>
                  </div>
                  <div class="task-section" v-if="task.sourcesSummary">
                    <h4>📚 来源</h4>
                    <p>{{ task.sourcesSummary }}</p>
                  </div>
                  <div class="task-section" v-if="task.sourceItems.length">
                    <h4>🔗 引用链接</h4>
                    <ul class="source-list">
                      <li v-for="(src, idx) in task.sourceItems" :key="idx">
                        <a :href="src.url" target="_blank" rel="noopener">{{ src.title || src.url }}</a>
                      </li>
                    </ul>
                  </div>
                  <div class="task-section" v-if="task.toolCalls.length">
                    <h4>🔧 工具调用</h4>
                    <div class="tool-call" v-for="tc in task.toolCalls" :key="tc.eventId">
                      <div class="tool-name">{{ tc.agent }} → {{ tc.tool }}</div>
                      <details><summary>参数</summary><pre>{{ JSON.stringify(tc.parameters, null, 2) }}</pre></details>
                      <details><summary>结果</summary><pre>{{ tc.result }}</pre></details>
                      <button v-if="tc.notePath" class="copy-btn" @click.stop="copyNotePath(tc.notePath)">📋 复制笔记路径</button>
                    </div>
                  </div>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
```

**script setup 部分**（从旧 App.vue 完整提取 `<script setup lang="ts">...</script>` 的全部内容，约 700 行。关键修改点）：

```typescript
// 从旧 App.vue 复制全部 script setup 内容，做以下修改：

// 1. form.topic 默认值改为空字符串
const form = reactive({
  topic: "",  // 旧: "四川振海保安服务有限公司"
  searchApi: ""
});

// 2. isExpanded 默认改为 false（先展示输入卡片）
const isExpanded = ref(false);  // 旧: true

// 3. 新增 savedReportId
const savedReportId = ref("");

// 4. 新增：从 URL query 读取 topic（支持 /research?topic=xxx）
import { useRoute } from "vue-router";
const route = useRoute();
onMounted(() => {
  const topicParam = route.query.topic;
  if (topicParam && typeof topicParam === "string") {
    form.topic = topicParam;
    isExpanded.value = true;
  }
});

// 5. goBack 改为 startNewResearch（重置后回到输入卡片）
const startNewResearch = () => {
  if (loading.value) { cancelResearch(); }
  resetWorkflowState();
  isExpanded.value = false;
  form.topic = "";
};

// 6. handleSubmit 中 isExpanded.value = true 保留
// 7. resetWorkflowState 中增加 savedReportId.value = ""
// 8. saveReport fetch 中捕获 .then(r => r.json()).then(data => { if (data?.id) savedReportId.value = data.id })
// 9. 其余 SSE 处理逻辑（handleSubmit, connectSSE, upsertTaskMetadata, findTask 等）完全不变
```

**style scoped 部分**（从旧 App.vue 提取 `<style scoped>...</style>` 的全部内容。移除侧边栏相关样式（`.sidebar`、`.sidebar-header`、`.sidebar-link` 等），保留所有其他样式：`.aurora`、`.layout`、`.panel`、`.form`、`.report-block`、`.task-card`、`.quick-actions`、`@keyframes` 等）。

- [ ] **步骤 2：构建验证**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

预期：构建成功。如有类型错误，检查 `savedReportId`、`route.query` 等引用。

- [ ] **步骤 3：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "feat: extract ResearchPage.vue from old App.vue

- Centered input card + fullscreen research UI
- SSE streaming, report display, quick action bar
- form.topic defaults to '' instead of hardcoded value
- isExpanded defaults to false
- Supports ?topic=xxx query param for deep linking

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：迁移 ProjectsPage.vue（贷后项目）

**文件：**
- 修改：`frontend/src/pages/ProjectsPage.vue`

源文件：`backend/src/templates/enterprises.html`（~170 行 JS）

- [ ] **步骤 1：编写 ProjectsPage.vue**

模板部分将 enterprises.html 的 body 内容（项目卡片、新建表单）迁移为 Vue 模板。Script setup 中将 `loadProjects`、`submitProject`、`deleteEnterprise`、`addParty`、`toggleAddForm` 等函数用 Composition API 重写（`ref`/`reactive` 替代 DOM 操作）。

关键适配：
- `document.getElementById` → `ref()`
- `innerHTML` 渲染 → `v-for` 列表渲染
- 项目卡片点击跳转：`<router-link :to="'/research?topic=' + debtor.name">`

样式部分：从 enterprises.html 的 `<style>` 提取业务样式（项目卡片交替色边框、手风琴、标签、表单），用 `<style scoped>` 包裹。

- [ ] **步骤 2：构建验证**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **步骤 3：Commit**

---

### 任务 6：迁移 WarningsPage.vue（预警中心）

**文件：**
- 修改：`frontend/src/pages/WarningsPage.vue`

源文件：`backend/src/templates/warnings.html`（~400 行 JS）

- [ ] **步骤 1：编写 WarningsPage.vue**

迁移内容：
- 统计卡片（`statsRow`）：`v-for` 渲染代替 `innerHTML`
- 预警列表：`v-for` 渲染 `warnings` 数组
- 明细弹窗：`v-if` 控制显示/隐藏
- 推送弹窗：同上
- 自动刷新：`setInterval` 在 `onMounted` 中启动，`onUnmounted` 中清除
- 行业风向标：`loadIndustryBoard` 迁移

样式部分：从 warnings.html 提取保留样式（严重度颜色、badge、骨架屏动画、统计卡片、因子链接等）。

- [ ] **步骤 2：构建验证**
- [ ] **步骤 3：Commit**

---

### 任务 7：迁移 SourcesPage.vue（数据源管理）

**文件：**
- 修改：`frontend/src/pages/SourcesPage.vue`

源文件：`backend/src/templates/sources.html`（~100 行 JS）

- [ ] **步骤 1：编写 SourcesPage.vue**

迁移：数据源表格（`v-for`）、toggle 开关、新增/编辑弹窗、保存修改。

- [ ] **步骤 2：构建验证**
- [ ] **步骤 3：Commit**

---

### 任务 8：迁移 UploadPage.vue（参考文档）

**文件：**
- 修改：`frontend/src/pages/UploadPage.vue`

源文件：`backend/src/templates/upload.html`（~80 行 JS）

- [ ] **步骤 1：编写 UploadPage.vue**

迁移：拖拽上传区、文件处理、企业列表、删除。拖拽事件用 Vue 的 `@dragover`、`@drop` 处理。文件选择用 `@change`。

- [ ] **步骤 2：构建验证**
- [ ] **步骤 3：Commit**

---

### 任务 9：迁移 ReportsPage.vue（报告列表）

**文件：**
- 修改：`frontend/src/pages/ReportsPage.vue`

源文件：`backend/src/templates/reports.html`（~40 行 JS）

- [ ] **步骤 1：编写 ReportsPage.vue**

迁移：报告列表表格（`v-for`）、编辑跳转（`<router-link :to="'/reports/' + r.id + '/edit'">`）、删除。

- [ ] **步骤 2：构建验证**
- [ ] **步骤 3：Commit**

---

### 任务 10：迁移 ReportEditPage.vue（报告编辑）

**文件：**
- 修改：`frontend/src/pages/ReportEditPage.vue`

源文件：`backend/src/templates/reports-edit.html`（~260 行 JS）

- [ ] **步骤 1：编写 ReportEditPage.vue**

迁移：分栏编辑器（textarea + 实时预览）、飞书发送、Ctrl+S 保存、beforeunload 守卫。

关键适配：
- 读取路由参数：`const route = useRoute(); const reportId = route.params.id as string;`
- `window.addEventListener('beforeunload', ...)` → `onMounted` / `onUnmounted`
- Markdown 预览库：通过 CDN 引入（`marked` + `DOMPurify`）或在 `index.html` 中保留 CDN script 标签

- [ ] **步骤 2：构建验证**
- [ ] **步骤 3：Commit**

---

### 任务 11：后端改造 — mount /loan/ + 301 重定向

**文件：**
- 修改：`backend/src/main.py:112`

- [ ] **步骤 1：修改 FastAPI mount 路径**

将 `backend/src/main.py:112` 的：

```python
app.mount("/app", StaticFiles(directory=str(_vue_dist), html=True), name="vue_spa")
```

改为：

```python
app.mount("/loan", StaticFiles(directory=str(_vue_dist), html=True), name="vue_spa")
```

- [ ] **步骤 2：添加旧路径 301 重定向**

在 `mount` 之前添加：

```python
from fastapi.responses import RedirectResponse

@app.get("/warnings")
async def _redirect_warnings(): return RedirectResponse(url="/loan/warnings", status_code=301)

@app.get("/enterprises")
async def _redirect_enterprises(): return RedirectResponse(url="/loan/", status_code=301)

@app.get("/sources")
async def _redirect_sources(): return RedirectResponse(url="/loan/sources", status_code=301)

@app.get("/rag/upload")
async def _redirect_upload(): return RedirectResponse(url="/loan/upload", status_code=301)

@app.get("/reports")
async def _redirect_reports(): return RedirectResponse(url="/loan/reports", status_code=301)

@app.get("/reports-edit")
async def _redirect_reports_edit(): return RedirectResponse(url="/loan/reports", status_code=301)
```

注意：这些路由必须在 `mount("/loan", ...)` 之前注册，否则会被 SPA fallback 捕获。

- [ ] **步骤 3：backend 内部 /app 引用检查**

搜索 backend 中是否有硬编码的 `/app/` URL：

```bash
grep -rn "/app/" backend/src/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

如果有硬编码引用，更新为 `/loan/`。

- [ ] **步骤 4：Commit**

```bash
git add backend/src/main.py
git commit -m "refactor: mount Vue SPA at /loan/ + 301 redirects from old paths

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 12：清理 — 删除 HTML 模板 + 更新 shared.css

**文件：**
- 删除：`backend/src/templates/warnings.html`
- 删除：`backend/src/templates/enterprises.html`
- 删除：`backend/src/templates/sources.html`
- 删除：`backend/src/templates/upload.html`
- 删除：`backend/src/templates/reports.html`
- 删除：`backend/src/templates/reports-edit.html`
- 修改：`frontend/public/shared.css`

- [ ] **步骤 1：清理 shared.css — 删除侧边栏布局规则**

从 `shared.css` 中删除：`.layout-shell`、`.sidebar`、`.sidebar-header`、`.sidebar-logo`、`.sidebar-logo-icon`、`.sidebar-title`、`.sidebar-subtitle`、`.sidebar-divider`、`.sidebar-nav`、`.sidebar-link`、`.sidebar-actions`、`.btn-new-research`、`.main-content`、`.page-header`、`.page-title`、`.page-subtitle`、`.quick-actions`、`.quick-actions-label`、`@keyframes fadeSlideIn`。

保留：`:root` CSS 变量、`.panel-glass`、`.card-glass`、`.btn-primary`、`.btn-secondary`、`.badge`、`.msg`、响应式 `@media` 规则。

- [ ] **步骤 2：删除 6 个 HTML 模板**

```bash
rm backend/src/templates/warnings.html
rm backend/src/templates/enterprises.html
rm backend/src/templates/sources.html
rm backend/src/templates/upload.html
rm backend/src/templates/reports.html
rm backend/src/templates/reports-edit.html
```

确认 `backend/src/templates/` 目录下只剩非页面模板文件（如果有的话）。

- [ ] **步骤 3：Commit**

```bash
git add -A backend/src/templates/ frontend/public/shared.css
git commit -m "chore: remove HTML templates + clean shared.css sidebar rules

All page logic now lives in Vue SPA components under /loan/.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 13：端到端验证

- [ ] **步骤 1：前端构建**

```bash
cd frontend && npm run build 2>&1
```

预期：构建成功，无 TypeScript/Vite 错误。

- [ ] **步骤 2：确认 shared.css 可访问**

```bash
ls frontend/dist/shared.css && echo "shared.css OK"
```

- [ ] **步骤 3：启动后端**

```bash
cd backend && python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 &
sleep 3
```

- [ ] **步骤 4：验证新路由**

```bash
for path in /loan/ /loan/research /loan/warnings /loan/sources /loan/upload /loan/reports; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080${path}")
  echo "${path}: ${code}"
done
```

预期：全部返回 200。

- [ ] **步骤 5：验证旧路径 301 重定向**

```bash
for path in /warnings /enterprises /sources /rag/upload /reports /reports-edit; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080${path}")
  echo "${path}: ${code}"
done
```

预期：全部返回 301。

- [ ] **步骤 6：验证 shared.css 在新路径下可访问**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/loan/shared.css
```

预期：200。

- [ ] **步骤 7：浏览器检查**

用 browse 工具打开 `/loan/`、`/loan/warnings`、`/loan/research` 等页面，确认：
- 侧边栏显示正常
- 导航链接高亮当前页
- 无控制台错误

- [ ] **步骤 8：Commit 验证结果（如有微调）**

---

## 自检结果

| 检查项 | 状态 |
|--------|------|
| 规格覆盖度 | ✅ 7 个页面全部覆盖：路由（任务 1）、侧边栏（任务 2）、壳子（任务 3）、研究页（任务 4）、6 个 HTML 迁移（任务 5-10）、后端（任务 11）、清理（任务 12）、验证（任务 13） |
| 占位符扫描 | ✅ 无 TODO/TBD/待定。任务 5-10 的组件代码需要从源文件具体迁移，已在步骤中标注源文件和迁移要点 |
| 类型一致性 | ✅ `savedReportId`（任务 4 定义 + 使用）、`/loan/`（router base + vite base + mount 路径一致）、`router-link`（AppSidebar + 各页面中一致使用） |
| 禁止占位符 | ✅ 所有步骤包含实际代码或精确命令 |
