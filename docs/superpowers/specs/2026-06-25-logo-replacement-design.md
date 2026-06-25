# 公司 LOGO 替换设计规格

**日期**: 2026-06-25
**状态**: 已批准
**来源**: E:\work\files\LOGO.png（2400×3009 RGBA PNG）

## 范围

1. 侧边栏顶部图标：从内联 SVG 图标替换为 LOGO.png
2. 浏览器标签页 favicon：新增（当前无 favicon）
3. 兼容性：覆盖所有主流浏览器 + IE（生成 .ico）

## 文件清单

### 新增文件（`frontend/public/`）

| 文件 | 尺寸 | 用途 |
|------|------|------|
| `LOGO.png` | 2400×3009 | 原始备份 |
| `logo-160.png` | 按比例缩放 | 侧边栏显示 + apple-touch-icon |
| `favicon-32.png` | 32×32 | 现代浏览器 favicon |
| `favicon-16.png` | 16×16 | 小尺寸 favicon |
| `favicon.ico` | 16+32 合并 | IE 兼容 favicon |

生成脚本：PowerShell，利用 `System.Drawing` 原生物理缩放 + 合并 .ico。无需安装额外依赖。

## 修改清单

### 1. `frontend/src/components/AppSidebar.vue`

**模板**：`sidebar-logo-icon` 内 SVG 替换为 `<img src="/logo-160.png" alt="贷后管理助手" />`

**样式**：
- `.sidebar-logo` → `flex-direction: column; align-items: center; gap: 12px`
- `.sidebar-logo-icon` → `width: 160px; height: 200px; border-radius: 12px; background: rgba(248, 250, 252, 1); border: 1px solid rgba(148, 163, 184, 0.2); overflow: hidden`
- 新增 `.sidebar-logo-icon img { width: 100%; height: 100%; object-fit: contain; }`

### 2. `frontend/index.html`

`<head>` 中 `<meta charset>` 之后、`<title>` 之前新增 4 行：

```html
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png" />
<link rel="shortcut icon" href="/favicon.ico" />
<link rel="apple-touch-icon" sizes="180x180" href="/logo-160.png" />
```

## 视觉效果

- 侧边栏头部从"小渐变方块图标 + 横向文字"变为"竖长 LOGO 图（浅色容器）+ 下方居中文字"
- LAYO 保持 contain 比例，透明部分由容器浅色背景衬出
- 文字"贷后管理助手"和副标题保持原有样式，居中显示

## 验证

1. `curl -s http://localhost:5173/logo-160.png` 返回图片
2. `curl -s http://localhost:5173/favicon.ico` 返回图片
3. 浏览器访问：侧边栏显示新 LOGO，标签页显示 favicon
