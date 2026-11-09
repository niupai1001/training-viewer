import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  root: "next",
  plugins: [react()],
  build: { outDir: "../../src/viewer_next/web", emptyOutDir: true },
});
