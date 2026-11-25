/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
const target = "http://127.0.0.1:8765";
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": { target, changeOrigin: true },
            "/ws": { target: target.replace("http", "ws"), ws: true },
        },
    },
    build: { outDir: "dist", sourcemap: false },
    test: { environment: "node", include: ["src/**/*.test.ts"] },
});
