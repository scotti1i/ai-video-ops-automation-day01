# Evidence · AI 视频运营流水线

## 真实验证记录

| 字段 | 内容 |
|---|---|
| 日期 | 2026-07-15 |
| 输入来源类型 | 本机私有课程逐字稿、对应成片、既有 YouTube 发布记录；公开证据只留哈希和聚合字段 |
| 运行方式 | uploader 隔离 Python 环境调用 Day 01 桥接器；真实读链通过 Day 1 HTTP 合同写入本地忽略数据库；写链执行频道护栏、`dry-run`、`private` 上传和独立反查 |
| 实际输出 | [`真实 YouTube 读链`](2026-07-14-youtube-read-validation.md)；[`真实 YouTube 写链`](2026-07-15-youtube-write-validation.md)；[`真实 YouTube 评论链`](2026-07-15-youtube-comment-validation.md)；[`真实模型链`](2026-07-14-model-validation.md)；[`带货脚本候选与质量门`](2026-07-15-commerce-script-upgrade.md)；[`需求证据矩阵`](2026-07-15-requirement-matrix.md)；[`完整验收审计`](2026-07-15-acceptance-audit.md)；[`最终 UI 验收`](2026-07-15-ui-validation.md)；原始响应和真实路径只在 `.local/` |
| 人工核对 | 已完成文件哈希、平台记录、产品内对象链、新 `private` 上传状态、真实评论归属和私密视频空结果核对 |
| 已知偏差 | 上传 token 仍不含评论权限；评论读取使用只含 `youtube.force-ssl` 的隔离 token，不会改写原上传 token |
| 真实写入 | [`2026-07-15-youtube-write-validation.md`](2026-07-15-youtube-write-validation.md)：一次 `private` 上传，平台编号、链接、隐私与处理状态均已回执并反查 |

## 证据清单

- [x] 零密钥 demo 输出与干净目录复现
- [x] 脱敏真实输入输出
- [x] 失败或边界记录
- [x] 如果有 UI：1440 / 390 真实页面截图
- [ ] 如果有视频：最终文件 QA，而不是预览

截图和小型脱敏结果可以提交。原始客户数据、账号、cookie、密钥和大体积媒体不提交。

## 最终 UI 截图

- [`批次工作台折叠态 · 1440×960`](ui/batch-workbench-1440.png)
- [`批次工作台展开态 · 1440×960`](ui/batch-workbench-expanded-1440.png)
- [`手机批次工作台折叠态 · 390×844`](ui/batch-workbench-390.png)
- [`手机批次工作台展开态 · 390×844`](ui/batch-workbench-expanded-390.png)
- [`视频工作台 · 1440×960`](demo-desktop-1440x960.png)
- [`视频详情 · 1440×960`](demo-desktop-detail-1440x960.png)
- [`账号 · 1440×960`](demo-desktop-accounts-1440x960.png)
- [`商品 · 1440×960`](demo-desktop-products-1440x960.png)
- [`发布日历 · 1440×960`](demo-desktop-calendar-1440x960.png)
- [`手机工作台 · 390×844`](demo-mobile-390x844.png)
- [`手机视频详情 · 390×844`](demo-mobile-detail-390x844.png)
- [`手机账号 · 390×844`](demo-mobile-accounts-390x844.png)
- [`手机商品 · 390×844`](demo-mobile-products-390x844.png)
- [`手机发布日历 · 390×844`](demo-mobile-calendar-390x844.png)

批次工作台四张为 2026-07-15 最新信息架构；其余十张保留账号、商品、日历与详情页证据。图片均先落盘再复核。

## 脚本候选与质量门截图

- [`桌面候选清单`](2026-07-15-script-candidates-desktop.jpg)
- [`候选完整口播与分镜`](2026-07-15-script-candidate-expanded.jpg)
- [`候选商品事实与结构检查`](2026-07-15-script-candidate-checks.jpg)
- [`正式视频风险面板`](2026-07-15-script-risk-desktop.jpg)
- [`手机候选清单`](2026-07-15-script-candidates-mobile.jpg)
- [`手机高密度工作台`](2026-07-15-script-workbench-mobile.jpg)
- [`手机正式视频风险`](2026-07-15-script-risk-mobile.jpg)
