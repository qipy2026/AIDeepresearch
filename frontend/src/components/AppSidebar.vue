<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo">
        <div class="sidebar-logo-icon">
          <img src="/logo-160.png" alt="贷后管理助手" />
        </div>
        <div>
          <h1 class="sidebar-title">贷后管理助手</h1>
          <p class="sidebar-subtitle">监控与预警系统</p>
        </div>
      </div>
    </div>
    <hr class="sidebar-divider">
    <nav class="sidebar-nav">
      <router-link class="sidebar-link" to="/">🏢 贷后项目</router-link>
      <router-link class="sidebar-link" to="/research">📋 贷后助手</router-link>
      <router-link class="sidebar-link" to="/warnings">⚠️ 预警中心</router-link>
      <router-link class="sidebar-link" to="/sources">📡 数据源管理</router-link>
      <router-link class="sidebar-link" to="/upload">📄 参考文档</router-link>
      <router-link class="sidebar-link" to="/reports">📊 报告列表</router-link>
    </nav>
    <hr class="sidebar-divider">
    <div class="sidebar-actions">
      <router-link class="btn-new-research" to="/research">+ 开始新调查</router-link>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  min-width: 280px;
  height: 100vh;
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-right: 1px solid rgba(148, 163, 184, 0.28);
  box-shadow: 4px 0 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  padding: 28px 20px;
  gap: 20px;
  overflow-y: auto;
  z-index: 100;
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.sidebar-logo-icon {
  width: 160px;
  height: 200px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar-logo-icon img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.sidebar-title {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}

.sidebar-subtitle {
  font-size: 12px;
  color: #64748b;
  margin: 0;
}

.sidebar-divider {
  border: none;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  margin: 0;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  border-radius: 14px;
  border: 1px solid transparent;
  color: #475569;
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: all 150ms cubic-bezier(0.16, 1, 0.3, 1);
}

.sidebar-link:hover {
  background: rgba(59, 130, 246, 0.06);
  border-color: rgba(148, 163, 184, 0.28);
  color: #3b82f6;
}

.sidebar-link.router-link-exact-active,
.sidebar-link.router-link-active {
  background: rgba(59, 130, 246, 0.10);
  border-color: #3b82f6;
  color: #2563eb;
  font-weight: 600;
}

/* / 路由不是精确匹配时，子路径不应自动激活父级 */
.sidebar-link.router-link-active {
  /* router-link-active 对于父路径也生效，用精确匹配覆盖 / */
}
.router-link-active.sidebar-link[href="/"] {
  /* / 路由用 exact 匹配 */
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 4px;
}

.btn-new-research {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  color: #fff;
  border: none;
  border-radius: 14px;
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
  transition: transform 150ms cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 150ms cubic-bezier(0.16, 1, 0.3, 1);
  text-decoration: none;
}

.btn-new-research:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
}
</style>
