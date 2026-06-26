<template>
  <main class="main-content">
    <div class="inner" style="max-width:1100px;">
      <div class="page-header">
        <h2 class="page-title">⚠️ 预警中心</h2>
        <p class="page-subtitle">
          实时监控企业风险动态
          <span class="auto-refresh">{{ refreshInfo }}</span>
          <button @click="refreshAll" style="margin-left:8px;padding:4px 10px;border-radius:6px;border:1px solid var(--border-medium);background:rgba(59,130,246,0.08);color:var(--color-primary-light);cursor:pointer;font-size:11px;">🔄 立即刷新</button>
        </p>
      </div>

      <div class="stats-row">
        <div class="stat-card red"><div class="num">{{ stats.red }}</div><div class="label">🔴 红色预警</div></div>
        <div class="stat-card orange"><div class="num">{{ stats.orange }}</div><div class="label">🟠 橙色预警</div></div>
        <div class="stat-card yellow"><div class="num">{{ stats.yellow }}</div><div class="label">🟡 黄色预警</div></div>
        <div class="stat-card"><div class="num">{{ stats.normal }}</div><div class="label">🟢 正常</div></div>
      </div>

      <div class="filters">
        <label>企业:</label>
        <select v-model="filterEnterprise">
          <option value="">全部</option>
          <option v-for="ent in enterpriseOptions" :key="ent" :value="ent">{{ ent }}</option>
        </select>
        <label>级别:</label>
        <select v-model="filterSeverity">
          <option value="">全部</option>
          <option value="red">🔴 红色</option>
          <option value="orange">🟠 橙色</option>
          <option value="yellow">🟡 黄色</option>
        </select>
        <button @click="loadWarnings" style="padding:8px 16px;border-radius:var(--radius-sm);border:1px solid var(--color-primary-light);background:#eff6ff;color:var(--color-primary-dark);cursor:pointer;font-weight:600;">刷新</button>
      </div>

      <!-- 行业风向标 -->
      <div v-if="industryData" class="industry-board" style="background:var(--surface-card);border-radius:var(--radius-lg);padding:16px 20px;box-shadow:var(--shadow-card);margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
          <span style="font-size:16px;">🏭</span>
          <span style="font-weight:700;font-size:14px;">行业风向标</span>
          <span style="font-size:11px;color:#94a3b8;">{{ industryTime }}</span>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <div style="flex:1;min-width:220px;">
            <div style="font-size:11px;font-weight:600;color:#16a34a;margin-bottom:6px;">📈 涨幅领先</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">
              <span v-for="s in topGainers" :key="s.name" style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;background:#dcfce7;color:#166534;white-space:nowrap;">{{ s.name }} <b>+{{ s.change_pct }}%</b></span>
              <span v-if="!topGainers.length" style="color:#94a3b8;font-size:12px;">no data</span>
            </div>
          </div>
          <div style="flex:1;min-width:220px;">
            <div style="font-size:11px;font-weight:600;color:#dc2626;margin-bottom:6px;">📉 跌幅领先</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">
              <span v-for="s in topLosers" :key="s.name" style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;background:#fee2e2;color:#991b1b;white-space:nowrap;">{{ s.name }} <b>{{ s.change_pct }}%</b></span>
              <span v-if="!topLosers.length" style="color:#94a3b8;font-size:12px;">no data</span>
            </div>
          </div>
        </div>
        <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">
          <span v-for="(r, i) in industryRisks" :key="'risk-'+i" :style="{ display:'inline-block',padding:'4px 10px',borderRadius:'8px',fontSize:'12px',background:r.level==='red'?'#fef2f2':'#fffbeb',border:'1px solid '+(r.level==='red'?'#fecaca':'#fde68a'),whiteSpace:'nowrap' }">!! <b>{{ truncName(r.enterprise) }}</b> {{ r.sector }} {{ r.change_pct }}%</span>
          <span v-for="(m, i) in industryMissed" :key="'missed-'+i" style="display:inline-block;padding:4px 10px;border-radius:8px;font-size:12px;background:#eff6ff;border:1px solid #bfdbfe;white-space:nowrap;">! <b>{{ m.sector }}</b> +{{ m.change_pct }}% no coverage</span>
        </div>
      </div>

      <!-- 骨架屏 -->
      <div v-if="loadingWarnings">
        <div v-for="n in 3" :key="'skel-'+n" class="card-skeleton" style="margin-bottom:12px;"></div>
      </div>

      <!-- 预警列表 -->
      <div v-else class="warning-list">
        <div v-if="!sortedWarnings.length" class="empty">
          <div class="icon">✅</div>
          <p>暂无预警，系统运行正常</p>
        </div>

        <div v-for="w in sortedWarnings" :key="w.id" :class="['warning-card', cardSeverityClass(w)]">
          <div class="sev-icon">{{ sevIcon(w) }}</div>
          <div class="warning-content">
            <div class="warning-title">{{ getRiskTitle(w) }}</div>
            <div class="warning-detail">
              <template v-if="isNormalWarning(w)">
                {{ getRiskSummary(w) || '✅ 数据正常' }}
              </template>
              <template v-else>
                <span v-for="f in getClickableFactors(w)" :key="f.factor" class="factor-link" @click.stop="showFactorDetail(w.enterprise, f.factor, f.tool, f.count)" :title="'点击查看'+f.factor+'详情'">{{ f.factor }}({{ f.count }})</span>
                <span v-if="!getClickableFactors(w).length">{{ getRiskSummary(w) }}</span>
              </template>
            </div>
            <div class="warning-meta">
              <span class="sev-label">{{ sevLabel(w) }}</span>
              <span v-if="isNewWarning(w)" class="new-badge">NEW</span>
              <span>🕐 {{ timeAgo(w) }}</span>
              <span>📡 {{ sourceName(w.source) }}</span>
              <a v-if="w.source_url" :href="w.source_url" target="_blank" style="color:var(--color-primary-light);font-size:12px;text-decoration:none;" @click.stop title="查看原文">原文</a>
              <span v-if="w.enterprise.includes('甲方')" class="tag tag-blue">甲方</span>
              <span v-if="w.enterprise.includes('乙方')" class="tag tag-blue">乙方</span>
              <span v-if="w.enterprise.includes('母公司')" class="tag tag-orange">母公司追溯</span>
              <span v-if="w.status === 'false_positive'" class="tag tag-orange">已标记误报</span>
            </div>
          </div>
          <div class="warning-actions">
            <template v-if="w.status === 'false_positive'">
              <button @click="unfalseWarning(w.id)" style="padding:6px 12px;border-radius:8px;border:1px solid #94a3b8;font-size:12px;cursor:pointer;background:var(--surface-card);color:#64748b;">↩ 撤销误报</button>
              <button class="detail-btn" @click="showDetail(w.id)">明细</button>
            </template>
            <template v-else>
              <button class="false-btn" @click="falseWarning(w.id)">标记误报</button>
              <select v-if="!isNormalWarning(w)" @change="setSeverity(w.id, ($event.target as HTMLSelectElement).value)" @click.stop :value="w.severity" style="padding:4px 8px;border-radius:6px;border:1px solid #cbd5e1;font-size:12px;cursor:pointer;">
                <option value="red">🔴 红色</option>
                <option value="orange">🟠 橙色</option>
                <option value="yellow">🟡 黄色</option>
              </select>
              <button v-if="(w.severity === 'red' || w.severity === 'orange') && !isNormalWarning(w)" class="push-btn" @click="showPush(w.id, w.enterprise, w.severity, w.title || '', w.detail || '')">📤 推送</button>
              <button class="detail-btn" @click="showDetail(w.id)">明细</button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 明细弹窗 -->
    <Teleport to="body">
      <div v-if="detailModalOpen" class="modal-backdrop" @click.self="closeDetail">
        <div class="modal-panel" style="max-width:800px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <h3 style="margin:0;font-size:18px;">{{ factorDetailTitle || '📋 风险明细' }}</h3>
            <button @click="closeDetail" style="padding:6px 14px;border-radius:8px;border:1px solid #cbd5e1;background:var(--surface-card);cursor:pointer;">关闭</button>
          </div>
          <div v-if="detailLoading" style="text-align:center;padding:40px;">
            <div class="generating-spinner"></div>
            <p>查询明细中...</p>
          </div>
          <div v-else-if="detailError" style="color:#dc2626;">{{ detailError }}</div>
          <div v-else v-html="detailHtml"></div>
        </div>
      </div>
    </Teleport>

    <!-- 推送弹窗 -->
    <Teleport to="body">
      <div v-if="pushModalOpen" class="modal-backdrop" @click.self="closePush">
        <div class="modal-panel" style="max-width:700px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <h3 style="margin:0;font-size:18px;">📤 推送预警到飞书</h3>
            <button @click="closePush" style="padding:6px 14px;border-radius:8px;border:1px solid #cbd5e1;background:var(--surface-card);cursor:pointer;">取消</button>
          </div>
          <label style="font-size:13px;font-weight:600;color:var(--text-body);display:block;margin-bottom:6px;">发送到：</label>
          <div style="display:flex;gap:8px;margin-bottom:12px;">
            <select v-model="pushChatSelect" @change="onPushChatSelectChange" style="flex:1;padding:8px 12px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px;">
              <option value="">选择群聊...</option>
              <option v-for="c in chatList" :key="c.chat_id" :value="c.chat_id">{{ c.name || c.chat_id }}</option>
              <option value="__custom__">✏️ 手动输入 chat_id...</option>
            </select>
            <button @click="loadChats" style="padding:8px 12px;border-radius:8px;border:1px solid #cbd5e1;background:#f8fafc;cursor:pointer;font-size:12px;" title="刷新群聊列表">🔄</button>
          </div>
          <input v-if="showCustomChatId" v-model="pushChatId" placeholder="或直接输入 chat_id (oc_xxx)" style="width:100%;padding:8px 12px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px;margin-bottom:12px;box-sizing:border-box;">
          <label style="font-size:13px;font-weight:600;color:var(--text-body);display:block;margin-bottom:6px;">风险摘要：</label>
          <textarea v-model="pushSummary" style="width:100%;height:100px;padding:12px;border:1px solid #cbd5e1;border-radius:var(--radius-sm);font-size:13px;line-height:1.6;resize:vertical;font-family:inherit;margin-bottom:12px;box-sizing:border-box;"></textarea>
          <label style="font-size:13px;font-weight:600;color:var(--text-body);display:block;margin-bottom:6px;">建议措施：</label>
          <textarea v-model="pushAction" style="width:100%;height:60px;padding:12px;border:1px solid #cbd5e1;border-radius:var(--radius-sm);font-size:13px;line-height:1.6;resize:vertical;font-family:inherit;box-sizing:border-box;"></textarea>
          <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
            <button @click="closePush" style="padding:8px 18px;border-radius:8px;border:1px solid #cbd5e1;background:var(--surface-card);cursor:pointer;">取消</button>
            <button @click="sendPush" :disabled="pushSending" style="padding:8px 24px;border-radius:8px;border:none;background:var(--gradient-brand);color:#fff;font-weight:600;cursor:pointer;">{{ pushSending ? '发送中...' : '发送' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

// ── Types ──────────────────────────────────────────────
interface Warning {
  id: number;
  enterprise: string;
  severity: string;
  title: string;
  detail: string;
  raw_data: string;
  source: string;
  source_url?: string;
  status: string;
  created_at: string;
}

interface FactorScan {
  "风险因子": string;
  "明细工具": string;
  "条目数": number;
}

interface IndustrySector {
  name: string;
  change_pct: number;
}

interface IndustryRisk {
  enterprise: string;
  sector: string;
  change_pct: number;
  level: string;
}

interface IndustryMissedOpp {
  sector: string;
  change_pct: number;
}

interface IndustryBoard {
  top_gainers: IndustrySector[];
  top_losers: IndustrySector[];
  matched_risks: IndustryRisk[];
  missed_opportunities: IndustryMissedOpp[];
  updated_at: string;
}

interface ChatItem {
  chat_id: string;
  name: string;
}

interface PushData {
  id: number;
  enterprise: string;
  severity: string;
}

// ── Constants ──────────────────────────────────────────
const BASE = import.meta.env.VITE_API_BASE_URL || "";
const API = `${BASE}/api/warnings`;

const SOURCE_MAP: Record<string, string> = {
  qichacha: "企查查",
  ths_stock: "同花顺",
  ths_macro: "同花顺宏观",
  ths_anomaly: "同花顺异常",
  ths_iwencai: "同花顺问财",
  piaojiaosuo: "票交所",
  web_search: "Web搜索",
  web_scrape: "网页采集",
};

const SEVERITY_ORDER: Record<string, number> = { red: 0, orange: 1, yellow: 2, normal: 3 };

// ── Reactive State ─────────────────────────────────────
const warnings = ref<Warning[]>([]);
const stats = ref({ red: 0, orange: 0, yellow: 0, normal: 0 });
const filterEnterprise = ref("");
const filterSeverity = ref("");
const refreshInfo = ref("60s后刷新");
const loadingWarnings = ref(true);
const enterpriseOptions = ref<string[]>([]);

// Industry board
const industryData = ref<IndustryBoard | null>(null);
const topGainers = computed(() => (industryData.value?.top_gainers || []).slice(0, 10));
const topLosers = computed(() => (industryData.value?.top_losers || []).slice(0, 10));
const industryRisks = computed(() => industryData.value?.matched_risks || []);
const industryMissed = computed(() => industryData.value?.missed_opportunities || []);
const industryTime = computed(() => {
  const t = industryData.value?.updated_at;
  return t ? " update " + new Date(t).toLocaleTimeString("zh-CN") : "";
});

// Detail modal
const detailModalOpen = ref(false);
const detailLoading = ref(false);
const detailError = ref("");
const detailHtml = ref("");
const factorDetailTitle = ref("");

// Push modal
const pushModalOpen = ref(false);
const pushData = ref<PushData | null>(null);
const pushChatSelect = ref("");
const pushChatId = ref(localStorage.getItem("last_feishu_chat_id") || "");
const pushSummary = ref("");
const pushAction = ref("");
const pushSending = ref(false);
const chatList = ref<ChatItem[]>([]);
const showCustomChatId = ref(false);

// Auto-refresh
let countdown = 60;
let industryRefreshCount = 0;
let refreshTimer: ReturnType<typeof setInterval> | null = null;

// ── Computed ───────────────────────────────────────────
const sortedWarnings = computed(() => {
  const filtered = warnings.value.filter((w) => {
    if (filterEnterprise.value && w.enterprise !== filterEnterprise.value) return false;
    if (filterSeverity.value && w.severity !== filterSeverity.value) return false;
    return true;
  });
  return [...filtered].sort(
    (a, b) =>
      SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
      (b.created_at || "").localeCompare(a.created_at || "")
  );
});

// ── Helpers ────────────────────────────────────────────
function escapeHtml(str: string): string {
  return (str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function parseRawData(raw: string): Record<string, any> {
  try {
    return JSON.parse(raw || "{}");
  } catch {
    return {};
  }
}

function parseRawForTitle(rawData: string): string {
  if (!rawData) return "";
  try {
    const obj = JSON.parse(rawData);
    if (obj["企业名称"]) return obj["企业名称"];
  } catch {
    /* ignore */
  }
  return "";
}

function parseDetail(text: string): string {
  if (!text) return "";
  try {
    const obj = JSON.parse(text);
    let s = (obj["摘要"] || "")
      .replace(/各因子明细请调用其「明细工具」/g, "")
      .replace(/。\s*$/, "")
      .trim();
    if (s) return s;
    if (obj["风险因子扫描"]) {
      const active = obj["风险因子扫描"]
        .filter((f: FactorScan) => f["条目数"] > 0)
        .map((f: FactorScan) => `${f["风险因子"]}(${f["条目数"]})`);
      return active.length ? active.join("、") : "未发现风险信号";
    }
    return text;
  } catch {
    let s = text
      .replace(/已全量扫描.*?。/g, "")
      .replace(/各因子明细请调用其.*/g, "")
      .trim();
    return s || text;
  }
}

function getRiskTitle(w: Warning): string {
  if (w.title && !w.title.startsWith("{")) return w.title;
  return parseRawForTitle(w.raw_data) || w.enterprise;
}

function getRiskSummary(w: Warning): string {
  return parseDetail(w.detail);
}

function getClickableFactors(w: Warning): { factor: string; tool: string; count: number }[] {
  try {
    const rd = parseRawData(w.raw_data);
    const scans: FactorScan[] = rd["风险因子扫描"] || [];
    return scans
      .filter((s) => s["条目数"] > 0)
      .slice(0, 8)
      .map((s) => ({ factor: s["风险因子"], tool: s["明细工具"], count: s["条目数"] }));
  } catch {
    return [];
  }
}

function isNormalWarning(w: Warning): boolean {
  if (w.severity === "normal") return true;
  try {
    const rd = parseRawData(w.raw_data);
    const scans: FactorScan[] = rd["风险因子扫描"] || [];
    return !scans.some((s) => s["条目数"] > 0);
  } catch {
    return false;
  }
}

function isNewWarning(w: Warning): boolean {
  const created = new Date((w.created_at || "") + "Z");
  const minutesAgo = Math.floor((Date.now() - created.getTime()) / 60000);
  return minutesAgo < 15 && !isNormalWarning(w);
}

function cardSeverityClass(w: Warning): string {
  return isNormalWarning(w) ? "normal" : w.severity;
}

function sevIcon(w: Warning): string {
  if (isNormalWarning(w)) return "✅";
  return { red: "🔴", orange: "🟠", yellow: "🟡" }[w.severity] || "🟡";
}

function sevLabel(w: Warning): string {
  if (isNormalWarning(w)) return "🟢 正常";
  const map: Record<string, string> = {
    red: "🔴 红色预警",
    orange: "🟠 橙色预警",
    yellow: "🟡 黄色预警",
  };
  return map[w.severity] || w.severity;
}

function timeAgo(w: Warning): string {
  const created = new Date((w.created_at || "") + "Z");
  const minutesAgo = Math.floor((Date.now() - created.getTime()) / 60000);
  if (minutesAgo < 1) return "刚刚";
  if (minutesAgo < 60) return `${minutesAgo}分钟前`;
  if (minutesAgo < 1440) return `${Math.floor(minutesAgo / 60)}小时前`;
  return `${Math.floor(minutesAgo / 1440)}天前`;
}

function sourceName(source: string): string {
  return SOURCE_MAP[source] || source;
}

function truncName(name: string): string {
  return (name || "").slice(0, 12);
}

// ── API Calls ──────────────────────────────────────────
async function loadWarnings() {
  const ent = filterEnterprise.value;
  const sev = filterSeverity.value;
  let url = `${API}?limit=200`;
  if (ent) url += `&enterprise=${encodeURIComponent(ent)}`;
  if (sev) url += `&severity=${encodeURIComponent(sev)}`;

  try {
    const resp = await fetch(url);
    const data = await resp.json();
    warnings.value = data.warnings || [];

    // Build enterprise filter options
    const seen = new Set<string>();
    const cur = filterEnterprise.value;
    const options: string[] = [];
    warnings.value.forEach((w) => {
      if (!seen.has(w.enterprise)) {
        seen.add(w.enterprise);
        options.push(w.enterprise);
      }
    });
    enterpriseOptions.value = options;
    if (cur && !seen.has(cur)) {
      filterEnterprise.value = "";
      filterEnterprise.value = cur;
    }

    refreshInfo.value = `最后更新: ${new Date().toLocaleTimeString()}`;
    loadingWarnings.value = false;
  } catch (err) {
    console.error(err);
    loadingWarnings.value = false;
  }
}

async function loadStats() {
  try {
    const resp = await fetch(`${API}/stats`);
    const data = await resp.json();
    const bySev = data.by_severity || {};
    stats.value = {
      red: bySev.red || 0,
      orange: bySev.orange || 0,
      yellow: bySev.yellow || 0,
      normal: bySev.normal || 0,
    };
    const total = Object.values(bySev).reduce((a: number, b: any) => a + (b || 0), 0);
    if (total) refreshInfo.value = `${total}条`;
  } catch (err) {
    console.error(err);
  }
}

async function loadIndustryBoard() {
  try {
    const resp = await fetch(`${BASE}/api/industry/sectors`);
    const data = await resp.json();
    if (data.status === "ok") {
      industryData.value = {
        top_gainers: data.top_gainers || [],
        top_losers: data.top_losers || [],
        matched_risks: data.matched_risks || [],
        missed_opportunities: data.missed_opportunities || [],
        updated_at: data.updated_at,
      };
    }
  } catch (err) {
    console.error("Industry scan:", err);
  }
}

async function falseWarning(id: number) {
  try {
    await fetch(`${API}/${id}/false`, {
      method: "PUT",
      headers: { "X-API-Key": "warning-dev-key-2026" },
    });
    setTimeout(loadWarnings, 400);
  } catch (err) {
    console.error(err);
  }
}

async function unfalseWarning(id: number) {
  try {
    await fetch(`${API}/${id}/unfalse`, {
      method: "PUT",
      headers: { "X-API-Key": "warning-dev-key-2026" },
    });
    setTimeout(loadWarnings, 400);
  } catch (err) {
    console.error(err);
  }
}

async function setSeverity(id: number, severity: string) {
  try {
    await fetch(`${API}/${id}/severity`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": "warning-dev-key-2026",
      },
      body: JSON.stringify({ severity }),
    });
    setTimeout(loadWarnings, 400);
  } catch (err) {
    console.error(err);
  }
}

// ── Detail Modal ───────────────────────────────────────
function formatParty(p: any): string {
  if (!p) return "";
  if (typeof p === "string") return p;
  const parts: string[] = [];
  for (const [role, names] of Object.entries(p)) {
    if (Array.isArray(names) && names.length) parts.push(`${role}: ${names.join("、")}`);
  }
  return parts.join(" | ") || JSON.stringify(p);
}

function formatFactorContent(content: string, factor: string): string {
  if (!content) return "";
  try {
    const data = JSON.parse(content);
    const listKeys = [
      "行政处罚信息",
      "裁判文书",
      "裁判文书信息",
      "立案信息",
      "开庭公告信息",
      "开庭公告",
      "法院公告",
    ];
    let items: any[] = [],
      listKey = "";
    for (const k of listKeys) {
      if (Array.isArray(data[k]) && data[k].length > 0) {
        items = data[k];
        listKey = k;
        break;
      }
    }
    if (!items.length) {
      const summary = data["摘要"] || data["检索结果"] || "";
      return summary
        ? `<div class="penalty-card"><div class="penalty-body" style="text-align:center;color:var(--text-subtle);padding:20px;">${escapeHtml(summary)}</div></div>`
        : "";
    }
    const getField = (d: any, names: string[]) => {
      for (const n of names) if (d[n]) return d[n];
      return "";
    };
    const getDate = (d: any) =>
      getField(d, ["裁判日期", "立案日期", "处罚日期", "开庭时间", "开庭日期", "发布日期"]);
    const getCourt = (d: any) => getField(d, ["法院", "法院名称", "处罚单位"]);
    const getCaseNo = (d: any) => getField(d, ["案号", "决定书文号"]);
    const getReason = (d: any) => getField(d, ["案由", "处罚结果"]);
    const emoji: Record<string, string> = {
      行政处罚信息: "📋",
      裁判文书: "⚖️",
      裁判文书信息: "⚖️",
      立案信息: "📝",
      开庭公告信息: "📅",
      开庭公告: "📅",
      法院公告: "📢",
    };
    const em = emoji[listKey] || "📄";
    return items
      .map((d: any, i: number) => {
        const hasPenalty = listKey.includes("处罚");
        return `
      <div class="penalty-card">
        <div class="penalty-header">${em} ${escapeHtml(factor)} ${i + 1}: ${escapeHtml(getCaseNo(d) || "")}</div>
        <div class="penalty-body">
          ${
            getReason(d)
              ? `<div class="penalty-row"><span>${hasPenalty ? "处罚结果" : "案由"}</span><span class="${hasPenalty ? "penalty-amount" : ""}">${escapeHtml(getReason(d))}</span></div>`
              : ""
          }
          ${
            d["当事人"] || d["当事人信息"]
              ? `<div class="penalty-row"><span>当事人</span><span>${escapeHtml(formatParty(d["当事人"] || d["当事人信息"]))}</span></div>`
              : ""
          }
          ${getCourt(d) ? `<div class="penalty-row"><span>${hasPenalty ? "处罚单位" : "法院"}</span><span>${escapeHtml(getCourt(d))}</span></div>` : ""}
          ${getDate(d) ? `<div class="penalty-row"><span>日期</span><span>${escapeHtml(getDate(d))}</span></div>` : ""}
          ${
            d["处罚金额"]
              ? `<div class="penalty-row"><span>处罚金额</span><span class="penalty-amount">¥${Number(d["处罚金额"]).toLocaleString()}</span></div>`
              : ""
          }
          ${d["裁判结果"] ? `<div class="penalty-row"><span>裁判结果</span><span>${escapeHtml(d["裁判结果"])}</span></div>` : ""}
          ${d["审理法官"] ? `<div class="penalty-row"><span>审理法官</span><span>${escapeHtml(d["审理法官"])}</span></div>` : ""}
        </div>
      </div>
    `;
      })
      .join("");
  } catch {
    /* fall through */
  }
  return `<pre style="white-space:pre-wrap;font-size:13px;line-height:1.6;color:var(--text-secondary);background:#f8fafc;padding:12px;border-radius:8px;">${escapeHtml(content)}</pre>`;
}

async function showDetail(id: number) {
  factorDetailTitle.value = "";
  detailModalOpen.value = true;
  detailLoading.value = true;
  detailError.value = "";
  detailHtml.value = "";
  try {
    const resp = await fetch(`${API}/${id}/detail`);
    const data = await resp.json();
    let html = "";
    html += `<p style="margin:0 0 12px;"><b>${escapeHtml(data.enterprise)}</b> | 数据源: ${escapeHtml(data.source)} | 预警ID: ${data.warning_id}</p>`;
    if (data.parse_error) {
      html += `<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px;margin-bottom:12px;"><b style="color:#dc2626;">⚠️ raw_data JSON 解析失败:</b> ${escapeHtml(data.parse_error)}</div>`;
    }
    if (data.factors && data.factors.length) {
      html += `<h4 style="margin:12px 0 8px;">风险因子 (有记录)</h4>`;
      html += data.factors
        .map(
          (f: any) => `
        <div style="padding:8px 12px;background:var(--surface-card);border-radius:8px;margin:4px 0;border:1px solid var(--border-medium);">
          ${escapeHtml(f.name)}: <b>${f.count}条</b>
          ${f.tool ? `<span style="color:var(--color-primary-light);font-size:12px;">→ 调用了 <code>${escapeHtml(f.tool)}</code></span>` : ""}
          ${f.raw_preview ? `<pre style="white-space:pre-wrap;font-size:11px;color:var(--text-subtle);margin:4px 0 0;">${escapeHtml(f.raw_preview)}</pre>` : ""}
        </div>
      `
        )
        .join("");
    }
    if (data.details && data.details.length) {
      html += `<h4 style="margin:12px 0 8px;">明细查询结果</h4>`;
      html += data.details
        .map(
          (d: any) => `
        <div style="background:#f8fafc;border:1px solid var(--border-medium);border-radius:var(--radius-sm);padding:14px;margin-bottom:12px;">
          <h4 style="margin:0 0 4px;color:var(--text-body);">${escapeHtml(d.factor)} (${d.count}条)
            <span style="font-weight:normal;font-size:12px;color:var(--color-primary-light);">调用: <code>${escapeHtml(d.tool_called || "N/A")}</code></span>
          </h4>
          ${d.error ? `<p style="color:#dc2626;font-size:12px;">错误: ${escapeHtml(d.error)}</p>` : ""}
          ${d.content ? formatFactorContent(d.content, d.factor) : ""}
          ${d.raw_response ? `<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:12px;color:var(--text-subtle);">📡 原始返回</summary><pre style="white-space:pre-wrap;font-size:11px;color:#94a3b8;max-height:200px;overflow-y:auto;">${escapeHtml(d.raw_response)}</pre></details>` : ""}
        </div>
      `
        )
        .join("");
    }
    if (!data.factors?.length && !data.details?.length) {
      html += '<p style="color:var(--text-subtle);">无可用数据</p>';
    }
    detailHtml.value = html;
  } catch (err: any) {
    detailError.value = `查询失败: ${err.message}`;
  } finally {
    detailLoading.value = false;
  }
}

async function showFactorDetail(enterprise: string, factor: string, tool: string, count: number) {
  factorDetailTitle.value = `${factor} — ${enterprise}`;
  detailModalOpen.value = true;
  detailLoading.value = true;
  detailError.value = "";
  detailHtml.value = "";
  try {
    const params = new URLSearchParams({ enterprise, tool, factor });
    const resp = await fetch(`${BASE}/api/warnings/factor?` + params);
    const data = await resp.json();
    detailHtml.value = `
      <p style="font-size:13px;color:var(--text-subtle);margin:0 0 12px;">${escapeHtml(data.factor)}: <b>${count}条</b> · 数据源: ${escapeHtml(data.tool)}</p>
      ${data.error ? `<p style="color:#dc2626;">${escapeHtml(data.error)}</p>` : ""}
      ${data.content ? formatFactorContent(data.content, data.factor) : '<p style="color:var(--text-subtle);">无数据</p>'}
    `;
  } catch (e: any) {
    detailError.value = `查询失败: ${e.message}`;
  } finally {
    detailLoading.value = false;
  }
}

function closeDetail() {
  detailModalOpen.value = false;
  detailHtml.value = "";
  detailError.value = "";
  factorDetailTitle.value = "";
}

// ── Push Modal ─────────────────────────────────────────
async function loadChats() {
  try {
    const resp = await fetch(`${BASE}/api/feishu/chats`);
    const data = await resp.json();
    chatList.value = data.chats || [];
  } catch {
    chatList.value = [];
  }
}

function showPush(id: number, enterprise: string, severity: string, title: string, detail: string) {
  pushData.value = { id, enterprise, severity };
  const cleanDetail = (detail || "")
    .replace(/已全量扫描.*?。/g, "")
    .replace(/各因子明细请调用其.*/g, "")
    .trim();
  pushSummary.value = cleanDetail || title || "";
  pushAction.value =
    severity === "red"
      ? "🚨 请立即核实，必要时启动风险应对流程"
      : "📋 请关注并在24小时内完成评估";
  pushChatId.value = localStorage.getItem("last_feishu_chat_id") || "";
  showCustomChatId.value = false;
  pushChatSelect.value = "";
  loadChats();
  pushModalOpen.value = true;
}

function onPushChatSelectChange() {
  showCustomChatId.value = pushChatSelect.value === "__custom__";
}

async function sendPush() {
  if (!pushData.value) return;
  let chatId =
    pushChatSelect.value && pushChatSelect.value !== "__custom__"
      ? pushChatSelect.value
      : pushChatId.value.trim();
  if (!chatId) {
    alert("请选择或输入发送目标");
    return;
  }
  localStorage.setItem("last_feishu_chat_id", chatId);
  pushSending.value = true;
  try {
    const resp = await fetch(`${API}/${pushData.value.id}/push`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": "warning-dev-key-2026",
      },
      body: JSON.stringify({
        chat_id: chatId,
        enterprise: pushData.value.enterprise,
        severity: pushData.value.severity,
        summary: pushSummary.value,
        action: pushAction.value,
        detail_url: `${BASE}/warnings`,
      }),
    });
    const data = await resp.json();
    if (data.status === "ok") {
      closePush();
    } else {
      alert("推送失败: " + (data.detail || ""));
    }
  } catch (e: any) {
    alert("推送异常: " + e.message);
  } finally {
    pushSending.value = false;
  }
}

function closePush() {
  pushModalOpen.value = false;
  pushData.value = null;
}

// ── Refresh ────────────────────────────────────────────
function refreshAll() {
  loadWarnings();
  loadStats();
}

function initAutoRefresh() {
  countdown = 60;
  industryRefreshCount = 0;
  refreshTimer = setInterval(() => {
    countdown--;
    if (countdown <= 0) {
      loadStats();
      loadWarnings();
      countdown = 60;
      industryRefreshCount++;
    }
    if (industryRefreshCount >= 5) {
      loadIndustryBoard();
      industryRefreshCount = 0;
    }
    refreshInfo.value = `${countdown}s后刷新`;
  }, 1000);
}

// ── Lifecycle ──────────────────────────────────────────
onMounted(() => {
  loadStats();
  loadWarnings();
  loadIndustryBoard();
  initAutoRefresh();
});

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
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

/* 统计卡片 */
.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 120px;
  padding: 16px 20px;
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-card);
  text-align: center;
}

.stat-card .num {
  font-size: 28px;
  font-weight: 800;
}

.stat-card .label {
  font-size: 12px;
  color: var(--text-subtle);
  margin-top: 4px;
}

.stat-card.red {
  border-left: 4px solid #ef4444;
}

.stat-card.orange {
  border-left: 4px solid #f97316;
}

.stat-card.yellow {
  border-left: 4px solid #eab308;
}

/* 筛选栏 */
.filters {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 20px;
  align-items: center;
}

.filters select,
.filters input {
  padding: 8px 14px;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: var(--surface-card);
}

.filters label {
  font-size: 13px;
  color: var(--text-subtle);
  font-weight: 600;
}

/* 预警列表 */
.warning-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.warning-card {
  background: var(--surface-card);
  border-radius: var(--radius-lg);
  padding: 18px 22px;
  box-shadow: var(--shadow-card);
  display: flex;
  gap: 16px;
  align-items: flex-start;
  transition: box-shadow var(--transition-fast);
}

.warning-card:hover {
  box-shadow: var(--shadow-panel);
}

.warning-card.red {
  border-left: 5px solid #ef4444;
}

.warning-card.orange {
  border-left: 5px solid #f97316;
}

.warning-card.yellow {
  border-left: 5px solid #eab308;
}

.warning-card.normal {
  border-left: 5px solid #22c55e;
  background: #f0fdf4;
}

.sev-icon {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}

.warning-content {
  flex: 1;
  min-width: 0;
}

.warning-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 4px;
  color: var(--text-primary);
}

.warning-detail {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.55;
  max-height: 60px;
  overflow: hidden;
}

.warning-meta {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #94a3b8;
}

.warning-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.warning-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.warning-actions button {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  font-size: 12px;
  cursor: pointer;
  background: var(--surface-card);
  transition: 0.15s;
}

.warning-actions button.ack {
  border-color: #22c55e;
  color: #166534;
}

.warning-actions button.ack:hover {
  background: #f0fdf4;
}

.warning-actions button.false-btn {
  border-color: #f97316;
  color: #9a3412;
}

.warning-actions button.false-btn:hover {
  background: #fff7ed;
}

.detail-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--color-primary-light);
  font-size: 12px;
  cursor: pointer;
  background: #eff6ff;
  color: var(--color-primary-dark);
  transition: 0.15s;
}

.detail-btn:hover {
  background: #dbeafe;
}

.push-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--color-accent);
  font-size: 12px;
  cursor: pointer;
  background: #f5f3ff;
  color: #6d28d9;
  transition: 0.15s;
}

.push-btn:hover {
  background: #ede9fe;
}

.factor-link {
  display: inline-block;
  padding: 3px 10px;
  margin: 2px 3px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  background: #eff6ff;
  color: var(--color-primary-dark);
  border: 1px solid #bfdbfe;
  transition: 0.15s;
}

.factor-link:hover {
  background: var(--color-primary-light);
  color: #fff;
  border-color: var(--color-primary-light);
}

.new-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  background: #dc2626;
  color: #fff;
  animation: pulse 2s infinite;
}

.auto-refresh {
  font-size: 12px;
  color: var(--text-subtle);
}

/* 空状态 */
.empty {
  text-align: center;
  padding: 60px 20px;
  color: #94a3b8;
}

.empty .icon {
  font-size: 48px;
  margin-bottom: 12px;
}

/* 骨架屏 */
.card-skeleton {
  background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-lg);
  height: 100px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

/* 标签 */
.tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

.tag-orange {
  background: #fff7ed;
  color: #9a3412;
}

.tag-blue {
  background: #dbeafe;
  color: #1e40af;
}

.sev-label {
  font-weight: 600;
  font-size: 12px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
}

.badge.red {
  background: #fecaca;
  color: #991b1b;
}

.badge.orange {
  background: #fed7aa;
  color: #9a3412;
}

.badge.yellow {
  background: #fef08a;
  color: #854d0e;
}

/* 状态已确认 */
.status-acked {
  opacity: 0.6;
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

.modal-panel {
  background: var(--surface-card);
  border-radius: 16px;
  width: 100%;
  max-height: 80vh;
  overflow-y: auto;
  padding: 24px;
  box-shadow: var(--shadow-modal);
}

/* 处罚卡片 */
.penalty-card {
  background: var(--surface-card);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  margin-bottom: 10px;
  overflow: hidden;
}

.penalty-header {
  background: #f1f5f9;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-body);
  border-bottom: 1px solid var(--border-medium);
}

.penalty-body {
  padding: 10px 14px;
}

.penalty-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid #f8fafc;
}

.penalty-row span:first-child {
  color: var(--text-subtle);
  min-width: 60px;
}

.penalty-row span:last-child {
  color: var(--text-body);
  font-weight: 500;
  text-align: right;
}

.penalty-amount {
  color: #dc2626 !important;
  font-weight: 700 !important;
}

/* Generating spinner */
.generating-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #bfdbfe;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
