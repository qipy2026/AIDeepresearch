# ResearchPage：Session 隔离 + 状态机 + UX 增强

## 元信息

- 日期：2026-06-25
- 目标文件：`frontend/src/pages/ResearchPage.vue`
- 改动范围：单文件，约 50-70 行变更

## 问题清单（10 项）

### Bug 修复（7 项）

| ID | 严重度 | 问题 | 根因 |
|----|--------|------|------|
| B1 | 🔴 | 无确认直接销毁所有调查结果 | `startNewResearch()` 无条件调 `resetWorkflowState()` |
| B2 | 🔴 | auto-save fetch 竞态条件 | fire-and-forget fetch 回调写 `savedReportId`，不校验 session |
| B3 | 🟡 | SSE reader 未显式取消 | `cancelResearch()` 只 abort fetch，不 cancel reader |
| B4 | 🟡 | 取消日志立即被清空 | `cancelResearch()` push 日志 → `resetWorkflowState()` 清空 |
| B5 | 🟡 | controller/loading 状态不一致 | `startNewResearch` 仅按 `loading` 判断是否取消 |
| B6 | 🟢 | body.style.overflow 双重管理 | `resetWorkflowState()` 和 `watch(taskDetailOpen)` 竞争 |
| B7 | 🟡 | 新调查时全屏空白闪烁 | `resetWorkflowState()` 先清数据再调 `isExpanded=false`，中间渲染空布局 |

### 功能增强（3 项）

| ID | 需求 | 描述 |
|----|------|------|
| F1 | 债务企业选择/模糊输入 | 从已有项目（乙方企业）中选择，支持模糊匹配和自由输入 |
| F2 | 隐藏搜索引擎 | 删除搜索引擎下拉选项，统一用后端配置 |
| F3 | 开始调查动画过渡 | 3 步动画：表单消失 → 过渡提示 → 结果页滑入 |

---

## 架构设计

### 1. 显式状态机：`researchPhase`

替代隐式拼凑的 `loading` / `isExpanded` / `generatingReport`：

```
researchPhase: 'idle' | 'running' | 'generating' | 'done' | 'error'

状态转换：
  idle       → running     (handleSubmit 开始)
  running    → generating  (收到 generating_report 事件)
  generating → done        (收到 final_report 事件)
  running    → error       (收到 error 事件 或 网络异常)
  *          → idle        (取消 / startNewResearch / 异常恢复)
```

模板条件替换：
- `v-if="!isExpanded"` → `v-if="researchPhase === 'idle'"`
- `v-if="loading"` → `v-if="researchPhase === 'running'"`
- `:disabled="loading"` → `:disabled="researchPhase === 'running'"`
- 全屏布局条件：`v-else`（非 idle 即全屏）

非法状态组合在设计中不可能出现。

### 2. Session 隔离：`researchEpoch`

```
researchEpoch: ref<number>(0)  // 单调递增

handleSubmit():
  const epoch = ++researchEpoch
  所有 SSE 回调入口: if (researchEpoch.value !== epoch) return
  auto-save 回调: .then(data => { if (researchEpoch.value === epoch) savedReportId.value = data.id })

startNewResearch():
  ++researchEpoch  // 旧 session 所有异步回调立即失效
  resetWorkflowState()
```

单一 `ref<number>` 消除 B2 + B5，且未来新增异步逻辑自动安全。

### 3. SSE 分层清理

```
cancelResearch():
  1. reader?.cancel()          // 释放 ReadableStream 资源
  2. controller.abort()        // 中断 fetch
  3. currentReader = null
  4. currentController = null
```

新增 `currentReader: ReadableStreamDefaultReader | null`，在 `runResearchStream` 中赋值。

### 4. `startNewResearch` 执行顺序

```
startNewResearch():
  // 1. 确认
  if (hasContent && !confirm('...')) return

  // 2. 废弃旧 session
  ++researchEpoch

  // 3. 清理 SSE（不依赖 loading 状态）
  cancelResearch()

  // 4. 先切布局（数据还在但不可见，避免空白闪烁）
  researchPhase.value = 'idle'

  // 5. 再清数据（此时在 v-if=false 分支中清）
  resetWorkflowState()
```

B7 通过「先切布局、再清数据」解决。

### 5. overflow 单一管理

`resetWorkflowState()` 中删除 `document.body.style.overflow = ""`。

`watch(taskDetailOpen)` 是 overflow 的唯一管理入口：
- `taskDetailOpen = false` → `body.style.overflow = ""`
- `resetWorkflowState` 设 `taskDetailOpen = false` → watcher 自动处理 overflow

---

## 功能设计

### F1：债务企业 Combobox

数据源：`onMounted` 时调用 `GET /api/enterprises`，过滤 `role === "乙方"`。

交互：
- 用户在 `<textarea>` 中输入
- 实时模糊匹配（`includes`，不区分大小写）已有企业名
- 匹配结果在下拉列表显示，点击填入
- 无匹配或用户想手打时，完全自由输入——不强制选择
- 聚焦 + 有匹配时显示下拉，点击外部关闭

新增状态：
```
enterprises: ref<string[]>([])      // 乙方企业名列表
enterpriseFilter: ref<string>("")    // 当前过滤文本
showEnterpriseDropdown: ref(false)   // 下拉显示
```

点击下拉项：
```
selectEnterprise(name): 
  form.topic = name
  showEnterpriseDropdown = false
```

边缘处理：
- API 失败 → 下拉为空，用户手打不受影响
- 企业名含特殊字符 → 仅做 `includes` 匹配，不做正则

### F2：删除搜索引擎选择

模板中删除 `<section class="options">` 整块（第 37-51 行）。

`form.searchApi` 保持默认 `""`，传给后端时 `search_api: undefined`，后端自行决定。

### F3：开始调查动画过渡

3 步流程：

**Step 1 — 表单退出（~300ms）:**
居中表单卡片 scale(1)→scale(0.95)，opacity 1→0，背景渐变淡化。
使用 Vue `<Transition name="form-exit">`。

**Step 2 — 启动提示（variable duration）:**
`researchPhase === 'running'` 且尚未收到第一个有效 SSE 事件时，显示启动遮罩：
- 居中 spinner + "正在启动调查引擎…"
- 收到第一个 `todo_list` 或 `status` 事件 → 立即消隐（或 2 秒超时）
- 遮罩自身也有淡出动画（~200ms）

**Step 3 — 结果页进入（~400ms）:**
全屏结果面板 translateX(30px)→0，opacity 0→1。
使用 Vue `<Transition name="result-enter">`。

CSS keyframes：
```css
.form-exit-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.form-exit-leave-to   { opacity: 0; transform: scale(0.95); }

.result-enter-enter-active { transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.result-enter-enter-from   { opacity: 0; transform: translateX(30px); }

.startup-overlay-leave-active { transition: opacity 0.2s ease; }
.startup-overlay-leave-to     { opacity: 0; }
```

「新调查」切回表单时同理，结果页淡出 → 表单淡入，只是反向播放。

---

## 变更清单

| # | 类别 | 变更 | 行范围 |
|---|------|------|--------|
| 1 | 新增 | `researchPhase` ref + 状态枚举 | script 顶部 |
| 2 | 新增 | `researchEpoch` ref | script 顶部 |
| 3 | 新增 | `currentReader` ref | script 顶部 |
| 4 | 新增 | F1：`enterprises` / `enterpriseFilter` / `showEnterpriseDropdown` | script 顶部 |
| 5 | 新增 | F1：`onMounted` 中加载企业列表 | onMounted |
| 6 | 新增 | F1：Combobox 模板 + 下拉列表 | template form 区域 |
| 7 | 删除 | F2：`<section class="options">` 引擎选择器 | template |
| 8 | 修改 | F3：表单区域包裹 `<Transition name="form-exit">` | template |
| 9 | 修改 | F3：结果区域包裹 `<Transition name="result-enter">` | template |
| 10 | 新增 | F3：启动遮罩 `<Transition name="startup-overlay">` | template |
| 11 | 新增 | F3：过渡动画 CSS keyframes | style |
| 12 | 重写 | `handleSubmit`：epoch 管理 + phase 状态机 | script |
| 13 | 修改 | SSE 回调：入口 epoch 校验 `if (researchEpoch !== epoch) return` | handleSubmit 内 |
| 14 | 修改 | auto-save fetch：epoch 校验 `.then(data => { if (...) savedReportId = data.id })` | handleSubmit 内 |
| 15 | 重写 | `cancelResearch`：reader.cancel → controller.abort 分层清理 | script |
| 16 | 重写 | `startNewResearch`：确认 → epoch++ → cancel → 切布局 → reset | script |
| 17 | 修改 | `resetWorkflowState`：删除 overflow 赋值 | script |
| 18 | 修改 | 模板条件：`loading`/`isExpanded` → `researchPhase` | template 多处 |

---

## 规格自检

- [x] **占位符扫描**：无 TODO / 待定 / 未完成章节
- [x] **内部一致性**：状态机转换表与代码变更描述一致；epoch 机制与所有异步点对应
- [x] **范围检查**：单文件改动，聚焦 ResearchPage，未涉及 router/store/后端
- [x] **模糊性检查**：动画时长、过渡曲线、Combobox 行为均已明确
