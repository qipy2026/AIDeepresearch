# UI 风格统一与路由修复 — 设计规格

- **日期**: 2026-06-25
- **分支**: loan
- **状态**: 待实现

## 1. 问题描述

应用存在两套独立的 UI 体系，视觉效果不统一：

| | 6 个 HTML 模板页 | 贷后助手 (App.vue) |
|---|---|---|
| 设计语言 | 扁平、不透明白底、Tailwind 石板色系 | 玻璃拟态、半透明、极光背景 |
| 导航 | 深色横条顶栏 + pill 链接 | 左侧固定侧边栏 + 垂直链接 |
| 圆角 | 8-14px | 12-20px |
| 按钮 | 紧凑型、扁平 | 大号、hover 浮起效果 |
| 阴影 | 简单灰色 | 多层彩色阴影 |
| CSS 架构 | 每个文件独立复制粘贴 `<style>` 块 | Vue scoped style |

路由问题：贷后助手侧边栏缺少「报告列表」和「编辑报告」入口；研究完成后无快捷跳转到编辑报告。

## 2. 目标

- 以贷后助手（App.vue / `/app/`）的玻璃拟态风格为基准，统一所有页面视觉效果
- 修复贷后助手侧边栏缺失的报告相关导航入口
- 研究完成后提供「编辑报告」快捷跳转按钮
- 长期可渐进迁移到 Vue SPA + Vue Router

## 3. 方案：共享样式基础库 + 渐进迁移（方案 C）

### 3.1 第一步（本次实现）

创建共享 CSS 基础库 → 快速统一所有 HTML 模板 + 贷后助手的视觉效果 → 修复路由入口。

### 3.2 第二步（后续）

按优先级逐步将 HTML 模板迁移为 Vue 组件，接入 Vue Router。

## 4. 设计系统 — CSS 变量基础库

### 4.1 文件位置

`frontend/src/assets/shared.css`（构建时由 Vite 输出到 `frontend/dist/assets/shared.css`）

### 4.2 CSS 变量定义

```css
:root {
  /* === 主色调 === */
  --color-primary: #2563eb;
  --color-primary-light: #3b82f6;
  --color-primary-dark: #1d4ed8;
  --color-accent: #7c3aed;
  --color-accent-light: #8b5cf6;
  --color-indigo: #4f46e5;

  /* === 渐变 === */
  --gradient-brand: linear-gradient(135deg, #2563eb, #7c3aed);
  --gradient-action: linear-gradient(90deg, #3b82f6, #8b5cf6);
  --gradient-report: linear-gradient(180deg, #2563eb, #7c3aed);

  /* === 表面/背景 === */
  --surface-panel: rgba(255, 255, 255, 0.95);
  --surface-sidebar: rgba(255, 255, 255, 0.98);
  --surface-card: #ffffff;
  --bg-app: radial-gradient(circle at 20% 20%, #f8fafc, #dbeafe 60%);
  --bg-report: linear-gradient(165deg, #ffffff 0%, #f8fafc 42%, #f1f5f9 100%);

  /* === 文字 === */
  --text-primary: #0f172a;
  --text-body: #1f2937;
  --text-secondary: #334155;
  --text-muted: #475569;
  --text-subtle: #64748b;

  /* === 边框 === */
  --border-light: rgba(148, 163, 184, 0.18);
  --border-medium: rgba(148, 163, 184, 0.28);
  --border-strong: rgba(148, 163, 184, 0.4);

  /* === 圆角 === */
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 18px;
  --radius-xl: 20px;
  --radius-full: 9999px;

  /* === 阴影 === */
  --shadow-card: 0 2px 12px rgba(15, 23, 42, 0.06);
  --shadow-panel: 0 12px 32px rgba(15, 23, 42, 0.10);
  --shadow-modal: 0 24px 64px rgba(15, 23, 42, 0.25);
  --shadow-button: 0 4px 12px rgba(59, 130, 246, 0.3);

  /* === 动效 === */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --transition-fast: 150ms var(--ease-out);
  --transition-normal: 250ms var(--ease-out);

  /* === 字体 === */
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
```

### 4.3 通用工具类

```css
/* 面板 */
.panel-glass {
  background: var(--surface-panel);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-panel);
}

/* 卡片 */
.card-glass {
  background: var(--surface-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  transition: transform var(--transition-normal), box-shadow var(--transition-normal);
}
.card-glass:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-panel);
}

/* 主按钮 */
.btn-primary {
  background: var(--gradient-brand);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  padding: 12px 24px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast);
}
.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-button);
}

/* 次按钮 */
.btn-secondary {
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid var(--border-medium);
  color: var(--text-muted);
  border-radius: var(--radius-md);
  padding: 10px 20px;
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
}
.btn-secondary:hover {
  border-color: var(--color-primary-light);
  color: var(--color-primary-light);
}

/* 极光背景 */
.bg-aurora {
  background: var(--bg-app);
  position: relative;
}
```

## 5. 导航布局统一

### 5.1 侧边栏结构（所有页面共用）

```
┌──────────────────────────┐
│  [logo] 贷后管理助手       │
│  ──────────────────────── │
│  📋 贷后助手    → /app/   │
│  ⚠️  预警中心    → /warnings│
│  🏢 贷后项目    → /enterprises│
│  📡 数据源管理  → /sources │
│  📄 参考文档    → /rag/upload│
│  📊 报告列表    → /reports │  ← 新增
│  ✏️  编辑报告    → /reports-edit│ ← 新增
│  ──────────────────────── │
│  [+ 开始新调查]            │
└──────────────────────────┘
```

- 宽度：280px（比贷后助手当前 400px 收窄，给内容区更多空间）
- 贷后助手展开状态宽度从 400px 改为 280px
- HTML 模板：新建此侧边栏结构，替代原有深色顶栏

### 5.2 路由修复清单

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `App.vue` | 侧边栏缺少「报告列表」「编辑报告」 | 增加 2 个 sidebar-link |
| 2 | `App.vue` | 研究完成后无编辑报告入口 | 报告区域顶部增加「✏️ 编辑报告」按钮，点击跳转 `/reports-edit?id={report_id}` |
| 3 | `App.vue` | 侧边栏宽度 400px 太宽 | 改为 280px |
| 4 | `reports-edit.html` | 无 report_id 时显示 404 | 已有处理，需加「返回报告列表」链接 |
| 5 | 6 个 HTML 模板 | 深色顶栏导航 | 替换为左侧侧边栏 |

### 5.3 快捷跳转按钮

研究完成后，在报告区域顶部显示操作栏：

```
┌──────────────────────────────────────────┐
│  ✅ 报告已生成       [✏️ 编辑报告] [📋 报告列表] │
└──────────────────────────────────────────┘
```

- 仅在 `reportMarkdown` 有内容时显示
- 「编辑报告」跳转 `/reports-edit?id={当前报告ID}`
- 「报告列表」跳转 `/reports`
- **关键前置条件**：App.vue 当前 `saveReport` 是 fire-and-forget fetch，需改为捕获响应中的 `id` 字段（`POST /api/reports` 返回 `{"status":"ok","id":"...","filename":"..."}`），存入新的响应式变量 `savedReportId`，供快捷按钮使用
- 动画：fadeIn + slideDown

## 6. 各页面迁移明细

### 6.1 公共改动模式（所有 6 个 HTML 模板）

每个文件：
1. **引入共享 CSS**：`<link rel="stylesheet" href="/app/assets/shared.css">`
2. **删除重复样式**：移除 `.header`、`.nav-link`、颜色/圆角/阴影/字体定义
3. **替换导航**：深色顶栏 → 侧边栏 HTML 结构
4. **替换类名**：`.btn-primary` / `.btn-outline` / `.container` / `.card` 等改为统一类名
5. **替换 body 背景**：`background: #f1f5f9` → `background: var(--bg-app)`
6. **保留页面特有样式**：仅保留该页独有的业务样式

### 6.2 各页面特殊处理

#### 预警中心 (`warnings.html`)
- **保留**: 严重度左边框颜色（红 `#ef4444` / 橙 `#f97316` / 黄 `#f59e0b`）
- **保留**: 骨架屏 shimmer 动画
- **保留**: Badge pill 系统（`.badge.red` / `.badge.orange` / `.badge.yellow`）
- **改动**: 卡片改用 `.card-glass`，去掉 `border-left` 硬编码颜色改用 CSS 变量引用

#### 贷后项目 (`enterprises.html`)
- **保留**: 项目卡片交替色左边框（nth-child 规则）
- **保留**: 手风琴展开 `.open` 逻辑
- **改动**: 手风琴动画从 `max-height` 过渡改为 `grid-template-rows`（更流畅）

#### 数据源管理 (`sources.html`)
- **保留**: CSS toggle 开关
- **保留**: 表格结构
- **改动**: 表格圆角从 `12px` 改为 `var(--radius-md)`

#### 参考文档 (`upload.html`)
- **保留**: 文件上传拖拽区虚线框
- **改动**: 虚线框颜色改为 `var(--border-medium)`，背景改为半透明

#### 报告列表 (`reports.html`)
- **保留**: 列表结构、搜索过滤逻辑
- **改动**: 列表项 hover 加浮起效果 `.card-glass:hover`

#### 报告编辑 (`reports-edit.html`)
- **保留**: 分栏编辑器（Markdown textarea + 预览）
- **保留**: 等宽字体
- **改动**: 预览区加 markdown 渲染样式（参考贷后助手 `:deep()` 中的 h1-h6、列表、代码块、引用样式）
- **改动**: 编辑区和预览区面板改为 `.panel-glass`

### 6.3 贷后助手 (`App.vue`)

改动最小，仅增加功能入口：
1. **侧边栏增加 2 个链接**：报告列表 → `/reports`、编辑报告 → `/reports-edit`
2. **研究完成后显示快捷操作栏**：`v-if="reportMarkdown"` 渲染操作按钮
3. **侧边栏宽度调整**：`400px` → `280px`（`min-width` 同步改为 `280px`）

## 7. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `frontend/src/assets/shared.css` | 新建 | CSS 变量 + 通用工具类 |
| `frontend/src/App.vue` | 修改 | 侧边栏 + 2 链接 + 快捷按钮 + 宽度调整 |
| `frontend/src/style.css` | 修改 | 将 `:root` 变量提取/同步到 shared.css |
| `backend/src/templates/warnings.html` | 修改 | 引入 shared.css + 导航替换 + 样式统一 |
| `backend/src/templates/enterprises.html` | 修改 | 同上 |
| `backend/src/templates/sources.html` | 修改 | 同上 |
| `backend/src/templates/upload.html` | 修改 | 同上 |
| `backend/src/templates/reports.html` | 修改 | 同上 |
| `backend/src/templates/reports-edit.html` | 修改 | 同上 |
| `frontend/vite.config.ts` | 可能修改 | 确保 `shared.css` 能被 HTML 模板引用 |

## 8. 验证方式

### 8.1 手动检查

1. 启动应用，依次访问 `/app/`、`/warnings`、`/enterprises`、`/sources`、`/rag/upload`、`/reports`、`/reports-edit`，确认侧边栏一致
2. 在贷后助手完成一次研究，确认快捷编辑按钮出现且跳转正确
3. 确认所有页面颜色、圆角、阴影风格一致

### 8.2 自动检查

- `curl -s http://localhost:8080/warnings | grep -c 'shared.css'` 期望返回 `1`
- 对所有 HTML 页面执行相同检查
- 用浏览器开发者工具检查 CSS 变量是否生效

## 9. 风险与注意事项

- **不要改业务逻辑**：只换 CSS 和导航 HTML 结构，JS 逻辑不动
- **已确认**：所有 6 个 HTML 模板的 JS 代码中均无对 `.header`、`.nav-link`、`.nav` 或任何导航相关 DOM 元素的引用。导航栏替换为零 JS 风险的纯 HTML/CSS 改动。
- **`shared.css` 需要被 `/app/` 路径访问到**：由 Vite 构建输出到 `dist/assets/`，FastAPI 通过 `/app` mount 自动可访问。HTML 模板中以 `<link href="/app/assets/shared.css">` 引用
- **构建流程**：`npm run build` 后才能看到 shared.css 生效
