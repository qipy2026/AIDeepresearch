# Research 页面表单卡片布局修复

**日期:** 2026-06-25
**状态:** 已确认

## 问题

`/loan/research` 页面在 idle 阶段（表单输入卡片）右侧有大片空白。
根因：表单卡片 `.layout-centered` 和 `.panel-centered` 的 `max-width` 为 `600px`，
在宽屏幕上（1920px），减去 280px 侧边栏后，内容区有约 1640px，
表单卡片居中后两侧各有约 520px 空白。

## 方案

将 `max-width` 从 `600px` 增大到 `800px`，减少两侧空白的同时保持居中布局。

## 改动

**文件:** `frontend/src/pages/ResearchPage.vue`

**1. `.layout-centered`（约第 1267 行）：**
```diff
 .layout-centered {
-  max-width: 600px;
+  max-width: 800px;
   justify-content: center;
   align-items: center;
 }
```

**2. `.panel-centered`（约第 1297 行）：**
```diff
 .panel-centered {
   width: 100%;
-  max-width: 600px;
+  max-width: 800px;
   padding: 40px;
   ...
 }
```

## 影响范围

- 仅影响 `researchPhase === 'idle'` 时的居中表单卡片
- 不改变 `layout-fullscreen`（调查中/结果展示）的任何行为
- 已有响应式断点 `@media (max-width: 960px)` 可覆盖小屏场景
- 1366px 笔记本屏幕下表单两侧各约 143px 空白，布局正常

## 屏幕表现预估

| 屏幕宽度 | 侧边栏 | 表单 | 每侧空白 |
|---------|-------|------|---------|
| 1920px | 280px | 800px | ~420px |
| 1440px | 280px | 800px | ~180px |
| 1366px | 280px | 800px | ~143px |
| 1280px | 280px | 800px | ~100px |
