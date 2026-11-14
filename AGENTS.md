# AGENTS.md — legacy-rescue-xiaonuo 操作说明

> 给进入本目录的 **AI 代理**看的操作说明。
> 本仓库采用与 `silicon-rider-xiaonuo` 一致的**单次执行者收尾 + 盲评后统一定稿模式**：被测模型自己完成“起局 → 沙盒排障 → 收工封包 → 计时校验与生成匿名盲评包”全流程（不提前生成得分）；随后独立评委在盲评阶段对匿名事实卡打分；最后由评测发起人手动运行一键出榜脚本，**统一完成官方脚本打分定稿与总分合成**。

## 0. 先分清：你在「选手域」还是「评委/汇总域」

这不是三个人，而是**两个角色阶段**。被测模型在排障收工后负责生成**匿名盲评包**，但**绝不能在排障期间偷看评分探针或参考补丁，也不能提前运行正式计分、兼任评委或运行最终出榜**。

| 角色域 | 典型承担者 | 你需要自己完成的动作 | 严禁触碰的红线（违反即成绩作废） |
| --- | --- | --- | --- |
| **选手域（含盲评打包收尾）** | 被测模型（可能就是正在读这份文件的你） | 1. 运行 `start_rescue.py` 起局；<br>2. 在 `sandbox/<run_id>/` 内修代码、订正脏账、写测试、填报告；<br>3. 运行 `finish_rescue.py` 收工封包并自报词元；<br>4. 收工后运行 `timing_audit.py` 与 `judge_pack.py` 生成匿名盲评包 | **排障期间严禁读取、列出或搜索** `src/scoring/`、`src/builders/`、`reference/`、`configs/`、`runs/`、`leaderboard/`；严禁修改任何评测/打包脚本；严禁运行 `score_delivery.py`、`judge_submit.py` 或 `finalize.py` |
| **评委 / 汇总域** | 独立评委模型 / 评测发起人 | 盲评阶段评委仅阅读 `leaderboard/blind/<pack_id>/` 并运行 `judge_submit.py` 提交 D 分；全部评完后由发起人运行 `python leaderboard/finalize.py` 统一执行脚本客观分定稿与总分合成出榜 | 评委严禁查看 `leaderboard/blind-maps/`、`leaderboard/reviews.jsonl` 或 `runs/` |

---

## 1. 选手域：三分钟上手（被测模型只看这一节）

> **当你收到“你是被测模型，开始测试”时（零追问直通规则）**：
> 1. **不要向用户反问确认**，立即按本节 4 步自动执行到底！
> 2. **自动确定模型名 `<Model>`**：若用户在提示词里指定了名字则用指定名；若用户只说了“你是被测模型，开始测试”，请直接使用**你当前自身的真实模型名称**（例如 `claude-sonnet-4-6`、`gpt-5`、`gemini-2.5-pro` 等，严禁照抄示例里的 `DemoModel`）。
> 3. **自动分配沙盒**：直接运行下方第一步命令，脚本会自动为你分配不冲突的 `<Model>-r1`（或顺延 `r2`）并创建 `sandbox/<run_id>/`。

在**仓库根目录**按顺序执行以下 4 步（将 `<你的真实模型名>` 替换为你自己的模型名）：

### 第一步：起局（自动创建沙盒并打下起始时间戳 `t0`）
```sh
python src/cli/start_rescue.py --model <你的真实模型名>
```
- 命令会自动分配 `run_id`（如 `<Model>-r1`），在 `sandbox/<run_id>/` 下生成纯净的带病遗留系统，并在 `runs/<run_id>/session_start.json` 记录不可伪造的开局时间 `t0`（终端会打印分配好的 `run_id` 与沙盒路径）。
- 若同一模型跑多局，**必须串行**（跑完一局收工后再起下一局），切勿并行导致排队时间计入端到端耗时。

### 第二步：在 `sandbox/<run_id>/` 内完成排障（核心工作）
进入第一步生成的 `sandbox/<run_id>/` 阅读其中的 `README.md`、`docs/`、`反馈汇总单.md` 与 `logs/`，面对多代并存的企业级遗留工程原地完成 4 项交付：
1. **修复前后端与定时任务代码**：顺着生产日志、中间件、门面层、兼容桥接层、事件钩子与领域模型理清真实活跃链路，定位底层根因，切忌误改进已废弃的死代码目录或做大面积破坏性重构。
2. **安全订正数据库 `sandbox/<run_id>/data/yunce_billing.db`**：
   - 将 `2026-11`（`OPEN`）未结清账期内的异常错账、重复单、卡死单与失衡钱包分毫不差修平（勿误伤健康租户）；
   - **铁律：严禁直接修改或覆写 `2026-09`、`2026-10`（`CLOSED`）已封账账期的历史账单与归档总额**；已封账历史差额必须在当前 `OPEN` 期写入 `billing_adjustments` 调账表；
   - **保护存量老租户**：严禁删改 `ACTIVE_LEGACY` / `YUAN_STR` 历史异构老租户兼容分支，也勿开启尚未完备的实验灰度流水线；
   - **识别伪反馈与越界需求**：对符合产品与税务规则的累进阶梯、退订不退费、价外增值税及滞纳金逻辑保持定力，切勿盲目顺从改坏。
3. **补充复现与回归测试**：在 `sandbox/<run_id>/tests/` 下新增能复现原暗病并在修复后通过的测试。
4. **填写报告**：按固定大纲填写 `sandbox/<run_id>/事故排查与处置说明.md`。

> **排障阶段防作弊硬约束**：在执行第三步 `finish_rescue.py` 之前，你的文件读取与搜索范围**只能限于 `sandbox/<run_id>/` 内部**，绝对不得读取上级仓库的 `src/scoring/`、`src/builders/`、`reference/` 或 `configs/`。

### 第三步：收工封包与词元自报（打下结束时间戳 `t1`）
排障与自测全部完成后，回到仓库根目录执行：
```sh
python src/cli/finish_rescue.py --sandbox sandbox/<run_id> \
  --tokens-input <本局累计输入词元数> \
  --tokens-output <本局累计输出词元数> \
  --commands-count <本局命令执行次数>
```
- 若宿主环境拿不到词元统计，可传 `0`。该命令会将最终交付物冻结至 `runs/<run_id>/delivery/` 并生成 `runs/<run_id>/protocol.json`。

### 第四步：执行者收尾（校验计时 + 生成匿名盲评包）
收工封包后，运行计时审计与盲评打包脚本（仅提取脱敏事实卡，不提前计算或写入正式得分）：
```sh
# 1. 校验计时窗口无重叠、无异常
python src/scoring/timing_audit.py runs --strict

# 2. 生成匿名盲评包（产出 leaderboard/blind/<pack_id>/ 与脱敏事实卡，不产出 评分.json）
python src/scoring/judge_pack.py --runs runs/<run_id>
```
完成后，将生成的 `leaderboard/blind/<pack_id>/` 目录路径汇报给用户即可。**不要运行 `score_delivery.py`、`judge_submit.py` 或 `finalize.py`。**

---

## 2. 评委与汇总域：盲评阶段打分与最终一键出榜

### 第一阶段（盲评阶段）：独立评委打分（仅看盲评包目录）
独立评委打开 `leaderboard/blind/<pack_id>/`，阅读其中的 `JUDGE_README.md` 与 `case-XX.md`（脱敏事实卡 + 选手排查说明），对每个 case 执行一次提交：
```sh
python src/scoring/judge_submit.py --pack-dir leaderboard/blind/<pack_id> --case-id case-01 \
  --judge-id <评委ID> --judge-model <评委模型> \
  --D1 <0-8> --D2 <0-6> --D3 <0-6> --evidence "[引用的事实卡证据]" --note "<简短评语>"
```
- 盲评分数自动追加写入 `leaderboard/reviews.jsonl`，不会向评委回显其他评委分数，也不会在此阶段生成总分。

### 第二阶段（统一定稿出榜）：评测发起人手动运行一键出榜
所有评委完成盲评提交后，由你手动运行：
```sh
python leaderboard/finalize.py
```
- 该命令会**从头对冻结交付快照执行权威脚本打分定稿**（产出 `runs/<run_id>/评分.json` 的 `A/B/C/T` 80 分客观分），并与 `leaderboard/reviews.jsonl` 中的盲评 `D` 分（20 分）统一合成为 100 分制最终成绩，输出裁决留档 `leaderboard/verdicts/<Model>.json` 并更新总榜 [`leaderboard/scores.md`](leaderboard/scores.md)。
