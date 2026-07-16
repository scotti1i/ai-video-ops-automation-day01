# 二次开发指南 · fork 后如何改造

这份文档给想把 Day 01 改成自己版本的人：换掉写脚本的模型、接自己的发布平台、加一个数据源，或把整条流水线搬到别的行业。先按 [`README.md`](README.md) 跑通零密钥 Demo，再回来看这里。

## 架构：业务核心与外部世界解耦

后端是六边形结构，业务规则不认识任何具体的模型商或平台：

```
domain/        纯业务：视频、脚本、发布、血缘的模型、状态机、质量门
  models.py        领域对象（Video / ScriptArtifact / Publication / MetricSnapshot …）
  ports.py         ★ 可替换合同（二开主要改这里的实现，不改核心）
  states.py        状态流转规则
  script_quality.py  带货脚本确定性质量门
application/   用例编排：一次生成、选稿、发布、数据回流、裂变
  service.py       应用服务，唯一对外用例入口
adapters/      ★ 合同的具体实现（换引擎、接平台就在这里加文件）
  script_producers.py  内置模板 + OpenAI 写脚本引擎
  cli_producers.py     本机 Claude / Codex 命令行写脚本引擎
  mock_platform.py     零密钥模拟平台
  youtube.py           YouTube 真实平台
  sqlite_repo.py       SQLite 持久化
api/           HTTP / SSE 边界，只做输入输出，不写业务规则
```

前端 `src/web/` 是一张锁定拓扑的节点画布（`canvas/`），每个节点点开是一个面板（`canvas/panels/`），只消费后端 API，不自己算第二套状态。

一句话：**要改的几乎都在 `adapters/`；`domain/ports.py` 定义了能改什么。核心 `domain/` 和 `application/` 尽量别动。**

## 三个最常见的改造

### 1. 换写脚本的模型（最常见）

合同就一个方法（`domain/ports.py`）：

```python
class ScriptProducer(Protocol):
    def produce(self, context: str, instruction: str) -> ScriptResult: ...
```

`produce` 吃一段 Context（商品 / 受众 / 场景）和一条指令，吐一个脚本 + 2–12 个镜头。返回结构见 `adapters/script_producers.py` 的 `GeneratedPlan`：每个镜头有时长、画面、口播、屏幕字和角色（hook / problem / value / proof / objection / cta）。

已有三种实现，复制一份改就行：

- 内置封闭模板（零密钥，`script_strategies.py`）——Demo 用，不需要网络；
- OpenAI Responses（`script_producers.py`）——配 `OPENAI_API_KEY`，兼容只填域名根的中继；
- 本机命令行（`cli_producers.py`）——装了并登录 `claude` 或 `codex` 就能用，不需要 API key。

选哪个由环境变量决定（`config.py`）：

```bash
export VIDEO_OPS_SCRIPT_PRODUCER=claude-cli   # openai / codex-cli / …
```

加自己的引擎：在 `adapters/` 新建一个类实现 `produce`，返回同一个 `ProducedPlan`，再在按 `VIDEO_OPS_SCRIPT_PRODUCER` 装配实现的地方登记一个新名字。**换引擎不会动到视频、发布、数据和血缘**——这正是合同的意义。

### 2. 接自己的发布平台

合同是 6 个方法（`domain/ports.py` 的 `PlatformAdapter`）：

| 方法 | 干什么 |
|---|---|
| `capabilities()` | 声明这个平台支持哪些能力 |
| `inspect_account(connector_ref)` | 校验账号 / 频道 |
| `publish(request)` | 上传或排期，返回平台编号和链接 |
| `get_publication(external_id)` | 反查一条发布的状态 |
| `collect_metrics(...)` | 拉播放、点赞、评论数等指标 |
| `collect_comments(...)` | 拉评论正文 + 分页游标 |

两份现成参照：`mock_platform.py`（零密钥，覆盖成功 / 失败 / 延迟 / 数据 / 评论）和 `youtube.py`（真实）。它们通过同一份合同测试；新平台照着补一份测试，就能保证行为一致。

平台专属字段放在 request 和原始响应里；核心只存账号引用、发布状态、平台编号、链接和最小通用指标——**不同平台的字段差异不会渗进业务核心**。

### 3. 接外部成片模块 / 数据表同步

- `ProductionProvider`（`ports.py`）：外部剪辑 / 生成工具只能返回「任务」或「成片」，四个方法 `capabilities / submit / get_task / collect_media`。
- `WorkspaceSync`（`ports.py`）：飞书这类表格只做「行 ↔ 记录」映射，不持有业务状态，三个方法 `preview_import / import_records / export_snapshot`。没有平台时，产品退化为 JSON / CSV 导入导出，主链路不受影响。

## 改前端 / 共享 UI

- 页面在 `src/web/`：节点画布 `canvas/`、节点面板 `canvas/panels/`、弹窗 `dialogs/`。
- 通用组件（AppShell、DataTable、Badge…）以 `vendor/*.tgz` 随仓库分发，直接使用即可。这些共享包的源码维护在另一个 monorepo，本仓库只携带打好的包，`npm install` 就能装上，无需仓库外的任何目录。
- 设计规范（配色、字号、圆角、画布手感）见本仓库 `design.md` 与 `design-v7-canvas.md` / `design-v8-canvas-feel.md`。

## 术语（改文案时保持一致）

脚本（不叫候选 / 产物）· 视频 · 镜头（不叫分镜）· 台词（不叫口播）· 字幕（不叫屏幕字）· 这批视频（不叫批次）· 数据（不叫回流）。内部编号（`VID-…`）不出现在界面上。

## 边界 / 别踩的线

- **核心不认平台**：`domain/`、`application/` 不 import 任何模型商或平台 SDK；这些只在 `adapters/` 出现。
- **密钥只走环境变量或本地加密库**，绝不进 Markdown、代码、日志、样例或 git。真实数据、token、大媒体只在 `.local/`、`output/`，都已在 `.gitignore` 里。
- **没有真实证据不标「已打通」**：一个平台 / 引擎只有真跑通并留证据才算数，否则「连接与配置」页显示「未验证」。
- **改完过门禁**：`uv run video-ops check`（后端测试 + 前端测试 + 生产构建）必须全绿，绝不 `--no-verify`。

## 关于这个系列

这是「50 天 50 个真实行业 AI 应用」挑战的 Day 01。每个应用独立成仓、可独立运行、各自开源——用真实、可验证、可下载的产品，对抗只在录屏里能跑的假 demo。
