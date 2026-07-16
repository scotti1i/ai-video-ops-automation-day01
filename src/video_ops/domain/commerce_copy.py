"""审稿通过的口播与标题：真人对观众说的话，导演指令一律留在分镜 visual 字段。

每条口播固定 hook/value/problem/proof/objection/cta 六句：
- 事实边界只用自然表达（"这条没测，先不吹"），不做念白式免责声明；
- 十个测试角度十种开头，同一商品下任意两条的前两句互不相同；
- 屏幕字与字段标签（"先看结果："）绝不进台词。
"""

from __future__ import annotations

# ============================================================
# 测试角度（与 batch_generation.ANGLES 的 label 一一对应）
# ============================================================

CURATED_ANGLES = (
    "痛点直击",
    "结果先看",
    "一镜实测",
    "双路对比",
    "购买标准",
    "使用场景",
    "购买问答",
    "连续证据",
    "核对清单",
    "异议先答",
)


def mechanism_key(point: str) -> str | None:
    """把商品卖点映射到已审稿的封闭机制；未知卖点返回 None。"""
    if "随行杯" in point or "直接饮用" in point:
        return "direct-drink"
    if "拆洗" in point or "可拆" in point:
        return "detachable-wash"
    if "USB-C" in point.upper() or "充电" in point:
        return "usb-c-charge"
    return None


def has_mechanism(point: str) -> bool:
    return mechanism_key(point) is not None


# ============================================================
# 同杯直饮 · 英文（美区）
# ============================================================

DIRECT_DRINK_EN = (
    (
        "Still pouring your smoothie into a second cup every morning?",
        "Here you blend and drink from the same cup.",
        "That extra cup is one more thing to wash before work.",
        "Blend it, pick up that same cup, and drink right there.",
        "Will it leak in your bag? That part I can't show yet.",
        "Check the product page and decide for yourself.",
    ),
    (
        "This smoothie never left the cup it was made in.",
        "You blend and sip from the same cup.",
        "Rewind one minute and this same cup was still blending.",
        "No pouring, no second cup, just the drink where you made it.",
        "Did I swap cups off camera? Watch the uncut version here.",
        "See the cup details on the product page.",
    ),
    (
        "One take, no cuts, watch the whole thing.",
        "Blending and drinking, all in the same cup.",
        "Cuts can hide a cup swap, so this clip keeps rolling.",
        "Ingredients in, blend, and the first sip from that same cup.",
        "Sped up or edited? No, this is the full take.",
        "Watch it again, then check the product page.",
    ),
    (
        "Two ways to make the same morning smoothie.",
        "On the right, you drink from the same cup.",
        "On the left, blend, pour into another cup, and wash both.",
        "On the right, blend and drink from the same cup, done.",
        "Is the right side faster? I'm only counting cups here.",
        "Compare both routes and pick your morning.",
    ),
    (
        "Before buying any blender cup, ask one question.",
        "Here, the answer is yes, same cup for both.",
        "Plenty of blenders still make you pour before you can drink.",
        "This one blends and then you sip from that same cup.",
        "Does that prove it's leakproof? No, that's a separate test.",
        "Take that question with you and compare listings.",
    ),
    (
        "Morning rush, keys in one hand, breakfast in the other.",
        "Breakfast is just the blender cup, sip and go.",
        "Mornings like this leave no time for a second cup.",
        "Blend at the counter, grab that same cup, head out.",
        "Commute safe in a bag? I haven't tested that here.",
        "See if that fits your morning routine.",
    ),
    (
        "The big question, can you actually drink from it?",
        "Yes, the blender cup is the drinking cup.",
        "Nobody wants to find out after buying that you can't.",
        "So here it is, blending done, drinking from that same cup.",
        "Anything this doesn't answer? Leaks and travel, still untested here.",
        "Check the listing if that answers your question.",
    ),
    (
        "Keep your eye on this cup the whole time.",
        "This same cup handles blending and drinking.",
        "The cup never leaves the frame, so nothing gets swapped.",
        "Ingredients go in and the sip comes from that same cup.",
        "Why film it this way? So you can trust the cup.",
        "Watch the full clip, then judge it yourself.",
    ),
    (
        "Three things to check before you trust this cup.",
        "First, the drink gets made in this same cup.",
        "Second, no pouring into a second bottle in the middle.",
        "Third, the first sip comes from that same cup on camera.",
        "Anything missing from the list? Leaks, that's a different video.",
        "Run the checklist yourself and then decide.",
    ),
    (
        "Let me say first what this video won't prove.",
        "It only shows you drinking from the same cup.",
        "No leak talk, no travel talk, none of that today.",
        "Just the blend and the sip from one same cup, uncut.",
        "So why watch? Because pouring into a second cup gets old.",
        "If that's enough, check the product page.",
    ),
)

# ============================================================
# 同杯直饮 · 中文
# ============================================================

DIRECT_DRINK_ZH = (
    (
        "打好果汁还要倒进另一个杯子，烦不烦？",
        "这个杯子打完直接喝，不用换杯。",
        "每天早上多洗一个杯子，那点时间就是这么没的。",
        "食材放进去，打完直接喝，中间不用换任何杯子。",
        "放包里会不会漏？这条没测，先不吹。",
        "觉得省事，就去商品页查看杯子细节。",
    ),
    (
        "我现在喝的这杯，就是刚才打果汁的那个杯子。",
        "打完不用倒杯，直接喝。",
        "往回倒几秒，它还在这个杯子里打着。",
        "从打完到入口，杯子没换过，就是同一个杯。",
        "中间有没有偷偷换杯？整段没剪，你自己看。",
        "再看一遍，顺手查看杯体设计。",
    ),
    (
        "一条镜头拍到底，中间不剪。",
        "就测一件事，打完能不能直接喝。",
        "剪辑可以换杯子，所以这条全程不切镜头。",
        "食材进去，打完，头一口就从这同一个杯子喝。",
        "有没有加速？没有，原速原样给你看。",
        "看完再去对比商品详情。",
    ),
    (
        "同一杯果汁，两种做法，差一个杯子。",
        "右边这种，打完原杯直接喝。",
        "左边先倒进随行杯，回头两个杯子都要洗。",
        "右边打完直接喝，台面上就一个杯子。",
        "右边有没有更快？这条只数杯子，不比速度。",
        "两条路线，自己对比再选择。",
    ),
    (
        "买这种杯子，我就看一条标准。",
        "打完的那个杯子，能不能直接喝。",
        "很多款打完还得倒一次，等于多买一个要洗的杯子。",
        "这款打完拿起来就喝，全程同一个杯。",
        "这能说明防漏吗？不能，防漏要另测。",
        "记住这条标准，再去对比其他款。",
    ),
    (
        "早上七点，出门前只有五分钟。",
        "果汁打完直接喝，杯子就是这一个。",
        "这种时候谁还有空再倒一次、再洗一个杯子。",
        "台边打完，拿着同一个杯子就出门。",
        "路上会不会洒？包里的事这条没拍。",
        "像不像你的早上？像就去查看详情。",
    ),
    (
        "买之前你最想确认的，是不是能直接喝？",
        "能，打完这杯直接喝，不用换杯。",
        "这种事最怕买回来才发现不行。",
        "所以拍给你看，打完当场从同一个杯子喝。",
        "那防漏和保温呢？这条不测，别急着下结论。",
        "答案够了，就去商品页查看。",
    ),
    (
        "盯住这个杯子，它全程不出画面。",
        "打果汁是它，直接喝还是它。",
        "杯子一出画就有换杯嫌疑，所以它全程在画面里。",
        "从放食材到喝头一口，同一个杯子看得清清楚楚。",
        "为什么这么较真？因为你隔着屏幕，只能信画面。",
        "完整看一遍，再判断值不值。",
    ),
    (
        "这杯子行不行，看三个地方就够。",
        "先看，打和喝是不是同一个杯子。",
        "再看，中间有没有倒进别的容器。",
        "最后看，打完直接喝，镜头切没切。",
        "三条之外呢？防漏耐摔这条不管。",
        "拿这三条清单，自己对比去。",
    ),
    (
        "先说清楚，这条视频不证明防漏。",
        "它只证明一件事，打完直接喝。",
        "防漏、保温、带出门，今天都不聊。",
        "只有打果汁和喝果汁，同一个杯子，一刀没剪。",
        "那还看什么？看你每天能不能少洗一个杯子。",
        "觉得值就去查看商品页。",
    ),
)

# ============================================================
# USB-C 充电 · 英文（美区）
# ============================================================

USB_C_EN = (
    (
        "Another gadget, another weird charging cable to keep track of?",
        "Not this one, it charges over USB-C.",
        "Proprietary cables are the first thing you lose in a drawer.",
        "The same USB-C cable your phone likely uses fits here.",
        "Does USB-C mean fast charging? Speed isn't tested in this clip.",
        "Check your cable drawer, then the listing.",
    ),
    (
        "Charging right now, with the cable I already own.",
        "The port on this blender is USB-C.",
        "Rewind a little and you can see the plug going in.",
        "One USB-C cable, one port, connected on camera.",
        "How long does a charge last? That's not what this shows.",
        "See the port for yourself on the listing.",
    ),
    (
        "No cuts here, just a cable and a port.",
        "Testing one thing, the USB-C charging port.",
        "Port shots get faked with edits, so this take keeps rolling.",
        "Plug in, unplug, plug in again, same USB-C port throughout.",
        "Could an edit hide an adapter? Not in one continuous take.",
        "Watch closely, then compare with your own cables.",
    ),
    (
        "Two cables on the table, only one fits this.",
        "One old-style plug, one USB-C plug.",
        "The round plug doesn't fit, wrong shape for this port.",
        "The USB-C plug slides in, one try, that's the port.",
        "Does fitting mean it charges faster? No, just that it fits.",
        "Match the port before you choose a cable.",
    ),
    (
        "My one rule for small gadgets, check the port first.",
        "This one passes, the charging port is USB-C.",
        "A dead gadget with a lost proprietary cable is just clutter.",
        "Here's the close-up, USB-C shape, cable in, charging.",
        "Is port type everything? No, but it's the easiest check.",
        "Try that rule on your next purchase.",
    ),
    (
        "Desk, laptop, one charger doing all the work.",
        "The blender cup joins in, it's USB-C too.",
        "One more proprietary charger on this desk would be too many.",
        "Unplug the phone, plug the cup in, same cable, charging.",
        "Can laptop ports charge it faster? That I can't tell you.",
        "Count the chargers on your desk, then decide.",
    ),
    (
        "Before you buy, you'll want to know the port type.",
        "Straight answer, it charges through USB-C.",
        "Listings love to bury this detail in the fine print.",
        "So here's the port on camera with a USB-C cable in.",
        "Does that cover charge time? No, only the connector type.",
        "Check the listing with that answer in mind.",
    ),
    (
        "Watch the port, it never leaves the frame.",
        "One shot, one port, USB-C the whole way.",
        "A hidden cut is all it takes to fake a port.",
        "The USB-C cable comes in from the side and connects.",
        "Why so paranoid? Because port swaps are an easy edit.",
        "See the uncut version and judge the port.",
    ),
    (
        "Three simple checks for this charging port.",
        "One, the listing says USB-C charging.",
        "Two, the port shape matches a USB-C plug on camera.",
        "Three, the cable connects and stays connected while we film.",
        "Does the checklist cover battery life? No, that needs real use.",
        "Save the checklist for your next gadget.",
    ),
    (
        "First, what this clip won't tell you about charging.",
        "No speed claims, just the USB-C charging port.",
        "Plenty of videos promise all that without showing the plug.",
        "This one keeps it simple, USB-C cable in, done.",
        "So what do you get? The port type, confirmed on camera.",
        "Take that certainty and check the rest yourself.",
    ),
)

# ============================================================
# USB-C 充电 · 中文
# ============================================================

USB_C_ZH = (
    (
        "又一个小家电，又一根专用充电线？",
        "这台不用，它就用 USB-C 充电。",
        "专用线这种东西，搬一次家准丢。",
        "手机那根 USB-C 线插上就充，不用翻抽屉找线。",
        "USB-C 就充得快吗？速度这条没测。",
        "翻翻你的线，再查看商品页。",
    ),
    (
        "它现在正在充电，用的是我手机的线。",
        "因为它的充电口就是 USB-C。",
        "倒回去几秒，你能看到线插进去的动作。",
        "一根 USB-C 线，一个口，插上就开始充。",
        "一次能用多久？续航这条不下结论。",
        "口长什么样，商品页自己查看。",
    ),
    (
        "不剪不切，就拍一根线一个口。",
        "今天只验一件事，USB-C 充电口。",
        "接口这种东西，剪一刀就能造假，所以一镜到底。",
        "插上、拔下、再插上，同一个 USB-C 口。",
        "会不会藏了转接头？一镜到底藏不住。",
        "盯着接口看完，再对比你家的线。",
    ),
    (
        "桌上两根线，只有一根插得进去。",
        "圆头老式线，和一根 USB-C。",
        "圆头的比一下就知道，口型对不上。",
        "USB-C 一插到底，这就是它的充电口。",
        "插得进就充得快吗？不，只说明口型。",
        "先对比接口，再选择买哪根线。",
    ),
    (
        "买小家电我只有一条硬标准，看接口。",
        "这台过关，充电口是 USB-C。",
        "专用线一丢，整台机器就变成摆设。",
        "特写给你，口型是 USB-C，插上就充。",
        "光看接口就够了吗？不够，但这步最省心。",
        "下次买东西，先试试这条标准。",
    ),
    (
        "办公桌上，一个充电头喂饱所有设备。",
        "这台榨汁杯也加入，USB-C 充电。",
        "桌上再多一种专用线，谁受得了。",
        "拔下手机线插到杯子上，同一根线继续充电。",
        "用电脑口充会更快吗？这条视频答不了。",
        "数数你桌上的线，再判断要不要。",
    ),
    (
        "下单前你多半想问，充电口是什么？",
        "直接回答你，充电口是 USB-C。",
        "详情页总把这种关键信息藏得很深。",
        "所以拍个特写，USB-C 线插进充电口。",
        "这能代表充满要多久吗？不能，只回答口型。",
        "带着答案，再去打开详情页。",
    ),
    (
        "眼睛别离开这个充电口。",
        "一个镜头，一个口，全程 USB-C。",
        "切一刀就能换接口，所以这条一刀不切。",
        "USB-C 线从画面右边进来，插上，没有切换。",
        "至于这么谨慎吗？接口造假就是一剪刀的事。",
        "看完整段，自己判断这个口。",
    ),
    (
        "验充电口，就三步。",
        "一看详情页，写的是 USB-C 充电。",
        "二看口型，和 USB-C 线头能不能对上。",
        "三看实插，线进去稳稳待住，镜头没切。",
        "这三步验得出续航吗？验不出，得真用。",
        "收藏这三步，下次买电器用。",
    ),
    (
        "先说这条视频回答不了什么。",
        "不测速度不测续航，只看 USB-C 口。",
        "敢把话说满的视频，多半连插口都不拍。",
        "这条只做一件事，USB-C 线插上充电口。",
        "那你能带走什么？口型确认，眼见为实。",
        "剩下的，去商品页自己查看。",
    ),
)

# ============================================================
# 杯体可拆洗 · 英文（美区）
# 卖点只有"可拆洗"四个字，未验证的细节留给 objection 自然带过。
# ============================================================

DETACHABLE_WASH_EN = (
    (
        "The worst part of any blender is cleaning it.",
        "This cup body comes apart for washing.",
        "Residue hides in corners a sponge can never quite reach.",
        "Take the cup body apart and rinse each piece clean.",
        "Is every single part washable? The listing doesn't spell that out.",
        "Check the details before you order one.",
    ),
    (
        "This is the cup fully taken apart.",
        "It's listed as a detachable, washable cup body.",
        "Moments ago it was assembled and full of smoothie leftovers.",
        "Each detached piece got rinsed, and now it rebuilds.",
        "Did reassembly take long? Watch the clock in the corner.",
        "See the whole teardown before you decide.",
    ),
    (
        "One take, from dirty cup to clean and rebuilt.",
        "The cup body detaches, that's today's test.",
        "No cuts, because cuts can skip the annoying scrubbing part.",
        "Apart, rinsed, dried, back together, all in one continuous shot.",
        "Was anything skipped? Watch the take, it's all in there.",
        "Watch it once, then judge the cleanup.",
    ),
    (
        "Cleaning a sealed cup versus one that comes apart.",
        "This one is the kind that comes apart.",
        "The sealed kind means shaking soapy water and hoping.",
        "This one opens up, so water actually reaches the inside.",
        "Which parts can get wet? The listing leaves that open.",
        "Compare the two and pick your cleanup style.",
    ),
    (
        "Judge a blender cup by cleanup, not the blending.",
        "So the standard here is a detachable cup body.",
        "A cup you can't open slowly turns into a science experiment.",
        "This one lists detachable washing, and here it is, apart.",
        "Is detachable the same as dishwasher safe? The listing doesn't say.",
        "Shop with that one standard in mind.",
    ),
    (
        "Sunday night, a full sink, the real test.",
        "The cup body detaches right when it counts.",
        "After a week of smoothies, the inside needs real cleaning.",
        "Pull it apart at the sink and rinse piece by piece.",
        "What about the motor section? That part stays away from water.",
        "Picture your own sink, then check the listing.",
    ),
    (
        "The question with these cups, how do you clean it?",
        "The cup body comes apart, that's the answer.",
        "Gear that's hard to clean ends up gathering dust.",
        "Open it up, rinse the pieces, let them dry, rebuild.",
        "How many pieces exactly? Count them yourself in this shot.",
        "Check the listing if cleanup decides it for you.",
    ),
    (
        "The cup stays on camera through the whole cleanup.",
        "It comes apart to wash, and you'll see everything.",
        "Off-camera cleanup proves nothing, so nothing leaves the frame.",
        "Apart, into the sink, rinsed, and rebuilt in plain view.",
        "Why no jump cuts? So the cleanup stays believable.",
        "See the whole sequence before you decide.",
    ),
    (
        "My cleanup checklist for blender cups, three items.",
        "Item one, the cup body must come apart.",
        "Item two, the pieces should rinse clean without tools.",
        "Item three, it should rebuild without a fight, so watch.",
        "Does it pass all three? Keep your own score while watching.",
        "Save the checklist for your next kitchen buy.",
    ),
    (
        "Straight up, this video can't answer everything about washing.",
        "It shows one thing, the cup body detaching.",
        "Dishwasher rules and deep cleaning aren't in the listing.",
        "What is here, the body coming apart and getting rinsed.",
        "Is that enough to decide? For daily rinsing, you'll see plenty.",
        "Judge the cleanup with your own eyes.",
    ),
)

# ============================================================
# 杯体可拆洗 · 中文
# ============================================================

DETACHABLE_WASH_ZH = (
    (
        "榨汁杯最劝退的，从来是洗杯子。",
        "这款的杯体可以拆开洗。",
        "死角里的残渣，海绵怎么都够不到。",
        "拆开杯体，一件一件冲干净，再装回去。",
        "每个零件都能进水吗？详情页没写全，留个心。",
        "在意清洗的，下单前先查看说明。",
    ),
    (
        "这就是它整个拆开的样子。",
        "杯体可拆洗，是它写明的卖点。",
        "几分钟前它还装着满杯的果渣。",
        "拆下来的每一件冲过水，现在装回去。",
        "装回去麻烦吗？镜头里多长时间就是多长时间。",
        "拆装全过程，看完再判断。",
    ),
    (
        "一条过，从脏杯子拍到洗完装好。",
        "今天验的就是杯体可拆洗。",
        "不剪，是因为剪辑最容易跳过刷洗那段。",
        "整套拆开、冲洗、沥干、装回，一条镜头拍完。",
        "有没有偷工减料？整段都在，自己看。",
        "看完这条，再判断洗它累不累。",
    ),
    (
        "洗封死的杯子，和洗能拆的杯子。",
        "这款属于能拆开的那种。",
        "封死的只能灌肥皂水使劲摇，听天由命。",
        "能拆的摊开在水池里，哪里脏冲哪里。",
        "哪些件能碰水？这个以说明书为准。",
        "两种洗法对比完，自己选择。",
    ),
    (
        "挑榨汁杯，先看好不好洗，再看别的。",
        "所以标准就一条，杯体能不能拆。",
        "拆不开的杯子，洗不净就开始有味道。",
        "这款写明可拆洗，拆开给你看就是了。",
        "可拆等于能进洗碗机吗？详情页没这么说。",
        "拿这条标准，再去对比其他家。",
    ),
    (
        "周日晚上，水池边，才是它真正的考场。",
        "杯体可拆洗，这时候才显出用处。",
        "连打一周果汁，杯子里面是真的该洗了。",
        "水池边拆开，一件件冲，顺手就洗完了。",
        "电机那部分呢？我不让它碰水，擦一擦就好。",
        "想想你家水池，再查看商品页。",
    ),
    (
        "这类杯子被问最多的，怎么洗？",
        "答案是，杯体拆开洗。",
        "难洗的电器，最后都在柜子里吃灰。",
        "拆开、冲净、晾干、装回，四步拍给你看。",
        "到底拆成几件？画面里自己数。",
        "清洗是你的重点，就去查看详情。",
    ),
    (
        "整个清洗过程，杯子不离开镜头。",
        "能拆开洗，拆给你看才算数。",
        "镜头外洗好的杯子说明不了什么。",
        "拆开、进水池、冲净、装回，全程在画面里。",
        "为什么不剪？剪了你就没法信这次清洗。",
        "完整看一遍，再判断好不好洗。",
    ),
    (
        "好不好洗，我就看三样。",
        "一看杯体是不是真能拆开。",
        "二看拆下的件，是不是随手就能冲。",
        "三看装回去顺不顺，盯着画面看。",
        "三样都过了吗？你边看边自己打分。",
        "收藏这三条，买厨房电器都能用。",
    ),
    (
        "先讲清楚，这条不回答洗碗机的事。",
        "它只演示一件事，杯体拆开洗。",
        "哪些件防水、能不能进洗碗机，详情页没写。",
        "这里有的，是拆开、冲洗、装回的完整过程。",
        "这够决定吗？日常手洗，看这条就够。",
        "眼见为实，看完自己判断。",
    ),
)

CURATED_EN = {
    "direct-drink": DIRECT_DRINK_EN,
    "detachable-wash": DETACHABLE_WASH_EN,
    "usb-c-charge": USB_C_EN,
}

CURATED_ZH = {
    "direct-drink": DIRECT_DRINK_ZH,
    "detachable-wash": DETACHABLE_WASH_ZH,
    "usb-c-charge": USB_C_ZH,
}

# ============================================================
# 未收录机制的商品：开头两句按角度手写，主体套用卖点
# ============================================================

GENERIC_OPENINGS_EN = (
    ("Tired of fighting the same little problem daily?", "This one is built around {point}."),
    ("Look at the after first, then the how.", "The how here is {point}."),
    ("One continuous take, no edits to hide behind.", "Only one feature on test, {point}."),
    ("Same job, two tools, side by side.", "The difference between them is {point}."),
    ("One standard decides this category for me.", "That standard is {point}."),
    ("Real home, real mess, real test.", "Here is {point} where it matters."),
    ("The question you'd ask before checkout, answered.", "It comes down to {point}."),
    ("Eyes on it the whole time, no cuts.", "We're watching whether {point} holds up."),
    ("Hold on, run three checks with me first.", "The opening check is {point}."),
    ("First, what this video cannot prove.", "It only demonstrates {point}."),
)

GENERIC_BODY_EN = (
    "Photos and captions can't really prove this kind of claim.",
    "So the camera gets close and shows {point} in action.",
    "Is everything else just as good? Not shown, not claimed.",
    "Compare it on the product page yourself.",
)

GENERIC_OPENINGS_ZH = (
    ("老毛病天天犯，今天换个思路。", "{title}主打的就是{point}。"),
    ("先看用完的样子，再讲它怎么做到。", "靠的就是{point}这一个设计。"),
    ("一条镜头拍完，不剪不摆拍。", "今天只试它的{point}。"),
    ("同一件事，两种做法，摆一起看。", "差别只在{point}这一处。"),
    ("买这类东西，我只认一条标准。", "这条标准就是{point}。"),
    ("搬回真实的家里用，才知道行不行。", "{point}到底实不实用，现场见。"),
    ("下单前你最想问的，直接拍答案。", "答案就落在{point}上。"),
    ("从头到尾盯着它，中间不切镜头。", "全程盯着{point}看真假。"),
    ("先别急着买，跟我核三个点。", "打头一项就核{point}。"),
    ("先说清楚，这条不能证明一切。", "它只演示{point}这一件事。"),
)

GENERIC_BODY_ZH = (
    "光看图片和详情文字，这种事真假难辨。",
    "镜头凑近拍，{point}的完整动作一遍给你看。",
    "别的功能也这么好吗？没拍到的，我不下结论。",
    "看完去商品页对比一下。",
)

# ============================================================
# 无商品（纯内容）：开头两句按角度手写，主体围绕 brief 场景
# ============================================================

BRIEF_OPENINGS_EN = (
    ("The same small mess wins every single morning?", "Today we film how it gets fixed."),
    ("Look at the finished corner first.", "The steps come right after."),
    ("One take, start to finish, no edits.", "What you see is the real pace."),
    ("Same routine, two ways, side by side.", "Only one habit changes between them."),
    ("One simple standard tells you if this works.", "You can see it at a glance."),
    ("A real room, a real mess, no staging.", "The setting stays exactly as found."),
    (
        "The question everyone keeps asking, answered on camera.",
        "The answer is shorter than you think.",
    ),
    ("The camera never cuts away from the work.", "The order you see is the real order."),
    ("Three steps, in order, none skipped.", "Each one filmed close enough to copy."),
    ("First, here's what this video won't promise.", "It only shows what actually happened."),
)

BRIEF_BODY_EN = (
    "Here is the messy part, exactly as it starts.",
    "Same camera position, and here is how it ends.",
    "Would this work at your place? The idea travels, adjust the details.",
    "Save this and try it once yourself.",
)

BRIEF_OPENINGS_ZH = (
    ("{scene}那点小混乱，今天正面拍一次。", "就拍它是怎么被理顺的。"),
    ("先看收拾完的样子，你再决定学不学。", "整个过程就在后面几镜。"),
    ("不剪不摆拍，一条镜头走完全程。", "真实{scene}什么样就拍什么样。"),
    ("同一个{scene}，两种过法，你看差在哪。", "只改了一个习惯，其他照旧。"),
    ("这事做没做对，看一个标准就够。", "标准很简单，一眼能看出来。"),
    ("把方法放回真实的{scene}里试。", "环境是真的，动作也是真的。"),
    ("最多人想问的那个问题，直接答。", "答案不复杂，看完你就有数。"),
    ("全程不切镜头，做到哪拍到哪。", "你看到的顺序就是真实顺序。"),
    ("照着三步走，别跳步。", "每一步都给你拍清楚。"),
    ("先说好，这条不打包票。", "只把我真实做的过程给你看。"),
)

BRIEF_BODY_ZH = (
    "{scene}最容易乱的就是这一段，先拍原样。",
    "同一个机位接着拍，改完之后什么样，你自己看。",
    "换到你家也管用吗？思路一样，细节自己调。",
    "觉得有用，收藏起来照着做。",
)

# ============================================================
# 候选标题：像真实视频标题，不是策略自述
# ============================================================

CURATED_TITLES = {
    "direct-drink": (
        "别再多洗一个杯子了",
        "我喝的就是刚打完的那个杯子",
        "一镜到底，打完直接喝",
        "倒杯喝和原杯喝，差在哪",
        "买榨汁杯先问这一句",
        "通勤路上直接喝的榨汁杯",
        "能不能对着杯子直接喝？拍给你看",
        "全程盯着这一个杯子",
        "三步验证能不能直接喝",
        "先说丑话，这条不测防漏",
    ),
    "usb-c-charge": (
        "又是一根专用充电线？这台不是",
        "正在用手机线给榨汁杯充电",
        "一镜实拍这个充电口",
        "两根线，只有一根插得进",
        "买小家电先看充电口",
        "办公桌一根线喂饱所有设备",
        "充电口是什么？直接拍答案",
        "盯死这个充电口，不切镜头",
        "三步验一个充电口",
        "这条不测续航，只看接口",
    ),
    "detachable-wash": (
        "榨汁杯难洗？拆开洗试试",
        "整个拆开的榨汁杯长这样",
        "一镜拍完拆洗全过程",
        "封死的杯子和能拆的杯子",
        "挑榨汁杯先看好不好洗",
        "周日晚上的水池实测",
        "怎么洗？拆开给你看",
        "清洗全程不离开镜头",
        "好不好洗，核这三样",
        "先说清楚，不聊洗碗机",
    ),
}

GENERIC_TITLES = (
    "{product}，治一个老毛病",
    "先看{product}用完的样子",
    "一镜实测{product}",
    "有没有{product}，差多少",
    "买{product}前只看一条",
    "把{product}放回家里用",
    "关于{product}，买前最该问的",
    "全程不切镜头看{product}",
    "三步核对{product}",
    "{product}不能证明什么，先说",
)

BRIEF_TITLES = (
    "{scene}最烦的一步，拍给你看",
    "先看{scene}整理完的样子",
    "一镜拍完{scene}的全过程",
    "{scene}的两种过法",
    "{scene}做没做对，看一条",
    "真实{scene}，不摆拍",
    "关于{scene}，最多人想问的",
    "{scene}全程不切镜头",
    "{scene}三步走，别跳步",
    "这条{scene}视频不打包票",
)


def scene_word(scenario: str) -> str:
    """取 brief 场景里第一个词，兜底成"日常"。"""
    first = (scenario or "").split("、")[0].strip()
    return first if first and first != "日常使用现场" else "日常"


def candidate_title(
    point: str,
    angle: str,
    *,
    product_title: str,
    scenario: str,
    has_product: bool,
) -> str:
    """按角度生成真人会起的候选标题。"""
    index = CURATED_ANGLES.index(angle) if angle in CURATED_ANGLES else 2
    key = mechanism_key(point) if point else None
    if key in CURATED_TITLES:
        return CURATED_TITLES[key][index]
    if has_product:
        return GENERIC_TITLES[index].format(product=product_title)
    return BRIEF_TITLES[index].format(scene=scene_word(scenario))
