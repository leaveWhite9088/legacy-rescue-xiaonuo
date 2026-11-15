# AGENTS.md — legacy-rescue-xiaonuo 操作说明

> 给进入本目录的 **AI 代理**看的操作说明。
> 本仓库采用**三轮预发定性门禁 + 单次执行者收尾 + 盲评后统一定稿模式**：被测模型收到“你是被测模型，开始测试”后，自己一条龙完成“起局计时 → 最多三轮沙盒排障与定性门禁巡检 → 收工封包 → 计时校验与生成匿名盲评包”全流程（选手阶段绝不生成正式得分）；随后独立评委在盲评阶段依据客观覆盖率硬锚点表对匿名事实卡打分；最后由评测发起人手动运行一键出榜脚本，**统一完成官方脚本打分定稿（含 `1.00 / 0.85 / 0.70` 轮次阶梯系数与时间分）与总分合成**。

## 0. 先分清：你在「选手域」还是「评委/汇总域」

这不是三个人，而是**两个角色阶段**。被测模型在排障收工后负责生成**匿名盲评包**，但**绝不能在排障期间偷看评分探针、门禁实现、构建脚本、参考补丁或开发蓝图，也不能提前运行正式计分、兼任评委或运行最终出榜**。

| 角色域 | 典型承担者 | 你需要自己完成的动作 | 严禁触碰的红线（违反即成绩作废） |
| --- | --- | --- | --- |
| **选手域（含三轮门禁与盲评打包收尾）** | 被测模型（可能就是正在读这份文件的你） | 1. 运行 `start_rescue.py` 起局计时；<br>2. 在 `sandbox/<run_id>/` 内完成全面排障后运行 `checkpoint_round.py` 提交预发定性门禁（最多 3 轮：若七大业务域全闭环即可直接封包拿全额修复分，若有未闭环大域则继续深挖第 2、3 轮）；<br>3. 运行 `finish_rescue.py` 收工封包并自报词元；<br>4. 收工后运行 `timing_audit.py` 与 `judge_pack.py` 生成匿名盲评包 | **排障期间严禁读取、列出或搜索** `src/scoring/`、`src/builders/`、`reference/`、`configs/`、`runs/`、`leaderboard/`、`DEV_ARCHITECTURE_MEMORY.md`；严禁修改任何评测/门禁/打包脚本；严禁运行 `score_delivery.py`、`gatekeeper.py`、`judge_submit.py` 或 `finalize.py` |
| **评委 / 汇总域** | 独立评委模型 / 评测发起人 | 盲评阶段评委仅阅读 `leaderboard/blind/<pack_id>/` 并严格按客观覆盖率硬锚点表运行 `judge_submit.py` 提交 D 分；全部评完后由发起人运行 `python leaderboard/finalize.py` 统一执行脚本客观分定稿与总分合成出榜 | 评委严禁查看 `leaderboard/blind-maps/`、`leaderboard/reviews.jsonl` 或 `runs/` |

---

## 1. 选手域：操作流程（被测模型只看这一节）

> **当你收到“你是被测模型，开始测试”时（零追问直通规则）**：
> 1. **不要向用户反问确认**，立即按本节 4 步一气呵成执行到底！
> 2. **自动确定模型名 `<Model>`**：若用户在提示词里指定了名字则用指定名；若用户只说了“你是被测模型，开始测试”，请直接使用**你当前自身的真实模型名称**（例如 `claude-sonnet-4-6`、`gpt-5`、`gemini-2.5-pro` 等，严禁照抄示例里的 `DemoModel`）。
> 3. **三轮定性门禁与首轮满分激励**：
>    - 每局最多可调用 **3 次** `checkpoint_round.py` 预发门禁巡检。门禁每次先冻结当前快照并记录单轮耗时，再返回**七大业务域**的定性状态（「已闭环」或「仍有异常未闭环」，**不透露题数，且严格隐去回归防误伤与合规红线状态**）。
>    - **首轮一次闭环的修复项计 `100%`（`1.00x`）满分**；靠第 2 轮门禁提示后补齐的修复项按 `85%`（`0.85x`）计分；第 3 轮补齐项按 `70%`（`0.70x`）计分。若第 1 轮七大业务域已全部显示「已闭环」，核验报告后直接收工封包即可，无需再跑第 2、3 轮。

在**仓库根目录**按顺序执行以下 4 步（将 `<你的真实模型名>` 替换为你自己的模型名）：

### 第一步：起局（自动创建沙盒并打下起始时间戳 `t0`）
```sh
python src/cli/start_rescue.py --model <你的真实模型名>
```
- 命令会自动分配 `run_id`（如 `<Model>-r1`），在 `sandbox/<run_id>/` 下生成独立的待排障企业遗留系统，并在 `runs/<run_id>/session_start.json` 记录不可伪造的开局时间 `t0`。
- 若同一模型跑多局，**必须串行**（跑完一局收工后再起下一局），切勿并行导致排队时间计入端到端耗时。

### 第二步：在 `sandbox/<run_id>/` 内完成排障并通过预发定性门禁（最多 3 轮）
进入 `sandbox/<run_id>/` 阅读 `README.md`、`docs/`、`反馈汇总单.md` 与 `logs/`，面对多代演进的企业遗留工程原地完成 4 项交付：
1. **精准修复活跃链路前后端与批处理缺陷**：追踪实际挂载的路由、服务、后台任务与前端脚本，排查线上反馈与系统内潜伏的未报障缺陷；保持改动收敛克制，避免破坏合规存量业务特例或误改未挂载的历史残留文件。
2. **审计并合规订正数据库 `sandbox/<run_id>/data/yunce_billing.db`**：结合现行生效的业务与财务会计制度，自主编写全库对账脚本清查并修平异常账务与子账本数据，严格遵守会计期间管理纪律。
3. **补充细粒度复现与回归测试**：在 `sandbox/<run_id>/tests/` 下新增细粒度 `unittest` 测试方法（需在未修复原件上真实失败抓错、在修复后绿灯通过），同时保持既有基线测试全绿。
4. **填写报告**：按模板结构填写 `sandbox/<run_id>/事故排查与处置说明.md`（逐条覆盖 `F01`～`F68` 全部反馈判定，并完整记录自主排查发现的潜伏缺陷与数据订正台账）。

每轮自测完成后，运行预发定性门禁巡检（第 1 轮 `--round 1`，若有未闭环大域则继续深挖后提交 `--round 2`、最多 `--round 3`；若七大业务域均已闭环则直接进入第三步）：
```sh
python src/cli/checkpoint_round.py --sandbox sandbox/<run_id> --round 1 --summary "<本轮排查与修复摘要>"
```

> **排障阶段防作弊硬约束**：在执行第三步 `finish_rescue.py` 之前，你的文件读取与搜索范围**只能限于 `sandbox/<run_id>/` 内部**，绝对不得读取上级仓库的 `src/scoring/`、`src/builders/`、`reference/`、`configs/`、`runs/`、`leaderboard/` 或 `DEV_ARCHITECTURE_MEMORY.md`。

### 第三步：收工封包与词元自报（打下结束时间戳 `t1`）
排障与门禁全部完成后，回到仓库根目录执行：
```sh
python src/cli/finish_rescue.py --sandbox sandbox/<run_id> \
  --tokens-input <本局累计输入词元数> \
  --tokens-output <本局累计输出词元数> \
  --commands-count <本局命令执行次数>
```
- 若宿主环境拿不到词元统计，可传 `0`。该命令会记录端到端总耗时与各轮分段耗时，将最终交付物冻结至 `runs/<run_id>/delivery/` 并生成 `runs/<run_id>/protocol.json`。

### 第四步：执行者收尾（校验计时 + 生成匿名盲评包）
收工封包后，运行计时审计与盲评打包脚本（仅提取脱敏事实卡，不提前计算或写入正式得分）：
```sh
# 1. 校验端到端计时窗口、轮次时间单调性与无重叠异常
python src/scoring/timing_audit.py runs --strict

# 2. 生成匿名盲评包（产出 leaderboard/blind/<pack_id>/ 与脱敏事实卡，不产出 评分.json）
python src/scoring/judge_pack.py --runs runs/<run_id>
```
完成后，将生成的 `leaderboard/blind/<pack_id>/` 目录路径汇报给用户即可。**不要运行 `score_delivery.py`、`judge_submit.py` 或 `finalize.py`。**

---

## 2. 评委与汇总域：盲评阶段打分与最终一键出榜

### 第一阶段（盲评阶段）：独立评委打分（仅看盲评包目录）
独立评委打开 `leaderboard/blind/<pack_id>/`，阅读其中的 `JUDGE_README.md` 与 `case-XX.md`（含**客观覆盖率硬锚点表**、门禁轮次轨迹、全部探针事实与选手排查说明），**严守定档与反端水铁律（严禁温和折中、给印象高分或同情分，必须严格按客观硬锚点封顶与缺陷漏查比例拉开真实区分度）**，对每个 case 执行一次提交：
```sh
python src/scoring/judge_submit.py --pack-dir leaderboard/blind/<pack_id> --case-id case-01 \
  --judge-id <评委ID> --judge-model <评委模型> \
  --D1 <0-8> --D2 <0-6> --D3 <0-6> --evidence "[引用的事实卡证据]" --note "<简短评语>"
```

### 第二阶段（统一定稿出榜）：评测发起人手动运行一键出榜
所有评委完成盲评提交后，由你手动运行：
```sh
python leaderboard/finalize.py
```
- 该命令会**从头对冻结交付快照与各轮门禁快照执行权威脚本打分定稿**（按 `1.00 / 0.85 / 0.70` 轮次系数与端到端耗时计算 `A/B/C/T` 80 分客观分，产出 `runs/<run_id>/评分.json`），并与 `leaderboard/reviews.jsonl` 中的盲评 `D` 分（20 分）统一合成为 100 分制最终成绩，输出裁决留档 `leaderboard/verdicts/<Model>.json` 并更新总榜 [`leaderboard/scores.md`](leaderboard/scores.md)。
