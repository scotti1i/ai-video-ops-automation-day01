# Day 01 UI 验收 · 2026-07-15

## 结论

使用当前零密钥 Demo 在真实应用内浏览器逐页操作。桌面和手机都覆盖工作台、视频详情、账号、商品、发布日历；没有浏览器错误，两个视口均无横向溢出。

## 当前页面事实

- 顶部明确显示“样例模式”和 `1/4 账号可用`，没有把需要授权的 YouTube 账号伪装成可用连接。
- Demo 初始返回 12 条视频；真实页面闭环新增父视频和裂变子视频后返回 14 条，编号、账号、阶段、排期、表现和下一步仍在同一工作台完成操作。
- “导入清单”是一级入口；Context、脚本分镜、成片、发布、数据和血缘仍围绕同一条视频记录展开。
- 高表现视频的下一步直接显示“裂变”；普通已发布视频仍显示“同步数据”。普通编号入口默认打开 Context，阶段动作会直达对应页签。
- 发布页和日历只显示中文业务状态，没有暴露 `draft`、`succeeded` 等内部枚举。

## 真实页面整链

在临时零密钥工作区从真实 UI 建立 `VID-013`，完成 Context 输入和 mock 脚本/分镜生成；随后通过本地上传合同登记 1 秒验收成片，再回到 UI 选择两个 mock 账号发布。一条成功、一条按样例故障失败，成功记录完成两次同步并获得 2 个指标时间点和 2 条评论；选择评论后创建 `VID-014`，父详情能看到子视频与本轮变化。整个过程没有调用 YouTube、TikTok、飞星或其他真实平台。

## 双视口验证

| 项目 | 结果 |
|---|---|
| 桌面视口 | 1440×960；五个页面逐页截图；`scrollWidth = clientWidth = 1440` |
| 手机视口 | 390×844；五个页面逐页截图；`scrollWidth = clientWidth = 390` |
| 浏览器错误日志 | 0 条 |
| 键盘与焦点 | 全局搜索打开后输入框自动聚焦；`Escape` 关闭并把焦点还给触发按钮 |
| 下一步路由 | 高表现视频可从工作台一键进入裂变；阶段动作直达对应详情页签 |

## 截图

| 页面 | 文件 | 尺寸 |
|---|---|---|
| 视频工作台 | [`demo-desktop-1440x960.png`](demo-desktop-1440x960.png) | 1440×960 |
| 视频详情 | [`demo-desktop-detail-1440x960.png`](demo-desktop-detail-1440x960.png) | 1440×960 |
| 账号 | [`demo-desktop-accounts-1440x960.png`](demo-desktop-accounts-1440x960.png) | 1440×960 |
| 商品 | [`demo-desktop-products-1440x960.png`](demo-desktop-products-1440x960.png) | 1440×960 |
| 发布日历 | [`demo-desktop-calendar-1440x960.png`](demo-desktop-calendar-1440x960.png) | 1440×960 |
| 手机工作台 | [`demo-mobile-390x844.png`](demo-mobile-390x844.png) | 390×844 |
| 手机视频详情 | [`demo-mobile-detail-390x844.png`](demo-mobile-detail-390x844.png) | 390×844 |
| 手机账号 | [`demo-mobile-accounts-390x844.png`](demo-mobile-accounts-390x844.png) | 390×844 |
| 手机商品 | [`demo-mobile-products-390x844.png`](demo-mobile-products-390x844.png) | 390×844 |
| 手机发布日历 | [`demo-mobile-calendar-390x844.png`](demo-mobile-calendar-390x844.png) | 390×844 |

浏览器截图接口返回 JPEG 字节。证据先保存，再统一转为真实 PNG；`file` 和图像元数据均确认格式与尺寸，转换后的十张图片又做了视觉复核。

## 自动交互门禁

- 前端交互测试：27/27 通过，含排序、血缘、重试、空状态、缺成片、版本恢复和评论裂变。
- TypeScript：通过。
- 生产构建：通过；仅保留 Vite 主包超过 500 kB 的非阻塞提示。

没有在 UI 验收中执行真实上传、OAuth 或平台写入。
