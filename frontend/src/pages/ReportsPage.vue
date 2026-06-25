<template>
  <main class="main-content">
    <div class="inner">
      <div class="page-header">
        <h2 class="page-title">📊 报告管理</h2>
        <p class="page-subtitle">查看、编辑和管理已生成的贷后报告</p>
      </div>

      <table v-if="reports.length">
        <thead>
          <tr>
            <th>报告名称</th>
            <th>更新时间</th>
            <th>大小</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reports" :key="r.id">
            <td>
              <a :href="API + '/api/reports/' + r.id + '?raw=1'" target="_blank" class="report-link">{{ r.name }}</a>
            </td>
            <td class="text-subtle">{{ new Date(r.updated).toLocaleString('zh-CN') }}</td>
            <td class="text-muted">{{ (r.size / 1024).toFixed(1) }} KB</td>
            <td>
              <router-link :to="'/reports/' + r.id + '/edit'" class="btn-sm">✏️ 编辑</router-link>
              <button class="btn-sm danger" @click="delReport(r.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else class="empty">
        <p>📋</p>
        <p>暂无报告，前往<router-link to="/research" class="empty-link">贷后助手</router-link>生成</p>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8080";

interface Report {
  id: string;
  name: string;
  updated: string;
  size: number;
}

const reports = ref<Report[]>([]);

async function load() {
  const resp = await fetch(API + "/api/reports");
  const data = await resp.json();
  reports.value = data.reports || [];
}

async function delReport(id: string) {
  if (!confirm("确定删除？")) return;
  await fetch(API + "/api/reports/" + id, { method: "DELETE" });
  load();
}

onMounted(() => {
  load();
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
  max-width: 960px;
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

/* 表格 */
table {
  width: 100%;
  border-collapse: collapse;
  background: #ffffff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
}

th {
  background: #f8fafc;
  text-align: left;
  padding: 12px 14px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  border-bottom: 2px solid #e2e8f0;
}

td {
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid #f1f5f9;
}

tr:hover {
  background: #fafbfc;
}

.report-link {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
}

.report-link:hover {
  text-decoration: underline;
}

.text-subtle {
  color: #64748b;
}

.text-muted {
  color: #94a3b8;
}

/* 按钮 */
.btn-sm {
  display: inline-flex;
  padding: 4px 8px;
  font-size: 11px;
  border-radius: 5px;
  cursor: pointer;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  text-decoration: none;
  color: inherit;
}

.btn-sm:hover {
  border-color: #3b82f6;
}

.btn-sm.danger {
  color: #dc2626;
  border-color: #fecaca;
  background: #fef2f2;
  margin-left: 4px;
}

.btn-sm.danger:hover {
  background: #fee2e2;
}

/* 空状态 */
.empty {
  text-align: center;
  padding: 60px 20px;
  color: #94a3b8;
}

.empty-link {
  color: #2563eb;
  text-decoration: none;
}

.empty-link:hover {
  text-decoration: underline;
}
</style>
