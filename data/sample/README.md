# 零密钥样例数据

`workspace-seed.json` 是完全合成、但按真实运营字段组织的工作空间（种子契约 v3）。它包含：

- 2 个账号分组、4 个账号，覆盖 YouTube 形状和通用模拟平台；
- 3 个可选商品；
- 12 条视频，覆盖待脚本、待成片、待发布、已排期、发布失败、已发布；
- 同一视频投两个账号后的独立发布记录；
- 两个时间点的指标、评论、父子血缘和批量裂变记录；
- 带货与非带货视频。

## 种子契约 v3

- 根部 `"version": 3` 声明契约版本。
- video 条目可选 `"script"`（`content` 为完整口播多行字符串，`note` 为版本备注）与
  `"storyboard"`（`shots` 为完整分镜数组，字段同 `StoryboardShot`）。两者都是运营手写
  的真实投放水平内容：17–30 秒、3–6 镜、每镜带画面/口播/屏幕字/时长与
  hook/problem/value/proof/objection/cta 角色标注。
- 口播是真人对观众说的话；导演指令只出现在 `visual`；屏幕字是 ≤12 字的点题短语。
- `needs_script` 状态的视频刻意不带 script/storyboard，保持“脚本待生成”空态真实。
- batches 条目可选 `"note"` 记录本批的运营背景。
- 字段缺席时回退到现有 MockScriptProducer 生成路径。

这里所有平台链接、播放、成交和评论均为样例，不代表真实业务成绩。真实验证只进入
`evidence/`，账号、token、cookie 和原始客户文件不会进入仓库。

`video-brief.txt` 与 `existing-script.md` 用于验证“一段自然语言 + 两个附件”以及导入
现成脚本的入口。
