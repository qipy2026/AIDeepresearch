<template>
  <main class="main-content">
    <div class="inner">
      <div class="page-header">
        <router-link to="/upload" class="back-link">← 返回文档列表</router-link>
        <h2 class="page-title">📄 {{ enterprise }}</h2>
        <p class="page-subtitle">
          {{ documents.length }} 个文档 · {{ totalChunks }} 个块
        </p>
      </div>

      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="errorMsg" class="error-banner err">❌ {{ errorMsg }}</div>
      <div v-else class="doc-list">
        <div v-for="doc in documents" :key="doc.id" class="doc-card">
          <div class="doc-info">
            <div class="doc-name">📎 {{ doc.filename }}</div>
            <div class="doc-meta">
              {{ doc.chunk_count }} 块 ·
              {{ formatSize(doc.file_size) }} ·
              {{ doc.created_at }}
              <span v-if="doc.minio_path" class="doc-minio">· MinIO</span>
            </div>
            <div v-if="doc.status === 'failed'" class="doc-error">
              ❌ {{ doc.error_msg }}
            </div>
          </div>
          <button class="btn-del-sm" @click="deleteDoc(doc.id)">删除</button>
        </div>

        <div v-if="documents.length === 0 && !loading" class="empty">
          该企业暂无文档
        </div>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const enterprise = ref(decodeURIComponent(route.params.enterprise as string));

interface Document {
  id: number;
  filename: string;
  file_size: number;
  chunk_count: number;
  minio_path: string | null;
  status: string;
  error_msg: string | null;
  created_at: string;
}

const documents = ref<Document[]>([]);
const loading = ref(true);
const errorMsg = ref("");

const totalChunks = computed(() =>
  documents.value.reduce((sum, d) => sum + d.chunk_count, 0)
);

function formatSize(bytes: number): string {
  if (bytes === 0) return "未知大小";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

async function loadDocuments() {
  loading.value = true;
  try {
    const resp = await fetch(
      "/rag/documents?enterprise=" + encodeURIComponent(enterprise.value)
    );
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    documents.value = data.documents || [];
  } catch (e: any) {
    errorMsg.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function deleteDoc(docId: number) {
  if (!confirm("确认删除此文档？")) return;
  alert("单文档删除功能将在后续版本实现。当前可在文档列表页删除整个企业的所有数据。");
}

onMounted(loadDocuments);
</script>

<style scoped>
.main-content {
  flex: 1;
  min-height: 100vh;
  overflow-y: auto;
  padding: 40px;
  background: #f8fafc;
}
.inner { margin: 0 auto; max-width: 720px; }
.page-header { margin-bottom: 24px; }
.back-link {
  color: #2563eb; text-decoration: none; font-size: 13px;
}
.back-link:hover { text-decoration: underline; }
.page-title { font-size: 26px; font-weight: 700; color: #0f172a; margin: 8px 0 6px; }
.page-subtitle { font-size: 13px; color: #64748b; margin: 0; }

.doc-list { display: flex; flex-direction: column; gap: 10px; }
.doc-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; background: #fff; border-radius: 10px;
  border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.doc-name { font-size: 15px; font-weight: 500; color: #0f172a; }
.doc-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.doc-error { font-size: 12px; color: #dc2626; margin-top: 4px; }
.doc-minio { color: #22c55e; }

.btn-del-sm {
  padding: 4px 12px; border-radius: 6px; border: 1px solid #fca5a5;
  background: #fff; color: #dc2626; font-size: 12px; cursor: pointer;
  flex-shrink: 0;
}
.btn-del-sm:hover { background: #fee2e2; }

.empty { color: #94a3b8; font-size: 13px; text-align: center; padding: 20px; }
.error-banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
.error-banner.err { background: #fee2e2; color: #991b1b; }
</style>
