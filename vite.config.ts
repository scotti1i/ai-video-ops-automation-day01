import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type PluginOption } from "vite";

const localModule = (name: string) => fileURLToPath(new URL(`./node_modules/${name}`, import.meta.url));
const apiOrigin = `http://127.0.0.1:${process.env.VIDEO_OPS_API_PORT ?? "8787"}`;

// ============================================================
// 共享包源码直连（可选增强，默认关闭）
// FIFTY_UI_SRC=1 且 monorepo 的 ../../packages 在场时，把三个 @fifty
// 包 alias 到包源码：改 packages 组件即时生效，无需重打 vendor tgz。
// 默认（CI、standalone 下载包、平时开发）仍走 tgz 安装的 node_modules；
// tgz 更新用 `npm run sync-ui`。
// ============================================================
const packagesDir = fileURLToPath(new URL("../../packages", import.meta.url));
const uiSrcMode = process.env.FIFTY_UI_SRC === "1" && existsSync(path.join(packagesDir, "workbench-ui/src"));
const pkgSrc = (rel: string) => path.join(packagesDir, rel);

const uiSrcAliases = uiSrcMode
  ? [
      { find: /^@fifty\/run-contract$/, replacement: pkgSrc("run-contract/src/index.ts") },
      { find: /^@fifty\/run-contract\/schema$/, replacement: pkgSrc("run-contract/src/run-event.schema.json") },
      { find: /^@fifty\/workbench-ui$/, replacement: pkgSrc("workbench-ui/src/index.ts") },
      { find: /^@fifty\/workbench-ui\/styles\.css$/, replacement: pkgSrc("workbench-ui/src/styles.css") },
      { find: /^@fifty\/workbench-ai$/, replacement: pkgSrc("workbench-ai/src/index.ts") },
    ]
  : [];

// 源码模式下强制共享依赖（radix/lucide/recharts…）只用本项目一份，
// 避免 packages/node_modules 出现第二份实例导致 React context 断裂。
const uiSrcDedupe = uiSrcMode
  ? Object.keys(
      (JSON.parse(readFileSync(pkgSrc("workbench-ui/package.json"), "utf8")) as { dependencies?: Record<string, string> })
        .dependencies ?? {},
    )
  : [];

// Tailwind 的 CSS @import / @source 走自己的解析器，不吃 vite alias；
// 源码模式下用 pre 插件改写入口 CSS：样式指向包源码，并补扫描路径。
function uiSrcCssPlugin(): PluginOption {
  if (!uiSrcMode) return false;
  const cssDir = fileURLToPath(new URL("./src/web", import.meta.url));
  const relTo = (rel: string) => path.relative(cssDir, pkgSrc(rel)).replaceAll(path.sep, "/");
  return {
    name: "fifty-ui-src-css",
    enforce: "pre",
    transform(code, id) {
      if (!id.split("?")[0].endsWith("/src/web/styles.css")) return;
      const redirected = code.replace(/(["'])@fifty\/workbench-ui\/styles\.css\1/g, `"${relTo("workbench-ui/src/styles.css")}"`);
      const extraSources = ["workbench-ui/src", "workbench-ai/src"].map((rel) => `@source "${relTo(rel)}";`).join("\n");
      return `${redirected}\n${extraSources}\n`;
    },
  };
}

export default defineConfig({
  plugins: [react(), uiSrcCssPlugin(), tailwindcss()],
  resolve: {
    alias: [
      ...uiSrcAliases,
      { find: /^react$/, replacement: localModule("react") },
      { find: /^react-dom$/, replacement: localModule("react-dom") },
      { find: /^react-dom\/(.*)$/, replacement: `${localModule("react-dom")}/$1` },
    ],
    dedupe: ["react", "react-dom", ...uiSrcDedupe],
    preserveSymlinks: true,
  },
  server: {
    proxy: {
      "/api": apiOrigin,
      "/files": apiOrigin,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/web/tests/setup.ts"],
    include: ["src/web/tests/**/*.test.{ts,tsx}"],
  },
});
