# 第三方依赖与许可

本项目自身及随包的 `@fifty/*` 共享模块使用 MIT License。下表记录直接运行依赖的上游许可；具体版本以 `uv.lock` 与 `package-lock.json` 为唯一事实源，发布时不得用本表替代锁文件。

## Python

| 依赖 | 许可 |
|---|---|
| FastAPI、Pydantic | MIT |
| OpenAI Python SDK、python-multipart | Apache-2.0 |
| Uvicorn | BSD-3-Clause |

开发依赖中，pytest 与 Ruff 为 MIT，HTTPX 为 BSD-3-Clause，Hatchling 为 MIT。

## Web

| 依赖组 | 许可 |
|---|---|
| React、React DOM、Vite、Vitest、Tailwind CSS | MIT |
| Radix UI、TanStack Table、Recharts、Sonner | MIT |
| clsx、tailwind-merge | MIT |
| class-variance-authority、TypeScript | Apache-2.0 |
| Lucide React | ISC |

测试和构建使用的 Testing Library、jsdom、`@vitejs/plugin-react` 与 `@tailwindcss/vite` 均为 MIT。

## 私有与外部工具

私有本地发布/剪辑工具、既有内容模块和 `lark-cli` 只通过运行时适配器调用，不复制进本项目发布包；它们的许可与数据使用边界见 [`research/upstreams.md`](research/upstreams.md)。平台 token、模型密钥和真实媒体不属于开源包内容。

## 产品流程参考

Day 1 的脚本流程借鉴了成熟带货脚本产品的公开流程结论（商品事实 → 多候选 → 选择/改稿 → 成片），只作产品流程评论与设计证据，不复制任何闭源代码或界面素材。
