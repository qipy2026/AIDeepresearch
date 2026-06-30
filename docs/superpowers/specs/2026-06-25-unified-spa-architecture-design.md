# 统一 SPA 架构 — 设计规格

日期：2026-06-25　|　状态：已确认　|　方案：A（完整迁移为 Vue 组件）

## 一、问题陈述

当前应用存在架构碎片化问题：

| # | 问题 | 根因 |
|---|------|------|
| ① | App.vue 与 6 个 HTML 模板使用**两套独立侧边栏**代码 | App.vue 内置 scoped style 侧边栏，HTML 模板引用 shared.css 侧边栏 |
| ② | `/app/` 与 `/warnings` 等路径不在统一命名空间下 | 历史原因，Vue SPA 挂载于 `/app/`，HTML 模板散落在根路径，本次统一到 `/loan/` |
| ③ | App.vue 硬编码 `topic: "四川振海保安服务有限公司"` 作为默认值 | 首次加载即进入 expanded 模式并在侧边栏显示该预设值 |
| ④ | "返回" 按钮语义模糊 | `goBack()` 实际是折叠布局（`isExpanded = false`），非浏览器返回 |
| ⑤ | "编辑报告" 作为顶级导航入口不合理 | `/reports-edit` 需要 `?id=xxx` 参数，无参数时显示"报告不存在" |

## 二、目标

- 全站统一为 Vue SPA（Vue 3 + Vue Router），所有路由在 `/loan/` 下
- 一套侧边栏组件（`AppSidebar.vue`）供 7 个页面共用，消除重复代码
- 路由语义清晰：主界面（贷后项目）→ 二级操作页面
- 去掉不合逻辑的导航入口和硬编码默认值

## 三、路由结构

```
/loan/                  → 贷后项目（ProjectsPage.vue）        ← 主界面
/loan/research          → 贷后助手（ResearchPage.vue）        ← 二级
/loan/warnings          → 预警中心（WarningsPage.vue）
/loan/sources           → 数据源管理（SourcesPage.vue）
/loan/upload            → 参考文档（UploadPage.vue）
/loan/reports           → 报告列表（ReportsPage.vue）
/loan/reports/:id/edit  → 编辑报告（ReportEditPage.vue）
```

旧路径（`/warnings`、`/enterprises`、`/sources`、`/rag/upload`、`/reports`、`/reports-edit`）在后端做 301 重定向到 `/loan/...`。

## 四、组件树

```
App.vue
├── AppSidebar.vue                    ← 统一侧边栏，所有页面共用
│   ├── Logo + 标题
│   ├── 6 个 <router-link> 导航项     ← 去掉"编辑报告"
│   └── "开始新调查" → /loan/research
└── <router-view />                   ← 各页面组件
    ├── ProjectsPage.vue              ← /loan/ 主界面
    ├── ResearchPage.vue              ← /loan/research
    ├── WarningsPage.vue              ← /loan/warnings
    ├── SourcesPage.vue               ← /loan/sources
    ├── UploadPage.vue                ← /loan/upload
    ├── ReportsPage.vue               ← /loan/reports
    └── ReportEditPage.vue            ← /loan/reports/:id/edit
```

## 五、侧边栏统一设计

### 5.1 唯一实现

`AppSidebar.vue` 是侧边栏的唯一实现，包含：
- Logo + "贷后管理助手" + "监控与预警系统"
- 6 个导航链接（按顺序：贷后项目 → 贷后助手 → 预警中心 → 数据源管理 → 参考文档 → 报告列表）
- "开始新调查" → `/loan/research`
- `router-link-active` / `router-link-exact-active` 自动高亮当前路由

### 5.2 两套旧侧边栏的处理

- App.vue 中原有侧边栏代码：**删除**，改用 `<AppSidebar />`
- shared.css 中侧边栏样式：**保留**（backward compatibility，后续可逐步清理）
- 6 个 HTML 模板中侧边栏：**不再需要**（页面逻辑已迁移到 Vue 组件）

## 六、各页面组件详情

### 6.1 ProjectsPage.vue（主界面）

- 路径：`/loan/`
- 来源：`enterprises.html`（~170 行 JS）
- 功能：项目卡片网格、手风琴展开/折叠、新建项目表单、删除项目
- 新增：卡片点击可跳转 `/loan/research?topic=企业名`

### 6.2 ResearchPage.vue（贷后助手）

- 路径：`/loan/research`
- 来源：App.vue 现有逻辑（search form + SSE + report + quick actions）
- 改造：
  - `isExpanded` 默认值改为 `false`（先展示输入卡片）
  - `form.topic` 默认值改为 `""`（去掉硬编码）
  - "返回" 按钮改为"新调查"按钮，点击重置表单（`resetWorkflowState`）
  - 收到 `?topic=xxx` 参数时自动填入 topic 并展开
  - 快捷操作栏保留（报告生成后显示编辑/报告列表按钮）

### 6.3 WarningsPage.vue

- 路径：`/loan/warnings`
- 来源：`warnings.html`（~400 行 JS）
- 功能：统计卡片、预警列表、明细弹窗、因子详情、飞书推送、行业风向标
- 保留：全部业务逻辑、严重度颜色体系、骨架屏动画、自动刷新

### 6.4 SourcesPage.vue

- 路径：`/loan/sources`
- 来源：`sources.html`（~100 行 JS）
- 功能：数据源表格、toggle 开关、新增/编辑弹窗、保存修改
- 保留：CSS toggle 开关样式、表格结构

### 6.5 UploadPage.vue

- 路径：`/loan/upload`
- 来源：`upload.html`（~80 行 JS）
- 功能：拖拽上传、企业列表、删除
- 保留：文件上传虚线框、进度条动画

### 6.6 ReportsPage.vue

- 路径：`/loan/reports`
- 来源：`reports.html`（~40 行 JS）
- 功能：报告列表表格、编辑跳转、删除

### 6.7 ReportEditPage.vue

- 路径：`/loan/reports/:id/edit`
- 来源：`reports-edit.html`（~260 行 JS）
- 功能：分栏 Markdown 编辑器 + 实时预览 + 飞书发送 + Ctrl+S 保存
- 无 `:id` 时显示"请从报告列表选择 → 返回列表链接"
- 预览区 markdown 渲染样式保留

## 七、后端改动

### 7.1 旧路径 301 重定向

```python
@app.get("/warnings")
async def redirect_warnings():
    return RedirectResponse(url="/loan/warnings", status_code=301)

@app.get("/enterprises")
async def redirect_enterprises():
    return RedirectResponse(url="/loan/", status_code=301)

# ... 其余旧路径同理
```

### 7.2 FastAPI SPA fallback

```python
app.mount("/loan", StaticFiles(directory=str(_vue_dist), html=True), name="vue_spa")
```

Vue Router history mode 下 `/loan/xxx` 刷新时需要服务端 fallback 到 `index.html`。当前 `html=True` 已覆盖此场景。

## 八、不做的事情

- **不保留 HTML 模板**：迁移完成后 6 个 `.html` 文件删除，避免维护两套代码
- **不保留 shared.css 侧边栏样式**：迁移后清理 shared.css 中的 `.sidebar`、`.sidebar-link` 等规则，仅保留 `.btn-primary`、`.card-glass` 等工具类
- **不迁移 App.vue 的旧 sidebar 样式**：这些 scoped style 随代码一并删除
- **不改变后端 API 路径**：`/api/warnings`、`/api/enterprises` 等保持不变

## 九、改动文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/main.ts` | 修改 | 注册 Vue Router |
| `frontend/src/App.vue` | 替换 | 最小壳子：AppSidebar + router-view |
| `frontend/src/components/AppSidebar.vue` | 新建 | 统一侧边栏组件 |
| `frontend/src/pages/ResearchPage.vue` | 新建 | 贷后助手（从 App.vue 提取） |
| `frontend/src/pages/ProjectsPage.vue` | 新建 | 贷后项目（从 enterprises.html 迁移） |
| `frontend/src/pages/WarningsPage.vue` | 新建 | 预警中心（从 warnings.html 迁移） |
| `frontend/src/pages/SourcesPage.vue` | 新建 | 数据源管理（从 sources.html 迁移） |
| `frontend/src/pages/UploadPage.vue` | 新建 | 参考文档（从 upload.html 迁移） |
| `frontend/src/pages/ReportsPage.vue` | 新建 | 报告列表（从 reports.html 迁移） |
| `frontend/src/pages/ReportEditPage.vue` | 新建 | 报告编辑（从 reports-edit.html 迁移） |
| `frontend/src/router/index.ts` | 新建 | 路由配置 |
| `frontend/public/shared.css` | 修改 | 删除侧边栏布局规则，保留工具类 |
| `backend/src/main.py` | 修改 | 添加 6 条旧路径 301 重定向 |
| `backend/src/templates/*.html` | 删除 | 6 个 HTML 模板文件 |

## 十、自检结果

| 检查项 | 状态 |
|--------|------|
| 占位符扫描 | ✅ 无 TODO/TBD/待定 |
| 内部一致性 | ✅ 路由表与组件树一致；旧路径重定向覆盖完整 |
| 范围检查 | ✅ 聚焦于架构统一，不涉及后端 API 改动 |
| 模糊性检查 | ✅ 所有路径/组件名/重定向规则明确 |
