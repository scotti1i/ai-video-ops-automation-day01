# YouTube 私密写入验证 · 2026-07-15

## 授权与边界

Scott 明确授权使用既有本地 uploader 上传一条 `private` 测试视频，并同意补充独立的评论只读权限。本次不调用 TikTok、抖音或飞星，不公开测试视频，也不修改既有上传 token 的授权范围。

平台视频编号、私密链接、频道编号和原始响应只保存在应用忽略目录；公开证据只记录可复核的状态、文件摘要和本地回执摘要。

## 上传输入

- 2 秒合成验收片，1280×720、H.264 视频和 AAC 静音音轨；
- 文件大小 7,419 字节，SHA-256 `a7c86953985428e6f19f693dcb18abfeee9ae46eccd27ff756c02b88a622ae41`；
- 隐私级别固定为 `private`，未设置 `publishAt`；
- 明确声明 `containsSyntheticMedia=true`；
- 上传前先执行频道护栏与 `dry-run`，只匹配到一个预期频道。

## 平台结果

2026-07-15 02:02（Asia/Shanghai）通过既有 uploader 执行一次 `videos.insert`，随后独立调用 `videos.list` 反查，而不是只相信上传命令输出：

| 字段 | 平台返回 |
|---|---|
| 平台视频编号与链接 | 已返回并保存到本机私有回执 |
| `privacyStatus` | `private` |
| `uploadStatus` | `processed` |
| `processingStatus` | `succeeded` |
| `failureReason` | 空 |
| `publishAt` | 空，不会自动公开 |

本机回执权限为 `0600`，SHA-256 为 `991cf8ceecc3f6efef8953de8988c8513ec053d62de04d25e9e74e0c42558ded`。Day 1 的 YouTube 适配器调用同一个 `publish_single.py` 入口，并已通过频道检查、命令构造、回执解析、未知结果保护和同合同回归测试。

## Day 1 产品内回写

随后以 `live` 模式启动 Day 1 API，加载同一个 YouTube 适配器和原有真实验证库，通过产品自己的 HTTP 合同完成：

1. 把新平台编号和链接关联为现有视频下的独立 `Publication`；
2. 保持账号、视频和原有历史发布记录不变，没有覆盖旧数据；
3. 连续同步两次，保存两个带独立获取时间的 `MetricSnapshot`；
4. 两次平台原始统计均为播放 0、点赞 0、评论计数 0；
5. 评论权限完成前明确保存“缺少 `youtube.force-ssl`”警告，没有把空列表冒充成已读取评论。

因此本次不仅验证了 uploader 本身，还验证了新平台回执能进入 Day 1 的视频—账号—发布—数据对象链。原始平台编号、链接、数据库和桥接响应仍只在 `.local/`。

## 评论只读权限

写链完成当时，评论读取仍等待 Scott 手工确认 Google 安全提示；这是当次验收的真实历史状态。随后已完成只含 `youtube.force-ssl` 的独立 OAuth，并通过真实评论正文与本次私密视频的平台可核验空结果补齐证据。详见 [`YouTube 评论回流验证`](2026-07-15-youtube-comment-validation.md)。

## 结论

- 能证明：真实频道护栏、真实私密上传、平台编号和链接回执、隐私与处理状态反查，以及 Day 1 产品内发布记录和两个数据快照均已通过。
- 不能证明：私密视频已公开；本次明确不公开。
- 当次写链结束时尚待证明的评论权限，已在后续独立评论验证中通过；原上传 token 未被修改。
