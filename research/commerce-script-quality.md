# 带货短视频脚本质量门

> 日期：2026-07-15  
> 用途：判断脚本是否合规、可拍、值得发布测试；不预测爆款，不替代真实转化数据。

## 官方依据

TikTok 的公开创意实践反复强调同一条主线：开头快速建立注意力，尽早让商品与价值出现，用画面演示或证明，而不是只口头形容，最后给出明确行动语，并持续测试多个差异创意。TikTok Shop 的高质量内容标准还要求真实使用场景和实用商品信息；广告与商业内容必须满足格式、声明和披露要求。

- [TikTok Creative best practices](https://ads.tiktok.com/help/article/creative-best-practices?lang=en)
- [TikTok Shop Creating High-Quality E-commerce Videos](https://seller-us.tiktok.com/university/essay?knowledge_id=2816204956665642)
- [TikTok Shop Video Assistant](https://seller-us.tiktok.com/university/essay?default_language=en&knowledge_id=1144590806566702)
- [TikTok Shop Shoppable Video Hub](https://seller-us.tiktok.com/university/essay?default_language=en&knowledge_id=6160394680010539)
- [TikTok Ad format and functionality policy](https://ads.tiktok.com/help/article/tiktok-ads-policy-ad-format-and-functionality?lang=en)
- [FTC Disclosures 101 for Social Media Influencers](https://www.ftc.gov/business-guidance/resources/disclosures-101-social-media-influencers)

## 先过硬门

任一项失败，候选标记为“需修改”：

1. 商品名称、功能、价格、优惠、效果和评价均可追溯到当前商品资料；
2. 没有减肥、治疗、保证效果、虚构销量、虚构评价等未提供声明；
3. 前 3 秒有钩子，前 6 秒让用户知道本条价值；
4. 全片只主打一个购买理由，镜头能演示或验证它；
5. 完整口播与逐镜 voiceover 一致，镜头总时长符合目标；
6. 有自然、可执行且不虚构优惠的 CTA；
7. 商业合作和 AI 生成内容在适用时保留平台披露位置。

全片平均词速合格还不够：每个镜头的口播都必须能在自己的时长内说完。英文普通镜头按不超过 180 WPM 检查，短钩子最多放宽到 210 WPM；画面、口播和屏幕字必须在同一镜表达同一个商品动作。

## 结构检查 100 分

这是本产品用于排序与解释的内部启发式规则，不是 TikTok 或 FTC 的官方分数，也不是转化预测。

| 维度 | 分值 | 检查重点 |
|---|---:|---|
| 商品声明 | 10 | 只使用当前商品资料允许的声明；自由文本必须保守待核对 |
| 前 3 秒钩子 | 15 | 首镜具体，不是空泛提问或内部提示词 |
| 前 6 秒价值 | 10 | 前两镜说清这条对用户有什么用 |
| 单一购买理由 | 10 | 全片只验证一个商品事实，不把多个卖点混成一条 |
| 画面证明 | 15 | 证明镜头有具体动作，画面能核对口播 |
| 真实异议 | 10 | 提出一个购买顾虑并给出有边界的回答 |
| 目标时长 | 10 | 分镜合计与目标相差不超过 2 秒 |
| 脚本一致 | 5 | 完整口播与逐镜 voiceover 一致 |
| 行动语 | 5 | 下一步清楚，未提供优惠时不编折扣和倒计时 |
| 口播完整 | 10 | 总词速和每镜词速均能在对应时长内说完 |

分数只用于排序与解释，不用于绕过硬门。只有 `10 / 10` 项全部通过才显示“结构通过，值得发布测试”；任意一项失败，无论总分多高都显示“需修改”。

## 声明审计边界

生成器返回的 `claims` 只是自报元数据，不能证明脚本没有偷偷加入其他商品事实。零密钥 Demo 的封闭模板只使用枚举过的商品机制，因此可以自动检查；模型输出、导入稿和人工编辑属于自由文本，在独立声明抽取与来源核对器尚未接入前必须保守标记为“需核对”。用户可以明确继续推进，但该风险必须跟随正式脚本版本保存，不能在进入成片后消失。

## 只有真实数据能回答的事

- 2 秒、6 秒留存与完播：钩子和节奏是否有效；
- 商品点击率：购买理由与 CTA 是否有效；
- 订单、成交额、退款：商品页、价格、信任和真实购买质量；
- 评论：异议、误解和下一轮 Context。

产品可以自动完成结构检查，也可以根据这些数据排序和裂变；但没有上述数据时，不能把候选命名为“高转化脚本”。
