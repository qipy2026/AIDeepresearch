<template>
  <main class="main-content">
    <div class="inner">
      <div class="page-header">
        <h2 class="page-title">📡 数据源管理</h2>
        <p class="page-subtitle">
          管理数据采集源与采集频率
          <span class="status-msg">{{ statusMsg }}</span>
        </p>
      </div>

      <div class="toolbar">
        <button class="btn btn-primary" @click="openAdd">+ 新增数据源</button>
        <button class="btn btn-outline" @click="saveAll">💾 保存修改</button>
      </div>

      <table>
        <thead>
          <tr>
            <th>状态</th>
            <th>名称</th>
            <th>URL</th>
            <th>分类</th>
            <th>采集频率</th>
            <th>builtin</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(s, i) in sources" :key="i">
            <td>
              <button
                class="toggle"
                :class="s.enabled ? 'on' : 'off'"
                @click="toggleSource(i)"
              ></button>
            </td>
            <td>{{ s.name }}</td>
            <td class="url-cell">
              <a :href="s.url" target="_blank" class="url-link">{{ s.url }}</a>
            </td>
            <td>
              <span class="tag" :class="'tag-' + categoryTag(s.category)">{{ s.category }}</span>
            </td>
            <td>{{ scheduleLabel(s.schedule) }}</td>
            <td>{{ s.builtin ? '🔒' : '' }}</td>
            <td class="action-cell">
              <button class="btn-sm" @click="openEdit(i)">编辑</button>
              <button
                v-if="!s.builtin"
                class="btn-sm btn-sm-delete"
                @click="deleteSource(i)"
              >删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑弹窗 -->
    <Teleport to="body">
      <div v-if="showModal" class="modal-backdrop" @click.self="closeModal">
        <div class="modal-box">
          <h3>{{ editingIndex >= 0 ? '编辑数据源' : '新增数据源' }}</h3>
          <div class="form-row">
            <div class="form-field" style="flex:2">
              <label>名称 *</label>
              <input v-model="formName" />
            </div>
            <div class="form-field">
              <label>分类</label>
              <select v-model="formCategory">
                <option value="宏观数据">宏观数据</option>
                <option value="行业报告">行业报告</option>
                <option value="舆情指数">舆情指数</option>
                <option value="电商流量">电商流量</option>
                <option value="影视票房">影视票房</option>
                <option value="行业排名">行业排名</option>
                <option value="其他">其他</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-field" style="flex:2">
              <label>URL *</label>
              <input v-model="formUrl" />
            </div>
            <div class="form-field">
              <label>采集频率</label>
              <select v-model="formSchedule">
                <option value="daily">每日</option>
                <option value="weekly">每周</option>
                <option value="monthly">每月</option>
              </select>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn btn-outline" @click="closeModal">取消</button>
            <button class="btn btn-primary" @click="saveSource">确定</button>
          </div>
          <div v-if="modalMsg.text" :class="['msg', modalMsg.type]">{{ modalMsg.text }}</div>
        </div>
      </div>
    </Teleport>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

const API = import.meta.env.VITE_API_BASE_URL || "";

interface Source {
  name: string;
  url: string;
  category: string;
  schedule: string;
  enabled: boolean;
  builtin?: boolean;
}

const CAT_TAGS: Record<string, string> = {
  "宏观数据": "macro",
  "行业报告": "report",
  "舆情指数": "opinion",
  "电商流量": "commerce",
  "影视票房": "movie",
  "行业排名": "rank",
  "上市公司公告": "stock",
  "其他": "macro",
};

const sources = ref<Source[]>([]);
const statusMsg = ref("");

// Modal state
const showModal = ref(false);
const editingIndex = ref(-1);
const formName = ref("");
const formUrl = ref("");
const formCategory = ref("其他");
const formSchedule = ref("daily");
const modalMsg = reactive({ text: "", type: "" });

function categoryTag(category: string): string {
  return CAT_TAGS[category] || "macro";
}

function scheduleLabel(schedule: string): string {
  if (schedule === "daily") return "每日";
  if (schedule === "weekly") return "每周";
  return "每月";
}

async function loadSources() {
  try {
    const resp = await fetch(API + "/api/sources");
    const data = await resp.json();
    sources.value = data.sources || [];
  } catch {
    sources.value = [];
  }
}

function toggleSource(i: number) {
  sources.value[i].enabled = !sources.value[i].enabled;
  statusMsg.value = "状态已修改，请点击「保存修改」";
}

function openAdd() {
  editingIndex.value = -1;
  formName.value = "";
  formUrl.value = "";
  formCategory.value = "其他";
  formSchedule.value = "daily";
  modalMsg.text = "";
  modalMsg.type = "";
  showModal.value = true;
}

function openEdit(i: number) {
  editingIndex.value = i;
  const s = sources.value[i];
  formName.value = s.name;
  formUrl.value = s.url;
  formCategory.value = s.category;
  formSchedule.value = s.schedule;
  modalMsg.text = "";
  modalMsg.type = "";
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
}

function saveSource() {
  const name = formName.value.trim();
  const url = formUrl.value.trim();
  if (!name || !url) {
    modalMsg.text = "名称和 URL 不能为空";
    modalMsg.type = "err";
    return;
  }
  const entry: Source = {
    name,
    url,
    category: formCategory.value,
    schedule: formSchedule.value,
    enabled: true,
  };
  if (editingIndex.value >= 0) {
    const old = sources.value[editingIndex.value];
    entry.enabled = old.enabled;
    if (old.builtin) entry.builtin = true;
    sources.value[editingIndex.value] = entry;
  } else {
    sources.value.push(entry);
  }
  showModal.value = false;
  statusMsg.value = "已修改，请点击「保存修改」";
}

function deleteSource(i: number) {
  if (!confirm("删除 " + sources.value[i].name + "？")) return;
  sources.value.splice(i, 1);
  statusMsg.value = "已修改，请点击「保存修改」";
}

async function saveAll() {
  try {
    const resp = await fetch(API + "/api/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sources: sources.value }),
    });
    const data = await resp.json();
    if (data.status === "ok") {
      statusMsg.value = "✅ 保存成功，下次采集周期生效";
    }
  } catch {
    statusMsg.value = "保存失败";
  }
}

onMounted(() => {
  loadSources();
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
  max-width: 1100px;
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

.status-msg {
  margin-left: 8px;
  font-size: 13px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}

/* 按钮 */
.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
}

.btn-primary {
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
}

.btn-primary:hover {
  opacity: 0.9;
}

.btn-outline {
  background: transparent;
  border: 1px solid #cbd5e1;
  color: #64748b;
}

.btn-outline:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
  border-radius: 5px;
  cursor: pointer;
  border: 1px solid #cbd5e1;
  background: #fff;
}

.btn-sm:hover {
  background: #f1f5f9;
}

.btn-sm-delete {
  color: #dc2626;
  border-color: #fecaca;
  background: #fef2f2;
}

.btn-sm-delete:hover {
  background: #fee2e2;
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
  border-bottom: 2px solid #cbd5e1;
}

td {
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid #f1f5f9;
}

tr:hover {
  background: #fafbfc;
}

.url-cell {
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.url-link {
  color: #3b82f6;
}

.url-link:hover {
  text-decoration: underline;
}

.action-cell {
  display: flex;
  gap: 4px;
}

/* 分类标签 */
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 600;
}

.tag-macro {
  background: #dbeafe;
  color: #1e40af;
}

.tag-report {
  background: #dcfce7;
  color: #166534;
}

.tag-opinion {
  background: #fef3c7;
  color: #92400e;
}

.tag-commerce {
  background: #fce7f3;
  color: #9d174d;
}

.tag-movie {
  background: #e0e7ff;
  color: #3730a3;
}

.tag-rank {
  background: #fef2f2;
  color: #991b1b;
}

.tag-stock {
  background: #e0f2fe;
  color: #075985;
}

/* Toggle 开关 */
.toggle {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
}

.toggle.on {
  background: #16a34a;
}

.toggle.off {
  background: #cbd5e1;
}

.toggle::after {
  content: "";
  display: block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #ffffff;
  margin: 2px;
  transition: transform 0.2s;
}

.toggle.on::after {
  transform: translateX(18px);
}

/* 弹窗 */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(15, 23, 42, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.modal-box {
  background: #ffffff;
  border-radius: 16px;
  padding: 24px;
  max-width: 500px;
  width: 100%;
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.25);
}

.modal-box h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
  color: #0f172a;
}

.form-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.form-field {
  flex: 1;
}

.form-field label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 3px;
}

.form-field input,
.form-field select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  font-size: 13px;
  box-sizing: border-box;
}

.form-field input:focus,
.form-field select:focus {
  outline: none;
  border-color: #3b82f6;
}

.modal-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* 消息 */
.msg {
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-top: 10px;
}

.msg.ok {
  background: #dcfce7;
  color: #166534;
}

.msg.err {
  background: #fee2e2;
  color: #991b1b;
}
</style>
