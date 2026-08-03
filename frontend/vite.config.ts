import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

const sitesWorker = () => ({
  name: "sites-worker",
  generateBundle(this: { emitFile: (file: { type: "asset"; fileName: string; source: string }) => void }) {
    this.emitFile({
      type: "asset",
      fileName: "server/index.js",
      source: `export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const url = new URL(request.url);
    const isPageRequest = request.method === "GET" && !url.pathname.split("/").pop().includes(".");

    if (response.status === 404 && isPageRequest) {
      return env.ASSETS.fetch(new Request(new URL("/", url), request));
    }

    return response;
  },
};\n`,
    });
  },
});

export default defineConfig(({ mode }) => ({
  plugins: [react(), sitesWorker()],
  resolve: {
    alias: {
      "@docs-blog": path.resolve(rootDir, "../docs/blog"),
    },
  },
  server: { port: Number(loadEnv(mode, ".", "PORT").PORT) || 5173 },
}));
