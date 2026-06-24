import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: '/app/',
  server: {
    host: '0.0.0.0',
    port: 5174,
    allowedHosts: true 
  }
});
