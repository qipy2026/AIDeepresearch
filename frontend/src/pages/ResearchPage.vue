<template>
  <main class="app-shell" :class="{ expanded: isExpanded }">
    <div class="aurora" aria-hidden="true">
      <span></span>
      <span></span>
      <span></span>
    </div>

    <!-- 初始状态：居中输入卡片 -->
    <div v-if="!isExpanded" class="layout layout-centered">
      <section class="panel panel-form panel-centered">
        <header class="panel-head">
          <div class="logo">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M12 2.5c-.7 0-1.4.2-2 .6L4.6 7C3.6 7.6 3 8.7 3 9.9v4.2c0 1.2.6 2.3 1.6 2.9l5.4 3.9c1.2.8 2.8.8 4 0l5.4-3.9c1-.7 1.6-1.7 1.6-2.9V9.9c0-1.2-.6-2.3-1.6-2.9L14 3.1a3.6 3.6 0 0 0-2-.6Z"
              />
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
            <textarea
              v-model="form.topic"
              placeholder="例如：四川振海保安服务有限公司"
              rows="4"
              required
            ></textarea>
          </label>

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

          <div class="form-actions">
            <button class="submit" type="submit" :disabled="loading">
              <span class="submit-label">
                <svg
                  v-if="loading"
                  class="spinner"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="9" stroke-width="3" />
                </svg>
                {{ loading ? "调查进行中..." : "开始调查" }}
              </span>
            </button>
            <button
              v-if="loading"
              type="button"
              class="secondary-btn"
              @click="cancelResearch"
            >
              取消调查
            </button>
          </div>
        </form>

        <p v-if="error" class="error-chip">
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M10 3.2c-.3 0-.6.2-.8.5L3.4 15c-.4.7.1 1.6.8 1.6h11.6c.7 0 1.2-.9.8-1.6L10.8 3.7c-.2-.3-.5-.5-.8-.5Zm0 4.3c.4 0 .7.3.7.7v4c0 .4-.3.7-.7.7s-.7-.3-.7-.7V8.2c0-.4.3-.7.7-.7Zm0 6.6a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"
            />
          </svg>
          {{ error }}
        </p>
        <p v-else-if="loading" class="hint muted">
          正在收集线索与证据，实时进展见右侧区域。
        </p>
      </section>
    </div>

    <!-- 全屏状态：结果面板 -->
    <div v-else class="layout layout-fullscreen">
      <section
        class="panel panel-result"
        v-if="todoTasks.length || reportMarkdown || progressLogs.length"
      >
        <header class="status-bar">
          <div class="status-main">
            <div class="status-chip" :class="{ active: loading }">
              <span class="dot"></span>
              {{ loading ? "调查进行中" : "调查流程完成" }}
            </div>
            <span class="status-meta">
              任务进度：{{ completedTasks }} / {{ totalTasks || todoTasks.length || 1 }}
            </span>
          </div>
          <div class="status-controls">
            <button class="secondary-btn" @click="startNewResearch" :disabled="loading">
              新调查
            </button>
          </div>
        </header>

        <div class="result-main">
          <!-- 快捷操作栏：报告生成后显示 -->
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
          <div
            v-if="reportMarkdown || generatingReport"
            class="report-block report-block--final"
            :class="{ 'block-highlight': reportHighlight }"
          >
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
              <li
                v-for="task in todoTasks"
                :key="task.id"
                :class="[
                  'task-card',
                  { 'task-card--active': task.id === activeTaskId, 'task-card--completed': task.status === 'completed' }
                ]"
              >
                <button
                  type="button"
                  class="task-card-inner"
                  @click="openTaskDetail(task.id)"
                >
                  <div class="task-card-top">
                    <span class="task-card-title">{{ task.title }}</span>
                    <span class="task-status" :class="task.status">
                      {{ formatTaskStatus(task.status) }}
                    </span>
                  </div>
                  <p v-if="task.intent" class="task-card-intent">{{ task.intent }}</p>
                  <p class="task-card-preview">{{ taskCardPreview(task) }}</p>
                  <span class="task-card-cta">查看详情</span>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <Teleport to="body">
        <div
          v-if="taskDetailOpen && currentTask"
          class="task-modal-backdrop"
          role="presentation"
          @click.self="closeTaskDetail"
        >
          <div
            class="task-modal-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="task-modal-title"
          >
            <header class="task-modal-toolbar">
              <h3 id="task-modal-title" class="task-modal-title">
                {{ currentTaskTitle || "任务详情" }}
              </h3>
              <button type="button" class="task-modal-close" @click="closeTaskDetail">
                关闭
              </button>
            </header>

            <div class="task-modal-body">
              <article class="task-detail task-detail--modal">
                <header class="task-header">
                  <div>
                    <p class="muted" v-if="currentTaskIntent">
                      {{ currentTaskIntent }}
                    </p>
                  </div>
                  <div class="task-chip-group">
                    <span class="task-label">查询：{{ currentTaskQuery || "" }}</span>
                    <span
                      v-if="currentTaskNoteId"
                      class="task-label note-chip"
                      :title="currentTaskNoteId"
                    >
                      笔记：{{ currentTaskNoteId }}
                    </span>
                    <span
                      v-if="currentTaskNotePath"
                      class="task-label note-chip path-chip"
                      :title="currentTaskNotePath"
                    >
                      <span class="path-label">路径：</span>
                      <span class="path-text">{{ currentTaskNotePath }}</span>
                      <button
                        class="chip-action"
                        type="button"
                        @click="copyNotePath(currentTaskNotePath)"
                      >
                        复制
                      </button>
                    </span>
                  </div>
                </header>

                <section v-if="currentTask && currentTask.notices.length" class="task-notices">
                  <h4>系统提示</h4>
                  <ul>
                    <li v-for="(notice, idx) in currentTask.notices" :key="`${notice}-${idx}`">
                      {{ notice }}
                    </li>
                  </ul>
                </section>

                <section
                  class="summary-block"
                  :class="{ 'block-highlight': summaryHighlight }"
                >
                  <h3>任务总结</h3>
                  <pre class="block-pre">{{ currentTaskSummary || "暂无可用信息" }}</pre>
                </section>

                <section
                  class="sources-block"
                  :class="{ 'block-highlight': sourcesHighlight }"
                >
                  <h3>最新来源</h3>
                  <template v-if="currentTaskSources.length">
                    <ul class="sources-list">
                      <li
                        v-for="(item, index) in currentTaskSources"
                        :key="`${item.title}-${index}`"
                        class="source-item"
                      >
                        <a
                          class="source-link"
                          :href="item.url || '#'"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {{ item.title || item.url || `来源 ${index + 1}` }}
                        </a>
                        <div v-if="item.snippet || item.raw" class="source-tooltip">
                          <p v-if="item.snippet">{{ item.snippet }}</p>
                          <p v-if="item.raw" class="muted-text">{{ item.raw }}</p>
                        </div>
                      </li>
                    </ul>
                  </template>
                  <p v-else class="muted">暂无可用来源</p>
                </section>

                <section
                  class="tools-block"
                  :class="{ 'block-highlight': toolHighlight }"
                  v-if="currentTaskToolCalls.length"
                >
                  <h3>工具调用记录</h3>
                  <ul class="tool-list">
                    <li
                      v-for="entry in currentTaskToolCalls"
                      :key="`${entry.eventId}-${entry.timestamp}`"
                      class="tool-entry"
                    >
                      <div class="tool-entry-header">
                        <span class="tool-entry-title">
                          #{{ entry.eventId }} {{ entry.agent }} → {{ entry.tool }}
                        </span>
                        <span
                          v-if="entry.noteId"
                          class="tool-entry-note"
                        >
                          笔记：{{ entry.noteId }}
                        </span>
                      </div>
                      <p v-if="entry.notePath" class="tool-entry-path">
                        笔记路径：
                        <button
                          class="link-btn"
                          type="button"
                          @click="copyNotePath(entry.notePath)"
                        >
                          复制
                        </button>
                        <span class="path-text">{{ entry.notePath }}</span>
                      </p>
                      <p class="tool-subtitle">参数</p>
                      <pre class="tool-pre">{{ formatToolParameters(entry.parameters) }}</pre>
                      <template v-if="entry.result">
                        <p class="tool-subtitle">执行结果</p>
                        <pre class="tool-pre">{{ formatToolResult(entry.result) }}</pre>
                      </template>
                    </li>
                  </ul>
                </section>
              </article>
            </div>
          </div>
        </div>
      </Teleport>

    </div>
  </main>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import DOMPurify from "dompurify";
import { marked } from "marked";

import {
  runResearchStream,
  type ResearchStreamEvent
} from "../services/api";

const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

marked.setOptions({ gfm: true, breaks: true });

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

interface SourceItem {
  title: string;
  url: string;
  snippet: string;
  raw: string;
}

interface ToolCallLog {
  eventId: number;
  agent: string;
  tool: string;
  parameters: Record<string, unknown>;
  result: string;
  noteId: string | null;
  notePath: string | null;
  timestamp: number;
}

interface TodoTaskView {
  id: number;
  title: string;
  intent: string;
  query: string;
  status: string;
  summary: string;
  sourcesSummary: string;
  sourceItems: SourceItem[];
  notices: string[];
  noteId: string | null;
  notePath: string | null;
  toolCalls: ToolCallLog[];
}

const route = useRoute();

const form = reactive({
  topic: "",
  searchApi: ""
});

const loading = ref(false);
const error = ref("");
const progressLogs = ref<string[]>([]);
const isExpanded = ref(false);
const generatingReport = ref(false);
const reportCollapsed = ref(false);
const tasksCollapsed = ref(false);

const todoTasks = ref<TodoTaskView[]>([]);
const activeTaskId = ref<number | null>(null);
const taskDetailOpen = ref(false);
const reportMarkdown = ref("");
const savedReportId = ref("");

const reportHtml = computed(() => {
  const md = reportMarkdown.value?.trim() ?? "";
  if (!md) return "";
  try {
    const raw = marked.parse(md, { async: false }) as string;
    return DOMPurify.sanitize(raw);
  } catch {
    return DOMPurify.sanitize(
      `<p class="report-parse-hint">Markdown 解析失败，以下为原文。</p><pre class="report-fallback">${escapeHtml(md)}</pre>`
    );
  }
});

const summaryHighlight = ref(false);
const sourcesHighlight = ref(false);
const reportHighlight = ref(false);
const toolHighlight = ref(false);

let currentController: AbortController | null = null;

const searchOptions = [
  "advanced",
  "duckduckgo",
  "tavily",
  "perplexity",
  "searxng"
];

const TASK_STATUS_LABEL: Record<string, string> = {
  pending: "待执行",
  in_progress: "进行中",
  completed: "已完成",
  skipped: "已跳过"
};

function formatTaskStatus(status: string): string {
  return TASK_STATUS_LABEL[status] ?? status;
}

const totalTasks = computed(() => todoTasks.value.length);
const completedTasks = computed(() =>
  todoTasks.value.filter((task) => task.status === "completed").length
);

const currentTask = computed(() => {
  if (activeTaskId.value === null) {
    return null;
  }
  return todoTasks.value.find((task) => task.id === activeTaskId.value) ?? null;
});

function taskCardPreview(task: TodoTaskView): string {
  const s = task.summary?.trim();
  if (s) {
    return s;
  }
  const intent = task.intent?.trim();
  if (intent) {
    return intent.length > 160 ? `${intent.slice(0, 160)}…` : intent;
  }
  const src = task.sourcesSummary?.trim();
  if (src) {
    const line = src.split("\n").find((l) => l.trim())?.trim() ?? src;
    return line.length > 160 ? `${line.slice(0, 160)}…` : line;
  }
  return "暂无摘要，点击查看详情";
}

function openTaskDetail(taskId: number) {
  activeTaskId.value = taskId;
  taskDetailOpen.value = true;
}

function closeTaskDetail() {
  taskDetailOpen.value = false;
}

watch(taskDetailOpen, (open) => {
  document.body.style.overflow = open ? "hidden" : "";
});

function onTaskModalKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && taskDetailOpen.value) {
    closeTaskDetail();
  }
}

const currentTaskSources = computed(() => currentTask.value?.sourceItems ?? []);
const currentTaskSummary = computed(() => currentTask.value?.summary ?? "");
const currentTaskTitle = computed(() => currentTask.value?.title ?? "");
const currentTaskIntent = computed(() => currentTask.value?.intent ?? "");
const currentTaskQuery = computed(() => currentTask.value?.query ?? "");
const currentTaskNoteId = computed(() => currentTask.value?.noteId ?? "");
const currentTaskNotePath = computed(() => currentTask.value?.notePath ?? "");
const currentTaskToolCalls = computed(
  () => currentTask.value?.toolCalls ?? []
);

const pulse = (flag: typeof summaryHighlight) => {
  flag.value = false;
  requestAnimationFrame(() => {
    flag.value = true;
    window.setTimeout(() => {
      flag.value = false;
    }, 1200);
  });
};

function parseSources(raw: string): SourceItem[] {
  if (!raw) {
    return [];
  }

  const items: SourceItem[] = [];
  const lines = raw.split("\n");

  let current: SourceItem | null = null;
  const truncate = (value: string, max = 360) => {
    const trimmed = value.trim();
    return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
  };

  const flush = () => {
    if (!current) {
      return;
    }
    const normalized: SourceItem = {
      title: current.title?.trim() || "",
      url: current.url?.trim() || "",
      snippet: current.snippet ? truncate(current.snippet) : "",
      raw: current.raw ? truncate(current.raw, 420) : ""
    };

    if (
      normalized.title ||
      normalized.url ||
      normalized.snippet ||
      normalized.raw
    ) {
      if (!normalized.title && normalized.url) {
        normalized.title = normalized.url;
      }
      items.push(normalized);
    }
    current = null;
  };

  const ensureCurrent = () => {
    if (!current) {
      current = { title: "", url: "", snippet: "", raw: "" };
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }

    if (/^\*/.test(trimmed) && trimmed.includes(" : ")) {
      flush();
      const withoutBullet = trimmed.replace(/^\*\s*/, "");
      const [titlePart, urlPart] = withoutBullet.split(" : ");
      current = {
        title: titlePart?.trim() || "",
        url: urlPart?.trim() || "",
        snippet: "",
        raw: ""
      };
      continue;
    }

    if (/^(Source|信息来源)\s*:/.test(trimmed)) {
      flush();
      const [, titlePart = ""] = trimmed.split(/:\s*(.+)/);
      current = {
        title: titlePart.trim(),
        url: "",
        snippet: "",
        raw: ""
      };
      continue;
    }

    if (/^URL\s*:/.test(trimmed)) {
      ensureCurrent();
      const [, urlPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.url = urlPart.trim();
      continue;
    }

    if (
      /^(Most relevant content from source|信息内容)\s*:/.test(trimmed)
    ) {
      ensureCurrent();
      const [, contentPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.snippet = contentPart.trim();
      continue;
    }

    if (
      /^(Full source content limited to|信息内容限制为)\s*:/.test(trimmed)
    ) {
      ensureCurrent();
      const [, rawPart = ""] = trimmed.split(/:\s*(.+)/);
      current!.raw = rawPart.trim();
      continue;
    }

    if (/^https?:\/\//.test(trimmed)) {
      ensureCurrent();
      if (!current!.url) {
        current!.url = trimmed;
        continue;
      }
    }

    ensureCurrent();
    current!.raw = current!.raw ? `${current!.raw}\n${trimmed}` : trimmed;
  }

  flush();
  return items;
}

function extractOptionalString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function ensureRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function applyNoteMetadata(
  task: TodoTaskView,
  payload: Record<string, unknown>
): void {
  const noteId = extractOptionalString(payload.note_id);
  if (noteId) {
    task.noteId = noteId;
  }
  const notePath = extractOptionalString(payload.note_path);
  if (notePath) {
    task.notePath = notePath;
  }
}

function formatToolParameters(parameters: Record<string, unknown>): string {
  try {
    return JSON.stringify(parameters, null, 2);
  } catch (error) {
    console.warn("无法格式化工具参数", error, parameters);
    return Object.entries(parameters)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join("\n");
  }
}

function formatToolResult(result: string): string {
  const trimmed = result.trim();
  const limit = 900;
  if (trimmed.length > limit) {
    return `${trimmed.slice(0, limit)}…`;
  }
  return trimmed;
}

async function copyNotePath(path: string | null | undefined) {
  if (!path) {
    return;
  }

  try {
    await navigator.clipboard.writeText(path);
    progressLogs.value.push(`已复制笔记路径：${path}`);
  } catch (error) {
    console.warn("无法直接复制到剪贴板", error);
    window.prompt("复制以下笔记路径", path);
    progressLogs.value.push("请手动复制笔记路径");
  }
}

function resetWorkflowState() {
  todoTasks.value = [];
  activeTaskId.value = null;
  taskDetailOpen.value = false;
  document.body.style.overflow = "";
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

function findTask(taskId: unknown): TodoTaskView | undefined {
  const numeric =
    typeof taskId === "number"
      ? taskId
      : typeof taskId === "string"
      ? Number(taskId)
      : NaN;
  if (Number.isNaN(numeric)) {
    return undefined;
  }
  return todoTasks.value.find((task) => task.id === numeric);
}

function upsertTaskMetadata(task: TodoTaskView, payload: Record<string, unknown>) {
  if (typeof payload.title === "string" && payload.title.trim()) {
    task.title = payload.title.trim();
  }
  if (typeof payload.intent === "string" && payload.intent.trim()) {
    task.intent = payload.intent.trim();
  }
  if (typeof payload.query === "string" && payload.query.trim()) {
    task.query = payload.query.trim();
  }
}

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

  try {
    await runResearchStream(
      payload,
      (event: ResearchStreamEvent) => {
        if (event.type === "status") {
          const message =
            typeof event.message === "string" && event.message.trim()
              ? event.message
              : "流程状态更新";
          progressLogs.value.push(message);

          const payload = event as Record<string, unknown>;
          const task = findTask(payload.task_id);
          if (task && message) {
            task.notices.push(message);
            applyNoteMetadata(task, payload);
          }
          return;
        }

        if (event.type === "todo_list") {
          const tasks = Array.isArray(event.tasks)
            ? (event.tasks as Record<string, unknown>[])
            : [];

          todoTasks.value = tasks.map((item, index) => {
            const rawId =
              typeof item.id === "number"
                ? item.id
                : typeof item.id === "string"
                ? Number(item.id)
                : index + 1;
            const id = Number.isFinite(rawId) ? Number(rawId) : index + 1;
            const noteId =
              typeof item.note_id === "string" && item.note_id.trim()
                ? item.note_id.trim()
                : null;
            const notePath =
              typeof item.note_path === "string" && item.note_path.trim()
                ? item.note_path.trim()
                : null;

            return {
              id,
              title:
                typeof item.title === "string" && item.title.trim()
                  ? item.title.trim()
                  : `任务${id}`,
              intent:
                typeof item.intent === "string" && item.intent.trim()
                  ? item.intent.trim()
                  : "探索与主题相关的关键信息",
              query:
                typeof item.query === "string" && item.query.trim()
                  ? item.query.trim()
                  : form.topic.trim(),
              status:
                typeof item.status === "string" && item.status.trim()
                  ? item.status.trim()
                  : "pending",
              summary: "",
              sourcesSummary: "",
              sourceItems: [],
              notices: [],
              noteId,
              notePath,
              toolCalls: []
            } as TodoTaskView;
          });

          if (todoTasks.value.length) {
            activeTaskId.value = todoTasks.value[0].id;
            progressLogs.value.push("已生成任务清单");
          } else {
            progressLogs.value.push("未生成任务清单，使用默认任务继续");
          }
          return;
        }

        if (event.type === "task_status") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }

          upsertTaskMetadata(task, payload);
          applyNoteMetadata(task, payload);
          const status =
            typeof event.status === "string" && event.status.trim()
              ? event.status.trim()
              : task.status;
          task.status = status;

          if (status === "in_progress") {
            task.summary = "";
            task.sourcesSummary = "";
            task.sourceItems = [];
            task.notices = [];
            activeTaskId.value = task.id;
            progressLogs.value.push(`开始执行任务：${task.title}`);
          } else if (status === "completed") {
            if (typeof event.summary === "string" && event.summary.trim()) {
              task.summary = event.summary.trim();
            }
            if (
              typeof event.sources_summary === "string" &&
              event.sources_summary.trim()
            ) {
              task.sourcesSummary = event.sources_summary.trim();
              task.sourceItems = parseSources(task.sourcesSummary);
            }
            progressLogs.value.push(`完成任务：${task.title}`);
            if (activeTaskId.value === task.id) {
              pulse(summaryHighlight);
              pulse(sourcesHighlight);
            }
          } else if (status === "skipped") {
            progressLogs.value.push(`任务跳过：${task.title}`);
          }
          return;
        }

        if (event.type === "sources") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }

          const textCandidates = [
            payload.latest_sources,
            payload.sources_summary,
            payload.raw_context
          ];
          const latestText = textCandidates
            .map((value) => (typeof value === "string" ? value.trim() : ""))
            .find((value) => value);

          if (latestText) {
            task.sourcesSummary = latestText;
            task.sourceItems = parseSources(latestText);
            if (activeTaskId.value === task.id) {
              pulse(sourcesHighlight);
            }
            progressLogs.value.push(`已更新任务来源：${task.title}`);
          }

          if (typeof payload.backend === "string") {
            progressLogs.value.push(
              `当前使用搜索后端：${payload.backend}`
            );
          }

          applyNoteMetadata(task, payload);

          return;
        }

        if (event.type === "task_summary_chunk") {
          const payload = event as Record<string, unknown>;
          const task = findTask(event.task_id);
          if (!task) {
            return;
          }
          const chunk =
            typeof event.content === "string" ? event.content : "";
          task.summary += chunk;
          applyNoteMetadata(task, payload);
          if (activeTaskId.value === task.id) {
            pulse(summaryHighlight);
          }
          return;
        }

        if (event.type === "tool_call") {
          const payload = event as Record<string, unknown>;
          const eventId =
            typeof payload.event_id === "number"
              ? payload.event_id
              : Date.now();
          const agent =
            typeof payload.agent === "string" && payload.agent.trim()
              ? payload.agent.trim()
              : "Agent";
          const tool =
            typeof payload.tool === "string" && payload.tool.trim()
              ? payload.tool.trim()
              : "tool";
          const parameters = ensureRecord(payload.parameters);
          const result =
            typeof payload.result === "string" ? payload.result : "";
          const noteId = extractOptionalString(payload.note_id);
          const notePath = extractOptionalString(payload.note_path);

          const task = findTask(payload.task_id);
          if (task) {
            task.toolCalls.push({
              eventId,
              agent,
              tool,
              parameters,
              result,
              noteId,
              notePath,
              timestamp: Date.now()
            });
            if (noteId) {
              task.noteId = noteId;
            }
            if (notePath) {
              task.notePath = notePath;
            }
            const logSummary = noteId
              ? `${agent} 调用了 ${tool}（任务 ${task.id}，笔记 ${noteId}）`
              : `${agent} 调用了 ${tool}（任务 ${task.id}）`;
            progressLogs.value.push(logSummary);
            if (activeTaskId.value === task.id) {
              pulse(toolHighlight);
            }
          } else {
            progressLogs.value.push(`${agent} 调用了 ${tool}`);
          }
          return;
        }

        if (event.type === "generating_report") {
          generatingReport.value = true;
          const msg = typeof event.message === "string" && event.message.trim()
            ? event.message.trim() : "正在生成最终报告...";
          progressLogs.value.push(msg);
          return;
        }

        if (event.type === "final_report") {
          generatingReport.value = false;
          const report =
            typeof event.report === "string" && event.report.trim()
              ? event.report.trim()
              : "";
          reportMarkdown.value = report || "报告生成失败，未获得有效内容";
          pulse(reportHighlight);
          progressLogs.value.push("最终报告已生成");
          // 自动保存到后端并捕获 report ID
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
          return;
        }

        if (event.type === "error") {
          const detail =
            typeof event.detail === "string" && event.detail.trim()
              ? event.detail
              : "调查过程中发生错误";
          error.value = detail;
          progressLogs.value.push("调查失败，已停止流程");
        }
      },
      { signal: controller.signal }
    );

    if (!reportMarkdown.value) {
      reportMarkdown.value = "暂无生成的报告";
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      progressLogs.value.push("已取消当前调查任务");
    } else {
      error.value = err instanceof Error ? err.message : "请求失败";
    }
  } finally {
    loading.value = false;
    if (currentController === controller) {
      currentController = null;
    }
  }
};

const cancelResearch = () => {
  if (!loading.value || !currentController) {
    return;
  }
  progressLogs.value.push("正在尝试取消当前调查任务…");
  currentController.abort();
};

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

onMounted(() => {
  window.addEventListener("keydown", onTaskModalKeydown);
  const topicParam = route.query.topic;
  if (topicParam && typeof topicParam === "string") {
    form.topic = topicParam;
    handleSubmit();
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onTaskModalKeydown);
  document.body.style.overflow = "";
  if (currentController) {
    currentController.abort();
    currentController = null;
  }
});
</script>


<style scoped>
.app-shell {
  position: relative;
  min-height: 100vh;
  padding: 72px 24px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: radial-gradient(circle at 20% 20%, #f8fafc, #dbeafe 60%);
  color: #1f2937;
  overflow: hidden;
  box-sizing: border-box;
  transition: padding 0.4s ease;
}

.app-shell.expanded {
  padding: 0;
  align-items: stretch;
}

.aurora {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.55;
}

.aurora span {
  position: absolute;
  width: 45vw;
  height: 45vw;
  max-width: 520px;
  max-height: 520px;
  background: radial-gradient(circle, rgba(148, 197, 255, 0.35), transparent 60%);
  filter: blur(90px);
  animation: float 26s infinite linear;
}

.aurora span:nth-child(1) {
  top: -20%;
  left: -18%;
  animation-delay: 0s;
}

.aurora span:nth-child(2) {
  bottom: -25%;
  right: -20%;
  background: radial-gradient(circle, rgba(166, 139, 255, 0.28), transparent 60%);
  animation-delay: -9s;
}

.aurora span:nth-child(3) {
  top: 35%;
  left: 45%;
  background: radial-gradient(circle, rgba(164, 219, 216, 0.26), transparent 60%);
  animation-delay: -16s;
}

.layout {
  position: relative;
  width: 100%;
  display: flex;
  gap: 24px;
  z-index: 1;
  transition: all 0.4s ease;
}

.layout-centered {
  max-width: 600px;
  justify-content: center;
  align-items: center;
}

.layout-fullscreen {
  height: 100vh;
  max-width: 100%;
  gap: 0;
  align-items: stretch;
}

.panel {
  position: relative;
  flex: 1 1 360px;
  padding: 24px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
  overflow: hidden;
}

.panel-form {
  max-width: 420px;
}

.panel-centered {
  width: 100%;
  max-width: 600px;
  padding: 40px;
  box-shadow: 0 32px 64px rgba(15, 23, 42, 0.15);
  transform: scale(1);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.panel-centered:hover {
  transform: scale(1.02);
  box-shadow: 0 40px 80px rgba(15, 23, 42, 0.2);
}

.panel-result {
  min-width: 360px;
  flex: 2 1 420px;
}

.panel::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(125, 86, 255, 0.1));
  opacity: 0;
  transition: opacity 0.35s ease;
  z-index: 0;
}

.panel:hover::before {
  opacity: 1;
}

.panel > * {
  position: relative;
  z-index: 1;
}

.panel-form h1 {
  margin: 0;
  font-size: 26px;
  letter-spacing: 0.01em;
}

.panel-form p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.logo {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  box-shadow: 0 12px 28px rgba(59, 130, 246, 0.4);
}

.logo svg {
  width: 28px;
  height: 28px;
  fill: #f8fafc;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field span {
  font-weight: 600;
  color: #475569;
}

textarea,
input,
select {
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(255, 255, 255, 0.92);
  color: #1f2937;
  font-size: 14px;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

textarea:focus,
input:focus,
select:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.65);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
  background: #ffffff;
}

.options {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.option {
  flex: 1;
  min-width: 140px;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.submit {
  align-self: flex-start;
  padding: 12px 24px;
  border-radius: 16px;
  border: none;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #ffffff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s, opacity 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  position: relative;
}

.submit-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.submit .spinner {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: rgba(255, 255, 255, 0.85);
  stroke-linecap: round;
  animation: spin 1s linear infinite;
}

.submit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.submit:not(:disabled):hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.28);
}

.secondary-btn {
  padding: 10px 18px;
  border-radius: 14px;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.28);
  color: #1f2937;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.secondary-btn:hover {
  background: rgba(148, 163, 184, 0.2);
  border-color: rgba(148, 163, 184, 0.35);
  color: #0f172a;
}

.error-chip {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(248, 113, 113, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.35);
  border-radius: 14px;
  color: #b91c1c;
  font-size: 14px;
}

.error-chip svg {
  width: 18px;
  height: 18px;
  fill: currentColor;
}

.panel-result {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.result-main {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  overflow-y: auto;
  padding-right: 4px;
}

.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status-controls {
  display: flex;
  gap: 8px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(191, 219, 254, 0.28);
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: #1f2937;
  border: 1px solid rgba(59, 130, 246, 0.35);
  transition: background 0.3s ease, color 0.3s ease;
}

.status-chip.active {
  background: rgba(129, 140, 248, 0.2);
  border-color: rgba(129, 140, 248, 0.4);
  color: #1e293b;
}

.status-chip .dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #2563eb;
  box-shadow: 0 0 12px rgba(37, 99, 235, 0.45);
  animation: pulse 1.8s ease-in-out infinite;
}

.status-meta {
  color: #64748b;
  font-size: 13px;
}

.timeline-wrapper {
  margin-top: 12px;
  flex-shrink: 0;
  min-height: 160px;
  max-height: min(48vh, 480px);
  overflow-y: auto;
  padding-right: 8px;
  scrollbar-width: thin;
  scrollbar-color: rgba(129, 140, 248, 0.45) rgba(226, 232, 240, 0.6);
}

.timeline-wrapper::-webkit-scrollbar {
  width: 6px;
}

.timeline-wrapper::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.6);
  border-radius: 999px;
}

.timeline-wrapper::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(129, 140, 248, 0.8), rgba(59, 130, 246, 0.7));
  border-radius: 999px;
}

.timeline-wrapper::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.9), rgba(37, 99, 235, 0.8));
}

.timeline {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
  padding-left: 12px;
}

.timeline::before {
  content: "";
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 0;
  width: 2px;
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.35), rgba(129, 140, 248, 0.15));
}

.timeline li {
  position: relative;
  padding-left: 24px;
  color: #1e293b;
  font-size: 14px;
  line-height: 1.5;
}

.timeline-node {
  position: absolute;
  left: -12px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, #38bdf8, #7c3aed);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.22);
}

.timeline-enter-active,
.timeline-leave-active {
  transition: all 0.35s ease, opacity 0.35s ease;
}

.timeline-enter-from,
.timeline-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.tasks-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: stretch;
}

.tasks-section-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #1f2937;
  letter-spacing: -0.01em;
}

.tasks-section-hint {
  margin: -4px 0 4px;
  font-size: 13px;
}

.task-card-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.task-card {
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(255, 255, 255, 0.95);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.15s ease;
}

.task-card:hover {
  border-color: rgba(99, 102, 241, 0.45);
  box-shadow: 0 8px 28px rgba(79, 70, 229, 0.12);
}

.task-card--active {
  border-color: rgba(129, 140, 248, 0.65);
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.18);
}

.task-card--completed {
  background: rgba(240, 253, 244, 0.45);
  border-color: rgba(34, 197, 94, 0.25);
}

.task-card-inner {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 16px 18px;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  text-align: left;
  border-radius: 16px;
}

.task-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.task-card-title {
  font-weight: 700;
  font-size: 15px;
  color: #0f172a;
  line-height: 1.35;
}

.task-card-intent {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.task-card-preview {
  margin: 0;
  font-size: 13px;
  color: #475569;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.task-card-cta {
  font-size: 12px;
  font-weight: 600;
  color: #4f46e5;
  margin-top: 2px;
}

.task-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  color: #1f2937;
  background: rgba(148, 163, 184, 0.2);
}

.task-status.pending {
  background: rgba(148, 163, 184, 0.18);
  color: #475569;
}

.task-status.in_progress {
  background: rgba(129, 140, 248, 0.24);
  color: #312e81;
}

.task-status.completed {
  background: rgba(34, 197, 94, 0.2);
  color: #15803d;
}

.task-status.skipped {
  background: rgba(248, 113, 113, 0.18);
  color: #b91c1c;
}

.task-detail {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.5);
}

.task-detail--modal {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
}

.task-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
}

.task-modal-panel {
  width: min(920px, 100%);
  max-height: min(90vh, 900px);
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.98);
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.25);
  overflow: hidden;
}

.task-modal-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.95), rgba(255, 255, 255, 0.98));
}

.task-modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.35;
}

.task-modal-close {
  flex-shrink: 0;
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: rgba(255, 255, 255, 0.95);
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  cursor: pointer;
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}

.task-modal-close:hover {
  background: rgba(241, 245, 249, 0.95);
  border-color: rgba(100, 116, 139, 0.5);
}

.task-modal-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 22px 24px;
  scrollbar-width: thin;
  scrollbar-color: rgba(99, 102, 241, 0.45) rgba(226, 232, 240, 0.7);
}

@media (max-width: 640px) {
  .task-modal-backdrop {
    padding: 0;
    align-items: stretch;
  }

  .task-modal-panel {
    width: 100%;
    max-height: 100%;
    border-radius: 0;
  }
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
}

.task-chip-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.task-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.task-header .muted {
  margin: 6px 0 0;
}

.task-label {
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(191, 219, 254, 0.32);
  border: 1px solid rgba(59, 130, 246, 0.35);
  font-size: 12px;
  color: #1e3a8a;
}

.task-label.note-chip {
  background: rgba(34, 197, 94, 0.2);
  border-color: rgba(34, 197, 94, 0.35);
  color: #15803d;
}

.task-label.path-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 360px;
  background: rgba(56, 189, 248, 0.2);
  border-color: rgba(56, 189, 248, 0.35);
  color: #0369a1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-label {
  font-weight: 500;
}

.path-text {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-action {
  border: none;
  background: rgba(56, 189, 248, 0.2);
  color: #0369a1;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.chip-action:hover {
  background: rgba(14, 165, 233, 0.28);
  color: #0f172a;
}

.task-notices {
  background: rgba(191, 219, 254, 0.28);
  border: 1px solid rgba(96, 165, 250, 0.35);
  border-radius: 16px;
  padding: 14px 18px;
  color: #1f2937;
}

.task-notices h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.task-notices ul {
  list-style: disc;
  margin: 0 0 0 18px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-notices li {
  font-size: 13px;
}

.report-block {
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.26);
  border-radius: 18px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.report-block h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.report-block--final {
  margin-bottom: 8px;
  padding: 26px 24px 24px;
  border: 1px solid rgba(59, 130, 246, 0.22);
  box-shadow:
    0 4px 24px rgba(37, 99, 235, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.9) inset;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(239, 246, 255, 0.65));
}

.report-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 4px;
}

.report-head-accent {
  width: 5px;
  height: 28px;
  border-radius: 6px;
  background: linear-gradient(180deg, #2563eb, #7c3aed);
  box-shadow: 0 2px 10px rgba(59, 130, 246, 0.4);
  flex-shrink: 0;
}

.report-block--final .report-head h3 {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #0f172a;
}

.report-block--final .report-body {
  max-height: min(70vh, 680px);
  overflow-y: auto;
  padding: 22px 26px;
  border-radius: 16px;
  background: linear-gradient(165deg, #ffffff 0%, #f8fafc 42%, #f1f5f9 100%);
  border: 1px solid rgba(148, 163, 184, 0.28);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
  font-size: 15px;
  line-height: 1.78;
  color: #334155;
  scrollbar-width: thin;
  scrollbar-color: rgba(99, 102, 241, 0.55) rgba(226, 232, 240, 0.75);
}

.report-block--final .report-body::-webkit-scrollbar {
  width: 7px;
}

.report-block--final .report-body::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.65);
  border-radius: 999px;
}

.report-block--final .report-body::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.8), rgba(59, 130, 246, 0.65));
  border-radius: 999px;
}

.report-block--final .report-body :deep(h1),
.report-block--final .report-body :deep(h2) {
  margin: 1.35em 0 0.65em;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
  line-height: 1.35;
}

.report-block--final .report-body :deep(h1:first-child),
.report-block--final .report-body :deep(h2:first-child) {
  margin-top: 0;
}

.report-block--final .report-body :deep(h1) {
  font-size: 1.45rem;
  padding-bottom: 0.45em;
  border-bottom: 2px solid rgba(59, 130, 246, 0.35);
}

.report-block--final .report-body :deep(h2) {
  font-size: 1.28rem;
  padding-bottom: 0.35em;
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.92), rgba(129, 140, 248, 0.5)) left bottom /
    100% 3px no-repeat;
}

.report-block--final .report-body :deep(h3) {
  margin: 1.15em 0 0.55em;
  font-size: 1.08rem;
  font-weight: 700;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 10px;
}

.report-block--final .report-body :deep(h3)::before {
  content: "";
  width: 4px;
  min-height: 1.05em;
  border-radius: 4px;
  background: linear-gradient(180deg, #3b82f6, #7c3aed);
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.35);
}

.report-block--final .report-body :deep(p) {
  margin: 0.6em 0;
}

.report-block--final .report-body :deep(p:first-child) {
  margin-top: 0;
}

.report-block--final .report-body :deep(strong) {
  color: #1d4ed8;
  font-weight: 700;
  background: linear-gradient(120deg, rgba(219, 234, 254, 0.95), rgba(224, 231, 255, 0.5));
  padding: 0.12em 0.4em;
  border-radius: 5px;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.report-block--final .report-body :deep(ol) {
  margin: 0.85em 0;
  padding-left: 0;
  list-style: none;
  counter-reset: report-ol;
}

.report-block--final .report-body :deep(ol > li) {
  position: relative;
  padding-left: 2.65em;
  margin: 0.7em 0;
  counter-increment: report-ol;
}

.report-block--final .report-body :deep(ol > li::before) {
  content: counter(report-ol);
  position: absolute;
  left: 0;
  top: 0.12em;
  min-width: 1.75em;
  height: 1.75em;
  padding: 0 0.25em;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #6366f1);
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(37, 99, 235, 0.38);
}

.report-block--final .report-body :deep(ul) {
  margin: 0.65em 0;
  padding-left: 1.35em;
}

.report-block--final .report-body :deep(ul li)::marker {
  color: #6366f1;
  font-weight: 700;
}

.report-block--final .report-body :deep(blockquote) {
  margin: 1em 0;
  padding: 12px 16px 12px 18px;
  border-left: 4px solid rgba(99, 102, 241, 0.65);
  background: rgba(238, 242, 255, 0.65);
  border-radius: 0 12px 12px 0;
  color: #475569;
}

.report-block--final .report-body :deep(a) {
  color: #2563eb;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: rgba(37, 99, 235, 0.35);
  text-underline-offset: 3px;
}

.report-block--final .report-body :deep(a:hover) {
  color: #1d4ed8;
  text-decoration-color: rgba(29, 78, 216, 0.55);
}

.report-block--final .report-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    "Courier New", monospace;
  font-size: 0.88em;
  font-weight: 600;
  color: #7c3aed;
  background: rgba(237, 233, 254, 0.95);
  padding: 0.15em 0.45em;
  border-radius: 6px;
  border: 1px solid rgba(167, 139, 250, 0.35);
}

.report-block--final .report-body :deep(pre) {
  margin: 1em 0;
  padding: 14px 16px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.65;
  background: rgba(15, 23, 42, 0.92);
  color: #e2e8f0;
  border-radius: 12px;
  border: 1px solid rgba(51, 65, 85, 0.6);
}

.report-block--final .report-body :deep(pre code) {
  color: inherit;
  background: none;
  border: none;
  padding: 0;
  font-weight: 500;
}

.report-block--final .report-body :deep(hr) {
  margin: 1.5em 0;
  border: none;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.55), transparent);
}

.report-block--final .report-body :deep(.report-parse-hint) {
  margin: 0 0 12px;
  color: #b45309;
  font-weight: 600;
}

.report-block--final .report-body :deep(.report-fallback) {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  color: #334155;
  background: rgba(248, 250, 252, 0.95);
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.35);
}

.block-pre {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular,
    Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1f2937;
  background: rgba(248, 250, 252, 0.9);
  padding: 16px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  overflow: auto;
  max-height: 420px;
  scrollbar-width: thin;
  scrollbar-color: rgba(129, 140, 248, 0.6) rgba(226, 232, 240, 0.7);
}

.block-pre::-webkit-scrollbar {
  width: 6px;
}

.block-pre::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.7);
  border-radius: 999px;
}

.block-pre::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.75), rgba(59, 130, 246, 0.65));
  border-radius: 999px;
}

.block-pre::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(79, 70, 229, 0.8), rgba(37, 99, 235, 0.75));
}

.summary-block .block-pre,
.sources-block .block-pre {
  max-height: none;
}


.tools-block {
  position: relative;
  margin-top: 16px;
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.4);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tools-block h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: 0.02em;
}

.tool-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tool-entry {
  background: rgba(248, 250, 252, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tool-entry-header {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.tool-entry-title {
  font-weight: 600;
  color: #1f2937;
}

.tool-entry-note {
  font-size: 12px;
  color: #0f766e;
}

.tool-entry-path {
  margin: 0;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #2563eb;
}

.tool-subtitle {
  margin: 0;
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}

.tool-pre {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular,
    Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1f2937;
  background: rgba(248, 250, 252, 0.9);
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  overflow: auto;
  max-height: 260px;
  scrollbar-width: thin;
  scrollbar-color: rgba(129, 140, 248, 0.6) rgba(226, 232, 240, 0.7);
}

.tool-pre::-webkit-scrollbar {
  width: 6px;
}

.tool-pre::-webkit-scrollbar-track {
  background: rgba(226, 232, 240, 0.7);
}

.tool-pre::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.7);
  border-radius: 10px;
}

.link-btn {
  background: none;
  border: none;
  color: #0369a1;
  cursor: pointer;
  padding: 0 4px;
  font-size: 12px;
  border-radius: 8px;
  transition: color 0.2s ease, background 0.2s ease;
}

.link-btn:hover {
  color: #0ea5e9;
  background: rgba(14, 165, 233, 0.16);
}


.sources-block,
.summary-block {
  position: relative;
  margin-top: 16px;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.4);
}

.sources-history {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sources-history h4 {
  margin: 0;
  color: #1f2937;
  font-size: 14px;
  letter-spacing: 0.01em;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-list details {
  background: rgba(248, 250, 252, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  padding: 12px 16px;
  color: #1f2937;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.history-list details[open] {
  background: rgba(224, 231, 255, 0.55);
  border-color: rgba(129, 140, 248, 0.4);
}

.history-list summary {
  cursor: pointer;
  font-weight: 600;
  outline: none;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.history-list summary::-webkit-details-marker {
  display: none;
}

.history-list summary::after {
  content: "▾";
  margin-left: 6px;
  font-size: 12px;
  opacity: 0.7;
  transition: transform 0.2s ease;
}

.history-list details[open] summary::after {
  transform: rotate(180deg);
}

.block-highlight {
  animation: glow 1.2s ease;
}

.sources-block h3,
.summary-block h3 {
  margin: 0 0 14px;
  color: #1f2937;
  letter-spacing: 0.02em;
}

.sources-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.source-item {
  position: relative;
  display: inline-flex;
  flex-direction: column;
  gap: 6px;
}

.source-link {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
  letter-spacing: 0.01em;
  transition: color 0.2s ease;
}

.source-link::after {
  content: " ↗";
  font-size: 12px;
  opacity: 0.6;
}

.source-link:hover {
  color: #0f172a;
}

.source-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 12px);
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.98);
  color: #1f2937;
  padding: 14px 16px;
  border-radius: 16px;
  box-shadow: 0 18px 32px rgba(15, 23, 42, 0.18);
  width: min(420px, 90vw);
  z-index: 20;
  border: 1px solid rgba(148, 163, 184, 0.24);
}

.source-tooltip::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border-width: 10px;
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.98) transparent transparent transparent;
}

.source-tooltip::before {
  content: "";
  position: absolute;
  bottom: -12px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 12px 10px 0 10px;
  border-style: solid;
  border-color: rgba(255, 255, 255, 0.98) transparent transparent transparent;
  filter: drop-shadow(0 -2px 4px rgba(15, 23, 42, 0.12));
}

.source-tooltip p {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.6;
}

.source-tooltip p:last-child {
  margin-bottom: 0;
}

.muted-text {
  color: #64748b;
}

.source-item:hover .source-tooltip,
.source-item:focus-within .source-tooltip {
  display: block;
}

.hint.muted {
  color: #64748b;
}

@keyframes float {
  0% {
    transform: translate3d(0, 0, 0) rotate(0deg);
  }
  50% {
    transform: translate3d(10%, 6%, 0) rotate(3deg);
  }
  100% {
    transform: translate3d(0, 0, 0) rotate(0deg);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.3);
    opacity: 0.5;
  }
}

@keyframes glow {
  0% {
    box-shadow: 0 0 0 rgba(59, 130, 246, 0.3);
    border-color: rgba(59, 130, 246, 0.5);
  }
  100% {
    box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.12);
    border-color: rgba(148, 163, 184, 0.2);
  }
}

@media (max-width: 960px) {
  .app-shell {
    padding: 56px 16px;
  }

  .layout {
    flex-direction: column;
    align-items: stretch;
  }

  .panel {
    padding: 22px;
  }

  .panel-form,
  .panel-result {
    max-width: none;
  }

  .status-bar {
    flex-direction: column;
    align-items: flex-start;
  }

  .status-main,
  .status-controls {
    width: 100%;
  }

  .status-controls {
    justify-content: flex-start;
  }
}

@media (max-width: 600px) {
  .options {
    flex-direction: column;
  }

  .status-meta {
    font-size: 12px;
  }

  .panel-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-form h1 {
    font-size: 24px;
  }
}

/* 可折叠区域 */
.collapsible-head {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 10px;
}
.collapsible-head:hover {
  opacity: 0.8;
}
.fold-arrow {
  font-size: 12px;
  color: #94a3b8;
  margin-left: auto;
  transition: transform 0.2s;
}
.tasks-section-header {
  display: flex;
  align-items: center;
  cursor: pointer;
  user-select: none;
}
.tasks-section-header:hover {
  opacity: 0.8;
}

/* 报告生成中 loading */
.report-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 60px 20px;
  border-radius: 16px;
  background: linear-gradient(165deg, #f0f9ff, #e0f2fe);
  border: 2px dashed #93c5fd;
  margin-top: 12px;
}
.generating-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #bfdbfe;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
.report-generating p {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e40af;
  animation: pulse-text 1.8s ease-in-out infinite;
}
@keyframes pulse-text {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* 全屏状态下的结果面板 */
.layout-fullscreen .panel-result {
  flex: 1;
  height: 100vh;
  min-height: 0;
  border-radius: 0;
  border: none;
  overflow: hidden;
  max-width: none;
}

@media (max-width: 768px) {
  .layout-fullscreen {
    flex-direction: column;
  }
}

/* 快捷操作栏动画 */
.quick-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(124, 58, 237, 0.06));
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  margin-bottom: 16px;
  animation: fadeSlideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

.quick-actions-label {
  font-size: 13px;
  font-weight: 600;
  color: #1d4ed8;
  flex: 1;
}

:deep(.quick-actions .btn-primary),
:deep(.quick-actions .btn-secondary) {
  text-decoration: none;
}

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
