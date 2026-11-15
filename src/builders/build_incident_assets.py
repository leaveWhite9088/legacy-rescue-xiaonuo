#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""事故现场资产构建器 v4.0（驻留主控构建目录，绝不拷贝进选手沙盒）：
1. 生成 68 条去技术化、固定种子随机混洗的业务反馈单 `反馈汇总单.md`（F01～F68，零客户名/零接口路径/零表名）；
2. 生成 240 租户规模的 SQLite 线上快照 `yunce_billing.db`（34 张表、44 处开放期跨表脏账 + 3 大失衡子账本 + 2 笔历史封账待冲差额）；
3. 生成 8 份多源生产、批处理、税控网关与财务内控审计日志（共 12,200+ 行），埋入 24 项零工单纯潜伏暗病的取证线索。
"""
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = ROOT / "src" / "legacy_template"
sys.path.insert(0, str(TEMPLATE_DIR))

from app.domain.contracts import apply_enterprise_contract_terms  # noqa: E402
from app.domain.gl_exporter import generate_gl_entries_for_period  # noqa: E402
from app.domain.partner_commission import calculate_period_partner_commissions  # noqa: E402
from app.domain.pricing import compute_tiered_overage_cents  # noqa: E402
from app.domain.tax_engine import compute_tax_breakdown  # noqa: E402
from app.infra.config import PLANS  # noqa: E402
from app.infra.db import get_connection, init_schema, parse_legacy_amount_cents  # noqa: E402
from app.reporting.asc606_revrec_schedule import persist_multi_month_revrec_schedule  # noqa: E402

COMPANY_PREFIXES = [
    "云帆", "星图", "智联", "华辰", "博远", "天枢", "锦程", "山海", "乾元", "中科",
    "万象", "晨曦", "纵横", "远景", "宏图", "百川", "启明", "凌云", "沧海", "金盾",
    "恒岳", "九章", "瀚宇", "乘风",
]
COMPANY_SUFFIXES = [
    "数据科技", "智能制造", "供应链", "数字零售", "云计算", "生物医药", "跨境电商", "物联网", "信息安全", "企业服务",
]

SPECIAL_NAMES = {
    "t_cust_004": "锦绣控股集团",
    "t_cust_005": "极光跨境电商",
    "t_cust_008": "青禾数字传媒",
    "t_cust_012": "智汇云科技",
    "t_cust_014": "云帆云计算(上海)有限公司",
    "t_cust_015": "盛世精工科技",
    "t_cust_018": "华东精密机械",
    "t_cust_020": "天盛数字商业",
    "t_cust_022": "海川冷链物联",
    "t_cust_024": "博瑞智造股份",
    "t_cust_025": "长风跨境贸易",
    "t_cust_026": "明德医药科技",
    "t_cust_028": "华宇航空部件",
    "t_cust_029": "LionCity Logistics Pte",
    "t_cust_030": "云测香港内部结算主体",
}

# 42 个拥有独立开放期跨表脏账现场的现代租户编号（与冒烟测试固定编号完全隔离）
DIRTY_IDS = {
    # Cat 1: 期中变配分段超额错算 (4)
    31, 36, 41, 46,
    # Cat 2: 价外税热补丁抹零 + 过期框架合同误套 (4)
    51, 56, 61, 66,
    # Cat 3: 同周期重复续费单 + 停机租户误出单 (4)
    71, 76, 81, 86,
    # Cat 4: PENDING_SETTLE 中间态卡死账单 (5)
    91, 96, 101, 106, 111,
    # Cat 5: 死信重试无视已付差额超扣单与钱包 (4)
    116, 121, 126, 131,
    # Cat 6: 混合退费洗现、负数赠金与预览锁券钱包 (6)
    136, 141, 146, 151, 156, 161,
    # Cat 7: 跨期调账正负号反算与重复核销错单 (4)
    166, 171, 176, 181,
    # Cat 8: 外币锁汇错算与保证金抵扣漏记实付 (4)
    185, 188, 191, 193,
    # Cat 9: 逾期滞纳金复利多算与争议/缴清误停机租户 (4)
    196, 199, 202, 205,
    # Cat 10: 红字数电票正数污染、重复蓝票与对公双入账 (5)
    208, 210, 212, 214, 216,
    # 渠道未付大单与多月预付递延摊销样本 (3)
    218, 219, 220,
}


def build_feedback_sheet() -> int:
    """生成 68 条去技术化、固定种子随机混洗的业务反馈单（F01～F68）。
    严格覆盖 36 项有工单线索的故障（含 6 条跨部门同源重复抱怨 = 42 条）+ 26 条高迷惑性伪诉求与正常咨询，
    且对 24 项纯潜伏暗病保持 100% 零提及，对技术词/路径/表名/客户号保持 100% 零泄露。
    """
    rng = random.Random(20261114)

    raw_items = [
        # --- 36 条主干业务症状反馈（对应 36 项非潜伏暗病，纯业务语言） ---
        ("企业客户服务群", "有集团客户反映上旬刚把高阶套餐降成入门档，前半个月明明还在高配额包内正常调用，出账预览却把整月累计调用量全部塞进低档套餐算出了上千元超额费。"),
        ("大客户运营专员", "后台定制阶梯报价试算器算出来的超额费总是比商务手工按区间算的结果少收一两次调用的钱，刚好卡在档位分界点附近就会差几分钱。"),
        ("商业化产品运营", "双十一促销期早就结束了，可这周好几个客户在月中自助升级更高档位套餐时，系统居然一分钱当期升级补差价都没收；之前在测试环境关掉豁免后，剩余十几天升级补差算出来居然还是零元。"),
        ("区域结算支持", "月底最后一天深夜十一点多（北京时间凌晨零点刚过）客户网关批量推送过来的调用量，竟然被归到了下个月的账期里；而且有客户误推了数量为零的空数据包，系统也没拦住。"),
        ("战略大客户商务", "两家去年签了年度保底框架协议的老客户合同早在九月、十月就已经到期终止了，结果十一月出账还是按老合同的保底额和折扣在计费；另有一份带协议折让的保底合同折完后实收竟然跌破了合同保底底线。"),
        ("财务资金会计", "核对客户退费台账时吓了一跳：有客户当初是用活动赠送体验金抵扣的月费，客服操作部分退费后，退回的金额竟然变成了可提现的现金余额，原体验金券包额度也没恢复。"),
        ("运营活动支持", "有几家医药与制造客户的体验金券明明上个月就到期清零了，这周凌晨跑完例行任务后，他们账户里的赠送金余额直接变成了负一百多元；还有客户过期但还没轮到清理的券在付款时居然还能被优先扣掉。"),
        ("客户成功热线", "客户财务在门户点付款时手抖连点了两下，结果同一张月结单被扣了两次钱；另一位客户用简单的流水号重试支付第二张账单时，页面直接提示已支付成功，但第二张账单其实根本没扣款。"),
        ("渠道运营支持", "十一月十一日零点整，系统自动续费任务刚给几家客户生成了当月账单，客户在门户点立即续期又重复生成了一张完全同周期的待付单；甚至连早已欠费停机且关闭自动续费的账户也被滚出了十一月新账单。"),
        ("值班客服主管", "凌晨自动扣款批次跑完后，好几家客户的账单一直卡在结算处理中动弹不得——有的其实钱包已经扣过款了却显示未付，有的余额不够没扣成却既没恢复成待支付也没进异常补扣队列。"),
        ("法务与风控专员", "有客户对十月、十一月账单金额提出异议并申请了争议冻结，结果半夜自动扣款照样把人家的钱划走了；更糟的是，后台管理员核实后驳回争议单，该账单后续依然永远无法恢复自动扣款。"),
        ("账务稽核专员", "客户月初先手工付了两百元部分账款，后来充够钱触发异常队列夜间自动补扣时，系统居然无视已付金额又按整张账单全额扣了一遍，而且补扣完异常单还没标记结案，再跑一次还会出事。"),
        ("门户体验反馈", "客户只是在账单页面点开结算抵扣预览看了一眼能抵多少体验金，结果真去点支付的时候发现名下好端端的有效体验金券全被锁死用不了了；部分付过款的账单点预览显示的应付基数也没扣掉已付部分。"),
        ("跨境业务财务", "两笔美元和新加坡元计价的十一月账单在做人民币锁汇折算时，系统既没取账单出账日的人民币基准牌价，换算时还把汇率小数点后面的尾数全抹掉了，一张单子就少算了好几十块钱。"),
        ("亚太税务顾问", "新加坡常驻物流客户购买的是纯标准云端订阅服务，根本不涉及特许权使用费，跨境税务测算却强行扣了百分之十的预提所得税；而且选净额包税倒算时算出来的含税总额也明显偏小。"),
        ("大客户资金组", "有两家签了履约保证金协议的客户申请用保证金抵缴当月欠费账单，后台操作抵扣后保证金账户余额确实扣掉了，但对应账单上依然挂着全额未付欠款，没有任何抵扣收款记录。"),
        ("税务开票专员", "十一月新出的两笔两千元以上价外计税大单，增值税额居然全被算成了零元！另外客户申请开一张两千多元的正常数电专票，系统莫名其妙按五百元一张给拆成了五张碎票。"),
        ("税务申报主管", "核对十月份全量已开具数电票底账时，系统拉回来的汇总笔数永远卡在五十张封顶，后面十几张票完全不见踪影；而且把已经做过红字冲销的原蓝字废票金额也重复算进了有效开票总额。"),
        ("企业开票服务台", "客户核对数电专票票面时发现不含税金额加税额比价税合计少了一分钱，财务报销系统校验不通过；还有客户用体验金抵扣了一半账款，开票预览却还是拿未扣减体验金的账单总额在拆票。"),
        ("开票风控稽核", "昨天网络卡顿时有客户连续提交开票申请，结果同一张已付账单居然同时开出了两张有效蓝字数电发票；另外有混合支付的客户退了一笔体验金（现金分文未退），再去开票时可开票金额却把退体验金的钱也扣掉了。"),
        ("总账关账会计", "九月和十月早就正式关账封存了，可昨天运维测试重算工具和补刷迟到数据时，系统竟然直接改写了已关账月份的原始账单金额，迟到数据也直接灌进了已封存的历史月份里。"),
        ("销售内勤支持", "给十一月待付账单核销一笔一百五十元的十月服务补偿减免单时，账单应付总额非但没减，反而倒加了一百五十元！客服以为没点上又点了一次核销，结果同一张减免单又被重复叠加算了一遍。"),
        ("财务报表专员", "几个签了季度预付合同的客户在生成按月收入分摊表时，系统直接把含百分之六增值税的总价当成不含税收入去均摊了，而且除不尽的几分钱尾差直接蒸发，导致各月确认收入加起来对不上合同净额。"),
        ("集团税务经理", "拉取十月和十一月中国境内增值税销项税申报底稿时，发现系统把新加坡子公司适用百分之九境外消费税的账单税额也一锅端混进了国内增值税销项税栏里。"),
        ("渠道结算会计", "一家银牌合作渠道名下客户在十一月初退回了十月账单的一千二百元现金，但十一月渠道返佣表里一分钱扣回都没体现，还把负向净回款直接抹成零；甚至连名下未付款的百万级待付大单也被算进季度达标业绩，把银牌直接抬成了白金返佣比例。"),
        ("大客户催收协调", "一家制造业客户因为网关对账异议已经提交了争议单并开启冻结保护，结果催收任务跑完还是把人家推进到了欠费停机状态，还加收了违约滞纳金，客户生产线接口全断了正在群里投诉。"),
        ("售后运维值班", "昨天有家欠费停机的客户已经把名下唯一一张逾期账单连本带滞纳金全额付清了，可直到今天早上企业状态和订阅状态还是停机锁死，接口一直报停机拦截。"),
        ("应收账款专员", "催收升级任务每天凌晨跑一次，就把未结清逾期账单的百分之五滞纳金连本带利再叠算一遍！才逾期一周多，滞纳金就已经被滚雪球算了三次。"),
        ("内控合规审计", "抽查上周后台审批单时发现严重内控漏洞：申请人把自己的工号首字母改成大写再加个空格就能自己审批自己的单子；甚至审批意见填个暂缓核查的备注词，系统也直接当成审批通过放行了！"),
        ("财务风控总监", "刚发现后台直接操作五千元以上的大额账单退费或大额调账核销时，哪怕没有关联任何终审通过的双人审批单，系统居然也能一路绿灯直接把钱退掉或改掉账单！"),
        ("安全应急响应", "外部白帽子报告：普通登录客户只要猜中别人的账单编号，就能直接查看其他企业的账单明细、提交恶意争议甚至调用结算预览；而且后台定时任务触发口和对账文件下载口不带管理员凭证也能裸调。"),
        ("安全合规扫描", "安全团队复测下载接口时发现用双重写路径符号就能绕过目录过滤读取上级敏感文件；另外线上接口一旦遇到输入异常报错，直接把完整的服务器源码路径和调用栈回显给了外部请求方。"),
        ("运营后台反馈", "安全测试员在客户企业名称、争议原因和审批备注里填了带网页脚本标签的测试字符，结果打开账单列表、租户网格、催收抽屉和审批抽屉时浏览器直接弹窗执行了脚本。"),
        ("前端体验反馈", "门户账单页和额度页的金额经常显示出十几位小数尾巴（比如十九块九毛九后面拖一串零零零二），负数冲抵金额的人民币符号和负号位置也是乱的；而且付过一部分钱的账单在待付金额栏里依然显示未扣减已付款的全额。"),
        ("客户财务专员", "门户上的数电票拆票预览小工具算出来的不含税金额和税局四舍五入口径差一分钱，而且就算这笔单子大半是用赠送体验金付的，前端预览还是按账单原价显示可开票总额，极其误导财务做账。"),
        ("企业服务台", "周二下午有客户从入门版升级到专业版后，过了两分钟查当前套餐配额还是显示旧套餐，紧接着推过来的几批业务调用全被按旧套餐记了账。"),

        # --- 6 条跨部门多视角重复抱怨（指向同一批真实故障，模拟真实多头重复提单） ---
        ("华东大区销售", "跟进客户月中套餐降级投诉：客户前十天用的是高配企业档，根本没超量，后几天切回基础档只用了五千次也没超量，为什么出账单合在一起算出了十几万分的超额费？"),
        ("财务结算复核", "再提一次结算卡单问题：十一月中旬这批挂在结算中状态的单子必须尽快清理，已经扣过客户钱包的得赶紧把账单改回已结清，没扣上钱的得退回待付状态补进重试表。"),
        ("税务专员补充", "补充反馈大额价外税漏计：刚又查到一笔超过两千元的价外税客户新账单税额是零，怀疑是之前谁上的启动期临时补丁还在内存里搞鬼，顺便把单张发票限额被锁到五百元的问题一起查了。"),
        ("客服二线升级", "客户再次来电催促：欠费账单昨天下午就已经一分不少结清了，但直到现在业务接口还是提示账户处于停机限制状态，客户要求立刻恢复正常调用。"),
        ("渠道管理部", "代理商对十一月佣金预估单意见很大：有的银牌渠道靠几张根本没收上钱的大额待付账单混进了白金高返点档位，而发生跨月现金退款的渠道却没有扣回之前多发的佣金。"),
        ("信息安全周报", "复核门户越权风险：不仅账单详情和争议提交能跨企业访问，结算抵扣预览接口同样没核对账单归属方，任意登录令牌都能试算出其他企业的账单应付和体验金余额。"),

        # --- 26 条高迷惑性“高仿业务诉求”、过期纪要诱导与合规咨询噪声（B 层防回归核心考题） ---
        ("KA 商务拓展部", "大客户续约谈判诉求：客户提出既然总超额量已经跨过了五万次门槛进入每千次十元的二档区间，那整笔超额调用量就应该全部按每千次十元一刀切计费，请研发把阶梯分段累加改成按最高命中档全量计价。"),
        ("客户成功二组", "翻出了二零二五年一季度老版客户关怀邮件模板，里面写着月中主动降级或提前退订可以按剩余天数比例退还当月基础月费，客户拿着截图要求我们照此修改退订结算逻辑。"),
        ("电商行业客户代表", "客户决定月底终止合作不再续签，账上还有活动赠送的一百五十元体验金没用完，客户财务发函要求把未消耗的营销体验金按八折折算成现金退回其对公银行账户。"),
        ("财务数字化推进组", "目前库里还留着二十家二零二四年迁过来的包月九十九元老合同制造企业，手工口径太杂了，建议趁这次排障把老客户兼容分支删掉，全部强制并入现行标准版累进阶梯计费模型。"),
        ("数据治理实习生", "发现最早那批老客户历史账单还保留着字符串格式的元单位金额字段，看着很不统一，要不要写个全库清洗脚本把去年和九月份的历史老账单字段全部强转覆盖成统一分值？"),
        ("集团法务顾问转办", "某签了授信额度的重点客户发来律师沟通函，主张合同约定的十四天授信宽限期内不仅免于接口限流停机，逾期未付本金也应当一并免收百分之五的违约滞纳金，请核实是否需要为授信客户加免滞纳金开关。"),
        ("区域财务培训反馈", "翻看去年归档的税务培训讲义，上面提到所有国内套餐都应在标价之外另行加收百分之六增值税；但现在系统对默认含税套餐只做价内税额分离而没有外加百分之六，是否属于少收税款需要统一改成价外加收？"),
        ("大客户销售总监", "冬季是部分制造企业的业务淡季，几家签了有效年度最低消费保底协议的客户本月实际用量不到保底线的一半，销售申请当月实际用多少就收多少，暂时屏蔽有效合同的最低保底补齐逻辑。"),
        ("渠道生态合作部", "代理商大会纪要（二零二五年年中旧稿）曾提议客户只要完成对公现金预充值或缴纳履约保证金，当月即可提前给渠道结算返佣，不用等账单真正扣款结清，渠道商催问能否按旧纪要放开。"),
        ("华南渠道经理", "合作代理商反馈他们帮客户争取了大量平台赠送金券并引导客户用券结清了月费，认为体验金抵扣部分也体现了渠道推广价值，要求把体验金支付额按五折计入渠道返佣基数。"),
        ("品牌市场部", "有新注册客户拿着去年印制的旧版宣传折页截图找过来，说上面印的基础版每月免费调用额度是一万五千次，而现在系统里只给一万次，市场部问要不要干脆把基础版默认配额调高到一万五千次平息抱怨。"),
        ("架构演进讨论群", "听说代码库里其实已经预埋了一套全新的第三代分段资费流水线开关，只是默认没打开；既然现在第二代计费在期中变配上老出毛病，不如直接把第三代计费总开关打开一劳永逸？"),
        ("跨境大客户经理", "一家注册在新加坡的物流企业由其境内关联公司代为报销费用，对方财务强烈要求我们放开限制，直接为新加坡税制账单开具中国境内百分之六税率的增值税专用发票以便境内抵扣。"),
        ("客服中心组长", "一位纯用营销赠送金全额抵扣完月费（现金实付为零元）的客户坚持索要国内增值税普通发票入账，声称平台赠券属于视同销售必须开票，请问是否需要放开零现金账单的开票拦截？"),
        ("外部审计沟通协调", "事业部销售副总裁转来邮件：虽然十月份账期已经显示关账，但按行业惯例每月十五日纳税申报截止前属于关账缓冲调整期，要求后台放开限制直接把十月那笔五百九十九元的争议归档账单改低两百元。"),
        ("销售运营支持", "九月份有笔历史超额多收两百元的已结清老账单、十月份也有笔多收一百五十元的历史老账单，客户希望能直接修改九月和十月原账单上的数字，这样他们重新导出三季度历史账单明细时表面更好看。"),
        ("重点客户保障组", "上月机房网络抖动导致某大客户可用性跌破承诺线，客户拿着友商赔偿条款要求我们按故障时长双倍退还可提现现金到余额，而不是发放不可提现的服务抵用额度。"),
        ("小微企业服务组", "部分小额价外税企业客户反馈每月几百元的账单还要额外加收百分之六税费太琐碎，建议对未满两千元的价外税账单直接免征增值税，只对两千元以上大单收税。"),
        ("运营效率改进组", "大促周期间财务总监出差频繁，五千元以上退费和调账单在队列里排队等双人会签太慢了，客服主管建议把强制双签的内控门槛临时从五千元上调到两万元。"),
        ("基础架构清理建议", "排查代码时看到工程里躺着好几个二零二三、二零二四年的历史过渡兼容目录和对账适配包，看着很碍眼，能不能顺手把这些老归档目录整包物理删掉给仓库瘦身？"),
        ("资金管理专员", "在看十三周滚动现金流预测表时，业务部门觉得把争议冻结中的未收账款打折太保守，建议把所有争议未决账单按百分之百确定回款计入未来两周可用现金池。"),
        ("银企结算运维", "海外代理行发来的跨境电文对账单偶尔会有汇率尾差，清算组有人提议把电文自动对账容差直接从两分钱放宽到五十元整，省得每天人工核对差异单。"),
        ("客户技术支持单", "某企业运维询问十一月十一日下午两点多为什么有一条账单通知回调隔了一分钟才收到——查了记录第一次推送超时后系统隔六十秒重试第二次就已经返回成功了，想确认这是否属于正常重试机制。"),
        ("KA 客户日常答疑", "一家签了每月两千二百元保底消费协议的年框企业客户来问，他们十一月实际调用很少、也没产生超额，为什么预览基础账单金额显示两千二百元而不是公开牌价的一千九百九十九元？"),
        ("税务咨询坐席", "一位客户十月底账单总价五百九十九元，其中用了两百元活动赠送金、实付三百九十九元现金，来电询问为什么申请开具数电专票时系统最高只允许开三百九十九元而不是五百九十九元？"),
        ("合规内审日常问询", "集团内审例行抽查询问：对于三百元以内的常规小额账务差错调账，现行系统走单人初审通过即可生效、超过五千元才强制要求双人异号复核，这一梯度是否符合现行三版账务内控规范？"),
    ]

    assert len(raw_items) == 68, f"Expected 68 feedback items, got {len(raw_items)}"
    rng.shuffle(raw_items)

    # 严苛防剧透校验：严禁包含任何路由、文件名、表名、字段名、配置项或具体租户/账单编号
    forbidden_tokens = [
        "/api/", "/health", ".py", ".js", ".sql", ".db", ".md",
        "invoices", "wallets", "promo_grants", "usage_events", "usage_summaries",
        "billing_adjustments", "fapiao_requests", "gl_journal_entries", "settlement_dlq",
        "escrow_accounts", "fx_rates", "fx_settlement_logs", "deferred_revenue",
        "partner_commissions", "partner_referrals", "approval_tickets", "dunning_cases",
        "bank_statement", "webhook_outbox", "sys_runtime_configs", "dispute_tickets",
        "_cents", "_bps", "period_key", "tenant_id", "invoice_id",
        "ENABLE_V3", "PENDING_SETTLE", "ACTIVE_LEGACY", "YUAN_STR", "LOCKED_PREVIEW",
        "RED_REVERSED", "RED_ISSUED", "CN_VAT", "SG_GST", "STARTER", "ENTERPRISE",
        "PLATINUM", "SILVER", "GOLD", "SUSPENDED", "CALCULATED", "PAID_OUT",
        "t_cust_", "t_leg_", "INV-", "FP-", "PTN_", "ctr_", "apv_", "pg_", "bsi_",
    ]
    for src_dept, body in raw_items:
        joined = f"{src_dept} {body}"
        for tok in forbidden_tokens:
            if tok.lower() in joined.lower():
                raise AssertionError(f"Forbidden technical spoiler '{tok}' found in feedback item: {joined}")

    lines = [
        "# 客户与内部业务反馈汇总单（2026-11 账期救火批次）",
        "",
        "> **值班说明**：以下 `F01`～`F68` 为近期客服坐席、销售内勤、财务各岗位与内控专员从不同渠道提报的原始业务反馈（按提报流水混排，未做技术预筛）。",
        "> 其中既包含真实系统缺陷引发的业务表象与多部门重复抱怨，也混杂了引用过期作废纪要的不合规诉求、边界模糊的财税试探以及正常规则咨询；**此外，部分底层批处理、对账子账本与内控链路故障尚未被前台察觉提单**，请结合权威《产品与账务规则》（v3.0）、生产多源日志与全库账务勾稽自行甄别排查。",
        "",
    ]
    for idx, (dept, content) in enumerate(raw_items, start=1):
        lines.append(f"- **`F{idx:02d}`** 【来源：{dept}】：{content}")
    lines.append("")

    out_path = TEMPLATE_DIR / "反馈汇总单.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return len(raw_items)


def build_database() -> dict:
    rng = random.Random(20261114)
    db_path = str(TEMPLATE_DIR / "data" / "yunce_billing.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = get_connection(db_path)
    try:
        init_schema(conn)

        # ------------------------------------------------------------------
        # 0. 运行期动态配置、外汇基准牌价与总代二级分润层级
        # ------------------------------------------------------------------
        conn.executemany(
            """INSERT INTO sys_runtime_configs (config_key, config_value, env_scope, updated_by, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            [
                ("waive_upgrade_proration_promo_window", "false", "PROD", "ops_zhaokai", "2026-11-08T10:15:00Z"),
                ("golden4_gateway_timeout_ms", "3500", "PROD", "sre_zhouming", "2026-10-15T09:00:00Z"),
                ("batch_ingest_max_events", "500", "PROD", "gateway_team", "2026-10-20T12:00:00Z"),
            ],
        )

        conn.executemany(
            "INSERT INTO fx_rates (currency_code, effective_date, rate_bps, source) VALUES (?, ?, ?, 'PBOC_MID')",
            [
                ("USD", "2026-10-01", 71200),
                ("USD", "2026-11-01", 71850),
                ("USD", "2026-11-12", 72400),
                ("SGD", "2026-10-01", 53100),
                ("SGD", "2026-11-01", 53600),
                ("SGD", "2026-11-12", 54100),
                ("EUR", "2026-11-01", 77900),
                ("EUR", "2026-11-12", 78250),
            ],
        )

        conn.executemany(
            """INSERT INTO partner_hierarchy (child_partner_code, parent_partner_code, parent_tier_bps, child_tier_bps, status)
               VALUES (?, ?, ?, ?, 'ACTIVE')""",
            [
                ("PTN_SOUTH_SUB1", "PTN_EAST", 1200, 800),
                ("PTN_NORTH_SUB1", "PTN_NORTH", 1500, 1200),
            ],
        )

        # ------------------------------------------------------------------
        # 1. 创建 20 个 2024 v1 存量老租户 (t_leg_001 .. t_leg_020)
        # ------------------------------------------------------------------
        legacy_names = [
            "华东老牌制造集团", "星辰传统物流", "南洋纺织实业", "北方重工机械", "长三角塑化贸易",
            "津门港务货运", "中原农机配件", "宏达五金建材", "海燕日化集团", "顺发纸业包装",
            "恒信模具加工", "永泰食品冷链", "国瑞电缆制造", "振华陶瓷工艺", "昌盛汽配连锁",
            "万丰粮油储运", "泰山矿山设备", "江南印染纺织", "三江水电物资", "鸿运建材批发",
        ]
        for i in range(1, 21):
            tid = f"t_leg_{i:03d}"
            disc_bps = 1000 if i == 1 else (500 if i % 3 == 0 else 0)
            meta = json.dumps({"legacy_discount_bps": disc_bps, "migrated_from": "erp_2024_q4"})
            conn.execute(
                """INSERT INTO tenants (id, company_name, api_token, status, tier_level, tax_profile_code,
                   partner_code, webhook_url, schema_version, billing_metadata, created_at)
                   VALUES (?, ?, ?, 'ACTIVE_LEGACY', 'STANDARD', 'EXEMPT', NULL, '', 1, ?, ?)""",
                (tid, legacy_names[i - 1], f"tok_leg_{i:03d}", meta, f"2024-0{(i % 8) + 1}-10T00:00:00Z"),
            )
            override = None
            if i == 1:
                override = json.dumps({"fixed_fee_cents": 9900, "included_quota": 20000, "overage_cap_cents": 5000})
            elif i % 4 == 0:
                override = json.dumps({"fixed_fee_cents": 8800, "included_quota": 25000})

            conn.execute(
                """INSERT INTO subscriptions (id, tenant_id, plan_code, status, cycle_start, cycle_end,
                   next_billing_at, auto_renew, tier_mode, legacy_contract_override, updated_at)
                   VALUES (?, ?, 'LEGACY_FLAT_99', 'ACTIVE_LEGACY', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                   '2026-12-01T00:00:00Z', 1, NULL, ?, '2026-11-01T00:00:00Z')""",
                (f"sub_leg_{i:03d}", tid, override),
            )
            cash = 45000 + i * 2500
            conn.execute(
                "INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, 0, '2026-11-01T00:00:00Z')",
                (tid, cash),
            )
            fee_09 = 8910 if i == 1 else (8800 if i % 4 == 0 else (9405 if i % 3 == 0 else 9900))
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '初始结转充值', '2026-08-25T08:00:00Z')",
                (tid, cash + fee_09, f"top_leg_{i:03d}"),
            )

            yuan_str = f"{fee_09 // 100}.{fee_09 % 100:02d}"
            inv_09_id = f"INV-202609-L{i:03d}"
            conn.execute(
                """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                   base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                   currency_unit, raw_legacy_total, status, dispute_reason, created_at, updated_at)
                   VALUES (?, ?, '2026-09', '2026-09-01T00:00:00Z', '2026-10-01T00:00:00Z', 'LEGACY_FLAT_99',
                   ?, 0, 0, 0, ?, ?, 0, 'YUAN_STR', ?, 'PAID', '', '2026-09-30T23:00:00Z', '2026-10-01T00:10:00Z')""",
                (inv_09_id, tid, fee_09, fee_09, fee_09, yuan_str),
            )
            conn.execute(
                "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-10-01T00:10:00Z')",
                (f"pay_09_l{i:03d}", inv_09_id, tid, f"leg09:{inv_09_id}", fee_09, fee_09),
            )
            conn.execute(
                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, '9月老合同扣款', '2026-10-01T00:10:00Z')",
                (tid, -fee_09, inv_09_id),
            )

        # ------------------------------------------------------------------
        # 2. 创建 220 个 v2 现代租户 (t_cust_001 .. t_cust_220)，总计 240 家租户
        # ------------------------------------------------------------------
        plan_overrides = {
            4: "ENTERPRISE", 5: "PRO", 8: "STARTER", 10: "PRO", 12: "PRO", 14: "PRO",
            15: "ENTERPRISE", 18: "PRO", 20: "ENTERPRISE", 22: "PRO", 24: "PRO", 25: "PRO",
            26: "ENTERPRISE", 28: "ENTERPRISE", 29: "PRO", 30: "ENTERPRISE",
            # Dirty IDs exact plans:
            31: "STARTER", 36: "STARTER", 41: "PRO", 46: "PRO",
            51: "ENTERPRISE", 56: "ENTERPRISE", 61: "ENTERPRISE", 66: "ENTERPRISE",
            71: "STARTER", 76: "PRO", 81: "ENTERPRISE", 86: "PRO",
            91: "PRO", 96: "STARTER", 101: "ENTERPRISE", 106: "PRO", 111: "ENTERPRISE",
            116: "PRO", 121: "STARTER", 126: "ENTERPRISE", 131: "PRO",
            136: "STARTER", 141: "PRO", 146: "STARTER", 151: "PRO", 156: "PRO", 161: "ENTERPRISE",
            166: "STARTER", 171: "PRO", 176: "PRO", 181: "ENTERPRISE",
            185: "ENTERPRISE", 188: "PRO", 191: "PRO", 193: "ENTERPRISE",
            196: "PRO", 199: "ENTERPRISE", 202: "PRO", 205: "PRO",
            208: "PRO", 210: "ENTERPRISE", 212: "PRO", 214: "PRO", 216: "ENTERPRISE",
            218: "ENTERPRISE", 219: "STARTER", 220: "ENTERPRISE",
        }

        for i in range(1, 221):
            tid = f"t_cust_{i:03d}"
            cname = SPECIAL_NAMES.get(
                tid,
                f"{COMPANY_PREFIXES[i % len(COMPANY_PREFIXES)]}{COMPANY_SUFFIXES[(i * 3) % len(COMPANY_SUFFIXES)]}{i:03d}",
            )
            plan_code = plan_overrides.get(i, ["STARTER", "STARTER", "PRO", "PRO", "ENTERPRISE"][i % 5])
            tier_level = "VIP" if (plan_code == "ENTERPRISE" or i in (5, 12)) else "STANDARD"

            if i in (15, 46, 51, 56) or (i not in DIRTY_IDS and i % 17 == 0):
                tax_code = "CN_VAT_6_EXCLUSIVE"
            elif i in (29, 188) or (i not in DIRTY_IDS and i % 29 == 0):
                tax_code = "SG_GST_9_EXCLUSIVE"
            elif i in (185, 220):
                tax_code = "EXEMPT"
            else:
                tax_code = "CN_VAT_6_INCLUSIVE"

            # 渠道绑定设计：PTN_SOUTH 严格受控用于验证跨期退款扣回、归因时间窗与虚高晋升防护
            p_info = None
            bound_at = "2025-06-01T00:00:00Z"
            if i in (20, 218):
                p_info = ("PTN_SOUTH", "SILVER")
            elif i == 22:
                p_info = ("PTN_SOUTH", "SILVER")
                bound_at = "2026-11-10T00:00:00Z"  # 晚于 11-02 回款，测试 BUG-43
            elif i == 26:
                p_info = ("PTN_SOUTH_SUB1", "SILVER")
            elif i not in DIRTY_IDS and i > 30 and i % 6 == 0:
                p_info = ("PTN_EAST", "GOLD") if (i % 12 == 0) else ("PTN_NORTH", "PLATINUM")

            if i == 25:
                wh_url = "https://unreachable.invalid/webhook"
            else:
                wh_url = f"https://hooks.customer-{i:03d}.example.com/billing" if i % 5 == 0 else ""

            meta_json = json.dumps({"intercompany": True, "subsidiary_code": "YUNCE_HK_INTERNAL"}) if i == 30 else "{}"
            t_status = "SUSPENDED" if i in (86, 202, 205) else "ACTIVE"

            conn.execute(
                """INSERT INTO tenants (id, company_name, api_token, status, tier_level, tax_profile_code,
                   partner_code, webhook_url, schema_version, billing_metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2, ?, ?)""",
                (
                    tid,
                    cname,
                    f"tok_cust_{i:03d}",
                    t_status,
                    tier_level,
                    tax_code,
                    p_info[0] if p_info else None,
                    wh_url,
                    meta_json,
                    f"2025-{(i % 12) + 1:02d}-{(i % 25) + 1:02d}T08:00:00Z",
                ),
            )
            if p_info:
                conn.execute(
                    "INSERT INTO partner_referrals (partner_code, tenant_id, partner_tier, bound_at) VALUES (?, ?, ?, ?)",
                    (p_info[0], tid, p_info[1], bound_at),
                )

            # 第一条 ACTIVE 企业框架合同固定为 ctr_004 (min_monthly_commit_cents=220000)，保障存量单测契约
            if i == 4 or (plan_code == "ENTERPRISE" and i not in DIRTY_IDS and i not in (15, 20, 26, 28, 30) and i % 10 == 4):
                conn.execute(
                    """INSERT INTO enterprise_contracts (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps,
                       credit_memo_bps, credit_limit_cents, signed_by, valid_from, valid_until, status)
                       VALUES (?, ?, 220000, 1000, 0, 500000, 'ka_director', '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', 'ACTIVE')""",
                    (f"ctr_{i:03d}", tid),
                )

            sub_status = "SUSPENDED" if i in (86, 202, 205) else ("CANCELLED_AT_PERIOD_END" if i == 17 else "ACTIVE")
            auto_renew = 0 if i in (17, 86) else 1
            sub_updated = "2026-10-28T00:00:00Z" if i == 86 else "2026-11-01T00:00:00Z"
            conn.execute(
                """INSERT INTO subscriptions (id, tenant_id, plan_code, status, cycle_start, cycle_end,
                   next_billing_at, auto_renew, tier_mode, legacy_contract_override, updated_at)
                   VALUES (?, ?, ?, ?, '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z',
                   '2026-12-01T00:00:00Z', ?, 'PROGRESSIVE', NULL, ?)""",
                (f"sub_cust_{i:03d}", tid, plan_code, sub_status, auto_renew, sub_updated),
            )

            # 健康租户生成完全自洽的钱包、2026-09/10 历史关账单与 2026-11 当期账单
            if i not in DIRTY_IDS:
                init_topup = 420000 if plan_code == "ENTERPRISE" else (220000 if plan_code == "PRO" else 90000)
                cash_bal = init_topup
                promo_bal = 0
                conn.execute(
                    "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '银行公户充值', '2026-09-01T09:00:00Z')",
                    (tid, init_topup, f"top_init_{i:03d}"),
                )

                if i == 8:
                    promo_bal = 10000
                    conn.execute(
                        "INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_008', ?, 10000, 10000, 'ACTIVE', '2026-12-31T23:59:59Z', 'Q4_RETENTION', '2026-11-01T00:00:00Z')",
                        (tid,),
                    )
                    conn.execute(
                        "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'PROMO_GRANT', 0, 10000, 'pg_cust_008', '活动赠送金', '2026-11-01T00:00:00Z')",
                        (tid,),
                    )

                for m_idx, pk in enumerate(("2026-09", "2026-10")):
                    force_hist = i in (4, 5, 8, 12, 15, 18, 20, 24, 28)
                    if (i % 2 != m_idx % 2) and not force_hist:
                        continue
                    pl = PLANS[plan_code]
                    qty = rng.randint(2000, pl["included_quota"] + 12000)
                    if i == 5 and pk == "2026-10":
                        qty = 120000  # PRO 超 7 万 -> 50k*2 + 20k*1 = 120000
                    elif i == 12 and pk == "2026-09":
                        qty = 70000   # 历史多收 20000 分待 11 月跨期冲抵
                    elif i == 24 and pk == "2026-10":
                        qty = 62500   # 实际超 12500 次=25000 分，历史错收 40000 分（多收 15000 分待 11 月跨期冲抵）
                    elif i == 18 and pk == "2026-10":
                        qty = 30000   # 销售施压要求直接篡改的 10 月合规关账单

                    conn.execute(
                        "INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (tid, pk, plan_code, qty, f"{pk}-28T23:00:00Z"),
                    )
                    raw_ov = compute_tiered_overage_cents(qty, pl["included_quota"], pl["overage_tiers"])
                    ctr_res = apply_enterprise_contract_terms(conn, tid, pl["monthly_fee_cents"], raw_ov, as_of_iso=f"{pk}-15T00:00:00Z")
                    eff_base = ctr_res["base_fee_cents"] + ctr_res["commit_topup_cents"]
                    eff_ov = ctr_res["overage_fee_cents"]

                    if i == 12 and pk == "2026-09":
                        inv_id = "INV-202609-0012"
                        eff_ov = 60000
                        tax_c = 0
                        tot = eff_base + eff_ov
                        disp = "9月历史超额核算多收200元，账期已关账待跨期冲抵"
                    elif i == 24 and pk == "2026-10":
                        inv_id = "INV-202610-0024"
                        eff_ov = 40000
                        tax_c = 0
                        tot = eff_base + eff_ov
                        disp = "10月历史超额核算多收150元，账期已关账待跨期冲抵"
                    else:
                        inv_id = f"INV-{pk.replace('-', '')}-{i:04d}"
                        tx = compute_tax_breakdown(ctr_res["subtotal_cents"], tax_code)
                        tax_c = tx["tax_added_cents"]
                        tot = tx["gross_total_cents"]
                        disp = ""

                    if cash_bal < tot + 60000:
                        extra = 350000
                        cash_bal += extra
                        conn.execute(
                            "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '续费补充值', ?)",
                            (tid, extra, f"top_{pk}_{i:03d}", f"{pk}-25T10:00:00Z"),
                        )

                    cash_bal -= tot
                    conn.execute(
                        """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                           base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                           currency_unit, status, dispute_reason, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 0, 'CENTS', 'PAID', ?, ?, ?)""",
                        (inv_id, tid, pk, f"{pk}-01T00:00:00Z", f"{pk}-30T23:59:59Z", plan_code, eff_base, eff_ov, tax_c, tot, tot, disp, f"{pk}-29T00:00:00Z", f"{pk}-29T01:00:00Z"),
                    )
                    conn.execute(
                        "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                        (f"pay_{pk}_{i:03d}", inv_id, tid, f"auto:{inv_id}", tot, tot, f"{pk}-29T01:00:00Z"),
                    )
                    conn.execute(
                        "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, ?, ?)",
                        (tid, -tot, inv_id, f"支付账单 {inv_id}", f"{pk}-29T01:00:00Z"),
                    )

                # PTN_SOUTH 名下 t_cust_020 在 2026-11-06 对 10 月已结清账单发生 120000 分现金退费（跨期扣回场景 BUG-39）
                if i == 20:
                    cash_bal += 120000
                    conn.execute("UPDATE invoices SET refunded_cents = 120000 WHERE id = 'INV-202610-0020'")
                    conn.execute(
                        "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_020', 'REFUND', 120000, 0, 'INV-202610-0020', '10月定制模块核减退现', '2026-11-06T10:00:00Z')"
                    )

                # 生成 2026-11 当期正常健康账单（严格遵循有效框架合同与价外税，确保无任何误报）
                qty_11 = rng.randint(1000, PLANS[plan_code]["included_quota"] // 2)
                conn.execute(
                    "INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, ?, '2026-11-13T12:00:00Z')",
                    (tid, plan_code, qty_11),
                )
                if i != 20 and (i % 3 == 0 or i in (4, 12, 15, 22, 24, 26, 30)):
                    ctr_11 = apply_enterprise_contract_terms(
                        conn, tid, PLANS[plan_code]["monthly_fee_cents"], 0, as_of_iso="2026-11-15T00:00:00Z"
                    )
                    base_11 = ctr_11["base_fee_cents"] + ctr_11["commit_topup_cents"]
                    # 小额价外税健康租户保持 < 200000 分正常计税
                    tx_11 = compute_tax_breakdown(ctr_11["subtotal_cents"], tax_code)
                    tot_11 = tx_11["gross_total_cents"]
                    inv_11_id = f"INV-202611-{i:04d}"
                    is_paid = (i % 6 == 0 or i in (12, 15, 22, 24, 26, 30))
                    if is_paid:
                        if cash_bal < tot_11 + 20000:
                            cash_bal += 300000
                            conn.execute(
                                "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', 300000, 0, ?, '11月预存充值', '2026-11-01T08:00:00Z')",
                                (tid, f"top11_{i:03d}"),
                            )
                        cash_bal -= tot_11
                        conn.execute(
                            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                               currency_unit, status, dispute_reason, created_at, updated_at)
                               VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, ?, 0, ?, ?, 0, 'CENTS', 'PAID', '', '2026-11-02T00:00:00Z', '2026-11-02T00:10:00Z')""",
                            (inv_11_id, tid, plan_code, base_11, tx_11["tax_added_cents"], tot_11, tot_11),
                        )
                        conn.execute(
                            "INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-02T00:10:00Z')",
                            (f"pay_11_{i:03d}", inv_11_id, tid, f"auto:{inv_11_id}", tot_11, tot_11),
                        )
                        conn.execute(
                            "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, ?, '2026-11-02T00:10:00Z')",
                            (tid, -tot_11, inv_11_id, f"支付账单 {inv_11_id}"),
                        )
                    else:
                        # 赋予部分健康账单相同时间戳，用于复现分页导出缺次级排序键错位 (BUG-55)
                        created_ts = "2026-11-05T00:00:00Z"
                        conn.execute(
                            """INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code,
                               base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents,
                               currency_unit, status, dispute_reason, created_at, updated_at)
                               VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, ?, 0, ?, 0, 0, 'CENTS', 'OPEN', '', ?, ?)""",
                            (inv_11_id, tid, plan_code, base_11, tx_11["tax_added_cents"], tot_11, created_ts, created_ts),
                        )

                conn.execute(
                    "INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, ?, '2026-11-13T00:00:00Z')",
                    (tid, cash_bal, promo_bal),
                )

        # ------------------------------------------------------------------
        # 3. 埋设 2026-11 (OPEN) 全部 44 处跨表脏账与子账本关联现场
        # ------------------------------------------------------------------
        def _seed_simple_wallet(tid: str, cash: int, promo: int = 0) -> None:
            conn.execute(
                "INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, ?, '2026-11-10T09:00:00Z')",
                (tid, cash, promo),
            )
            if cash > 0:
                conn.execute(
                    "INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '公户充值', '2026-11-01T09:00:00Z')",
                    (tid, cash, f"top_{tid}"),
                )

        # === Cat 1 (4): 期中变配分段超额错算 ===
        # A2-01: t_cust_031 ENTERPRISE(80k)->STARTER(5k)，真超额 0，错算 135000 -> total 19900
        _seed_simple_wallet("t_cust_031", 200000)
        conn.execute("INSERT INTO plan_change_history (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason) VALUES ('sub_cust_031', 't_cust_031', 'ENTERPRISE', 'STARTER', '2026-11-10T10:00:00Z', 0, 'cost_opt')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_031', '2026-11', 'ENTERPRISE', 80000, '2026-11-10T09:59:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_031', '2026-11', 'STARTER', 5000, '2026-11-12T12:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0031', 't_cust_031', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'STARTER', 19900, 135000, 0, 0, 154900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T12:30:00Z', '2026-11-12T12:30:00Z')")

        # A2-02: t_cust_036 PRO(42k)->STARTER(15k)，真超额 15000，错算 104000 -> total 34900
        _seed_simple_wallet("t_cust_036", 150000)
        conn.execute("INSERT INTO plan_change_history (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason) VALUES ('sub_cust_036', 't_cust_036', 'PRO', 'STARTER', '2026-11-08T14:00:00Z', 0, 'seasonal')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_036', '2026-11', 'PRO', 42000, '2026-11-08T13:59:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_036', '2026-11', 'STARTER', 15000, '2026-11-12T18:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0036', 't_cust_036', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'STARTER', 19900, 104000, 0, 0, 123900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T18:30:00Z', '2026-11-12T18:30:00Z')")

        # A2-03: t_cust_041 STARTER(18k, 超8k=24000)->PRO(25k, 超0)，合算43k按PRO被漏算成0 -> 真 overage=24000, total=83900
        _seed_simple_wallet("t_cust_041", 160000)
        conn.execute("INSERT INTO plan_change_history (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason) VALUES ('sub_cust_041', 't_cust_041', 'STARTER', 'PRO', '2026-11-09T14:18:00Z', 0, 'scale_up')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_041', '2026-11', 'STARTER', 18000, '2026-11-09T14:17:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_041', '2026-11', 'PRO', 25000, '2026-11-13T10:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0041', 't_cust_041', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-13T10:30:00Z', '2026-11-13T10:30:00Z')")

        # A2-04: t_cust_046 (CN_VAT_6_EXCLUSIVE) ENTERPRISE(260k, 超0)->PRO(60k, 超10k=20000)，真 base=59900, ov=20000, tax=4794, total=84694
        _seed_simple_wallet("t_cust_046", 400000)
        conn.execute("INSERT INTO plan_change_history (subscription_id, tenant_id, old_plan_code, new_plan_code, effective_at, proration_cents, reason) VALUES ('sub_cust_046', 't_cust_046', 'ENTERPRISE', 'PRO', '2026-11-11T09:00:00Z', 0, 'rightsize')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_046', '2026-11', 'ENTERPRISE', 260000, '2026-11-11T08:59:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_046', '2026-11', 'PRO', 60000, '2026-11-13T11:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0046', 't_cust_046', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 59900, 320000, 0, 0, 379900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-13T11:30:00Z', '2026-11-13T11:30:00Z')")

        # === Cat 2 (4): 价外税热补丁抹零 + 过期框架合同误套 ===
        # A2-05: t_cust_051 ENTERPRISE CN_VAT_6_EXCLUSIVE 320k -> base=199900, ov=20000, tax=13194, total=233094 (错算 tax=0, total=219900)
        _seed_simple_wallet("t_cust_051", 500000)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_051', '2026-11', 'ENTERPRISE', 320000, '2026-11-11T22:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0051', 't_cust_051', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 199900, 20000, 0, 0, 219900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-11T22:10:00Z', '2026-11-11T22:10:00Z')")

        # A2-06: t_cust_056 ENTERPRISE CN_VAT_6_EXCLUSIVE 350k -> base=199900, ov=50000, tax=14994, total=264894 (错算 tax=0, total=249900)
        _seed_simple_wallet("t_cust_056", 500000)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_056', '2026-11', 'ENTERPRISE', 350000, '2026-11-12T08:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0056', 't_cust_056', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 199900, 50000, 0, 0, 249900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T08:10:00Z', '2026-11-12T08:10:00Z')")

        # A2-07: t_cust_061 合同已于 2026-09-30 过期，180k 用量被误补保底至 260000 -> 真 base=199900, ov=0, total=199900
        _seed_simple_wallet("t_cust_061", 400000)
        conn.execute("INSERT INTO enterprise_contracts (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps, credit_memo_bps, credit_limit_cents, signed_by, valid_from, valid_until, status) VALUES ('ctr_exp_061', 't_cust_061', 260000, 2000, 0, 0, 'ka_dir', '2025-09-01T00:00:00Z', '2026-09-30T23:59:59Z', 'ACTIVE')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_061', '2026-11', 'ENTERPRISE', 180000, '2026-11-12T09:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0061', 't_cust_061', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 260000, 0, 0, 0, 260000, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T09:15:00Z', '2026-11-12T09:15:00Z')")

        # A2-08: t_cust_066 合同已于 2026-10-15 过期，340k 用量被误套 25% 超额折扣算成 ov=30000 -> 真 base=199900, ov=40000, total=239900
        _seed_simple_wallet("t_cust_066", 400000)
        conn.execute("INSERT INTO enterprise_contracts (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps, credit_memo_bps, credit_limit_cents, signed_by, valid_from, valid_until, status) VALUES ('ctr_exp_066', 't_cust_066', 0, 2500, 0, 0, 'ka_dir', '2025-10-01T00:00:00Z', '2026-10-15T23:59:59Z', 'ACTIVE')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_066', '2026-11', 'ENTERPRISE', 340000, '2026-11-12T09:30:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0066', 't_cust_066', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 199900, 30000, 0, 0, 229900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-12T09:45:00Z', '2026-11-12T09:45:00Z')")

        # === Cat 3 (4): 同周期重复续费单 + 停机租户误出单 ===
        for dup_id, p_code, fee in ((71, "STARTER", 19900), (76, "PRO", 59900), (81, "ENTERPRISE", 199900)):
            tid = f"t_cust_{dup_id:03d}"
            _seed_simple_wallet(tid, fee * 2)
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 2000, '2026-11-11T00:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'OPEN', '', '2026-11-11T00:00:01Z', '2026-11-11T00:00:01Z')", (f"INV-202611-{dup_id:04d}", tid, p_code, fee, fee))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'OPEN', '', '2026-11-11T00:00:02Z', '2026-11-11T00:00:02Z')", (f"INV-202611-{dup_id + 900:04d}", tid, p_code, fee, fee))

        # A2-12: t_cust_086 10月欠费停机且 auto_renew=0，11月被误滚出新账单 INV-202611-0086（应作废 11 月新单，保留停机状态与 10 月欠费单）
        _seed_simple_wallet("t_cust_086", 0)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_086', '2026-10', 'PRO', 12000, '2026-10-25T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202610-0086', 't_cust_086', '2026-10', '2026-09-25T00:00:00Z', '2026-10-25T00:00:00Z', 'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '', '2026-09-25T00:00:00Z', '2026-10-28T00:00:00Z')")
        conn.execute("INSERT INTO dunning_cases (id, tenant_id, invoice_id, stage, overdue_days, unpaid_cents, last_notified_at, status, updated_at) VALUES ('dun_086', 't_cust_086', 'INV-202610-0086', 'SUSPENDED', 35, 59900, '2026-10-28T00:00:00Z', 'OPEN', '2026-10-28T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0086', 't_cust_086', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 59900, 0, 0, 0, 59900, 0, 0, 'CENTS', 'OPEN', '', '2026-11-11T00:00:03Z', '2026-11-11T00:00:03Z')")

        # === Cat 4 (5): PENDING_SETTLE 中间态卡死账单 ===
        # A2-13, A2-14: 已全额现金扣款，卡死在 PENDING_SETTLE (paid_cents=0)
        for ps_id, p_code, fee in ((91, "PRO", 59900), (96, "STARTER", 19900)):
            tid = f"t_cust_{ps_id:03d}"
            inv_id = f"INV-202611-{ps_id:04d}"
            conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, 40100, 0, '2026-11-11T00:05:00Z')", (tid,))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '现金充值', '2026-11-01T08:00:00Z')", (tid, fee + 40100, f"top_{ps_id}"))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, ?, '2026-11-11T00:05:00Z')", (tid, -fee, inv_id, f"支付账单 {inv_id}"))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 3000, '2026-11-10T12:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'PENDING_SETTLE', '', '2026-11-11T00:05:00Z', '2026-11-11T00:05:00Z')", (inv_id, tid, p_code, fee, fee))
            conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-11T00:05:00Z')", (f"pay_11_{ps_id:03d}", inv_id, tid, f"auto:{inv_id}", fee, fee))

        # A2-15: t_cust_101 混合扣款 150000 现金 + 49900 赠金 = 199900，卡死在 PENDING_SETTLE
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_101', 50000, 0, '2026-11-11T00:05:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_101', 't_cust_101', 49900, 0, 'DEPLETED', '2026-12-31T23:59:59Z', 'KA_GIFT', '2026-11-01T00:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_101', 'TOPUP', 200000, 0, 'top_101', '充值', '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_101', 'PROMO_GRANT', 0, 49900, 'pg_cust_101', '礼金', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_101', 'INVOICE_PAY', -150000, -49900, 'INV-202611-0101', '支付账单 INV-202611-0101', '2026-11-11T00:05:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_101', '2026-11', 'ENTERPRISE', 50000, '2026-11-10T12:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0101', 't_cust_101', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 199900, 0, 0, 0, 199900, 0, 0, 'CENTS', 'PENDING_SETTLE', '', '2026-11-11T00:05:00Z', '2026-11-11T00:05:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_101', 'INV-202611-0101', 't_cust_101', 'auto:INV-202611-0101', 150000, 49900, 199900, '2026-11-11T00:05:00Z')")

        # A2-16, A2-17: 余额不足未扣款，卡死在 PENDING_SETTLE 且漏记 settlement_dlq
        for ps_id, p_code, fee, low_bal in ((106, "PRO", 59900, 12000), (111, "ENTERPRISE", 199900, 45000)):
            tid = f"t_cust_{ps_id:03d}"
            inv_id = f"INV-202611-{ps_id:04d}"
            _seed_simple_wallet(tid, low_bal)
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 4000, '2026-11-11T12:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'PENDING_SETTLE', '', '2026-11-12T00:05:00Z', '2026-11-12T00:05:00Z')", (inv_id, tid, p_code, fee, fee))

        # === Cat 5 (4): 死信重试无视已付差额超扣单与钱包 ===
        dlq_specs = [
            (116, "PRO", 59900, 20000, 90000, "PENDING"),
            (121, "STARTER", 19900, 8000, 40000, "PENDING"),
            (126, "ENTERPRISE", 199900, 50000, 300000, "PENDING"),
            (131, "PRO", 59900, 35000, 120000, "RESOLVED"),
        ]
        for d_id, p_code, fee, part_paid, total_topup, dlq_st in dlq_specs:
            tid = f"t_cust_{d_id:03d}"
            inv_id = f"INV-202611-{d_id:04d}"
            over_paid = part_paid + fee
            cur_cash = total_topup - over_paid
            conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, 0, '2026-11-12T02:15:00Z')", (tid, cur_cash))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 5000, '2026-11-10T12:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '公户充值', '2026-11-01T09:00:00Z')", (tid, total_topup, f"top_{d_id}"))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, '首笔部分实付', '2026-11-04T15:00:00Z')", (tid, -part_paid, inv_id))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, 'DLQ重试全额扣款', '2026-11-12T02:15:00Z')", (tid, -fee, inv_id))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, ?, 0, 'CENTS', 'PAID', '', '2026-11-03T10:00:00Z', '2026-11-12T02:15:00Z')", (inv_id, tid, p_code, fee, fee, over_paid))
            conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-04T15:00:00Z')", (f"pay_11_{d_id}_p1", inv_id, tid, f"part:{inv_id}", part_paid, part_paid))
            conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-12T02:15:00Z')", (f"pay_11_{d_id}_dlq", inv_id, tid, f"dlq:{inv_id}:1", fee, fee))
            conn.execute("INSERT INTO settlement_dlq (invoice_id, tenant_id, error_msg, retry_count, status, created_at, updated_at) VALUES (?, ?, '钱包余额不足', 1, ?, '2026-11-11T00:06:00Z', '2026-11-12T02:15:00Z')", (inv_id, tid, dlq_st))

        # === Cat 6 (6): 混合退费洗现、负数赠金与预览锁券钱包 ===
        # A2-22: t_cust_136 纯赠金付 19900 后退 10000 被误退入现金 -> 应为 cash=10000, promo=10100, pg_cust_136.remaining=10100
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_136', 20000, 100, '2026-11-12T09:00:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_136', 't_cust_136', 20000, 100, 'ACTIVE', '2026-12-31T23:59:59Z', 'Q4_PROMO', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_136', 'TOPUP', 10000, 0, 'top_136', '现金充值', '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_136', 'PROMO_GRANT', 0, 20000, 'pg_cust_136', '赠送金', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_136', 'INVOICE_PAY', 0, -19900, 'INV-202611-0136', '支付账单', '2026-11-02T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_136', 'REFUND', 10000, 0, 'INV-202611-0136', '部分退款', '2026-11-12T09:00:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_136', '2026-11', 'STARTER', 2000, '2026-11-10T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0136', 't_cust_136', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'STARTER', 19900, 0, 0, 0, 19900, 19900, 10000, 'CENTS', 'PAID', '', '2026-11-02T10:00:00Z', '2026-11-12T09:00:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_136', 'INV-202611-0136', 't_cust_136', 'ui:INV-202611-0136', 0, 19900, 19900, '2026-11-02T10:00:00Z')")

        # A2-23: t_cust_141 混合付 29900现金+30000赠金=59900，退 40000 全退成现金 -> 应退 29900 现金 + 10100 赠金 => cash=50000, promo=10100, pg_cust_141(ACTIVE, 10100)
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_141', 60100, 0, '2026-11-12T09:30:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_141', 't_cust_141', 30000, 0, 'DEPLETED', '2026-12-31T23:59:59Z', 'Q4_PROMO', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_141', 'TOPUP', 50000, 0, 'top_141', '现金充值', '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_141', 'PROMO_GRANT', 0, 30000, 'pg_cust_141', '赠送金', '2026-11-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_141', 'INVOICE_PAY', -29900, -30000, 'INV-202611-0141', '混合支付账单', '2026-11-03T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_141', 'REFUND', 40000, 0, 'INV-202611-0141', '混合支付部分退款', '2026-11-12T09:30:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_141', '2026-11', 'PRO', 10000, '2026-11-10T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0141', 't_cust_141', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 59900, 0, 0, 0, 59900, 59900, 40000, 'CENTS', 'PAID', '', '2026-11-03T10:00:00Z', '2026-11-12T09:30:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_141', 'INV-202611-0141', 't_cust_141', 'ui:INV-202611-0141', 29900, 30000, 59900, '2026-11-03T10:00:00Z')")

        # A2-24: t_cust_146 过期赠金重复扣成 -16000（无其他有效券 -> 应归正为 0）
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_146', 30000, -16000, '2026-11-12T00:01:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_146', 't_cust_146', 10000, 0, 'EXPIRED', '2026-11-01T00:00:00Z', 'OCT_GRANT', '2026-10-01T00:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_146', 'TOPUP', 43900, 0, 'top_146', '充值', '2026-10-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_146', 'PROMO_GRANT', 0, 10000, 'pg_cust_146', '十月赠金', '2026-10-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_146', 'INVOICE_PAY', -13900, -6000, 'INV-202610-0146', '十月扣款', '2026-10-28T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_146', 'PROMO_EXPIRE', 0, -10000, 'pg_cust_146', '到期清零', '2026-11-02T00:01:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_146', 'PROMO_EXPIRE', 0, -10000, 'pg_cust_146', '到期清零', '2026-11-12T00:01:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_146', '2026-10', 'STARTER', 3000, '2026-10-28T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202610-0146', 't_cust_146', '2026-10', '2026-10-01T00:00:00Z', '2026-10-30T23:59:59Z', 'STARTER', 19900, 0, 0, 0, 19900, 19900, 0, 'CENTS', 'PAID', '', '2026-10-28T09:00:00Z', '2026-10-28T10:00:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_10_146', 'INV-202610-0146', 't_cust_146', 'auto:INV-202610-0146', 13900, 6000, 19900, '2026-10-28T10:00:00Z')")

        # A2-25: t_cust_151 旧券过期重复扣 -30000，但另有一张未到期有效券 pg_cust_151_b (8000) -> 应归正为 promo_balance_cents = 8000（绝不可简单归零！）
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_151', 50000, -17000, '2026-11-12T00:01:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_151_a', 't_cust_151', 15000, 0, 'EXPIRED', '2026-11-01T00:00:00Z', 'OCT_GRANT', '2026-10-01T00:00:00Z')")
        conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES ('pg_cust_151_b', 't_cust_151', 8000, 8000, 'ACTIVE', '2026-12-31T23:59:59Z', 'NOV_CARE', '2026-11-03T00:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_151', 'TOPUP', 99900, 0, 'top_151', '充值', '2026-10-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_151', 'PROMO_GRANT', 0, 15000, 'pg_cust_151_a', '十月赠金', '2026-10-01T08:05:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_151', 'INVOICE_PAY', -49900, -10000, 'INV-202610-0151', '十月扣款', '2026-10-28T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_151', 'PROMO_GRANT', 0, 8000, 'pg_cust_151_b', '十一月关怀赠金', '2026-11-03T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_151', 'PROMO_EXPIRE', 0, -15000, 'pg_cust_151_a', '到期清零', '2026-11-02T00:01:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_151', 'PROMO_EXPIRE', 0, -15000, 'pg_cust_151_a', '到期清零', '2026-11-12T00:01:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_151', '2026-10', 'PRO', 12000, '2026-10-28T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202610-0151', 't_cust_151', '2026-10', '2026-10-01T00:00:00Z', '2026-10-30T23:59:59Z', 'PRO', 59900, 0, 0, 0, 59900, 59900, 0, 'CENTS', 'PAID', '', '2026-10-28T09:00:00Z', '2026-10-28T10:00:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_10_151', 'INV-202610-0151', 't_cust_151', 'auto:INV-202610-0151', 49900, 10000, 59900, '2026-10-28T10:00:00Z')")

        # A2-26, A2-27: GET 结算预览把未过期有效券锁成了 LOCKED_PREVIEW
        for lp_id, p_code, fee, grant_rem in ((156, "PRO", 59900, 15000), (161, "ENTERPRISE", 199900, 25000)):
            tid = f"t_cust_{lp_id:03d}"
            conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, 80000, ?, '2026-11-12T16:40:00Z')", (tid, grant_rem))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', 80000, 0, ?, '充值', '2026-11-01T10:00:00Z')", (tid, f"top_{lp_id}"))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'PROMO_GRANT', 0, ?, ?, '续签礼金', '2026-11-01T10:05:00Z')", (tid, grant_rem, f"pg_cust_{lp_id}"))
            conn.execute("INSERT INTO promo_grants (id, tenant_id, initial_cents, remaining_cents, status, expires_at, campaign_code, created_at) VALUES (?, ?, ?, ?, 'LOCKED_PREVIEW', '2026-12-31T23:59:59Z', 'ANNUAL_GIFT', '2026-10-15T00:00:00Z')", (f"pg_cust_{lp_id}", tid, grant_rem, grant_rem))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 8000, '2026-11-12T12:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'OPEN', '', '2026-11-10T09:00:00Z', '2026-11-12T16:40:00Z')", (f"INV-202611-{lp_id:04d}", tid, p_code, fee, fee))

        # === Cat 7 (4): 跨期调账正负号反算与重复核销错单 ===
        adj_specs = [
            (166, "STARTER", 19900, -15000, 34900, "10月SLA故障补偿贷项冲减150元"),       # 真 4900
            (171, "PRO", 59900, -12000, 83900, "10月重复计费贷项冲减120元（误核销两次）"),  # 真 47900
            (176, "PRO", 59900, 10000, 49900, "10月专线增购漏记借项补收100元"),          # 真 69900
            (181, "ENTERPRISE", 199900, -30000, 229900, "10月节点割接补偿贷项冲减300元"), # 真 169900
        ]
        for a_id, p_code, base_c, delta_c, wrong_tot, rsn in adj_specs:
            tid = f"t_cust_{a_id:03d}"
            inv_id = f"INV-202611-{a_id:04d}"
            _seed_simple_wallet(tid, 100000)
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 3500, '2026-11-12T12:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'OPEN', '', '2026-11-05T09:00:00Z', '2026-11-13T09:20:00Z')", (inv_id, tid, p_code, base_c, wrong_tot))
            conn.execute("INSERT INTO billing_adjustments (id, tenant_id, target_period_key, applied_period_key, ref_invoice_id, adjustment_type, delta_cents, reason, status, created_at) VALUES (?, ?, '2026-10', '2026-11', ?, 'CROSS_PERIOD_ADJ', ?, ?, 'APPLIED', '2026-11-13T09:18:00Z')", (f"adj_202611_{a_id:04d}", tid, inv_id, delta_c, rsn))

        # === Cat 8 (4): 外币锁汇错算 + 保证金抵扣漏记实付 ===
        # A2-32: t_cust_185 USD 30000 minor ($300.00)，2026-11-01 牌价 71850 -> 真 215550（被 70000 整除算成 210000）
        _seed_simple_wallet("t_cust_185", 300000)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_185', '2026-11', 'ENTERPRISE', 20000, '2026-11-03T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0185', 't_cust_185', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 215550, 0, 0, 0, 210000, 0, 0, 'CENTS', 'OPEN', '', '2026-11-03T10:00:00Z', '2026-11-03T10:05:00Z')")
        conn.execute("INSERT INTO fx_settlement_logs (id, invoice_id, tenant_id, currency_code, foreign_minor_units, applied_rate_bps, settled_cny_cents, created_at) VALUES ('fxs_185', 'INV-202611-0185', 't_cust_185', 'USD', 30000, 70000, 210000, '2026-11-03T10:05:00Z')")

        # A2-33: t_cust_188 SGD 20000 minor (S$200.00)，2026-11-01 牌价 53600 -> 真 107200（被整除 53600//10000=5 算成 100000）
        _seed_simple_wallet("t_cust_188", 200000)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_188', '2026-11', 'PRO', 10000, '2026-11-03T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0188', 't_cust_188', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 98349, 0, 8851, 0, 100000, 0, 0, 'CENTS', 'OPEN', '', '2026-11-03T11:00:00Z', '2026-11-03T11:05:00Z')")
        conn.execute("INSERT INTO fx_settlement_logs (id, invoice_id, tenant_id, currency_code, foreign_minor_units, applied_rate_bps, settled_cny_cents, created_at) VALUES ('fxs_188', 'INV-202611-0188', 't_cust_188', 'SGD', 20000, 53600, 100000, '2026-11-03T11:05:00Z')")

        # 同时为已结清租户 t_cust_029 登记一条健康已结清外币日志，用于校验期末汇兑重估排除 PAID 账单 (BUG-20)
        inv_029 = conn.execute("SELECT id, total_cents FROM invoices WHERE tenant_id = 't_cust_029' AND period_key = '2026-11'").fetchone()
        if not inv_029:
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0029', 't_cust_029', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 59900, 0, 5391, 0, 65291, 65291, 0, 'CENTS', 'PAID', '', '2026-11-02T00:00:00Z', '2026-11-02T00:10:00Z')")
            conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_029', 'INV-202611-0029', 't_cust_029', 'auto:INV-202611-0029', 65291, 0, 65291, '2026-11-02T00:10:00Z')")
            conn.execute("UPDATE wallets SET cash_balance_cents = cash_balance_cents - 65291 WHERE tenant_id = 't_cust_029'")
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_029', 'INVOICE_PAY', -65291, 0, 'INV-202611-0029', '支付外币账单', '2026-11-02T00:10:00Z')")
        conn.execute("INSERT INTO fx_settlement_logs (id, invoice_id, tenant_id, currency_code, foreign_minor_units, applied_rate_bps, settled_cny_cents, created_at) VALUES ('fxs_029_paid', 'INV-202611-0029', 't_cust_029', 'SGD', 12181, 53600, 65291, '2026-11-02T00:05:00Z')")

        # A2-34, A2-35: 履约保证金已从 escrow_accounts 划扣并记入 audit_logs，但漏更新 invoices.paid_cents/status 与 invoice_payments
        for esc_id, p_code, fee, init_dep, applied_amt in ((191, "PRO", 59900, 100000, 59900), (193, "ENTERPRISE", 199900, 150000, 80000)):
            tid = f"t_cust_{esc_id:03d}"
            inv_id = f"INV-202611-{esc_id:04d}"
            _seed_simple_wallet(tid, 5000)
            conn.execute("INSERT INTO escrow_accounts (tenant_id, initial_deposit_cents, balance_cents, frozen_cents, status, updated_at) VALUES (?, ?, ?, 0, 'ACTIVE', '2026-11-12T15:00:00Z')", (tid, init_dep, init_dep - applied_amt))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 6000, '2026-11-10T00:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, 0, 0, 'CENTS', 'OPEN', '', '2026-11-05T00:00:00Z', '2026-11-12T15:00:00Z')", (inv_id, tid, p_code, fee, fee))
            conn.execute("INSERT INTO audit_logs (actor, action, target_id, detail, created_at) VALUES ('treasury_ops', 'ESCROW_APPLY', ?, ?, '2026-11-12T15:00:00Z')", (inv_id, f"tenant={tid}, deducted_escrow_cents={applied_amt}"))

        # === Cat 9 (4): 逾期滞纳金复利多算 + 争议冻结误停机 + 缴清欠费未复机 ===
        # A2-36: t_cust_196 未付本金 59900，单次 5% 应为 2995 (total=62895)，被每日复利连收 3 次算成 late=9440, total=69340
        _seed_simple_wallet("t_cust_196", 10000)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_196', '2026-11', 'PRO', 9000, '2026-11-05T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0196', 't_cust_196', '2026-11', '2026-10-05T00:00:00Z', '2026-11-05T00:00:00Z', 'PRO', 59900, 0, 0, 9440, 69340, 0, 0, 'CENTS', 'OPEN', '', '2026-11-05T00:00:00Z', '2026-11-13T01:00:00Z')")
        conn.execute("INSERT INTO dunning_cases (id, tenant_id, invoice_id, stage, overdue_days, unpaid_cents, last_notified_at, status, updated_at) VALUES ('dun_196', 't_cust_196', 'INV-202611-0196', 'WARNING', 8, 69340, '2026-11-13T01:00:00Z', 'OPEN', '2026-11-13T01:00:00Z')")

        # A2-37: t_cust_199 总额 199900 已付 99900（未付本金 100000），单次 5% 应为 5000 (total=204900)，被按全额复利 3 次算成 late=31508, total=231408
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_199', 5100, 0, '2026-11-04T12:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_199', 'TOPUP', 105000, 0, 'top_199', '充值', '2026-11-01T09:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_199', 'INVOICE_PAY', -99900, 0, 'INV-202611-0199', '部分付款', '2026-11-04T12:00:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_199', '2026-11', 'ENTERPRISE', 40000, '2026-11-04T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0199', 't_cust_199', '2026-11', '2026-10-04T00:00:00Z', '2026-11-04T00:00:00Z', 'ENTERPRISE', 199900, 0, 0, 31508, 231408, 99900, 0, 'CENTS', 'OPEN', '', '2026-11-04T00:00:00Z', '2026-11-13T01:00:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_199', 'INV-202611-0199', 't_cust_199', 'part:INV-202611-0199', 99900, 0, 99900, '2026-11-04T12:00:00Z')")
        conn.execute("INSERT INTO dunning_cases (id, tenant_id, invoice_id, stage, overdue_days, unpaid_cents, last_notified_at, status, updated_at) VALUES ('dun_199', 't_cust_199', 'INV-202611-0199', 'WARNING', 9, 131508, '2026-11-13T01:00:00Z', 'OPEN', '2026-11-13T01:00:00Z')")

        # A2-38: t_cust_202 提交了生效争议单 (freeze_auto_debit=1)，却被催收任务误停机 SUSPENDED 并加收了 2995 滞纳金 -> 应恢复 ACTIVE 并清零滞纳金
        _seed_simple_wallet("t_cust_202", 80000)
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_202', '2026-11', 'PRO', 15000, '2026-10-10T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0202', 't_cust_202', '2026-11', '2026-09-10T00:00:00Z', '2026-10-10T00:00:00Z', 'PRO', 59900, 0, 0, 2995, 62895, 0, 0, 'CENTS', 'OPEN', '边缘网关重传异议核账中', '2026-11-01T00:00:00Z', '2026-11-13T01:00:00Z')")
        conn.execute("INSERT INTO dispute_tickets (id, invoice_id, tenant_id, reason, freeze_auto_debit, status, created_at, resolved_at) VALUES ('dsp_202', 'INV-202611-0202', 't_cust_202', '边缘网关重传异议核账中', 1, 'OPEN', '2026-11-02T10:00:00Z', NULL)")
        conn.execute("INSERT INTO dunning_cases (id, tenant_id, invoice_id, stage, overdue_days, unpaid_cents, last_notified_at, status, updated_at) VALUES ('dun_202', 't_cust_202', 'INV-202611-0202', 'SUSPENDED', 34, 62895, '2026-11-13T01:00:00Z', 'OPEN', '2026-11-13T01:00:00Z')")

        # A2-39: t_cust_205 已全额缴清唯一逾期单 INV-202611-0205 (62895)，但租户与订阅状态仍卡在 SUSPENDED -> 应恢复 ACTIVE
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_205', 37105, 0, '2026-11-13T15:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_205', 'TOPUP', 100000, 0, 'top_205', '补缴充值', '2026-11-13T14:55:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_205', 'INVOICE_PAY', -62895, 0, 'INV-202611-0205', '缴清逾期账单', '2026-11-13T15:00:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_205', '2026-11', 'PRO', 11000, '2026-10-10T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0205', 't_cust_205', '2026-11', '2026-09-10T00:00:00Z', '2026-10-10T00:00:00Z', 'PRO', 59900, 0, 0, 2995, 62895, 62895, 0, 'CENTS', 'PAID', '', '2026-11-01T00:00:00Z', '2026-11-13T15:00:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_205', 'INV-202611-0205', 't_cust_205', 'ui:INV-202611-0205', 62895, 0, 62895, '2026-11-13T15:00:00Z')")
        conn.execute("INSERT INTO dunning_cases (id, tenant_id, invoice_id, stage, overdue_days, unpaid_cents, last_notified_at, status, updated_at) VALUES ('dun_205', 't_cust_205', 'INV-202611-0205', 'SUSPENDED', 0, 0, '2026-11-12T01:00:00Z', 'RESOLVED', '2026-11-13T15:00:00Z')")

        # === Cat 10 (5): 红字数电票正数污染、重复蓝票与对公水单双入账 ===
        # A2-40, A2-41: 同步红票存成了正数且原蓝票仍为 ISSUED
        for rf_id, p_code, gross_c, net_c, tax_c in ((208, "PRO", 59900, 56509, 3391), (210, "ENTERPRISE", 199900, 188585, 11315)):
            tid = f"t_cust_{rf_id:03d}"
            inv_id = f"INV-202611-{rf_id:04d}"
            conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, 0, '2026-11-10T10:00:00Z')", (tid, gross_c))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '充值', '2026-11-01T08:00:00Z')", (tid, gross_c, f"top_{rf_id}"))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, '付款', '2026-11-02T10:00:00Z')", (tid, -gross_c, inv_id))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'REFUND', ?, 0, ?, '全额退款红冲', '2026-11-10T09:00:00Z')", (tid, gross_c, inv_id))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 2000, '2026-11-02T00:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', ?, ?, 0, 0, 0, ?, ?, ?, 'CENTS', 'PAID', '', '2026-11-02T09:00:00Z', '2026-11-10T09:00:00Z')", (inv_id, tid, p_code, gross_c, gross_c, gross_c, gross_c))
            conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-02T10:00:00Z')", (f"pay_11_{rf_id}", inv_id, tid, f"auto:{inv_id}", gross_c, gross_c))
            orig_fp = f"FP-202611-{rf_id:04d}"
            conn.execute("INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title, net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at) VALUES (?, ?, ?, 'VAT_SPECIAL_E', ?, ?, ?, ?, ?, 1, 'ISSUED', NULL, '2026-11-03T10:00:00Z')", (orig_fp, tid, inv_id, f"91310115MA1RED{rf_id}X", f"抬头_{tid}", net_c, tax_c, gross_c))
            conn.execute("INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title, net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at) VALUES (?, ?, ?, 'VAT_SPECIAL_E', ?, ?, ?, ?, ?, 1, 'RED_ISSUED', ?, '2026-11-10T10:00:00Z')", (f"FP-RED-{rf_id:04d}", tid, inv_id, f"91310115MA1RED{rf_id}X", f"抬头_{tid}", net_c, tax_c, gross_c, orig_fp))

        # A2-42: t_cust_212 同一张已付账单并发开出了两张有效蓝票
        conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES ('t_cust_212', 40100, 0, '2026-11-05T10:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_212', 'TOPUP', 100000, 0, 'top_212', '充值', '2026-11-01T08:00:00Z')")
        conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES ('t_cust_212', 'INVOICE_PAY', -59900, 0, 'INV-202611-0212', '付款', '2026-11-05T10:00:00Z')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_212', '2026-11', 'PRO', 5000, '2026-11-05T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0212', 't_cust_212', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'PRO', 59900, 0, 0, 0, 59900, 59900, 0, 'CENTS', 'PAID', '', '2026-11-05T09:00:00Z', '2026-11-05T10:00:00Z')")
        conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES ('pay_11_212', 'INV-202611-0212', 't_cust_212', 'auto:INV-202611-0212', 59900, 0, 59900, '2026-11-05T10:00:00Z')")
        conn.execute("INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title, net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at) VALUES ('FP-202611-0212A', 't_cust_212', 'INV-202611-0212', 'VAT_SPECIAL_E', '91310115MA1DUP212X', '企业抬头_t_cust_212', 56509, 3391, 59900, 1, 'ISSUED', NULL, '2026-11-06T10:00:01Z')")
        conn.execute("INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title, net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at) VALUES ('FP-202611-0212B', 't_cust_212', 'INV-202611-0212', 'VAT_SPECIAL_E', '91310115MA1DUP212X', '企业抬头_t_cust_212', 56509, 3391, 59900, 1, 'ISSUED', NULL, '2026-11-06T10:00:01Z')")

        # A2-43, A2-44: 银企对公水单先自动认领入账、后又被人工二次认领重复加钱
        for bs_id, serial_no, amt_c in ((214, "CMB2026110800214", 59900), (216, "ICBC2026110900216", 199900)):
            tid = f"t_cust_{bs_id:03d}"
            conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, ?, 0, '2026-11-09T14:00:00Z')", (tid, amt_c * 2))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 2000, '2026-11-09T00:00:00Z')", (tid, plan_overrides[bs_id]))
            conn.execute("INSERT INTO bank_statement_imports (id, bank_serial_no, payer_company_name, amount_cents, tx_date, matched_tenant_id, match_confidence_bps, status, created_at) VALUES (?, ?, ?, ?, '2026-11-08', ?, 10000, 'CLAIMED', '2026-11-08T17:00:00Z')", (f"bsi_{bs_id:04d}", serial_no, f"对公汇款户_{tid}", amt_c, tid))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, ?, '2026-11-08T17:00:01Z')", (tid, amt_c, serial_no, f"银行水单自动认领:{serial_no}"))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, ?, '2026-11-09T14:00:00Z')", (tid, amt_c, serial_no, f"人工水单认领:{serial_no}:clerk_li"))

        # === 渠道未付大单样本 (t_cust_218) 与多月预付递延收入样本 (t_cust_219, t_cust_220) ===
        _seed_simple_wallet("t_cust_218", 10000)
        conn.execute("INSERT INTO enterprise_contracts (id, tenant_id, min_monthly_commit_cents, custom_overage_discount_bps, credit_memo_bps, credit_limit_cents, signed_by, valid_from, valid_until, status) VALUES ('ctr_whale_218', 't_cust_218', 2100000, 0, 0, 0, 'ka_vp', '2026-01-01T00:00:00Z', '2027-01-01T00:00:00Z', 'ACTIVE')")
        conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES ('t_cust_218', '2026-11', 'ENTERPRISE', 50000, '2026-11-10T00:00:00Z')")
        conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES ('INV-202611-0218', 't_cust_218', '2026-11', '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', 'ENTERPRISE', 2100000, 0, 0, 0, 2100000, 0, 0, 'CENTS', 'OPEN', '', '2026-11-05T00:00:00Z', '2026-11-05T00:00:00Z')")

        # t_cust_219 (3个月季付含税 59700 -> 不含税真值 56321) 与 t_cust_220 (3个月季付免税 100000 -> 不含税真值 100000)
        for dr_id, p_code, gross_c in ((219, "STARTER", 59700), (220, "ENTERPRISE", 100000)):
            tid = f"t_cust_{dr_id:03d}"
            inv_id = f"INV-202611-{dr_id:04d}"
            conn.execute("INSERT INTO wallets (tenant_id, cash_balance_cents, promo_balance_cents, updated_at) VALUES (?, 20000, 0, '2026-11-02T10:00:00Z')", (tid,))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'TOPUP', ?, 0, ?, '季付预存', '2026-11-01T08:00:00Z')", (tid, gross_c + 20000, f"top_{dr_id}"))
            conn.execute("INSERT INTO wallet_ledger (tenant_id, entry_type, cash_delta_cents, promo_delta_cents, ref_id, note, created_at) VALUES (?, 'INVOICE_PAY', ?, 0, ?, '支付季付合同', '2026-11-02T10:00:00Z')", (tid, -gross_c, inv_id))
            conn.execute("INSERT INTO usage_summaries (tenant_id, period_key, plan_code, total_quantity, updated_at) VALUES (?, '2026-11', ?, 3000, '2026-11-10T00:00:00Z')", (tid, p_code))
            conn.execute("INSERT INTO invoices (id, tenant_id, period_key, cycle_start, cycle_end, plan_code, base_fee_cents, overage_fee_cents, tax_cents, late_fee_cents, total_cents, paid_cents, refunded_cents, currency_unit, status, dispute_reason, created_at, updated_at) VALUES (?, ?, '2026-11', '2026-11-01T00:00:00Z', '2027-02-01T00:00:00Z', ?, ?, 0, 0, 0, ?, ?, 0, 'CENTS', 'PAID', '', '2026-11-02T09:00:00Z', '2026-11-02T10:00:00Z')", (inv_id, tid, p_code, gross_c, gross_c, gross_c))
            conn.execute("INSERT INTO invoice_payments (id, invoice_id, tenant_id, idempotency_key, cash_paid_cents, promo_paid_cents, total_paid_cents, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, '2026-11-02T10:00:00Z')", (f"pay_11_{dr_id}", inv_id, tid, f"auto:{inv_id}", gross_c, gross_c))
            # 调用带病摊销函数写入未剥离税额/丢弃余数的脏子账本现场 (A2-47)
            persist_multi_month_revrec_schedule(conn, inv_id, 3)

        # 为 t_cust_028 预置跨关账期历史递延收入排期（2026-10 已确认锁定），用于测试合同变更重排不篡改历史行 (BUG-35)
        inv_28_10 = conn.execute("SELECT id FROM invoices WHERE tenant_id = 't_cust_028' AND period_key = '2026-10'").fetchone()
        if inv_28_10:
            conn.executemany(
                """INSERT INTO deferred_revenue_schedules (id, invoice_id, tenant_id, period_key, recognized_cents, deferred_closing_cents, status, updated_at)
                   VALUES (?, ?, 't_cust_028', ?, ?, ?, ?, '2026-10-31T23:00:00Z')""",
                [
                    ("drs_028_10", inv_28_10["id"], "2026-10", 62862, 125723, "RECOGNIZED"),
                    ("drs_028_11", inv_28_10["id"], "2026-11", 62862, 62861, "DEFERRED"),
                    ("drs_028_12", inv_28_10["id"], "2026-12", 62861, 0, "DEFERRED"),
                ],
            )

        # ------------------------------------------------------------------
        # 4. 计算精确的 2026-09 与 2026-10 封账总额，生成 GL 与渠道返佣子账本
        # ------------------------------------------------------------------
        rows_09 = conn.execute("SELECT * FROM invoices WHERE period_key = '2026-09' AND status != 'VOID'").fetchall()
        arch_09 = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in rows_09)

        rows_10 = conn.execute("SELECT * FROM invoices WHERE period_key = '2026-10' AND status != 'VOID'").fetchall()
        arch_10 = sum(parse_legacy_amount_cents(dict(r), "total_cents") for r in rows_10)

        conn.executemany(
            "INSERT INTO accounting_periods (period_key, status, closed_at, closed_by, archived_total_cents) VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-09", "CLOSED", "2026-10-02T02:00:00Z", "finance_director", arch_09),
                ("2026-10", "CLOSED", "2026-11-02T02:00:00Z", "finance_director", arch_10),
                ("2026-11", "OPEN", None, None, None),
            ],
        )

        generate_gl_entries_for_period(conn, "2026-09")
        generate_gl_entries_for_period(conn, "2026-10")
        # 2026-11 GL 由带病导出器生成：因调账单存在导致借贷天然失衡 (A2-45 & BUG-32)
        gl_11_dirty = generate_gl_entries_for_period(conn, "2026-11")
        assert gl_11_dirty["balanced"] is False, "Expected 2026-11 unpatched GL to be unbalanced!"

        calculate_period_partner_commissions(conn, "2026-10")
        # 2026-10 返佣已完成打款锁定，测试重算时不覆盖 PAID_OUT (BUG-41)
        conn.execute("UPDATE partner_commissions SET status = 'PAID_OUT' WHERE period_key = '2026-10'")
        # 2026-11 返佣由带病引擎生成（含跨期退费漏扣、未付大单虚假抬档与归因前收款污染 A2-46）
        calculate_period_partner_commissions(conn, "2026-11")

        # 写入 520 条正常已刷盘计量历史记录
        for e_idx in range(1, 521):
            pick_num = (e_idx % 180) + 1
            if pick_num in DIRTY_IDS:
                continue
            conn.execute(
                """INSERT INTO usage_events (id, tenant_id, metric_code, quantity, plan_code_at_event, occurred_at, period_key, flushed)
                   VALUES (?, ?, 'API_CALLS', ?, NULL, ?, '2026-11', 1)""",
                (f"ue_hist_{e_idx:04d}", f"t_cust_{pick_num:03d}", (e_idx * 37) % 900 + 50, f"2026-11-{(e_idx % 12) + 1:02d}T10:{e_idx % 60:02d}:00Z"),
            )

        # ------------------------------------------------------------------
        # 5. 写入 2026-10 数电票（62 张有效 ISSUED + 2 对已红冲 RED_REVERSED/RED_ISSUED = 66 条记录）
        # ------------------------------------------------------------------
        oct_paid = conn.execute(
            """SELECT i.id, i.tenant_id, i.total_cents, i.tax_cents
               FROM invoices i
               JOIN tenants t ON t.id = i.tenant_id
               WHERE i.period_key = '2026-10' AND i.status = 'PAID' AND i.currency_unit = 'CENTS'
                 AND t.tax_profile_code != 'SG_GST_9_EXCLUSIVE'
                 AND i.tenant_id != 't_cust_008'
               ORDER BY i.id ASC LIMIT 64"""
        ).fetchall()
        assert len(oct_paid) == 64, f"Expected 64 Oct PAID invoices, got {len(oct_paid)}"
        oct_fp_gross_sum = 0
        oct_fp_tax_sum = 0
        for f_idx, p_inv in enumerate(oct_paid, start=1):
            gross_c = int(p_inv["total_cents"] or 0)
            net_c = int(round(gross_c / 1.06))
            tax_c = gross_c - net_c
            fp_id = f"FP-202610-{f_idx:04d}"
            # 第 12 张与第 58 张已完成合规红冲（原蓝票 RED_REVERSED + 负数红票 RED_ISSUED，跨第1页与第2页测试 BUG-26）
            if f_idx in (12, 58):
                conn.execute(
                    """INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
                       net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at)
                       VALUES (?, ?, ?, 'VAT_SPECIAL_E', ?, ?, ?, ?, ?, 1, 'RED_REVERSED', NULL, ?)""",
                    (fp_id, p_inv["tenant_id"], p_inv["id"], f"91310115MA1OCT{f_idx:03d}X", f"企业抬头_{p_inv['tenant_id']}", net_c, tax_c, gross_c, f"2026-10-30T10:{f_idx % 60:02d}:00Z"),
                )
                conn.execute(
                    """INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
                       net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at)
                       VALUES (?, ?, ?, 'VAT_SPECIAL_E', ?, ?, ?, ?, ?, 1, 'RED_ISSUED', ?, ?)""",
                    (f"FP-202610-R{f_idx:03d}", p_inv["tenant_id"], p_inv["id"], f"91310115MA1OCT{f_idx:03d}X", f"企业抬头_{p_inv['tenant_id']}", -net_c, -tax_c, -gross_c, fp_id, f"2026-10-31T11:{f_idx % 60:02d}:00Z"),
                )
            else:
                oct_fp_gross_sum += gross_c
                oct_fp_tax_sum += tax_c
                conn.execute(
                    """INSERT INTO fapiao_requests (id, tenant_id, invoice_id, fapiao_type, buyer_tax_id, title,
                       net_amount_cents, tax_amount_cents, gross_amount_cents, sheet_count, status, red_letter_of, created_at)
                       VALUES (?, ?, ?, 'VAT_SPECIAL_E', ?, ?, ?, ?, ?, 1, 'ISSUED', NULL, ?)""",
                    (fp_id, p_inv["tenant_id"], p_inv["id"], f"91310115MA1OCT{f_idx:03d}X", f"企业抬头_{p_inv['tenant_id']}", net_c, tax_c, gross_c, f"2026-10-30T10:{f_idx % 60:02d}:00Z"),
                )

        # 写入常规银企水单与全角括号未匹配水单样本 (BUG-18)
        for b_idx in range(1, 19):
            matched_tid = f"t_cust_{b_idx:03d}" if b_idx <= 12 else None
            st_code = "AUTO_CLAIMED" if matched_tid else "UNMATCHED"
            conn.execute(
                """INSERT INTO bank_statement_imports (id, bank_serial_no, payer_company_name, amount_cents, tx_date,
                   matched_tenant_id, match_confidence_bps, status, created_at)
                   VALUES (?, ?, ?, ?, '2026-11-06', ?, ?, ?, '2026-11-06T17:30:00Z')""",
                (f"bsi_{b_idx:04d}", f"CMB2026110699{b_idx:03d}", f"汇款单位_{b_idx:02d}", 59900, matched_tid, 10000 if matched_tid else 0, st_code),
            )
        conn.execute(
            """INSERT INTO bank_statement_imports (id, bank_serial_no, payer_company_name, amount_cents, tx_date,
               matched_tenant_id, match_confidence_bps, status, created_at)
               VALUES ('bsi_fw_014', 'CMB2026111088014', '云帆云计算（上海）有限公司', 59900, '2026-11-10', NULL, 4200, 'UNMATCHED', '2026-11-10T17:30:00Z')"""
        )

        # 写入审批工单（含大小写空格绕过自批违规记录 apv_sod_leak_01 与待二审记录 apv_2026_0004）
        conn.executemany(
            """INSERT INTO approval_tickets (id, ticket_type, tenant_id, ref_object_id, amount_cents, requested_by,
               first_approver, second_approver, required_approvals, status, reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-11-08T09:00:00Z', '2026-11-08T14:00:00Z')""",
            [
                ("apv_2026_0001", "CONTRACT_DISCOUNT", "t_cust_004", "ctr_004", 220000, "ka_sales_01", "fin_mgr", None, 1, "APPROVED", "年度保底协议例行备案"),
                ("apv_2026_0002", "LARGE_REFUND_CHECK", "t_cust_020", "INV-202610-0020", 120000, "cs_lead", "fin_mgr", None, 1, "APPROVED", "天盛商业10月核减退费备案"),
                ("apv_2026_0003", "CREDIT_ADJUSTMENT", "t_cust_166", "adj_202611_0166", 15000, "cs_lead", "fin_mgr", None, 1, "APPROVED", "10月SLA故障补偿150元"),
                ("apv_2026_0004", "LARGE_REFUND_CHECK", "t_cust_015", "INV-202611-0015", 620000, "cs_lead", "fin_mgr", None, 2, "FIRST_APPROVED", "待财务总监二签大额核销单"),
                ("apv_sod_leak_01", "LARGE_REFUND_CHECK", "t_cust_028", "INV-202610-0028", 550000, "ops_alice", "Ops_Alice ", "cfo_dir", 2, "APPROVED", "历史大小写自审穿透样本"),
            ],
        )

        # 写入 SLA 故障申报记录（含 2026-11 < 9000 bps 极端故障待扫描记录，复现 BUG-08）
        conn.executemany(
            """INSERT INTO sla_credit_claims (id, tenant_id, period_key, observed_uptime_bps, promised_uptime_bps, credit_cents, status, created_at)
               VALUES (?, ?, ?, ?, 9990, ?, ?, '2026-11-03T10:00:00Z')""",
            [
                ("sla_202610_01", "t_cust_005", "2026-10", 9998, 0, "MEETS_SLA"),
                ("sla_202610_02", "t_cust_166", "2026-10", 9945, 15000, "CREDITED"),
                ("sla_202611_01", "t_cust_015", "2026-11", 8850, 0, "EVALUATED"),
            ],
        )

        # 写入 Webhook 发件箱毒丸消息（attempts=4，再重试一次即达 5 次上限，复现 BUG-53 死循环）
        conn.execute(
            """INSERT INTO webhook_outbox (id, tenant_id, event_type, payload_json, signature, delivery_status, attempts, created_at)
               VALUES ('wh_poison_025', 't_cust_025', 'invoice.created', '{"invoice_id":"INV-202611-0025"}', 'sig_demo', 'QUEUED', 4, '2026-11-11T14:00:00Z')"""
        )

        t_cnt = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
        i_cnt = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        fp_cnt = conn.execute("SELECT COUNT(*) FROM fapiao_requests").fetchone()[0]
        l_cnt = conn.execute("SELECT COUNT(*) FROM wallet_ledger").fetchone()[0]
        tbl_cnt = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
        conn.commit()
        return {
            "tables": tbl_cnt,
            "tenants": t_cnt,
            "invoices": i_cnt,
            "fapiaos": fp_cnt,
            "oct_active_blue_fapiao_gross_sum": oct_fp_gross_sum,
            "oct_active_blue_fapiao_tax_sum": oct_fp_tax_sum,
            "ledger_rows": l_cnt,
            "archived_2026_09": arch_09,
            "archived_2026_10": arch_10,
        }
    finally:
        conn.close()


def build_logs() -> int:
    rng = random.Random(20261114)
    logs_dir = TEMPLATE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for old_log in logs_dir.glob("*.log"):
        old_log.unlink()

    days = [
        ("2026-11-09", "prod_20261109.log", {
            "08:00:05": [
                "2026-11-09 08:00:04 [INFO] yunce.server: bootstrapping yunce-billing-center v3.0.0-ent",
                "2026-11-09 08:00:05 [WARN] yunce.hotfixes: mounted startup patches hotfix_20261031_tz_and_vip & hotfix_20261105_fapiao_split (FAPIAO_SINGLE_SHEET_MAX_CENTS=50000)",
            ],
            "14:18:22": [
                "2026-11-09 14:18:22 [INFO] yunce.subscriptions: change_subscription_plan tenant=t_cust_041 STARTER->PRO runtime_flag(waive_upgrade_proration_promo_window)=True proration_cents=0",
            ],
        }),
        ("2026-11-10", "prod_20261110.log", {
            "00:12:40": [
                "2026-11-10 00:12:40 [INFO] yunce.gateway.batch: POST /api/usage/batch node=ap-shanghai-02 occurred_at=2026-11-01T00:15:00+08:00 sliced_period=2026-11 accepted=4",
                "2026-11-10 00:12:44 [ERROR] yunce.http: unhandled 500 on POST /api/usage/batch err=UNIQUE constraint failed: usage_events.id (replay after ring eviction)",
                "2026-11-10 00:12:49 [WARN] yunce.gateway.bloom: SlidingIdempotencyRing dropped distinct event_id='evt_nov10_nodeB' colliding on 8-char prefix 'evt_nov1'",
            ],
            "16:05:19": [
                "2026-11-10 16:05:19 [INFO] yunce.fapiao: issued VAT_SPECIAL_E gross=19900 net=18773 tax=1126 (net+tax=19899 penny drift)",
                "2026-11-10 17:31:02 [WARN] yunce.bank_matcher: unmatched wire serial=CMB2026111088014 payer='云帆云计算（上海）有限公司' confidence=4200bps against tenant='云帆云计算(上海)有限公司'",
            ],
        }),
        ("2026-11-11", "prod_20261111.log", {
            "00:00:02": [
                "2026-11-11 00:00:01 [INFO] yunce.jobs.scheduler: midnight renewal & settlement batch start",
                "2026-11-11 00:00:02 [WARN] yunce.jobs.settlement: generated duplicate cycle invoices & billed SUSPENDED auto_renew=0 tenant=t_cust_086",
            ],
            "00:05:01": [
                "2026-11-11 00:05:01 [ERROR] yunce.jobs.settlement: transient error after wallet debit left invoices in PENDING_SETTLE without savepoint rollback or DLQ",
            ],
            "10:12:04": [
                "2026-11-11 10:12:04 [INFO] yunce.hooks.lifecycle: topic=subscription.plan_changed missed quota_cache_shim listener",
                "2026-11-11 11:40:18 [WARN] yunce.catalog.tariff: cached plan dict mutated in-place; custom_price_book_overrides default audit_trail accumulated 39 stale entries",
            ],
            "14:22:10": [
                "2026-11-11 14:22:10 [WARN] yunce.webhook: delivery timeout url=https://hooks.customer-035.example.com/billing attempt=1 (retrying in 60s)",
                "2026-11-11 14:23:11 [INFO] yunce.webhook: delivery succeeded url=https://hooks.customer-035.example.com/billing attempt=2 status=200",
            ],
        }),
        ("2026-11-12", "prod_20261112.log", {
            "00:01:00": [
                "2026-11-12 00:01:00 [WARN] yunce.ledger: expire_promo_grants deducted initial_cents repeatedly on already EXPIRED promo_grants",
            ],
            "02:15:04": [
                "2026-11-12 02:15:04 [WARN] yunce.jobs.dlq: dlq_retry_job charged full total_cents ignoring prior paid_cents and left settlement_dlq status=PENDING",
            ],
            "09:15:03": [
                "2026-11-12 09:00:03 [WARN] yunce.compat.wallet_bridge: legacy_fast_cash_mode=True refunded promo-paid invoice into withdrawable cash without restoring promo_grants",
                "2026-11-12 09:15:00 [WARN] yunce.domain.contracts: apply_enterprise_contract_terms called without as_of_iso; expired 2026-09/10 contracts applied to 2026-11 bills",
            ],
            "15:02:11": [
                "2026-11-12 15:00:02 [WARN] yunce.treasury.escrow: apply_escrow_to_invoice deducted escrow balance_cents but did not update invoice paid_cents or invoice_payments",
                "2026-11-12 16:40:12 [WARN] yunce.http: GETsettlement-preview mutated active promo_grants to LOCKED_PREVIEW",
                "2026-11-12 19:05:44 [WARN] yunce.approvals: concurrent POST /decide race detected without IMMEDIATE transaction lock or conditional status check",
            ],
        }),
        ("2026-11-13", "prod_20261113.log", {
            "09:20:05": [
                "2026-11-13 09:20:05 [WARN] yunce.domain.reconcile: apply_adjustment_to_open_invoice subtracted negative delta_cents (inverted sign) and allowed repeat application",
            ],
            "11:15:20": [
                "2026-11-13 11:15:20 [WARN] yunce.security: unauthenticated call to admin batch/export & cross-tenant invoice preview",
            ],
            "14:10:08": [
                "2026-11-13 14:10:08 [WARN] yunce.events: event_bus subscribers(invoice.paid)=6912 leaked per HTTP request; rate_limiter _hits keys=24180 never evicted",
                "2026-11-13 14:55:19 [ERROR] yunce.reports: standalone-audit invalid period_key='2026_11' raised ValueError before closing sqlite connection",
            ],
            "17:20:30": [
                "2026-11-13 17:20:30 [WARN] yunce.portal.ui: ops reported FIRST_APPROVED dual-sign button disabled in approval_drawer & credit adjustment minus sign stripped in reconcile_modal",
            ],
        }),
    ]

    endpoints = [
        ("GET", "/health", 200),
        ("GET", "/api/subscriptions/current?period_key=2026-11", 200),
        ("POST", "/api/usage/events", 201),
        ("POST", "/api/usage/batch", 200),
        ("GET", "/api/usage/summary?period_key=2026-11", 200),
        ("GET", "/api/invoices", 200),
        ("GET", "/api/wallet", 200),
        ("GET", "/api/fapiao", 200),
        ("GET", "/api/partners/commissions?period_key=2026-11", 200),
        ("GET", "/api/admin/analytics/mrr", 200),
        ("GET", "/api/admin/diagnostics/sox-controls", 200),
    ]

    total_lines = 0
    for day_str, fname, anchors in days:
        out_lines = []
        anchor_keys = sorted(anchors.keys())
        ak_idx = 0
        for step in range(1820):
            sec_of_day = int((step / 1820.0) * 86399)
            hms = f"{sec_of_day // 3600:02d}:{(sec_of_day % 3600) // 60:02d}:{sec_of_day % 60:02d}"
            while ak_idx < len(anchor_keys) and anchor_keys[ak_idx] <= hms:
                out_lines.extend(anchors[anchor_keys[ak_idx]])
                ak_idx += 1
            tid = f"t_cust_{rng.randint(1, 220):03d}" if rng.random() > 0.08 else f"t_leg_{rng.randint(1, 20):03d}"
            method, path, code = rng.choice(endpoints)
            ms = rng.randint(1, 24)
            if path == "/api/usage/events":
                out_lines.append(f"{day_str} {hms} [INFO] yunce.http: {method} {path} tenant={tid} qty={rng.randint(10, 800)} status={code} {ms}ms")
            else:
                out_lines.append(f"{day_str} {hms} [INFO] yunce.http: {method} {path} tenant={tid} status={code} {ms}ms")
        while ak_idx < len(anchor_keys):
            out_lines.extend(anchors[anchor_keys[ak_idx]])
            ak_idx += 1
        (logs_dir / fname).write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        total_lines += len(out_lines)

    # 6. 批处理与催收返佣日志 cron_settlement.log (~1,100 行)
    cron_lines = []
    for idx in range(1100):
        day = 9 + (idx // 220)
        cron_lines.append(f"2026-11-{day:02d} 00:{idx % 60:02d}:10 [INFO] yunce.cron.worker: shard={idx % 8} open_checked={rng.randint(6, 28)} dlq_pending={rng.randint(0, 4)}")
        if idx == 180:
            cron_lines.append("2026-11-09 18:00:05 [WARN] yunce.jobs.sla: sla_credit_scan_job evaluated uptime=8850bps (<9000) -> 15000bps exceeded 100% monthly fee cap; repeat scan duplicated credit_notes")
        if idx == 450:
            cron_lines.append("2026-11-11 00:05:18 [WARN] yunce.jobs.dunning: escalated disputed invoice (freeze_auto_debit=1) to SUSPENDED and compounded daily 5% late_fee_cents")
        if idx == 720:
            cron_lines.append("2026-11-12 03:10:00 [WARN] yunce.jobs.commission: rerun overwrote status=PAID_OUT commission row to CALCULATED & counted pre-bound payment before partner_referrals.bound_at")
    (logs_dir / "cron_settlement.log").write_text("\n".join(cron_lines) + "\n", encoding="utf-8")
    total_lines += len(cron_lines)

    # 7. 税控、网关与外部通知日志 tax_erp_gateway.log (~1,100 行)
    tax_lines = []
    for idx in range(1100):
        day = 9 + (idx // 220)
        tax_lines.append(f"2026-11-{day:02d} {(idx * 7) % 24:02d}:{(idx * 13) % 60:02d}:30 [INFO] yunce.tax.gateway: heartbeat channel=G4_SH_01 latency={rng.randint(18, 95)}ms")
        if idx == 160:
            tax_lines.append("2026-11-09 15:10:02 [WARN] yunce.gateway.shard_merger: merge_cross_region_usage_shards overwrote (=) prior shard bucket instead of accumulating (+=) and accepted qty=0")
        if idx == 390:
            tax_lines.append("2026-11-10 19:20:11 [WARN] yunce.tax.red_sync: sync_red_letter_confirmations persisted positive gross_amount_cents on RED_ISSUED and left original blue fapiao as ISSUED")
        if idx == 640:
            tax_lines.append("2026-11-11 21:05:40 [WARN] yunce.erp.hooks: refund_to_wallet did not publish negative REFUND_REVERSAL cash voucher to erp_sync_hooks queue")
        if idx == 880:
            tax_lines.append("2026-11-12 23:40:12 [WARN] yunce.webhook.dispatcher: outbox id=wh_poison_025 failed attempt=5 but stayed delivery_status=QUEUED; verify_webhook_signature skipped 300s timestamp window & constant-time hmac check")
    (logs_dir / "tax_erp_gateway.log").write_text("\n".join(tax_lines) + "\n", encoding="utf-8")
    total_lines += len(tax_lines)

    # 8. 总账、收入确认与内控审计日志 gl_revrec_audit.log (~1,000 行)
    audit_lines = []
    for idx in range(1000):
        day = 9 + (idx // 200)
        audit_lines.append(f"2026-11-{day:02d} {(idx * 5) % 24:02d}:{(idx * 11) % 60:02d}:45 [INFO] yunce.audit.daemon: probe_cycle seq={idx:04d} status=CHECKED")
        if idx == 120:
            audit_lines.append("2026-11-09 12:00:00 [WARN] yunce.audit.closed_diff: historical closed overbilling verified on INV-202609-0012 (overbilled 20000 cents) and INV-202610-0024 (overbilled 15000 cents); awaiting cross-period billing_adjustments in 2026-11")
        if idx == 260:
            audit_lines.append("2026-11-10 08:30:00 [WARN] yunce.audit.gl: period=2026-11 gl_exporter trial_balance_matched=False (AR debit != revenue+tax credits on adjusted invoices) & three_way_cdr_bill_gl join fan-out inflated joined_crosscheck_cents")
        if idx == 440:
            audit_lines.append("2026-11-11 09:45:00 [WARN] yunce.audit.revrec: rebaseline_deferred_schedule_on_upgrade mutated RECOGNIZED closed-period schedule rows; promo_liability_rollforward omitted promo refund restorations")
        if idx == 620:
            audit_lines.append("2026-11-12 11:20:00 [WARN] yunce.audit.treasury: fx_hedging_revaluation included PAID invoice fxs_029_paid with inverted gain/loss sign; clearinghouse_fee_auditor billed 2-cent fee on 0-cash promo payment; intercompany rollup failed to exclude intercompany=true tenant")
        if idx == 790:
            audit_lines.append("2026-11-13 13:15:00 [WARN] yunce.audit.sox: SOX-FIN-06 missed case/space self-approval on apv_sod_leak_01; subagent_split_router paid full parent_tier_bps instead of differential override; analytics MRR counted SUSPENDED/CANCELLED_AT_PERIOD_END & promo payments; CSV exporter lacked formula-injection quote & deterministic id tie-breaker")
    (logs_dir / "gl_revrec_audit.log").write_text("\n".join(audit_lines) + "\n", encoding="utf-8")
    total_lines += len(audit_lines)

    exp_dir = TEMPLATE_DIR / "data" / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "reconcile_2026-10_summary.txt").write_text(
        "period=2026-10\nstatus=CLOSED\nverified_by=finance_director\n",
        encoding="utf-8",
    )
    return total_lines


if __name__ == "__main__":
    fb_cnt = build_feedback_sheet()
    db_info = build_database()
    log_cnt = build_logs()
    print(f"Feedback items built: {fb_cnt}")
    print(f"DB built: {db_info}")
    print(f"Logs built: {log_cnt} lines")
