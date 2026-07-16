# 可组合创作设定验收 · 2026-07-15

## 目标

在“开始一批视频”里增加语言、表达方式、时长和可排序叙事结构，但不把首屏变成提示词编辑器，也不允许只改变界面、生成结果不变。

## 上游调研与选择

| 方案 | 实践边界 | 本项目结论 |
|---|---|---|
| [dnd-kit](https://github.com/clauderic/dnd-kit) | React 当前 API 提供 Pointer / Keyboard sensor、独立拖柄、可配置 ARIA 播报；MIT | 采用。精确锁定 `@dnd-kit/react`、`@dnd-kit/dom`、`@dnd-kit/helpers` `0.5.0` |
| [Atlassian Pragmatic Drag and Drop](https://github.com/atlassian/pragmatic-drag-and-drop) | 核心轻量、框架无关，键盘与读屏需要应用层组合 | 不采用。本场景会多写一套无障碍状态机 |
| [React Spectrum DnD](https://react-spectrum.adobe.com/dnd.html) | collection 与无障碍能力完整 | 不采用。会为 3 个排序项引入第二套集合与控件语义 |
| [BlockNote](https://github.com/TypeCellOS/BlockNote) | 成熟块编辑器，可拖动、增删、富文本 | 不采用。用户需要叙事顺序控制，不需要一套文档编辑器 |

最终只让真正有顺序含义的中段可排序：

```text
开场钩子 · 价值承诺（固定）
  ↕ 使用场景 / 痛点
  ↕ 产品证明
  ↕ 异议处理
行动引导（固定）
```

语言、表达方式和时长是批次参数，不做无意义拖拽。首版也不允许任意增删结构块，避免用户误以为系统已经能安全处理任意脚本方法论。

## 真实实现链路

1. 前端把 `language / writing_tone / duration_seconds / narrative_blocks` 作为结构化 `script_settings` 提交。
2. 后端先解析显式设定；语言或时长为“跟随 Context”时，才从本批 Context 推断。
3. 解析后的 `ScriptSettings` 保存为批次快照，而不是只拼进一段 Prompt。
4. 初次生成、单条重写、人工编辑后的质量重检和选稿进入正式视频，均读取同一份快照。
5. SQLite 自动补 `script_settings_json` 可空列；旧批次没有快照时继续走历史 Context，不要求重建数据库。

## 真实页面验收

桌面端以以下输入生成 1 条候选：

- 商品：便携榨汁杯；
- Context：`为每天早上赶时间的上班族推广便携榨汁杯，重点讲随行杯直接饮用，目标 20 秒，美区英文。`；
- 语言：美式英文；
- 表达方式：直接利落；
- 时长：跟随 Context；
- 结构：产品证明上移到使用场景 / 痛点之前。

提交后的批次依据显示 `美式英文 · 直接利落 · 20 秒 · 已调整结构`。生成结果为 6 个分镜、22 秒，落在目标时长 ±2 秒内；逐镜角色顺序为：

```text
hook → value → proof → problem → objection → cta
```

这证明不是只移动卡片：自动时长解析、批次持久化和生成分镜都消费了同一设置。

移动端 390×844 保留固定开场/收尾、44px 拖柄和 44px 上移/下移按钮；无需 hover 或长按。真实浏览器测得 document 为 390/390、dialog 为 374/374、内部 scroller 为 374/374，没有被 `overflow-hidden` 掩住的横向溢出。键盘 Space + 方向键和手机移动按钮已经过真实浏览器操作；鼠标路径复用 dnd-kit 的 Pointer sensor，并由同一个纯排序回调落库。排序结果通过中文 live region 播报。

## 自动检查

- `uv run video-ops check`：Ruff 通过；Python `139 passed`；前端 `54 passed`；TypeScript 与 Vite build 通过。
- 组合回归：2 种语言 × 3 种时长 × 4 种表达方式 × 10 个脚本角度，共 240 个 mock 产物，全部满足结构门和目标时长误差。
- `uv run python -m fifty_harness check`：项目结构检查通过。
- 所有 Python / TypeScript / TSX 文件均小于 800 行。
- Vite 仍提示现有主包大于 500k；它不影响本功能正确性，后续应在独立性能里程碑处理代码分包。

## 截图

- [桌面折叠态](2026-07-15-script-controls-desktop-collapsed.png)
- [桌面展开态](2026-07-15-script-controls-desktop-expanded.png)
- [桌面已配置](2026-07-15-script-controls-desktop-configured.png)
- [真实生成结果](2026-07-15-script-controls-generated-result.png)
- [手机折叠态](2026-07-15-script-controls-mobile-collapsed.png)
- [手机展开态](2026-07-15-script-controls-mobile-expanded.png)
- [手机叙事排序区](2026-07-15-script-controls-mobile-structure.png)

## 当前边界

- 参考视频仍只保存来源，没有解析其内容；界面已经明确提示。
- “结构通过”只表示脚本满足可发布测试门，不代表高转化；真实转化仍由发布后的点击、订单和成交数据决定。
- 当前 0.5.x 上游仍处于 0.x；已精确锁版并把依赖封装在 Day 01 局部组件，未来升级先跑交互与无障碍回归。
- 本轮没有做浏览器级鼠标拖动轨迹回放或 VoiceOver 实机听测；鼠标拖柄、中文 ARIA 语义和 live region 已由组件测试覆盖，键盘与按钮路径已在真实浏览器验证。
