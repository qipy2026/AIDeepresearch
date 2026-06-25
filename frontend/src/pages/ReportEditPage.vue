<template>
  <main class="main-content" @keydown="onKeydown">
    <!-- Header bar -->
    <div class="edit-header">
      <span>📊</span>
      <h1>编辑报告</h1>
      <span class="report-title">{{ reportTitle }}</span>
      <span style="flex:1"></span>
      <router-link to="/reports" class="back-link">← 返回列表</router-link>
    </div>

    <!-- Banner -->
    <div v-if="banner" class="banner" :class="banner.type">{{ banner.msg }}</div>

    <!-- Spinner -->
    <div v-if="loading" class="spinner active"></div>

    <!-- Not found -->
    <div v-if="!reportId" class="not-found">
      <h2>💭 报告不存在</h2>
      <p>report_id 无效或报告已被删除</p>
      <router-link to="/reports">← 返回报告列表</router-link>
    </div>

    <!-- Not found by load failure -->
    <div v-else-if="notFound" class="not-found">
      <h2>💭 报告不存在</h2>
      <p>report_id 无效或报告已被删除</p>
      <router-link to="/reports">← 返回报告列表</router-link>
    </div>

    <!-- Editor -->
    <div v-else-if="reportLoaded" class="editor-container">
      <div class="toolbar">
        <button class="btn btn-primary" :disabled="saving" @click="saveReport">
          {{ saving ? '保存中...' : '💾 保存' }}
        </button>
        <button class="btn btn-outline" :disabled="sending || loadingChats" @click="openSendModal">
          {{ loadingChats ? '加载群列表中...' : '📨 发送飞书' }}
        </button>
        <span class="save-status">{{ saveStatus }}</span>
      </div>
      <div class="editor-area">
        <div class="editor-pane">
          <div class="pane-header">Markdown 编辑</div>
          <textarea
            ref="editorEl"
            v-model="editorContent"
            placeholder="报告内容..."
            spellcheck="false"
            @input="onEditorInput"
          ></textarea>
        </div>
        <div class="preview-pane">
          <div class="pane-header">预览</div>
          <div id="preview" v-html="previewHtml"></div>
        </div>
      </div>
    </div>

    <!-- Send modal -->
    <Teleport to="body">
      <div class="modal-overlay" :class="{ active: showSendModal }" @click.self="closeSendModal">
        <div class="modal">
          <h3>📨 发送到飞书群</h3>
          <input
            type="text"
            class="chat-search"
            v-model="chatSearchQuery"
            placeholder="搜索群聊..."
            @input="filterChats"
          />
          <div class="chat-list">
            <div v-if="chatList.length === 0 && !chatEmptyMsg" class="empty-hint">未找到群聊</div>
            <div v-if="chatEmptyMsg && filteredChats.length === 0" class="empty-hint">{{ chatEmptyMsg }}</div>
            <label
              v-for="chat in filteredChats"
              :key="chat.chat_id"
              class="chat-item"
              :class="{ selected: selectedChatId === chat.chat_id }"
              :data-chat-id="chat.chat_id"
            >
              <input
                type="radio"
                name="chat"
                :value="chat.chat_id"
                v-model="selectedChatId"
                @change="onChatSelected(chat.chat_id)"
              />
              <span>{{ chat.name }}</span>
            </label>
          </div>
          <input
            type="text"
            class="manual-input"
            v-model="manualChatId"
            placeholder="或手动输入 chat_id..."
          />
          <div class="modal-actions">
            <button class="btn btn-outline" @click="closeSendModal">取消</button>
            <button class="btn btn-primary" :disabled="!canSend || feishuSending" @click="sendToFeishu">
              {{ feishuSending ? '发送中...' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Toast -->
    <div v-if="toast" class="toast" :class="toast.type">{{ toast.msg }}</div>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { marked } from "marked";
import DOMPurify from "dompurify";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const route = useRoute();
const router = useRouter();

const reportId = computed(() => route.params.id as string | undefined);

// State
const loading = ref(true);
const notFound = ref(false);
const reportLoaded = ref(false);
const reportTitle = ref("加载中...");
const editorContent = ref("");
const editorEl = ref<HTMLTextAreaElement | null>(null);
let lastSavedContent: string | null = null;

const saving = ref(false);
const saveStatus = ref("");
const banner = ref<{ type: string; msg: string } | null>(null);
const toast = ref<{ type: string; msg: string } | null>(null);

// Send modal
const showSendModal = ref(false);
const chatList = ref<{ chat_id: string; name: string }[]>([]);
const chatSearchQuery = ref("");
const selectedChatId = ref("");
const manualChatId = ref("");
const chatEmptyMsg = ref("");
const loadingChats = ref(false);
const sending = ref(false);
const feishuSending = ref(false);

// Computed
const previewHtml = computed(() => {
  try {
    const raw = marked.parse(editorContent.value || "", { async: false }) as string;
    return DOMPurify.sanitize(raw);
  } catch {
    return `<pre>${escapeHtml(editorContent.value || "")}</pre>`;
  }
});

const canSend = computed(() => {
  return !!(manualChatId.value.trim() || selectedChatId.value);
});

const filteredChats = computed(() => {
  const q = chatSearchQuery.value.toLowerCase();
  if (!q) return chatList.value;
  return chatList.value.filter((c) => c.name.toLowerCase().includes(q));
});

// Methods
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showBanner(type: string, msg: string) {
  banner.value = { type, msg };
}

function hideBanner() {
  banner.value = null;
}

function showToast(type: string, msg: string) {
  toast.value = { type, msg };
  setTimeout(() => {
    toast.value = null;
  }, 3500);
}

let renderTimer: ReturnType<typeof setTimeout> | null = null;

function onEditorInput() {
  if (renderTimer) clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    // previewHtml is computed from editorContent, so it updates automatically
  }, 300);
}

async function loadReport(id: string) {
  try {
    const resp = await fetch(`${API}/api/reports/${id}`);
    if (!resp.ok) {
      if (resp.status === 404) {
        notFound.value = true;
      } else {
        showBanner("error", `加载失败，服务器返回 ${resp.status}`);
      }
      loading.value = false;
      return;
    }
    const data = await resp.json();
    reportTitle.value = data.title;
    editorContent.value = data.content || "";
    lastSavedContent = data.content || "";
    loading.value = false;
    reportLoaded.value = true;
  } catch {
    loading.value = false;
    showBanner("error", "网络连接失败，请检查后端服务是否运行");
  }
}

async function saveReport() {
  const content = editorContent.value;
  if (!content.trim()) {
    showBanner("error", "内容不能为空");
    return;
  }

  saving.value = true;
  hideBanner();

  try {
    const resp = await fetch(`${API}/api/reports/${reportId.value}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: reportTitle.value, content }),
    });
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(err);
    }
    const data = await resp.json();
    if (data.id !== reportId.value) {
      router.replace(`/reports/${data.id}/edit`);
    }
    lastSavedContent = content;
    saveStatus.value = "已保存 " + new Date().toLocaleTimeString("zh-CN");
    showToast("success", "保存成功");
  } catch (e: any) {
    showBanner("error", "保存失败: " + (e.message || "未知错误"));
  } finally {
    saving.value = false;
  }
}

async function openSendModal() {
  // Auto-save if dirty
  if (editorContent.value !== lastSavedContent) {
    await saveReport();
    if (banner.value?.type === "error") return;
  }

  loadingChats.value = true;
  selectedChatId.value = "";
  chatSearchQuery.value = "";
  manualChatId.value = "";
  chatEmptyMsg.value = "";

  try {
    const resp = await fetch(`${API}/api/feishu/chats`);
    const data = await resp.json();
    chatList.value = data.chats || [];
    const hint = data.hint || "";
    if (chatList.value.length === 0 && hint) {
      chatEmptyMsg.value = hint;
    }
  } catch {
    chatEmptyMsg.value = "无法获取群列表，请手动输入 chat_id";
  } finally {
    loadingChats.value = false;
  }

  showSendModal.value = true;
}

function closeSendModal() {
  showSendModal.value = false;
}

function onChatSelected(chatId: string) {
  selectedChatId.value = chatId;
}

function filterChats() {
  // Handled by filteredChats computed
}

async function sendToFeishu() {
  const chatId = manualChatId.value.trim() || selectedChatId.value;
  if (!chatId) return;

  feishuSending.value = true;

  try {
    // Save before sending if dirty
    if (editorContent.value !== lastSavedContent) {
      await fetch(`${API}/api/reports/${reportId.value}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: reportTitle.value, content: editorContent.value }),
      });
    }

    const resp = await fetch(`${API}/api/reports/${reportId.value}/send-to-feishu`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId }),
    });
    const data = await resp.json();

    if (data.status === "ok") {
      showToast("success", data.truncated ? "发送成功（内容过长已截断）" : "发送成功");
      closeSendModal();
    } else {
      showToast("error", "发送失败: " + (data.detail || "未知错误"));
    }
  } catch (e: any) {
    showToast("error", "发送失败: " + (e.message || "网络错误"));
  } finally {
    feishuSending.value = false;
  }
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    saveReport();
  }
}

// Beforeunload guard
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (editorContent.value !== lastSavedContent) {
    e.preventDefault();
    e.returnValue = "你有未保存的修改，确定离开吗？";
    return e.returnValue;
  }
}

onMounted(() => {
  window.addEventListener("beforeunload", onBeforeUnload);
  const id = reportId.value;
  if (!id) {
    loading.value = false;
    notFound.value = true;
  } else {
    loadReport(id);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", onBeforeUnload);
  if (renderTimer) clearTimeout(renderTimer);
});
</script>

<style scoped>
/* Layout */
.main-content {
  flex: 1;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
}

/* Header */
.edit-header {
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-bottom: 1px solid #e2e8f0;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.edit-header h1 {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}

.report-title {
  font-size: 13px;
  color: #64748b;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.back-link {
  color: #2563eb;
  text-decoration: none;
  font-size: 13px;
}

.back-link:hover {
  text-decoration: underline;
}

/* Banner */
.banner {
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.banner.error {
  background: #fef2f2;
  color: #dc2626;
  border-bottom: 1px solid #fecaca;
}

.banner.success {
  background: #f0fdf4;
  color: #16a34a;
  border-bottom: 1px solid #bbf7d0;
}

/* Spinner */
.spinner {
  display: none;
  width: 40px;
  height: 40px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 40px auto;
}

.spinner.active {
  display: block;
}

/* Toolbar */
.toolbar {
  display: flex;
  gap: 8px;
  padding: 10px 20px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  align-items: center;
  flex-shrink: 0;
}

.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-primary {
  background: #3b82f6;
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.btn-outline {
  background: #ffffff;
  color: #3b82f6;
  border: 1px solid #3b82f6;
}

.btn-outline:hover:not(:disabled) {
  background: #eff6ff;
}

.btn-outline:disabled {
  color: #94a3b8;
  border-color: #e2e8f0;
  cursor: not-allowed;
}

.save-status {
  font-size: 12px;
  color: #64748b;
  margin-left: auto;
}

/* Editor area */
.editor-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.editor-area {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.editor-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e2e8f0;
}

.preview-pane {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #ffffff;
}

.pane-header {
  padding: 8px 16px;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.editor-pane textarea {
  flex: 1;
  border: none;
  resize: none;
  padding: 16px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  line-height: 1.6;
  outline: none;
}

/* Preview markdown */
#preview :deep(h1) {
  font-size: 1.6em;
  color: #0f172a;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 8px;
}

#preview :deep(h2) {
  font-size: 1.3em;
  color: #1e293b;
  margin: 20px 0 12px;
}

#preview :deep(h3) {
  font-size: 1.1em;
  color: #475569;
  margin: 16px 0 8px;
}

#preview :deep(p) {
  margin: 8px 0;
  line-height: 1.7;
}

#preview :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

#preview :deep(th),
#preview :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 8px 12px;
  text-align: left;
  font-size: 13px;
}

#preview :deep(th) {
  background: #f8fafc;
  font-weight: 700;
}

#preview :deep(img) {
  max-width: 100%;
}

#preview :deep(blockquote) {
  border-left: 3px solid #3b82f6;
  padding: 8px 16px;
  color: #94a3b8;
  background: rgba(59, 130, 246, 0.04);
  border-radius: 0 8px 8px 0;
  margin: 12px 0;
}

#preview :deep(code) {
  background: rgba(124, 58, 237, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.88em;
}

#preview :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 16px 20px;
  border-radius: 12px;
  overflow-x: auto;
}

#preview :deep(pre code) {
  background: transparent;
  padding: 0;
  color: inherit;
}

#preview :deep(ul li::marker) {
  color: #6366f1;
}

#preview :deep(ol) {
  counter-reset: item;
}

#preview :deep(ol li) {
  counter-increment: item;
}

#preview :deep(ol li::marker) {
  color: #6366f1;
  font-weight: 700;
}

/* Not found */
.not-found {
  text-align: center;
  padding: 80px 20px;
}

.not-found h2 {
  font-size: 18px;
  color: #64748b;
  margin-bottom: 8px;
}

.not-found p {
  color: #94a3b8;
  margin: 8px 0;
}

.not-found a {
  color: #3b82f6;
}

/* Modal */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 100;
  justify-content: center;
  align-items: center;
}

.modal-overlay.active {
  display: flex;
}

.modal {
  background: #ffffff;
  border-radius: 12px;
  padding: 24px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.25);
}

.modal h3 {
  font-size: 16px;
  margin-bottom: 12px;
  color: #0f172a;
}

.modal .chat-list {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 12px;
}

.modal .chat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
}

.modal .chat-item:hover {
  background: #f8fafc;
}

.modal .chat-item.selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

.modal .chat-item input[type="radio"] {
  accent-color: #3b82f6;
}

.modal .chat-search {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 8px;
  outline: none;
  box-sizing: border-box;
}

.modal .chat-search:focus {
  border-color: #3b82f6;
}

.modal .manual-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  margin-top: 8px;
  outline: none;
  box-sizing: border-box;
}

.modal .manual-input:focus {
  border-color: #3b82f6;
}

.modal .modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 12px;
}

.empty-hint {
  text-align: center;
  padding: 20px;
  color: #94a3b8;
  font-size: 13px;
}

/* Toast */
.toast {
  position: fixed;
  bottom: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  z-index: 200;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  animation: slideIn 0.3s;
}

.toast.success {
  background: #16a34a;
  color: #fff;
}

.toast.error {
  background: #dc2626;
  color: #fff;
}

/* Animations */
@keyframes slideIn {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
