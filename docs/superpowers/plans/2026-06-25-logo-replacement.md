# 公司 LOGO 替换 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将侧边栏内联 SVG 图标替换为 LOGO.png，同时为应用添加浏览器 favicon

**架构：** 使用 PowerShell + System.Drawing 从源 LOGO（2400×3009）生成多尺寸 PNG + .ico，放入 `frontend/public/`；修改 AppSidebar.vue 模板/样式和 index.html

**技术栈：** PowerShell (System.Drawing), Vue 3 单文件组件, HTML5 favicon

---

### 任务 1：生成多尺寸 LOGO 图片

**文件：**
- 创建：`frontend/public/generate-logos.ps1`（一次性脚本，运行后可删除）

- [ ] **步骤 1：编写 PowerShell 图片生成脚本**

```powershell
Add-Type -AssemblyName System.Drawing

$source = "E:\work\files\LOGO.png"
$outDir = "e:\work\code\AIDeepresearch\frontend\public"

$srcImg = [System.Drawing.Image]::FromFile($source)

# logo-160.png — 保持比例，高度 160px
$h = 160
$w = [int]($srcImg.Width * $h / $srcImg.Height)
$bmp160 = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp160)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($srcImg, 0, 0, $w, $h)
$g.Dispose()
$bmp160.Save("$outDir\logo-160.png", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp160.Dispose()

# favicon-32.png
$bmp32 = New-Object System.Drawing.Bitmap(32, 32)
$g = [System.Drawing.Graphics]::FromImage($bmp32)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($srcImg, 0, 0, 32, 32)
$g.Dispose()
$bmp32.Save("$outDir\favicon-32.png", [System.Drawing.Imaging.ImageFormat]::Png)

# favicon-16.png
$bmp16 = New-Object System.Drawing.Bitmap(16, 16)
$g = [System.Drawing.Graphics]::FromImage($bmp16)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($srcImg, 0, 0, 16, 16)
$g.Dispose()
$bmp16.Save("$outDir\favicon-16.png", [System.Drawing.Imaging.ImageFormat]::Png)

# favicon.ico — 包含 32px 和 16px 两个尺寸
# ICO 文件头
$fs = [System.IO.File]::Open("$outDir\favicon.ico", [System.IO.FileMode]::Create)
$bw = New-Object System.IO.BinaryWriter($fs)

# ICO header: reserved(2) + type=1(2) + count(2)
$bw.Write([UInt16]0)  # reserved
$bw.Write([UInt16]1)  # type = ICO
$bw.Write([UInt16]2)  # 2 images

# 写入两个尺寸的 ICO entry + 数据
$images = @(
    @{ Bmp=$bmp32; Size=32 },
    @{ Bmp=$bmp16; Size=16 }
)

$offset = 6 + 16 * $images.Count  # header + entries

foreach ($img in $images) {
    $b = $img.Bmp
    $s = $img.Size
    # 转为带 AND mask 的 32bpp raw 数据
    $ms = New-Object System.IO.MemoryStream
    $b.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngBytes = $ms.ToArray()
    $ms.Close()

    $bw.Write([Byte]$s)           # width (0 = 256)
    $bw.Write([Byte]$s)           # height (0 = 256)
    $bw.Write([Byte]0)            # color palette
    $bw.Write([Byte]0)            # reserved
    $bw.Write([UInt16]1)          # color planes
    $bw.Write([UInt16]32)         # bits per pixel
    $bw.Write([UInt32]$pngBytes.Length)  # data size
    $bw.Write([UInt32]$offset)    # offset
    $offset += $pngBytes.Length
}
foreach ($img in $images) {
    $ms = New-Object System.IO.MemoryStream
    $img.Bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bw.Write($ms.ToArray())
    $ms.Close()
}

$bw.Close()
$fs.Close()

# Copy original
Copy-Item $source "$outDir\LOGO.png" -Force

$bmp32.Dispose()
$bmp16.Dispose()
$srcImg.Dispose()

Write-Host "Done: logo-160.png, favicon-32.png, favicon-16.png, favicon.ico, LOGO.png"
```

- [ ] **步骤 2：运行脚本生成图片**

```bash
powershell -ExecutionPolicy Bypass -File frontend/public/generate-logos.ps1
```

预期输出：`Done: logo-160.png, favicon-32.png, favicon-16.png, favicon.ico, LOGO.png`

- [ ] **步骤 3：验证生成文件**

```bash
ls -la frontend/public/LOGO.png frontend/public/logo-160.png frontend/public/favicon-32.png frontend/public/favicon-16.png frontend/public/favicon.ico
```

预期：5 个文件均存在，大小 > 0

- [ ] **步骤 4：删除一次性脚本**

```bash
rm frontend/public/generate-logos.ps1
```

- [ ] **步骤 5：Commit**

```bash
git add frontend/public/LOGO.png frontend/public/logo-160.png frontend/public/favicon-32.png frontend/public/favicon-16.png frontend/public/favicon.ico
git commit -m "feat: add resized logo images and favicons
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：更新 AppSidebar.vue 模板和样式

**文件：**
- 修改：`frontend/src/components/AppSidebar.vue`

- [ ] **步骤 1：替换模板中的 SVG 图标为 img 标签**

将第 5-8 行：

```html
<div class="sidebar-logo-icon">
  <svg viewBox="0 0 24 24" width="20" height="20">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="white" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</div>
```

替换为：

```html
<div class="sidebar-logo-icon">
  <img src="/logo-160.png" alt="贷后管理助手" />
</div>
```

- [ ] **步骤 2：更新 .sidebar-logo 样式（第 58-62 行）**

将：

```css
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}
```

替换为：

```css
.sidebar-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
```

- [ ] **步骤 3：更新 .sidebar-logo-icon 样式（第 64-73 行）**

将：

```css
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
```

替换为：

```css
.sidebar-logo-icon {
  width: 160px;
  height: 200px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}
```

- [ ] **步骤 4：新增 img 样式（在第 73 行之后插入）**

在 `.sidebar-logo-icon svg` 块替换为：

```css
.sidebar-logo-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
```

- [ ] **步骤 5：验证构建不报错**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

预期：`Build succeeded` 或类似成功信息，无编译错误

- [ ] **步骤 6：Commit**

```bash
git add frontend/src/components/AppSidebar.vue
git commit -m "feat: replace inline SVG logo with LOGO.png in sidebar
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：添加 favicon 到 index.html

**文件：**
- 修改：`frontend/index.html`

- [ ] **步骤 1：在 head 中添加 favicon 链接**

在 `<meta charset="UTF-8" />` 之后、`<title>` 之前，插入 4 行：

```html
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png" />
<link rel="shortcut icon" href="/favicon.ico" />
<link rel="apple-touch-icon" sizes="180x180" href="/logo-160.png" />
```

最终 `<head>` 应为：

```html
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png" />
  <link rel="shortcut icon" href="/favicon.ico" />
  <link rel="apple-touch-icon" sizes="180x180" href="/logo-160.png" />
  <title>AIDeepresearch 贷后管理助手</title>
  <link rel="stylesheet" href="/shared.css" />
</head>
```

- [ ] **步骤 2：验证构建不报错**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

预期：构建成功

- [ ] **步骤 3：Commit**

```bash
git add frontend/index.html
git commit -m "feat: add favicon and apple-touch-icon links
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：端到端验证

**文件：**
- 无新建/修改文件

- [ ] **步骤 1：启动开发服务器（后台）**

```bash
cd frontend && npm run dev &
sleep 3
```

- [ ] **步骤 2：验证 logo-160.png 可访问**

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download}" http://localhost:5173/logo-160.png
```

预期：`200` 且 `size_download` > 1000（非空图片）

- [ ] **步骤 3：验证 favicon.ico 可访问**

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download}" http://localhost:5173/favicon.ico
```

预期：`200` 且 `size_download` > 0

- [ ] **步骤 4：验证 favicon-32.png 可访问**

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download}" http://localhost:5173/favicon-32.png
```

预期：`200` 且 `size_download` > 0

- [ ] **步骤 5：验证首页 HTML 包含 favicon 链接**

```bash
curl -s http://localhost:5173/ | grep -c 'favicon'
```

预期：输出 `3`（3 个 favicon 相关 link）

- [ ] **步骤 6：停止开发服务器**

```bash
kill %1 2>/dev/null; true
```
