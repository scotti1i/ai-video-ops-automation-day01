# 上游调查 · AI 视频运营流水线

## 真实需求切片

每天生产数十条视频的运营团队，当前在 AI 对话、飞书、群聊、NAS、本地文件、手机和第三方发布工具之间搬运同一条视频。Day 01 不重写这些工具，而是建立一个以 `Video` 为核心的业务记录，让脚本、分镜、成片、发布、数据和裂变不再断链。

## 候选

| 候选 | 来源 | License / 边界 | 已验证能力 | 本项目使用方式 | 不直接使用的原因 |
|---|---|---|---|---|---|
| Week 2 AI 视频工厂 | 既有内容管线的视频工厂模块 | 按模块核验 | 脚本、分镜 prompt、视频 provider、轮询、飞书写回 | 借鉴 provider 合同；必要时通过 CLI 或小型适配器调用 | 状态和字段绑定课程 Base，脚本模板不是通用产品核心 |
| Week 6 自动剪辑 | 既有内容管线的自动剪辑模块 | 按模块核验 | 接受外部脚本、`storyboard.json` 中枢、配音、成片、剪映草稿 | 作为可选制作模块，输入脚本/分镜/素材，接收成片 | 不把剪辑场景和产品主状态机耦合 |
| 口播剪辑工具 | 私有本地工具，由运行时适配器发现 | private-local；不打包源码 | 转录、语义剪辑、字幕、横竖屏、QA、交付 | 真实模式通过现有 skill / CLI 调用 | 只覆盖口播，且含私有资产和用户未提交工作 |
| YouTube uploader | 私有本地 uploader，由 `YOUTUBE_UPLOAD_DIR` 定位 | private-local；token 和 client secret 永不复制 | 单条上传、封面、元数据、定时发布、频道校验 | 复用已验证上传路径；新写通用账号适配器和数据回流 | 当前脚本绑定本机 token、频道默认值，尚无产品化多账号与 analytics 读取 |
| 飞星开放平台 | 用户提供的《飞星开放平台 API 接口》文档（私有，不外链） | 仅作接口形状参考；Day 01 不配置、不调用 | 文档覆盖账号授权/查询、素材上传、创建发布任务、查询任务、社媒指标和评论列表 | 校准 `PlatformAdapter` 的能力边界，不成为运行依赖 | 用户明确不使用该 CLI；避免把单一供应商字段写进核心 |
| 飞书 | PATH 中的 `lark-cli` | 外部 CLI / 按实际依赖声明 | Base 记录 upsert、导入导出、既有授权 | 只做可替换同步适配器 | 飞书不能继续充当产品主数据源 |
| 共享 UI 基座 | 根仓库 `packages/` | 根仓库已锁版和测试 | AppShell、DataTable、文件输入、筛选、状态、AI 运行、双视口门禁 | 直接消费 Level 0–2 组件 | 视频、账号、发布和血缘属于 Day 01 domain，不能抽成通用组件 |
| dnd-kit React | [`clauderic/dnd-kit`](https://github.com/clauderic/dnd-kit)，精确锁定 `@dnd-kit/react@0.5.0`、`@dnd-kit/dom@0.5.0`、`@dnd-kit/helpers@0.5.0` | MIT；新 API 为 0.x，精确锁版 | React 19、Pointer/Keyboard sensor、独立拖柄、ARIA 与 live region；2026-07 仍维护 | 只在“创作设定”的叙事中段封装一个 `SortableNarrativeList`；React 负责排序，DOM 插件负责中文播报，helpers 负责纯数组换序 | 不上提共享 UI；语言、语气、时长没有顺序含义，不使用拖拽 |
| Pragmatic Drag and Drop | [`atlassian/pragmatic-drag-and-drop`](https://github.com/atlassian/pragmatic-drag-and-drop) | Apache-2.0 | 轻量、框架无关、触控成熟 | 仅作比较 | 官方核心不自动提供键盘和读屏控制，本场景会增加自建无障碍工作 |
| React Aria DnD / hello-pangea | Adobe / hello-pangea 官方仓库 | Apache-2.0 | 前者无障碍完整；后者列表交互成熟且支持 React 19 | 仅作回退比较 | 前者会引入第二套 collection/UI 语义；后者依赖和体积更大，当前维护节奏较慢 |
| 最简自有核心 | 本项目 | MIT | 完全可测试 | 新写 Video、ContextSnapshot、Artifact、Publication、MetricSnapshot、Lineage 和适配器合同 | 这是产品资产，现有上游没有覆盖 |

## 决定

- **自己拥有**：视频领域模型、生命周期、Context 快照、产物版本、多账号发布关系、数据归一、血缘、裂变和产品页面。
- **直接复用**：根共享 UI、平台官方 SDK、数据库、对象存储、媒体工具、`lark-cli`。
- **局部复用**：精确锁定 dnd-kit 三个直接依赖，只负责叙事中段排序与基础无障碍事件；移动按钮、中文文案和业务快照由 Day 01 自己负责。
- **通过适配器调用**：Week 2、Week 6、口播剪辑工具、YouTube uploader。
- **仅作接口参考**：飞星开放平台；不调用飞星 / TikTok CLI。
- **不使用**：整仓复制、把 Week 2 固定 Base schema 当产品 schema、把聊天或报表当首页、在 Day 01 自研剪辑器和视频模型。

## 适配器边界

每个外部模块只允许通过以下合同影响核心：

```text
ScriptProducer      ContextSnapshot → ScriptArtifact + StoryboardArtifact
ProductionProvider  Script/Storyboard/Assets → ExternalTask | MediaArtifact
PlatformAdapter     capabilities / inspectAccount / publish / getPublication
                    / collectMetrics / collectComments
WorkspaceSync       Video domain records ↔ external table rows
```

外部工具返回的状态先原样保存，再归一为本项目状态。任何外部工具都不能直接修改视频血缘或跨模块产物。

Day 01 只有两个实现：

1. `YouTubePlatformAdapter`：真实频道校验、上传/排期、发布结果、基础指标和评论回流；上传底层复用现有 uploader，基础指标与评论使用 YouTube Data API。
2. `MockPlatformAdapter`：零密钥覆盖相同合同，包括成功、失败、任务延迟、数据快照和评论。

平台专属字段放在适配器请求和原始响应中；核心只保存账号引用、发布状态、平台内容编号、链接、原始证据引用和最小通用指标。Day 01 的 YouTube 真实回流以播放、点赞、评论数和评论内容为准；留存、观看时长等深层 Analytics 不是首版前置。成交等 YouTube 不提供的数据可以由未来连接器或结构化导入补充，Day 01 不伪造真实成交回流。

## 锁定、退出与发布

- 既有内容管线只作开发参考；需要提取代码时逐文件核验 License 和测试。
- 私有本地工具只在真实模式通过进程调用，公开下载包提供同合同的 mock / import 适配器。
- YouTube 连接器必须支持替换；连接器不可用时，视频、脚本、分镜、成片、历史导入和 demo 仍可运行。
- 所有 token、cookie、账号 ID、真实客户数据和大媒体只放 `.local/`、环境变量或加密库，不进入 git。
- 飞书失效时退化为 CSV/JSON 导入导出，不影响产品主记录。
