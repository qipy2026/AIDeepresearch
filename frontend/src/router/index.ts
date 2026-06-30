import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/",              name: "projects",  component: () => import("../pages/ProjectsPage.vue") },
  { path: "/research",      name: "research",  component: () => import("../pages/ResearchPage.vue") },
  { path: "/warnings",      name: "warnings",  component: () => import("../pages/WarningsPage.vue") },
  { path: "/sources",       name: "sources",   component: () => import("../pages/SourcesPage.vue") },
  { path: "/upload",        name: "upload",    component: () => import("../pages/UploadPage.vue") },
  { path: "/reports",       name: "reports",   component: () => import("../pages/ReportsPage.vue") },
  { path: "/reports/:id/edit", name: "report-edit", component: () => import("../pages/ReportEditPage.vue") },
  {
    path: "/upload/:enterprise",
    name: "upload-detail",
    component: () => import("../pages/UploadDetailPage.vue"),
  },
];

const router = createRouter({
  history: createWebHistory("/loan/"),
  routes,
});

export default router;
