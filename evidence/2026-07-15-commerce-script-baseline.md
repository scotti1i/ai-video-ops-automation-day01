# 带货脚本升级前基线

> 记录时间：2026-07-15  
> 固定输入：商品“便携榨汁杯”；卖点“随行杯直接饮用、杯体可拆洗、USB-C 充电”；主 Context“给独居上班族讲清早晨快速做果昔”；参考链接仅作可追溯引用。  
> 目的：保存改造前的真实输出，避免把“API 返回成功”误写成“脚本质量通过”。

## 当前结果

前三个所谓角度的标题分别是：

1. `别再被给独居上班族讲清早晨快速做果昔卡住了`
2. `先看给独居上班族讲清早晨快速做果昔做到后的结果`
3. `现场演示：给独居上班族讲清早晨快速做果昔`

三条脚本骨架完全相同，第一条口播直接泄漏内部生成指令：

```text
你是不是也遇到过：【痛点】从一个具体失败或麻烦开场，再给解决路径。围绕“给独居上班族讲清早晨快速做果昔”写成可拍摄脚本。？
先别急着下结论。我们把“商品：便携榨汁杯”拆成三个动作：先说明具体问题，再展示过程，最后给出可以验证的结果。
如果你正在做同类内容，先收藏这条，再按同一个结构测试三个不同开头。
```

分镜也固定为 `3 + 8 + 6 = 17 秒`，内容是“先看问题 / 现场拆解 / 继续裂变”，没有具体商品演示、购买理由、画面证据或商品行动语。

## 结论

- 当前输出只是合法的 `script + shots` 数据，不是带货脚本；
- 角度差异只存在于被念出来的 instruction，不存在于真实创意；
- 商品卖点没有进入口播和证明镜头；
- 没有结构质量门，测试只验证字符串不同；
- 批量生成会把这些结果直接创建为正式视频，污染工作台。

升级后的同输入结果必须与本文件做逐项对比，并且只能标记为“结构通过、值得测试”，不能在没有发布数据时声称“高转化”。

## 真实模型改造前结果

通过现有 OpenAI 兼容适配器调用 `gemini-2.5-flash`，模型成功返回英文脚本与 8 镜分镜；密钥和地址只从本机加密库注入，未落盘。完整口播为：

```text
Morning rush got you stressed? No time? No problem! Say hello to your new morning essential: this portable blender cup! Just add your favorite ingredients, blend in seconds, and you're good to go! Drink right from the cup, then effortlessly detach for a quick, easy clean. And charging is a breeze with USB-C, just like your other devices. Fuel your busy day, grab yours from the link below!
```

这证明真实通道可用，但仍未达到本轮质量线：

- 8 镜总时长 23 秒，不符合输入的 25 秒；
- 同时讲“直接饮用、可拆洗、USB-C”三个卖点，没有单一购买理由；
- `blend in seconds`、`effortlessly`、`quick, easy clean` 超出已知商品事实；
- 展示了功能动作，但没有围绕一个主卖点形成证明闭环；
- CTA 写成 `link below`，不是当前场景可执行的商品卡动作；
- API 成功、英文自然和镜头完整，仍然不能等同于“值得投放测试”。
