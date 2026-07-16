#!/usr/bin/env node
// ============================================================
// sync-ui：共享 UI 包一键同步（monorepo → 本项目 vendor tgz）
//
// 做两件事：
//   1. 对 ../../packages 下三个共享包依次 npm pack 到 vendor/（覆盖同名 tgz）
//   2. 在本项目 npm install 这三个 tgz（刷新 package-lock 与 node_modules）
//
// 用法：npm run sync-ui [-- --dry-run]
//   --dry-run 只打印将执行的命令，不落任何改动
//
// 单项目 standalone 下载包没有 ../../packages，本脚本会明确报错退出——
// 那种环境下 vendor/*.tgz 已随包携带，直接 npm install 即可，无需 sync。
// ============================================================
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const packagesDir = path.resolve(appDir, "..", "..", "packages");
const vendorDir = path.join(appDir, "vendor");
const dryRun = process.argv.includes("--dry-run");

// 打包顺序 = 依赖顺序（workbench-ai 依赖前两个包）
const SHARED_PACKAGES = ["run-contract", "workbench-ui", "workbench-ai"];

function fail(message) {
  console.error(`[sync-ui] 错误：${message}`);
  process.exit(1);
}

// 统一执行入口：dry-run 只打印，不执行
function run(args, cwd) {
  console.log(`[sync-ui] $ npm ${args.join(" ")}\n          (cwd: ${cwd})`);
  if (dryRun) return;
  execFileSync("npm", args, { cwd, stdio: "inherit" });
}

// npm pack 的产物名由包名+版本决定：@fifty/run-contract@0.1.0 → fifty-run-contract-0.1.0.tgz
function tarballName(pkgDir) {
  const manifest = JSON.parse(readFileSync(path.join(pkgDir, "package.json"), "utf8"));
  return `${manifest.name.replace(/^@/, "").replace("/", "-")}-${manifest.version}.tgz`;
}

if (!existsSync(packagesDir)) {
  fail(
    `未找到共享包目录 ${packagesDir}\n` +
      "  当前是单项目 standalone 环境（不在 50 天 monorepo 内），共享 UI 已固化在 vendor/*.tgz，\n" +
      "  无需也无法 sync；请直接 npm install。",
  );
}

const tarballs = [];
for (const name of SHARED_PACKAGES) {
  const pkgDir = path.join(packagesDir, name);
  if (!existsSync(path.join(pkgDir, "package.json"))) {
    fail(`共享包缺失：${pkgDir}（monorepo 结构不完整）`);
  }
  run(["pack", "--pack-destination", vendorDir], pkgDir);
  tarballs.push(`./vendor/${tarballName(pkgDir)}`);
}

// 显式把 tgz 作为 install 参数传入：内容变了（版本没变）也会重算 integrity 并刷新
run(["install", ...tarballs], appDir);

console.log(
  dryRun
    ? "[sync-ui] dry-run 结束，以上为计划执行的命令。"
    : "[sync-ui] 完成：vendor tgz、package-lock、node_modules 已同步。",
);
