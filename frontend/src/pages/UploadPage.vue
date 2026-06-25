<template>
  <main class="main-content">
    <div class="inner">
      <div class="page-header">
        <h2 class="page-title">📄 参考文档</h2>
        <p class="page-subtitle">上传企业文档，自动嵌入向量库供 RAG 检索</p>
      </div>

      <div class="card">
        <h1>📄 企业参考文档</h1>
        <p class="desc">上传企业的工商、票据、风险数据文档，自动嵌入向量库供 RAG 检索</p>

        <!-- 拖拽上传区 -->
        <div
          class="upload-area"
          :class="{ dragover: isDragover, 'has-file': hasFile }"
          @dragover.prevent="onDragOver"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop"
          @click="triggerFileInput"
        >
          <div class="upload-icon">{{ uploadIcon }}</div>
          <div class="upload-text">{{ uploadText }}</div>
          <div class="upload-hint">{{ uploadHint }}</div>
          <input
            ref="fileInputRef"
            type="file"
            accept=".md,.docx,.pdf,.html,.htm,.txt"
            multiple
            style="display:none"
            @change="onFileChange"
          />
          <div class="upload-progress" :class="{ active: progressActive }">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
            </div>
            <div class="progress-text">{{ progressText }}</div>
          </div>
        </div>

        <div
          v-if="msg.text"
          class="msg"
          :class="msg.type"
        >{{ msg.text }}</div>

        <!-- 已上传企业列表 -->
        <div class="section-title">已上传企业</div>
        <div v-if="loading" class="empty">加载中...</div>
        <div v-else-if="enterprises.length === 0" class="empty">暂无已上传企业</div>
        <div v-else class="ent-list">
          <div v-for="ent in enterprises" :key="ent" class="ent-row">
            <div>
              <div class="ent-name">{{ ent }}</div>
            </div>
            <button class="btn-del" @click="deleteEnt(ent)">删除</button>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

// --- Reactive state ---
const fileInputRef = ref<HTMLInputElement | null>(null);

const isDragover = ref(false);
const hasFile = ref(false);
const uploadIcon = ref("📤");
const uploadText = ref("点击选择文件或拖拽到此处");
const uploadHint = ref("支持 .md .docx .pdf .html .txt");

const progressActive = ref(false);
const progressPct = ref(0);
const progressText = ref("上传中...");

const msg = reactive({ text: "", type: "" });

const enterprises = ref<string[]>([]);
const loading = ref(true);

// --- Helper ---
function extractEnterprise(filename: string): string {
  let name = filename.replace(/\.[^.]+$/, "");
  const seps = [" - ", " – ", " _ ", "_", "-"];
  for (const sep of seps) {
    if (name.includes(sep)) return name.split(sep)[0].trim();
  }
  return name.trim();
}

function showMsg(text: string, type: string) {
  msg.text = text;
  msg.type = type;
}

// --- Drag events ---
function onDragOver() {
  isDragover.value = true;
}

function onDragLeave() {
  isDragover.value = false;
}

function onDrop(e: DragEvent) {
  isDragover.value = false;
  if (e.dataTransfer?.files) {
    handleFiles(e.dataTransfer.files);
  }
}

function onFileChange() {
  if (fileInputRef.value?.files) {
    handleFiles(fileInputRef.value.files);
  }
}

function triggerFileInput() {
  fileInputRef.value?.click();
}

// --- Upload logic ---
async function handleFiles(files: FileList) {
  if (!files || files.length === 0) return;
  const total = files.length;
  uploadText.value = files[0].name + (total > 1 ? " 等 " + total + " 个文件" : "");
  uploadHint.value = "共 " + total + " 个文件，开始上传...";
  uploadIcon.value = "⏳";
  hasFile.value = true;
  progressActive.value = true;
  showMsg("", "");
  let ok = 0;
  let err = 0;

  for (let i = 0; i < total; i++) {
    const file = files[i];
    const pct = Math.round((i / total) * 100);
    progressPct.value = pct;
    progressText.value = "上传中 " + (i + 1) + "/" + total + "：" + file.name;

    const enterprise = extractEnterprise(file.name);
    const fd = new FormData();
    fd.append("enterprise", enterprise);
    fd.append("file", file);

    try {
      const resp = await fetch("/rag/upload/file", { method: "POST", body: fd });
      if (resp.ok) {
        ok++;
      } else {
        err++;
      }
    } catch {
      err++;
    }
  }

  progressPct.value = 100;
  progressText.value = "✅ 完成 " + ok + "/" + total + "，失败 " + err;
  uploadIcon.value = ok > 0 ? "✅" : "❌";
  if (ok > 0) refreshList();
  setTimeout(() => {
    progressActive.value = false;
  }, 4000);
}

// --- Enterprise list ---
async function refreshList() {
  try {
    const resp = await fetch("/rag/enterprises");
    const data = await resp.json();
    enterprises.value = data.enterprises || [];
  } catch {
    enterprises.value = [];
  } finally {
    loading.value = false;
  }
}

async function deleteEnt(enterprise: string) {
  if (!confirm('确认删除 "' + enterprise + '" 的所有数据？')) return;
  try {
    const resp = await fetch("/rag/enterprise/" + encodeURIComponent(enterprise), {
      method: "DELETE",
    });
    if (resp.ok) {
      refreshList();
    } else {
      alert("删除失败");
    }
  } catch {
    alert("删除失败");
  }
}

// --- Init ---
onMounted(() => {
  refreshList();
});
</script>

<style scoped>
/* 页面布局 */
.main-content {
  flex: 1;
  min-height: 100vh;
  overflow-y: auto;
  padding: 40px;
  background: #f8fafc;
}

.inner {
  margin: 0 auto;
  max-width: 640px;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 6px 0;
}

.page-subtitle {
  font-size: 13px;
  color: #64748b;
  margin: 0;
}

/* 卡片 */
.card {
  background: #ffffff;
  border-radius: 16px;
  padding: 28px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
}

.card h1 {
  margin: 0 0 6px;
  font-size: 20px;
  color: #0f172a;
}

.desc {
  color: #64748b;
  font-size: 14px;
  margin: 0 0 20px;
}

/* 上传区 */
.upload-area {
  border: 2px dashed #cbd5e1;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: 0.2s;
  background: #f8fafc;
}

.upload-area:hover,
.upload-area.dragover {
  border-color: #93c5fd;
  background: #eff6ff;
}

.upload-area.has-file {
  border-color: #22c55e;
  background: #f0fdf4;
}

.upload-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.upload-text {
  color: #64748b;
  font-size: 14px;
}

.upload-hint {
  color: #94a3b8;
  font-size: 12px;
  margin-top: 6px;
}

/* 进度条 */
.upload-progress {
  margin-top: 12px;
  display: none;
}

.upload-progress.active {
  display: block;
}

.progress-bar {
  width: 100%;
  height: 6px;
  background: #cbd5e1;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  border-radius: 3px;
  width: 0;
  transition: width 0.3s;
}

.progress-text {
  font-size: 13px;
  color: #64748b;
  margin-top: 6px;
}

/* 消息提示 */
.msg {
  padding: 10px 14px;
  border-radius: 8px;
  margin-top: 12px;
  font-size: 13px;
}

.msg.ok {
  background: #dcfce7;
  color: #166534;
}

.msg.err {
  background: #fee2e2;
  color: #991b1b;
}

/* 企业列表 */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  margin: 20px 0 10px;
}

.ent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ent-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
}

.ent-name {
  font-size: 14px;
  font-weight: 500;
  color: #0f172a;
}

.btn-del {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #fca5a5;
  background: #ffffff;
  color: #dc2626;
  font-size: 12px;
  cursor: pointer;
  transition: 0.2s;
}

.btn-del:hover {
  background: #fee2e2;
}

.empty {
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}
</style>
