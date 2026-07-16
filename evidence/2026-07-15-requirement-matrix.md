# Day 01 需求—证据矩阵 · 2026-07-15

## 当前判定

真实验证清单已全部完成，状态进入 `verified`。本地产品、零密钥闭环、真实 `private` YouTube 写链、独立评论授权、真实评论正文和平台可核验空结果均有脱敏证据。

## 核心合同

| 需求 | 实现证据 | 自动验证 | 页面验证 | 判定 |
|---|---|---|---|---|
| 视频是最小单元，账号是管理维度 | `Video` 聚合 Context、产物、发布、数据和血缘；平台只在 `Account` | 领域与仓储测试 | 工作台、账号页 | 通过 |
| 一条视频投多个账号 | 独立 `Publication`、幂等键和平台结果 | 并发、隔离、重试测试 | `VID-013` 两账号一成一败 | 通过 |
| 脚本分镜可生成、导入、编辑、恢复 | 统一 artifact 版本合同 | 入口、导入、恢复测试 | 新建视频真实操作 | 通过 |
| 成片可上传或登记 | 安全上传目录与 `MediaArtifact` | 路径、取消清理、缺成片测试 | `VID-013` 成片就位 | 通过 |
| 数据与评论回到发布记录 | 时间序列快照和评论快照 | 回流与归属测试 | 两轮指标、两条评论 | 通过 |
| 高表现视频一键裂变 | 子视频继承来源并保存变化 | 评论选择、父子血缘测试 | `VID-013 → VID-014` | 通过 |
| 四类排序与失败恢复 | 播放、成交、发布时间、状态排序；重试/空状态 | 前端交互测试 | 工作台与详情 | 通过 |
| 平台能力可替换 | `PlatformAdapter` 运行时合同；YouTube 薄适配；mock 同合同 | YouTube 与 mock 合同测试 | 账号连接状态 | 通过 |
| 导入导出不依赖飞书 | 可回灌 JSON/CSV、预览、冲突和幂等 | 往返与公式注入测试 | 一级导入/导出入口 | 通过 |

## 边界与待办

| 项目 | 当前边界 | 状态 |
|---|---|---|
| YouTube 上传/排期 | 已完成频道护栏、`dry-run`、真实 `private` 上传、状态反查、Day 1 产品内关联和两次指标同步 | 通过 |
| YouTube 评论 | 只含 `youtube.force-ssl` 的隔离 token 已拉回真实评论；私密验收视频返回“评论已关闭”，两者均回写对应 Publication | 通过 |
| TikTok / 飞星 | 只保留统一平台接口，不调用 CLI/API | 明确不做 |
| 飞书 | Day 01 完成通用导入导出合同；后续适配 `lark-cli` | 后置 |
| 外部视频制作任务 | Day 01 接收已完成成片；只保留 `ProductionProvider` 合同，不编排外部任务 | 后置 |
| 操作记录 | 由持久化领域对象投影；不是事件溯源系统 | 明确边界 |
| 正式录屏与开源包 | `verified` 已通过；下一步依次进入 `recorded / released` | 未开始 |

## 证据入口

- 本地与净室门禁：[`2026-07-15-acceptance-audit.md`](2026-07-15-acceptance-audit.md)
- 双视口与真实页面整链：[`2026-07-15-ui-validation.md`](2026-07-15-ui-validation.md)
- 真实模型：[`2026-07-14-model-validation.md`](2026-07-14-model-validation.md)
- 真实 YouTube 只读链：[`2026-07-14-youtube-read-validation.md`](2026-07-14-youtube-read-validation.md)
- 真实 YouTube 写链：[`2026-07-15-youtube-write-validation.md`](2026-07-15-youtube-write-validation.md)
- 真实 YouTube 评论链：[`2026-07-15-youtube-comment-validation.md`](2026-07-15-youtube-comment-validation.md)
