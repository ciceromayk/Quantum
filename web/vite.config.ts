import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base relativa: funciona em https://<usuario>.github.io/<repositorio>/ sem configuração.
export default defineConfig({
  base: "./",
  plugins: [react()],
  worker: { format: "es" },
  build: { outDir: "dist" },
});
