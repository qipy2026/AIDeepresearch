# ResearchPage Session 隔离 + 状态机 + UX 增强 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 ResearchPage "开启新调查"按钮的 7 个隐藏 bug，并增加企业选择 Combobox、过渡动画 3 项 UX 增强。

**架构：** 引入 `researchPhase` 显式状态机替代隐式 flags；`researchEpoch` 单调计数器实现 Session 隔离消除异步竞态；SSE 流分层清理协议。

**技术栈：** Vue 3 Composition API + TypeScript

**设计文档：** `docs/superpowers/specs/2026-06-25-research-session-isolation-and-ux-improvement-design.md`

---

## 文件结构

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `frontend/src/services/api.ts` | SSE 流服务，新增 `onReader` 回调暴露 reader 引用 | 修改（2 行） |
| `frontend/src/pages/ResearchPage.vue` | 调查页面，所有 10 项变更的主战场 | 重写（~100 行） |

---

### 任务 1：api.ts — 暴露 ReadableStream reader 引用

**文件：**
- 修改：`frontend/src/services/api.ts:14-22`

**目的：** 让调用方能拿到 `ReadableStreamDefaultReader`，以便取消时调用 `reader.cancel()`。

- [ ] **步骤 1：修改 `StreamOptions` 接口，增加 `onReader` 回调**

编辑 `frontend/src/services/api.ts`，找到第 14-16 行：

```typescript
export interface StreamOptions {
  signal?: AbortSignal;
}
```

替换为：

```typescript
export interface StreamOptions {
  signal?: AbortSignal;
  onReader?: (reader: ReadableStreamDefaultReader<Uint8Array>) => void;
}
```

- [ ] **步骤 2：在 `reader` 创建后调用 `onReader`**

找到 `runResearchStream` 函数中 `const reader = body.getReader();` 行（第 45 行），在其后插入：

```typescript
const reader = body.getReader();
options.onReader?.(reader);  // ← 新增：暴露 reader 供调用方取消
```

- [ ] **步骤 3：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit src/services/api.ts 2>&1 | head -5
```

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(api): expose SSE reader via onReader callback for graceful cancellation

Required for B3 fix — caller can now call reader.cancel() before aborting fetch.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：ResearchPage.vue — 引入状态机 + Session 隔离基础设施

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue`

**目的：** 添加 `researchPhase` ref、`researchEpoch` ref、`currentReader` ref，以及 `loading`/`isExpanded`/`generatingReport` 三个向后兼容的 computed。

- [ ] **步骤 1：替换 3 个独立 ref + 新增基础设施**

找到第 400-406 行：

```typescript
const loading = ref(false);
const error = ref("");
const progressLogs = ref<string[]>([]);
const isExpanded = ref(false);
const generatingReport = ref(false);
const reportCollapsed = ref(false);
const tasksCollapsed = ref(false);
```

替换为：

```typescript
// --- 状态机 ---
type ResearchPhase = 'idle' | 'running' | 'generating' | 'done' | 'error';
const researchPhase = ref<ResearchPhase>('idle');

// 向后兼容 computed（模板中 loading/isExpanded/generatingReport 不变）
const loading = computed(() => researchPhase.value === 'running' || researchPhase.value === 'generating');
const isExpanded = computed(() => researchPhase.value !== 'idle');
const generatingReport = computed(() => researchPhase.value === 'generating');

// --- Session 隔离 ---
const researchEpoch = ref(0);

// --- SSE 资源 ---
let currentController: AbortController | null = null;
let currentReader: ReadableStreamDefaultReader<Uint8Array> | null = null;

// --- 其他状态（不变） ---
const error = ref("");
const progressLogs = ref<string[]>([]);
const reportCollapsed = ref(false);
const tasksCollapsed = ref(false);
```

删除原来的 `let currentController: AbortController | null = null;` 行（第 432 行，因为上面已经声明）。

- [ ] **步骤 2：验证 `computed` 已从 `vue` 导入**

第 338 行已经导入 `computed`，确认无需修改：

```typescript
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
```

- [ ] **步骤 3：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "refactor(research): introduce researchPhase state machine and researchEpoch session isolation

- Replace loading/isExpanded/generatingReport refs with researchPhase enum
- Add backward-compatible computed properties for template compatibility
- Add researchEpoch ref for session isolation
- Add currentReader tracking for SSE cleanup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：ResearchPage.vue — SSE 分层清理协议

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue:1055-1061, 744-753`

**目的：** 修复 B3（reader 未取消）、B4（取消日志丢失）、B5（controller 检查不一致）。

- [ ] **步骤 1：重写 `cancelResearch` — reader.cancel → controller.abort 分层清理**

找到第 1055-1061 行：

```typescript
const cancelResearch = () => {
  if (!loading.value || !currentController) {
    return;
  }
  progressLogs.value.push("正在尝试取消当前调查任务…");
  currentController.abort();
};
```

替换为：

```typescript
const cancelResearch = () => {
  // 检查是否有活跃的 SSE 连接（不依赖 loading 状态，消除 B5）
  if (!currentController && !currentReader) {
    return;
  }

  // 分层清理（修复 B3）：
  // 1. 先取消 reader — 释放浏览器端流缓冲
  if (currentReader) {
    currentReader.cancel().catch(() => {});
    currentReader = null;
  }
  // 2. 再 abort fetch — 中断网络请求
  if (currentController) {
    currentController.abort();
    currentController = null;
  }

  // 仅在非 idle 状态下记录取消日志
  if (researchPhase.value !== 'idle') {
    progressLogs.value.push("已取消当前调查任务");
  }
};
```

- [ ] **步骤 2：修改 `handleSubmit` 开头，增加 reader 捕获 + epoch 管理**

找到第 744-760 行开头部分：

```typescript
const handleSubmit = async () => {
  if (!form.topic.trim()) {
    error.value = "请输入调查主题";
    return;
  }

  if (currentController) {
    currentController.abort();
    currentController = null;
  }

  loading.value = true;
  error.value = "";
  isExpanded.value = true;
  resetWorkflowState();

  const controller = new AbortController();
  currentController = controller;

  const payload = {
    topic: form.topic.trim(),
    search_api: form.searchApi || undefined
  };
```

替换为：

```typescript
const handleSubmit = async () => {
  if (!form.topic.trim()) {
    error.value = "请输入调查主题";
    return;
  }

  // 先清理前一个未完成的 SSE 连接（分层清理）
  cancelResearch();

  // 新 Session：递增 epoch 使旧 session 的所有回调失效
  const epoch = ++researchEpoch.value;

  researchPhase.value = 'running';
  error.value = "";
  resetWorkflowState();

  const controller = new AbortController();
  currentController = controller;

  const payload = {
    topic: form.topic.trim(),
    search_api: form.searchApi || undefined
  };
```

- [ ] **步骤 3：在 `runResearchStream` 调用中传入 `onReader` 回调**

找到 `runResearchStream` 调用（约第 769 行）：

```typescript
await runResearchStream(
  payload,
  (event: ResearchStreamEvent) => {
```

替换 options 参数部分。找到第 1035 行附近的 `{ signal: controller.signal }`：

```typescript
      { signal: controller.signal }
    );
```

替换为：

```typescript
      {
        signal: controller.signal,
        onReader: (r) => { currentReader = r; }
      }
    );
```

- [ ] **步骤 4：在第一个有效事件到达时消除启动遮罩**

在 SSE 回调中，`todo_list` 和第一个 `status` 事件处理逻辑不变，但需确保 `researchPhase` 状态转换。找到 `generating_report` 事件处理（约第 994 行）：

```typescript
if (event.type === "generating_report") {
  generatingReport.value = true;
  ...
}
```

替换为：

```typescript
if (event.type === "generating_report") {
  researchPhase.value = 'generating';
  ...
}
```

- [ ] **步骤 5：`final_report` 事件 — 切换到 done 状态**

找到第 1002-1003 行：

```typescript
if (event.type === "final_report") {
  generatingReport.value = false;
```

替换为：

```typescript
if (event.type === "final_report") {
  researchPhase.value = 'done';
```

- [ ] **步骤 6：`error` 事件 — 切换到 error 状态**

找到第 1026-1033 行 `error` 事件处理，在设置 `error.value` 之前加：

```typescript
if (event.type === "error") {
  researchPhase.value = 'error';
  const detail = ...
```

- [ ] **步骤 7：`finally` 块 — 清理资源**

找到第 1047-1052 行：

```typescript
} finally {
  loading.value = false;
  if (currentController === controller) {
    currentController = null;
  }
}
```

替换为：

```typescript
} finally {
  if (researchPhase.value === 'running' || researchPhase.value === 'generating') {
    researchPhase.value = 'done';  // 流正常结束但未收到 final_report 事件
  }
  if (currentController === controller) {
    currentController = null;
  }
  currentReader = null;
}
```

- [ ] **步骤 8：在关键 SSE 回调入口添加 epoch 校验**

在每个 SSE 回调类型处理（`todo_list`、`task_status`、`sources`、`task_summary_chunk`、`tool_call`）的开头添加 epoch guard。找到每个 `if (event.type === "xxx")` 块的函数体第一行，添加：

```typescript
if (event.type === "todo_list") {
  if (researchEpoch.value !== epoch) return;  // ← 新增
  ...
}
if (event.type === "task_status") {
  if (researchEpoch.value !== epoch) return;  // ← 新增
  ...
}
if (event.type === "sources") {
  if (researchEpoch.value !== epoch) return;  // ← 新增
  ...
}
if (event.type === "task_summary_chunk") {
  if (researchEpoch.value !== epoch) return;  // ← 新增
  ...
}
if (event.type === "tool_call") {
  if (researchEpoch.value !== epoch) return;  // ← 新增
  ...
}
```

- [ ] **步骤 9：auto-save fetch — 添加 epoch 校验（修复 B2）**

找到第 1011-1022 行的 auto-save fetch：

```typescript
fetch(`${BASE}/api/reports`, {
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

替换为：

```typescript
fetch(`${BASE}/api/reports`, {
  method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({title: form.topic, content: reportMarkdown.value})
})
.then(r => r.json())
.then(data => {
  // epoch 校验：只有当前 session 才写入 savedReportId（修复 B2）
  if (data && data.id && researchEpoch.value === epoch) {
    savedReportId.value = data.id;
  }
})
.catch(() => {});
```

- [ ] **步骤 10：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **步骤 11：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "fix(research): SSE cleanup protocol, epoch guards, and phase transitions

- cancelResearch: reader.cancel() → controller.abort() layered cleanup
- handleSubmit: researchEpoch++ to invalidate old session callbacks
- All SSE callbacks: epoch guard at entry (researchEpoch !== epoch → return)
- auto-save fetch: epoch guard in .then() callback
- researchPhase transitions: running → generating → done → error
- Fixes B2, B3, B4, B5

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：ResearchPage.vue — 重写 startNewResearch + resetWorkflowState

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue:1063-1072, 703-717`

**目的：** 修复 B1（无确认）、B6（overflow 双管）、B7（空白闪烁）。

- [ ] **步骤 1：重写 `startNewResearch` — 确认 → epoch++ → cancel → 切布局 → 重置**

找到第 1063-1072 行：

```typescript
const startNewResearch = () => {
  if (loading.value) {
    cancelResearch();
  }
  resetWorkflowState();
  error.value = "";
  isExpanded.value = false;
  form.topic = "";
  form.searchApi = "";
};
```

替换为：

```typescript
const startNewResearch = () => {
  // 1. 确认对话框（修复 B1）—— 只有存在实质数据时才弹窗
  const hasContent = reportMarkdown.value.trim() !== "" || todoTasks.value.length > 0;
  if (hasContent && !window.confirm("当前调查结果将在开启新调查后丢失，确认继续？")) {
    return;
  }

  // 2. 废弃旧 session —— 让所有异步回调立即失效（修复 B2）
  ++researchEpoch.value;

  // 3. 清理 SSE 连接（修复 B3/B5）—— 不依赖 loading 状态
  cancelResearch();

  // 4. 先切回表单布局（数据还在但不可见 —— 修复 B7 空白闪烁）
  researchPhase.value = 'idle';

  // 5. 再清空数据（此时 v-if="researchPhase === 'idle'" 已生效，清数据不会渲染空白）
  resetWorkflowState();
  error.value = "";
  form.topic = "";
  form.searchApi = "";
};
```

- [ ] **步骤 2：`resetWorkflowState` — 删除 overflow 双重管理（修复 B6）**

找到第 703-717 行，删除 `document.body.style.overflow = "";` 那一行：

```typescript
function resetWorkflowState() {
  todoTasks.value = [];
  activeTaskId.value = null;
  taskDetailOpen.value = false;
  // document.body.style.overflow = "";  ← 删除这行（由 watch(taskDetailOpen) 统一管理）
  reportMarkdown.value = "";
  savedReportId.value = "";
  progressLogs.value = [];
  summaryHighlight.value = false;
  sourcesHighlight.value = false;
  reportHighlight.value = false;
  toolHighlight.value = false;
  reportCollapsed.value = false;
  tasksCollapsed.value = false;
}
```

- [ ] **步骤 3：更新 `onBeforeUnmount` 中的清理逻辑**

找到第 1083-1090 行，确保也使用分层清理：

```typescript
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onTaskModalKeydown);
  document.body.style.overflow = "";
  cancelResearch();  // 替代原来的 currentController.abort()
});
```

- [ ] **步骤 4：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "fix(research): startNewResearch confirmation, execution order, and overflow cleanup

- Add confirmation dialog when research data exists (B1)
- Reorder: phase→idle before resetWorkflowState to prevent white flash (B7)
- Remove body.style.overflow from resetWorkflowState (B6, watcher is single owner)
- Use cancelResearch() in onBeforeUnmount for consistent cleanup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：ResearchPage.vue — F1 债务企业 Combobox

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue`

**目的：** 用户可以从已有乙方企业中选择或自由输入。

- [ ] **步骤 1：添加企业列表相关状态**

在 script 顶部 ref 声明区（约第 400 行，`researchPhase` 声明之后）添加：

```typescript
// --- 企业选择（F1）---
const enterprises = ref<string[]>([]);
const showEnterpriseDropdown = ref(false);
```

- [ ] **步骤 2：添加 `filteredEnterprises` computed 和 `selectEnterprise` 函数**

在 `searchOptions` 数组定义（第 434 行）之后添加：

```typescript
// F1：模糊匹配已有乙方企业
const filteredEnterprises = computed(() => {
  const query = form.topic.trim();
  if (!query) return enterprises.value;
  const lower = query.toLowerCase();
  return enterprises.value.filter(name => name.toLowerCase().includes(lower));
});

function selectEnterprise(name: string) {
  form.topic = name;
  showEnterpriseDropdown.value = false;
}

function onTopicFocus() {
  showEnterpriseDropdown.value = enterprises.value.length > 0;
}

function onTopicBlur() {
  // 延迟关闭，让 click 事件先触发
  setTimeout(() => { showEnterpriseDropdown.value = false; }, 150);
}
```

- [ ] **步骤 3：在 `onMounted` 中加载企业列表**

找到第 1074-1081 行的 `onMounted`，在现有逻辑前添加企业加载：

```typescript
onMounted(() => {
  window.addEventListener("keydown", onTaskModalKeydown);

  // F1：加载乙方企业列表（失败不影响正常使用）
  fetch(`${BASE}/api/enterprises`)
    .then(r => r.json())
    .then(data => {
      const all: { name: string; role: string }[] = data.enterprises || [];
      enterprises.value = all
        .filter(e => e.role === "乙方")
        .map(e => e.name);
    })
    .catch(() => { /* 加载失败时下拉为空，用户手打不受影响 */ });

  const topicParam = route.query.topic;
  if (topicParam && typeof topicParam === "string") {
    form.topic = topicParam;
    handleSubmit();
  }
});
```

- [ ] **步骤 4：替换模板中的 textarea 为 Combobox**

找到第 28-35 行：

```html
<label class="field">
  <span>债务企业</span>
  <textarea
    v-model="form.topic"
    placeholder="例如：四川振海保安服务有限公司"
    rows="4"
    required
  ></textarea>
</label>
```

替换为：

```html
<label class="field">
  <span>债务企业</span>
  <div class="combobox-wrapper">
    <textarea
      v-model="form.topic"
      placeholder="输入企业名称，或从已有项目中选择"
      rows="3"
      required
      @focus="onTopicFocus"
      @blur="onTopicBlur"
      @input="showEnterpriseDropdown = true"
    ></textarea>
    <ul
      v-if="showEnterpriseDropdown && filteredEnterprises.length"
      class="combobox-dropdown"
    >
      <li
        v-for="name in filteredEnterprises"
        :key="name"
        class="combobox-option"
        @mousedown.prevent="selectEnterprise(name)"
      >
        {{ name }}
      </li>
    </ul>
  </div>
</label>
```

- [ ] **步骤 5：添加 Combobox 样式**

在 `<style scoped>` 末尾（`</style>` 之前）添加：

```css
/* F1：债务企业 Combobox */
.combobox-wrapper {
  position: relative;
}
.combobox-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 10;
  max-height: 200px;
  overflow-y: auto;
  margin: 4px 0 0;
  padding: 6px 0;
  list-style: none;
  background: #fff;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
}
.combobox-option {
  padding: 10px 16px;
  font-size: 14px;
  color: #1f2937;
  cursor: pointer;
  transition: background 0.15s ease;
}
.combobox-option:hover {
  background: rgba(59, 130, 246, 0.08);
  color: #1d4ed8;
}
```

- [ ] **步骤 6：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **步骤 7：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "feat(research): enterprise name combobox with fuzzy search (F1)

- Load 乙方 enterprises from GET /api/enterprises on mount
- Fuzzy match as user types (case-insensitive includes)
- Click to select, or free-type a new enterprise name
- Dropdown auto-closes on blur with 150ms delay for click event

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 6：ResearchPage.vue — F2 删除搜索引擎选择器

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue`

**目的：** 隐藏搜索引擎下拉菜单，统一使用后端配置。

- [ ] **步骤 1：删除搜索引擎 section**

找到第 37-51 行，删除整个块：

```html
          <section class="options">
            <label class="field option">
              <span>搜索引擎</span>
              <select v-model="form.searchApi">
                <option value="">沿用后端配置</option>
                <option
                  v-for="option in searchOptions"
                  :key="option"
                  :value="option"
                >
                  {{ option }}
                </option>
              </select>
            </label>
          </section>
```

- [ ] **步骤 2：删除不再需要的 `searchOptions` 数组**

找到第 434-440 行，删除：

```typescript
const searchOptions = [
  "advanced",
  "duckduckgo",
  "tavily",
  "perplexity",
  "searxng"
];
```

（`form.searchApi` 保持默认空字符串，传给后端时 `search_api: undefined`，后端自行决定。）

- [ ] **步骤 3：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "feat(research): remove search engine selector, use backend default (F2)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 7：ResearchPage.vue — F3 开始调查过渡动画

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue`

**目的：** 3 步动画——表单退出 → 启动遮罩 → 结果页滑入，消除生硬切换。

- [ ] **步骤 1：包裹表单区域 — 退出动画**

找到第 10-11 行：

```html
    <div v-if="!isExpanded" class="layout layout-centered">
      <section class="panel panel-form panel-centered">
```

这里 `v-if="!isExpanded"` 仍能用（isExpanded 已改为 computed，idle 时返回 false）。用 `<Transition>` 包裹：

```html
    <Transition name="form-exit">
      <div v-if="researchPhase === 'idle'" class="layout layout-centered">
        <section class="panel panel-form panel-centered">
```

对应的闭合标签也需要调整。找到第 90 行的 `</div>`（layout-centered 闭合标签），在它后面加上 `</Transition>`。

布局结构变为：

```html
    <!-- 初始状态：居中输入卡片 -->
    <Transition name="form-exit">
      <div v-if="researchPhase === 'idle'" class="layout layout-centered">
        ...表单内容...
      </div>
    </Transition>

    <!-- 全屏状态：结果面板 -->
    <Transition name="result-enter">
      <div v-if="researchPhase !== 'idle'" class="layout layout-fullscreen">
        ...结果内容...
      </div>
    </Transition>
```

- [ ] **步骤 2：包裹全屏区域 + 添加启动遮罩**

找到第 93-96 行：

```html
    <div v-else class="layout layout-fullscreen">
      <section
        class="panel panel-result"
        v-if="todoTasks.length || reportMarkdown || progressLogs.length"
      >
```

替换为：

```html
    <Transition name="result-enter">
      <div v-if="researchPhase !== 'idle'" class="layout layout-fullscreen">
        <!-- 启动遮罩（F3 Step 2）-->
        <Transition name="startup-overlay">
          <div
            v-if="researchPhase === 'running' && !todoTasks.length && !reportMarkdown"
            class="startup-overlay"
          >
            <div class="startup-content">
              <div class="startup-spinner"></div>
              <p>正在启动调查引擎…</p>
            </div>
          </div>
        </Transition>

        <section
          class="panel panel-result"
          v-if="todoTasks.length || reportMarkdown || progressLogs.length"
        >
```

闭合标签：找到第 333 行 `</div>`（layout-fullscreen 闭合），后面加上 `</Transition>`。

- [ ] **步骤 3：添加动画 CSS**

在 `<style scoped>` 末尾（`</style>` 之前）添加：

```css
/* F3：过渡动画 */
/* Step 1: 表单退出 */
.form-exit-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.form-exit-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

/* Step 3: 结果页进入 */
.result-enter-enter-active {
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.result-enter-enter-from {
  opacity: 0;
  transform: translateX(30px);
}

/* 新调查切回表单时，结果页退出 */
.result-enter-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.result-enter-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

/* 表单重新进入 */
.form-exit-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.form-exit-enter-from {
  opacity: 0;
  transform: scale(0.95);
}

/* Step 2: 启动遮罩 */
.startup-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at 20% 20%, #f8fafc, #dbeafe 60%);
  border-radius: inherit;
}
.startup-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}
.startup-content p {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
}
.startup-spinner {
  width: 44px;
  height: 44px;
  border: 4px solid #bfdbfe;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.startup-overlay-leave-active {
  transition: opacity 0.25s ease;
}
.startup-overlay-leave-to {
  opacity: 0;
}
```

- [ ] **步骤 4：验证编译通过**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "feat(research): 3-step transition animations for form→result flow (F3)

- Step 1: form card scales down + fades out (300ms)
- Step 2: startup overlay with spinner until first SSE event
- Step 3: result panel slides in from right (400ms)
- Reverse animation for 'New Research' button

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 8：最终验证 — 编译 + 静态分析

**文件：**
- 全部

- [ ] **步骤 1：完整 TypeScript 编译检查**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1
```

预期：无错误输出。

- [ ] **步骤 2：检查是否存在遗留引用**

确认以下旧 ref 名不再以 `ref(` 形式出现（仅以 `computed` 形式出现）：

```bash
cd frontend && grep -n "loading\|isExpanded\|generatingReport" src/pages/ResearchPage.vue
```

预期结果：
- `loading` 只在 `computed(() => researchPhase.value === 'running' || ...)` 中定义
- `isExpanded` 只在 `computed(() => researchPhase.value !== 'idle')` 中定义
- `generatingReport` 只在 `computed(() => researchPhase.value === 'generating')` 中定义
- 模板中仍然引用这些 computed 名（合法）

- [ ] **步骤 3：检查 `startNewResearch` 中无 `loading` / `isExpanded` 赋值**

```bash
cd frontend && grep -A 15 "const startNewResearch" src/pages/ResearchPage.vue
```

确认函数体中不再出现 `loading.value =` 或 `isExpanded.value =`，只有 `researchPhase.value = 'idle'`。

- [ ] **步骤 4：检查 `cancelResearch` 中无 `loading` 检查**

```bash
cd frontend && grep -A 12 "const cancelResearch" src/pages/ResearchPage.vue
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "chore(research): final verification — remove stale ref assignments

Ensure no lingering loading/isExpanded/generatingReport as ref() assignments.
All three are now computed from researchPhase.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 自检

### 1. 规格覆盖度

| 规格需求 | 对应任务 | 状态 |
|----------|----------|------|
| B1 确认对话框 | 任务 4 步骤 1 | ✅ |
| B2 auto-save 竞态 | 任务 3 步骤 9 | ✅ |
| B3 SSE reader 未取消 | 任务 1 + 任务 3 步骤 1 | ✅ |
| B4 取消日志丢失 | 任务 3 步骤 1（移到 cancelResearch 内部） | ✅ |
| B5 controller 检查不一致 | 任务 3 步骤 1（check currentController \|\| currentReader） | ✅ |
| B6 overflow 双管 | 任务 4 步骤 2（删除一行） | ✅ |
| B7 空白闪烁 | 任务 4 步骤 1（先切布局再清数据） | ✅ |
| F1 企业 Combobox | 任务 5 | ✅ |
| F2 隐藏搜索引擎 | 任务 6 | ✅ |
| F3 过渡动画 | 任务 7 | ✅ |

### 2. 占位符扫描

无 TODO / 待定 / 后续实现 / 补充细节。所有步骤包含完整代码。

### 3. 类型一致性

- `researchPhase` 类型 `'idle' | 'running' | 'generating' | 'done' | 'error'` — 所有赋值和比较一致
- `researchEpoch` 类型 `number` — 递增用 `++`，比较用 `===`
- `currentReader` 类型 `ReadableStreamDefaultReader<Uint8Array> | null` — 来自 api.ts 的 `onReader` 回调
- `enterprises` 类型 `string[]` — `filter`/`map` 返回 `string[]`
- template 中 `loading`/`isExpanded`/`generatingReport` 保持为 computed boolean — 模板无需改动

---
