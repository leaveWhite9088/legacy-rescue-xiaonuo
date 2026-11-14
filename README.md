# 《遗留救火 · 复杂暗病排障基准》（legacy-rescue-xiaonuo）

> **一句话定位**：单旗舰级、多代架构并存的大型企业遗留工程纵深、带真实 128 租户线上事故现场与跨期脏账包袱的深度排障（DEBUG）评测基准。

## 核心特点
1. **真实多代耦合企业级遗留代码库（327 个源码文件、18,000+ 行纯源码 + 3,500+ 行生产日志 = 21,600+ 行）**：围绕“云策企业订阅与阶梯计费账务中心”，真实还原 2023 初创种子归档、2024 第一代包干单体与运维批处理遗留、2025 H1 过渡期混合双写层、当前主力生产 V2 纵深调用链（路由 → 中间件 → 门面 → 服务 → 跨代兼容桥 → 领域模型 → 事件钩子 → 仓储 → 基础设施）以及未完工灰度特性开关下的 V3 流水线，配套数电发票、财务双签、金蝶/用友/SAP 对接、ASC606 收入确认、FinOps 成本分摊、跨境结算等子系统与多套废弃前端页面，埋设 **7 个跨层传导与并发连环暗病**，并混入 6 条伪反馈/税率误解/良性瞬态告警/越界需求。
2. **去标签化真实事故现场**：沙盒内含近三日 3,564 行多层混合生产日志、架构演进与账务规范文档、16 条一线口语化反馈（不直接喂内部账单号）、以及 128 家租户与 167 张账单的线上数据库快照（所有受灾租户与正常租户采用统一编号体系，需靠 SQL 不变量审计自主揪出 7 处未结清错账并严守 `CLOSED` 封账红线）。
3. **两阶段严格解耦（盲评先行 → 一键统一定稿出榜）**：只需对进场模型发送一句“你是被测模型，开始测试”，模型即可一条龙完成“起局计时 → 沙盒内排障交付 → 收工封包 → 计时校验与生成匿名盲评包”（选手收尾阶段只提取脱敏事实卡，不提前生成得分）；独立评委在盲评阶段提交主观分后，由评测发起人最后手动运行 `python leaderboard/finalize.py`，一次性统一完成**官方脚本客观分定稿**与**总分合成出榜**。
4. **80% 机器铁判 + 20% 匿名盲评**：`A(35) + B(20) + C(10) + T(15) + D(20) = 100`，时间效率分 `T` 采用连续指数衰减并以 `A/B` 质量乘数联合封顶。

## 一局怎么跑（被测模型一条龙流程）

详细规范见 [`AGENTS.md`](AGENTS.md)。被测模型在仓库根目录按顺序执行：

```sh
# 1. 起局：自动分配 <Model>-r1 沙盒并打下不可伪造的起始时间戳 t0
python src/cli/start_rescue.py --model <你的真实模型名>

# 2. 排障：仅在 sandbox/<run_id>/ 内完成跨层代码修复、未结清脏账订正、新增回归测试与填写《事故排查与处置说明.md》
#    （排障期间严禁读取 src/scoring/、src/builders/、reference/、configs/）

# 3. 收工：打下结束时间戳 t1、冻结交付快照并记录词元消耗
python src/cli/finish_rescue.py --sandbox sandbox/<run_id> --tokens-input 18000 --tokens-output 4500 --commands-count 20

# 4. 收尾：校验计时窗口并生成匿名盲评包（不提前写入正式评分）
python src/scoring/timing_audit.py runs --strict
python src/scoring/judge_pack.py --runs runs/<run_id>
```

## 盲评阶段与最终一键出榜

```sh
# 1. 盲评阶段：独立评委仅看 leaderboard/blind/<pack_id>/ 脱敏事实卡并提交 D 分（D1:0-8, D2:0-6, D3:0-6）
python src/scoring/judge_submit.py --pack-dir leaderboard/blind/<pack_id> --case-id case-01 \
  --judge-id judge-A --judge-model gpt-5 --D1 8 --D2 6 --D3 6 --evidence "[BUG-01..07]"

# 2. 最终一键出榜：所有盲评完成后手动运行，统一执行脚本客观分定稿（80分）+ 盲评合成（20分） -> leaderboard/scores.md
python leaderboard/finalize.py
```

## 基准开发自检（零修改下限 + 盲评隔离断言 + 黄金补丁满分闭环核验）
```sh
python reference/verify_benchmark.py
```

## 文档索引
- AI 代理操作总则（必读）：[AGENTS.md](AGENTS.md)
- 选手沙盒须知：[docs/contestant_guide.md](docs/contestant_guide.md)
- 评委盲评指南：[docs/judge_guide.md](docs/judge_guide.md)
- 计分与时间维度细则：[docs/scoring.md](docs/scoring.md)
