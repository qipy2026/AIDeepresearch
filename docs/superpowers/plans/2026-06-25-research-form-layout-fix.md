# Research 页面表单卡片布局修复 实现计划

> **面向 AI 代理的工作者：** 此计划极其简单，直接在当前会话中执行即可，无需子代理。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 /loan/research 页面 idle 阶段表单卡片的 max-width 从 600px 扩大到 800px，减少右侧空白。

**架构：** 纯 CSS 调整，仅修改 ResearchPage.vue 中两处 max-width 值，无逻辑变更。

**技术栈：** Vue 3 scoped CSS

---

### 任务 1：增大表单卡片 max-width

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue`

- [ ] **步骤 1：修改 `.layout-centered` 的 max-width**

找到第 1267 行附近：
```css
.layout-centered {
  max-width: 600px;
  justify-content: center;
  align-items: center;
}
```

改为：
```css
.layout-centered {
  max-width: 800px;
  justify-content: center;
  align-items: center;
}
```

- [ ] **步骤 2：修改 `.panel-centered` 的 max-width**

找到第 1297 行附近：
```css
.panel-centered {
  width: 100%;
  max-width: 600px;
  padding: 40px;
  ...
}
```

改为：
```css
.panel-centered {
  width: 100%;
  max-width: 800px;
  padding: 40px;
  ...
}
```

- [ ] **步骤 3：在浏览器中验证**

1. 启动开发服务器（如未启动）：`cd frontend && npm run dev`
2. 打开 `http://localhost:5174/loan/research`
3. 确认表单卡片在 1920px 宽屏幕下右侧空白明显减少
4. 确认 1366px 屏幕下仍然居中且不溢出
5. 确认切换到调查中状态（输入企业名并提交）后结果面板不受影响

- [ ] **步骤 4：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue
git commit -m "fix: expand research form card max-width from 600px to 800px"
```
