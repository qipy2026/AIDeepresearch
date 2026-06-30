<template>
  <main class="main-content">
    <div class="inner">
      <div class="page-header">
        <h2 class="page-title">🏢 贷款项目管理</h2>
        <p class="page-subtitle">管理债务企业与核心企业关联关系 <span>{{ totalInfo }}</span></p>
      </div>

      <!-- 快捷操作按钮 -->
      <div class="toolbar">
        <button class="btn btn-primary" @click="toggleAddForm">➕ 新建项目</button>
        <button class="btn btn-outline" @click="toggleAll">展开/折叠全部</button>
      </div>

      <!-- 新建项目表单 -->
      <div v-if="showAddForm" class="add-card" ref="addCardRef">
        <h2>➕ 新建贷款项目</h2>
        <div class="form-section">
          <h3>🏢 乙方 — 债务企业（借款方）</h3>
          <div class="form-row">
            <div class="form-field" style="flex:2"><label>企业全称 *</label><input v-model="debtorForm.name" placeholder="如：四川振海保安服务有限公司"></div>
            <div class="form-field"><label>行业</label><input v-model="debtorForm.industry" placeholder="安保服务"></div>
            <div class="form-field"><label>贷款金额(万元)</label><input v-model="debtorForm.loan_amount" type="number" placeholder="1000"></div>
            <div class="form-field" style="flex:2"><label>搜索关键词</label><input v-model="debtorForm.keywords" placeholder="逗号分隔"></div>
          </div>
        </div>
        <div class="form-section">
          <h3>📋 甲方 — 核心监管企业（可添加多个）</h3>
          <div class="form-row">
            <div class="form-field" style="flex:2"><label>企业全称 *</label><input v-model="partyForm.name" placeholder="国家管网集团西南管道有限责任公司"></div>
            <div class="form-field"><label>行业</label><input v-model="partyForm.industry" placeholder="管道运输"></div>
            <div class="form-field"><label>母公司</label><input v-model="partyForm.parent" placeholder="国家管网集团"></div>
            <div class="form-field"><label>股票/概念代码</label><input v-model="partyForm.stock" placeholder="601186.SH或885692.TI"></div>
          </div>
          <div class="form-actions">
            <button type="button" class="btn btn-outline" @click="addParty">+ 添加此甲方</button>
            <span class="party-count">已添加 {{ pendingParties.length }} 个甲方</span>
            <span class="spacer"></span>
            <button type="button" class="btn btn-primary" @click="submitProject">创建项目</button>
            <button type="button" class="btn btn-outline" @click="toggleAddForm">取消</button>
          </div>
          <div class="party-preview" v-if="pendingParties.length">
            <div v-for="(p, i) in pendingParties" :key="i" class="party-preview-item">
              <span class="party-preview-num">{{ i + 1 }}.</span>
              <span class="party-preview-name">{{ p.name }}</span>
              <span v-if="p.industry" class="party-preview-industry">🏭 {{ p.industry }}</span>
              <span v-if="p.parent" class="party-preview-parent">母:{{ p.parent }}</span>
              <span v-if="p.stock" class="party-preview-stock">{{ p.stock }}</span>
              <span class="party-preview-remove" @click="removePendingParty(i)">×</span>
            </div>
          </div>
        </div>
        <div v-if="msg.text" :class="['msg', msg.type]">{{ msg.text }}</div>
      </div>

      <!-- 空状态 -->
      <div v-if="!debtors.length && !unlinkedParties.length && !loading" class="empty">
        <p class="empty-icon">📋</p>
        <p>暂无企业，请添加</p>
      </div>

      <!-- 项目卡片列表 -->
      <div v-else class="projects-grid">
        <div
          v-for="(d, i) in debtors"
          :key="d.name"
          class="project-card"
          :class="{ open: openProjects.has(d.name) }"
          :style="{ borderLeftColor: COLORS[i % COLORS.length] }"
        >
          <div class="project-head" @click="toggleProject(d.name)">
            <div class="num" :style="{ background: COLORS[i % COLORS.length] }">{{ i + 1 }}</div>
            <div class="info">
              <div class="name">
                <router-link :to="'/research?topic=' + encodeURIComponent(d.name)" class="name-link">
                  {{ d.name }}
                </router-link>
                <span class="tag tag-debtor">乙方·债务企业</span>
              </div>
              <div class="meta">
                <span v-if="d.industry">🏭 {{ d.industry }}</span>
                <span v-if="d.loan_amount">💰 {{ d.loan_amount }}万元</span>
                <span>甲方 {{ getParties(d.name).length }} 家</span>
              </div>
            </div>
            <button class="btn btn-sm" @click.stop="deleteEnterprise(d.name)">删除</button>
          </div>
          <div class="project-body">
            <template v-if="getParties(d.name).length">
              <div v-for="p in getParties(d.name)" :key="p.name" class="party-row">
                <div class="party-info">
                  <span class="arrow">└</span>
                  <span class="party-name">{{ p.name }}</span>
                  <span class="tag tag-party-a">甲方</span>
                  <span v-if="p.parent" class="tag tag-parent">母公司 {{ p.parent }}</span>
                  <span v-if="p.parent_stock_code" class="tag tag-stock">{{ p.parent_stock_code }}</span>
                  <div class="party-industry">🏭 {{ p.industry || '未填行业' }}</div>
                </div>
                <button class="btn btn-sm" @click.stop="deleteEnterprise(p.name)">删除</button>
              </div>
            </template>
            <div v-else class="party-row party-row-empty">暂无关联甲方</div>
          </div>
        </div>

        <!-- 未关联甲方卡片 -->
        <div v-if="unlinkedParties.length" class="project-card" :class="{ open: unlinkedOpen }" style="border-left-color:#94a3b8;">
          <div class="project-head" @click="toggleUnlinked">
            <div class="num" style="background:#94a3b8;">!</div>
            <div class="info">
              <div class="name name-muted">📋 未关联的甲方（{{ unlinkedParties.length }}家）</div>
              <div class="meta">缺少债务企业绑定</div>
            </div>
          </div>
          <div class="project-body">
            <div v-for="p in unlinkedParties" :key="p.name" class="party-row">
              <div class="party-info">
                <span class="party-name">{{ p.name }}</span>
                <span class="tag tag-party-a">甲方</span>
                <span v-if="p.parent" class="tag tag-parent">母公司 {{ p.parent }}</span>
                <div class="party-industry">🏭 {{ p.industry || '未填行业' }}</div>
              </div>
              <button class="btn btn-sm" @click.stop="deleteEnterprise(p.name)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, nextTick } from "vue";

const API = import.meta.env.VITE_API_BASE_URL || "";
const COLORS = ["#3b82f6", "#8b5cf6", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#ec4899", "#6366f1"];

interface Enterprise {
  name: string;
  role: string;
  industry?: string;
  loan_amount?: string;
  keywords?: string;
  debtor?: string;
  parent?: string;
  parent_stock_code?: string;
}

interface PendingParty {
  name: string;
  industry: string;
  parent: string;
  stock: string;
}

const debtors = ref<Enterprise[]>([]);
const parties = ref<Enterprise[]>([]);
const openProjects = ref(new Set<string>());
const showAddForm = ref(false);
const pendingParties = ref<PendingParty[]>([]);
const msg = reactive({ text: "", type: "" });
const unlinkedOpen = ref(true);
const loading = ref(true);
const addCardRef = ref<HTMLElement | null>(null);

const debtorForm = reactive({
  name: "",
  industry: "",
  loan_amount: "",
  keywords: "",
});

const partyForm = reactive({
  name: "",
  industry: "",
  parent: "",
  stock: "",
});

const unlinkedParties = computed(() => parties.value.filter((p) => !p.debtor));

const totalInfo = computed(() => {
  const all = debtors.value.length + parties.value.length;
  if (!all) return "";
  return `共 ${debtors.value.length} 个项目，${all} 家企业`;
});

function getParties(debtorName: string): Enterprise[] {
  return parties.value.filter((p) => p.debtor === debtorName);
}

function showMsgFn(text: string, type: string) {
  msg.text = text;
  msg.type = type;
  setTimeout(() => {
    msg.text = "";
    msg.type = "";
  }, 3000);
}

function addParty() {
  const name = partyForm.name.trim();
  if (!name) return;
  pendingParties.value.push({
    name,
    industry: partyForm.industry.trim(),
    parent: partyForm.parent.trim(),
    stock: partyForm.stock.trim(),
  });
  partyForm.name = "";
  partyForm.industry = "";
  partyForm.parent = "";
  partyForm.stock = "";
}

function removePendingParty(index: number) {
  pendingParties.value.splice(index, 1);
}

async function submitProject() {
  const debtor = {
    name: debtorForm.name.trim(),
    industry: debtorForm.industry.trim(),
    loan_amount: debtorForm.loan_amount.trim(),
    keywords: debtorForm.keywords.trim(),
  };
  if (!debtor.name) {
    showMsgFn("请输入乙方企业名称", "err");
    return;
  }
  if (!pendingParties.value.length) {
    showMsgFn("请至少添加一个甲方", "err");
    return;
  }

  let ok = 0;
  try {
    const r = await fetch(API + "/api/enterprises", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...debtor, role: "乙方" }),
    });
    if ((await r.json()).status === "ok") ok++;
  } catch {
    /* ignore network errors */
  }
  for (const p of pendingParties.value) {
    try {
      const r = await fetch(API + "/api/enterprises", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: p.name,
          role: "甲方",
          industry: p.industry,
          debtor: debtor.name,
          parent: p.parent,
          parent_stock_code: p.stock,
          keywords: "",
        }),
      });
      if ((await r.json()).status === "ok") ok++;
    } catch {
      /* ignore network errors */
    }
  }
  showMsgFn(`✅ 项目创建完成：${ok}家企业`, "ok");
  showAddForm.value = false;
  pendingParties.value = [];
  debtorForm.name = "";
  debtorForm.industry = "";
  debtorForm.loan_amount = "";
  debtorForm.keywords = "";
  await loadProjects();
}

async function loadProjects() {
  try {
    const resp = await fetch(API + "/api/enterprises");
    const data = await resp.json();
    const all: Enterprise[] = data.enterprises || [];
    debtors.value = all.filter((e) => e.role === "乙方");
    parties.value = all.filter((e) => e.role === "甲方");
    // Open all projects by default (matching original behavior)
    const nextOpen = new Set<string>();
    debtors.value.forEach((d) => nextOpen.add(d.name));
    openProjects.value = nextOpen;
  } catch {
    debtors.value = [];
    parties.value = [];
  } finally {
    loading.value = false;
  }
}

async function deleteEnterprise(name: string) {
  if (!confirm(`删除 ${name}？`)) return;
  await fetch(API + "/api/enterprises/" + encodeURIComponent(name), { method: "DELETE" });
  await loadProjects();
}

function toggleAddForm() {
  showAddForm.value = !showAddForm.value;
  if (showAddForm.value) {
    nextTick(() => {
      addCardRef.value?.scrollIntoView({ behavior: "smooth" });
    });
  }
}

function toggleAll() {
  if (openProjects.value.size === debtors.value.length && unlinkedOpen.value) {
    // All open -> close all
    openProjects.value = new Set();
    unlinkedOpen.value = false;
  } else {
    // Open all
    const nextOpen = new Set<string>();
    debtors.value.forEach((d) => nextOpen.add(d.name));
    openProjects.value = nextOpen;
    unlinkedOpen.value = true;
  }
}

function toggleProject(name: string) {
  const next = new Set(openProjects.value);
  if (next.has(name)) {
    next.delete(name);
  } else {
    next.add(name);
  }
  openProjects.value = next;
}

function toggleUnlinked() {
  unlinkedOpen.value = !unlinkedOpen.value;
}

onMounted(() => {
  loadProjects();
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

/* 工具栏 */
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: center;
}

/* 按钮 */
.btn {
  padding: 8px 18px;
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
  font-size: 12px;
}

.btn-outline:hover {
  border-color: #3b82f6;
  color: #3b82f6;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 6px;
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
  cursor: pointer;
}

.btn-sm:hover {
  background: #fee2e2;
}

/* 新建表单 */
.add-card {
  background: #ffffff;
  border-radius: 12px;
  padding: 22px 24px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
  border: 2px dashed #cbd5e1;
  margin-bottom: 24px;
}

.add-card h2 {
  font-size: 16px;
  margin: 0 0 16px 0;
  color: #0f172a;
}

.form-section {
  margin-bottom: 14px;
  padding: 14px;
  background: #f8fafc;
  border-radius: 8px;
}

.form-section h3 {
  font-size: 13px;
  font-weight: 700;
  margin: 0 0 10px 0;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 6px;
}

.form-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.form-field {
  flex: 1;
  min-width: 160px;
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
  background: #ffffff;
  box-sizing: border-box;
}

.form-field input:focus,
.form-field select:focus {
  outline: none;
  border-color: #3b82f6;
}

.form-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.party-count {
  font-size: 12px;
  color: #94a3b8;
}

.spacer {
  flex: 1;
}

/* 甲方预览 */
.party-preview {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.party-preview-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #ffffff;
  border-radius: 6px;
  font-size: 13px;
}

.party-preview-num {
  color: #64748b;
}

.party-preview-name {
  font-weight: 600;
}

.party-preview-industry {
  color: #64748b;
  font-size: 11px;
}

.party-preview-parent {
  color: #9d174d;
  font-size: 11px;
}

.party-preview-stock {
  color: #166534;
  font-size: 11px;
}

.party-preview-remove {
  margin-left: auto;
  cursor: pointer;
  color: #ef4444;
  font-size: 16px;
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

/* 项目网格 */
.projects-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.project-card {
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06);
  overflow: hidden;
  border-left: 4px solid #e2e8f0;
}

.project-head {
  padding: 18px 22px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  user-select: none;
}

.project-head:hover {
  background: #fafbfc;
}

.project-body {
  padding: 0 22px 16px 22px;
  border-top: 1px solid #f1f5f9;
  display: none;
}

.project-card.open .project-body {
  display: block;
}

.project-head .num {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 16px;
  color: #fff;
}

.project-head .info {
  flex: 1;
}

.project-head .info .name {
  font-weight: 700;
  font-size: 15px;
  color: #0f172a;
}

.name-link {
  color: inherit;
  text-decoration: none;
}

.name-link:hover {
  text-decoration: underline;
}

.name-muted {
  color: #64748b;
}

.project-head .info .meta {
  font-size: 12px;
  color: #94a3b8;
  display: flex;
  gap: 12px;
  margin-top: 3px;
}

/* 甲方行 */
.party-row {
  margin-left: 36px;
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.party-row + .party-row {
  margin-top: 6px;
}

.party-row-empty {
  color: #94a3b8;
}

.party-info {
  flex: 1;
  min-width: 0;
}

.party-name {
  font-weight: 600;
  font-size: 14px;
}

.party-industry {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 3px;
  margin-left: 18px;
}

.arrow {
  color: #94a3b8;
  margin-right: 4px;
}

/* 标签 */
.tag {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}

.tag-debtor {
  background: #fef3c7;
  color: #92400e;
}

.tag-party-a {
  background: #dbeafe;
  color: #1e40af;
}

.tag-parent {
  background: #fce7f3;
  color: #9d174d;
}

.tag-stock {
  background: #dcfce7;
  color: #166534;
}

/* 空状态 */
.empty {
  text-align: center;
  padding: 60px 20px;
  color: #94a3b8;
}

.empty-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
</style>
