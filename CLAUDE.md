<!-- superpowers-zh:begin (do not edit between these markers) -->
# Superpowers-ZH 中文增强版

本项目已安装 superpowers-zh 技能框架（20 个 skills）。

## 核心规则

1. **收到任务时，先检查是否有匹配的 skill** — 哪怕只有 1% 的可能性也要检查
2. **设计先于编码** — 收到功能需求时，先用 brainstorming skill 做需求分析
3. **测试先于实现** — 写代码前先写测试（TDD）
4. **验证先于完成** — 声称完成前必须运行验证命令

## 可用 Skills

Skills 位于 `.claude/skills/` 目录，每个 skill 有独立的 `SKILL.md` 文件。

- **brainstorming**: 在任何创造性工作之前必须使用此技能——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。
- **chinese-code-review**: 中文 review 沟通参考——话术模板、分级标注（必须修复/建议修改/仅供参考）、国内团队常见反模式应对。仅在用户显式 /chinese-code-review 时调用，不要根据上下文自动触发。
- **chinese-commit-conventions**: 中文 commit 与 changelog 配置参考——Conventional Commits 中文适配、commitlint/husky/commitizen 中文模板、conventional-changelog 中文配置。仅在用户显式 /chinese-commit-conventions 时调用，不要根据上下文自动触发。
- **chinese-documentation**: 中文文档排版参考——中英文空格、全半角标点、术语保留、链接格式、中文文案排版指北约定。仅在用户显式 /chinese-documentation 时调用，不要根据上下文自动触发。
- **chinese-git-workflow**: 国内 Git 平台配置参考——Gitee、Coding.net、极狐 GitLab、CNB 的 SSH/HTTPS/凭据/CI 接入差异与镜像同步配置。仅在用户显式 /chinese-git-workflow 时调用，不要根据上下文自动触发。
- **dispatching-parallel-agents**: 当面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用
- **executing-plans**: 当你有一份书面实现计划需要在单独的会话中执行，并设有审查检查点时使用
- **finishing-a-development-branch**: 当实现完成、所有测试通过、需要决定如何集成工作时使用——通过提供合并、PR 或清理等结构化选项来引导开发工作的收尾
- **mcp-builder**: MCP 服务器构建方法论 — 系统化构建生产级 MCP 工具，让 AI 助手连接外部能力
- **receiving-code-review**: 收到代码审查反馈后、实施建议之前使用，尤其当反馈不明确或技术上有疑问时——需要技术严谨性和验证，而非敷衍附和或盲目执行
- **requesting-code-review**: 完成任务、实现重要功能或合并前使用，用于验证工作成果是否符合要求
- **subagent-driven-development**: 当在当前会话中执行包含独立任务的实现计划时使用
- **systematic-debugging**: 遇到任何 bug、测试失败或异常行为时使用，在提出修复方案之前执行
- **test-driven-development**: 在实现任何功能或修复 bug 时使用，在编写实现代码之前
- **using-git-worktrees**: 当需要开始与当前工作区隔离的功能开发，或在执行实现计划之前使用——通过原生工具或 git worktree 回退机制确保隔离工作区存在
- **using-superpowers**: 在开始任何对话时使用——确立如何查找和使用技能，要求在任何响应（包括澄清性问题）之前调用 Skill 工具
- **verification-before-completion**: 在宣称工作完成、已修复或测试通过之前使用，在提交或创建 PR 之前——必须运行验证命令并确认输出后才能声称成功；始终用证据支撑断言
- **workflow-runner**: 在 Claude Code / OpenClaw / Cursor 中直接运行 agency-orchestrator YAML 工作流——无需 API key，使用当前会话的 LLM 作为执行引擎。当用户提供 .yaml 工作流文件或要求多角色协作完成任务时触发。
- **writing-plans**: 当你有规格说明或需求用于多步骤任务时使用，在动手写代码之前
- **writing-skills**: 当创建新技能、编辑现有技能或在部署前验证技能是否有效时使用

## 如何使用

当任务匹配某个 skill 时，使用 `Skill` 工具加载对应 skill 并严格遵循其流程。绝不要用 Read 工具读取 SKILL.md 文件。

如果你认为哪怕只有 1% 的可能性某个 skill 适用于你正在做的事情，你必须调用该 skill 检查。
<!-- superpowers-zh:end -->

# gstack

本项目已安装 gstack 技能集。位于 `~/.claude/skills/gstack/`。

## 关键规则

- **所有网页浏览必须使用 `/browse`** — 绝不使用 `mcp__claude-in-chrome__*` 工具进行任何网页浏览
- gstack 提供快速无头浏览器用于 QA 测试和站点 dogfooding

## 可用 gstack Skills

- **/office-hours** — 办公室时间：记录设计决策并在团队间交接工作
- **/plan-ceo-review** — CEO 审查规划
- **/plan-eng-review** — 工程审查规划
- **/plan-design-review** — 设计审查规划
- **/design-consultation** — 设计咨询
- **/design-shotgun** — 设计快速迭代
- **/design-html** — HTML 设计
- **/review** — 代码审查
- **/ship** — 发布交付
- **/land-and-deploy** — 上线部署
- **/canary** — 金丝雀发布
- **/benchmark** — 基准测试
- **/browse** — 网页浏览（所有网页浏览的首选工具）
- **/connect-chrome** — 连接 Chrome 浏览器
- **/qa** — QA 测试
- **/qa-only** — 仅 QA 测试
- **/design-review** — 设计审查
- **/setup-browser-cookies** — 设置浏览器 Cookies
- **/setup-deploy** — 设置部署
- **/setup-gbrain** — 设置 gbrain
- **/retro** — 回顾总结
- **/investigate** — 调查分析
- **/document-release** — 发布文档
- **/document-generate** — 生成文档
- **/codex** — Codex 代码智能
- **/cso** — 首席安全官安全审计
- **/autoplan** — 自动规划
- **/plan-devex-review** — 开发者体验审查规划
- **/devex-review** — 开发者体验审查
- **/careful** — 谨慎模式
- **/freeze** — 冻结模式
- **/guard** — 守护模式
- **/unfreeze** — 解冻模式
- **/gstack-upgrade** — gstack 升级
- **/learn** — 学习模式
