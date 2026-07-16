# 随包共享模块

Day 01 使用根仓库 `packages/` 下的三个小型共享模块。为了让单项目下载包脱离根仓库仍能安装，本目录固定携带对应的 npm tarball：

- `@fifty/run-contract`
- `@fifty/workbench-ai`
- `@fifty/workbench-ui`

它们只包含源码与 `package.json`，与本项目一起按 MIT License 分发。

## 同步工作流（monorepo 内）

改了 `packages/` 里的组件后，在本项目跑一条命令：

```bash
npm run sync-ui           # 重打三个 tgz 到 vendor/ 并 npm install，刷新 lock 与 node_modules
npm run sync-ui -- --dry-run   # 只打印计划，不落改动
```

脚本在 `scripts/sync-ui.mjs`，零第三方依赖。单项目 standalone 包没有 `../../packages`，脚本会明确报错退出——那种环境下直接 `npm install` 即可，tgz 已随包携带。

**注意**：sync-ui 换掉的是 `node_modules` 里的包，Vite 的依赖预构建缓存不会自动失效。dev server 正在跑时同步完共享包，必须重启 dev server（必要时先 `rm -rf node_modules/.vite`），否则页面上仍是旧组件。改 day-01 自己的 `src/web/**` 不受影响，照常热更新。

## 源码直连模式（开发期可选）

频繁迭代共享组件时，可跳过打包直接吃 `packages/` 源码（即时 HMR）：

```bash
FIFTY_UI_SRC=1 npm run dev
```

`vite.config.ts` 检测到该环境变量且 `../../packages` 在场时，会把三个 `@fifty` 包 alias 到源码，并改写 Tailwind 的样式入口与 `@source` 扫描路径。默认（不带变量、CI、standalone 包）一律走 vendor tgz，行为不变。迭代完成后仍需 `npm run sync-ui` 把结果固化进 tgz。
