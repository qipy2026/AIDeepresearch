<template>
  <div class="layout-shell">
    <AppSidebar />
    <router-view />
  </div>
</template>

<script setup lang="ts">
import AppSidebar from "./components/AppSidebar.vue";
</script>
