# 《遗留救火 · 复杂暗病排障基准》（legacy-rescue-xiaonuo v3.0）

> **一句话定位**：单旗舰级、多代架构并存、系统性植入 19 类真实企业级遗留反模式、带 180 租户线上事故现场与跨期脏账包袱的多轮深度排障（DEBUG）评测基准。

## 核心特点
1. **超大规模真实多代企业遗留代码库（471 个文件、35,170+ 行纯源码 + 310+ 行演进文档 + 6,940 行生产日志 = 42,420+ 行）**：围绕“云策企业订阅与阶梯计费账务中心”，完整还原 2023 初创种子归档、2024 第一代包干单体与工程师个人知识孤岛、2025 架构委员会过度设计抽象链与混合双写过渡层、当前主力生产 V2 纵深调用链、深夜值班紧急猴子补丁、第三方财税黑盒 SDK 以及未完备的 V3 实验管线，系统性涵盖高耦合、复制粘贴分叉、死代码、魔法数字、深层布尔陷阱、只读接口写副作用、抽象缓存引用泄漏、文档与代码歧义、隐式符号潜规则、状态机撕裂、并发竞态、跨时区归属错配、监听器与连接句柄泄漏、动态配置漂移等 **19 类真实遗留病灶**。
2. **专为多轮递进深挖设计的 15 大连环暗病 + 38 条真假混杂一线反馈**：埋设 **15 个跨层传导与隐蔽暗病（`BUG-01`～`BUG-15`）**，配套 **38 条多部门原始反馈（`F01`～`F38`）**（含 24 条多对多表象投诉 + 14 条引用 2025 废止旧 PRD 的误导投诉、销售施压私改封账历史单、税率/阶梯/返佣规则误解与架构诱导陷阱），以及 29 张表、180 家租户、236 张账单、82 张数电发票的线上 SQLite 数据库快照（需自主定位并修平 `2026-11` 开放期 **11 处异构脏账**并严守 `2026-09`/`2026-10` 封账红线）。支持单轮直通，也支持通过 `checkpoint_round.py` 开展 2～3 轮递进深挖评测。
3. **两阶段严格解耦（盲评先行 → 一键统一定稿出榜）**：只需对进场模型发送一句“你是被测模型，开始测试”，模型即可一条龙完成“起局计时 → 沙盒内排障交付 → 收工封包 → 计时校验与生成匿名盲评包”（选手收尾阶段只提取脱敏事实卡，不提前生成得分）；独立评委在盲评阶段提交主观分后，由评测发起人最后手动运行 `python leaderboard/finalize.py`，一次性统一完成**官方脚本客观分定稿**与**总分合成出榜**。
4. **80% 机器铁判 + 20% 匿名盲评**：`A(35) + B(20) + C(10) + T(15) + D(20) = 100`，时间效率分 `T` 采用连续指数衰减并以 `A/B` 质量乘数联合封顶。

## 一局怎么跑（被测模型一条龙流程）

详细规范见 [`AGENTS.md`](AGENTS.md)。被测模型在仓库根目录按顺序执行：

```sh
# 1. 起局：自动分配 <Model>-r1 沙盒并打下不可伪造的起始时间戳 t0
python src/cli/start_rescue.py --model <你的真实模型名>

# 2. 排障：仅在 sandbox/<run_id>/ 内完成跨层代码修复、11 处开放期脏账订正、新增回归测试与填写《事故排查与处置说明.md》
#    （可选：若采用三轮递进深挖模式，中间每轮结束可运行 checkpoint_round.py 记录轮次快照而不封包）
python src/cli/checkpoint_round.py --sandbox sandbox/<run_id> --round 1 --summary "首轮显性链路排查"

# 3. 收工：最后一轮完成后打下结束时间戳 t1、冻结交付快照并记录词元消耗
python src/cli/finish_rescue.py --sandbox sandbox/<run_id> --tokens-input 36000 --tokens-output 9500 --commands-count 35

# 4. 收尾：校验计时窗口并生成匿名盲评包（不提前写入正式评分）
python src/scoring/timing_audit.py runs --strict
python src/scoring/judge_pack.py --runs runs/<run_id>
```

## 盲评阶段与最终一键出榜

```sh
# 1. 盲评阶段：独立评委仅看 leaderboard/blind/<pack_id>/ 脱敏事实卡并提交 D 分（D1:0-8, D2:0-6, D3:0-6）
python src/scoring/judge_submit.py --pack-dir leaderboard/blind/<pack_id> --case-id case-01 \
  --judge-id judge-A --judge-model gpt-5 --D1 8 --D2 6 --D3 6 --evidence "[BUG-01..15 PASS]"

# 2. 最终一键出榜：所有盲评完成后手动运行，统一执行脚本客观分定稿（80分）+ 盲评合成（20分） -> leaderboard/scores.md
python leaderboard/finalize.py
```

## 基准开发自检（零修改下限 + 多轮检查点 + 盲评隔离断言 + 黄金补丁满分闭环核验）
```sh
python reference/verify_benchmark.py
```

## 文档索引
- AI 代理操作总则（必读）：[AGENTS.md](AGENTS.md)
- 选手沙盒须知：[docs/contestant_guide.md](docs/contestant_guide.md)
- 评委盲评指南：[docs/judge_guide.md](docs/judge_guide.md)
- 计分与时间维度细则：[docs/scoring.md](docs/scoring.md)
- 评测流转与出榜手册：[docs/ops_guide.md](docs/ops_guide.md)
