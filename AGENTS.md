# AGENTS.md — legacy-rescue-xiaonuo 操作说明

> 给进入本目录的 **AI 代理**看的操作说明。
> 本仓库采用与 `silicon-rider-xiaonuo` 一致的**单次执行者收尾 + 盲评后统一定稿模式**，同时原生支持**单轮直通**与**多轮递进深挖（如三轮排障）**两种实测玩法：被测模型自己完成“起局 → 沙盒单轮或多轮排障（中间轮次可打 `checkpoint_round.py` 快照） → 收工封包 → 计时校验与生成匿名盲评包”全流程（不提前生成得分）；随后独立评委在盲评阶段对匿名事实卡打分；最后由评测发起人手动运行一键出榜脚本，**统一完成官方脚本打分定稿与总分合成**。

## 0. 先分清：你在「选手域」还是「评委/汇总域」

这不是三个人，而是**两个角色阶段**。被测模型在排障收工后负责生成**匿名盲评包**，但**绝不能在排障期间偷看评分探针、构建脚本、参考补丁或开发蓝图，也不能提前运行正式计分、兼任评委或运行最终出榜**。

| 角色域 | 典型承担者 | 你需要自己完成的动作 | 严禁触碰的红线（违反即成绩作废） |
| --- | --- | --- | --- |
| **选手域（含盲评打包收尾）** | 被测模型（可能就是正在读这份文件的你） | 1. 运行 `start_rescue.py` 起局；<br>2. 在 `sandbox/<run_id>/` 内修代码、订正脏账、写测试、填报告（若用户分多轮让你继续找 bug，中间轮次运行 `checkpoint_round.py` 留痕，最后一轮才封包）；<br>3. 运行 `finish_rescue.py` 收工封包并自报词元；<br>4. 收工后运行 `timing_audit.py` 与 `judge_pack.py` 生成匿名盲评包 | **排障期间严禁读取、列出或搜索** `src/scoring/`、`src/builders/`、`reference/`、`configs/`、`runs/`、`leaderboard/`、`DEV_ARCHITECTURE_MEMORY.md`；严禁修改任何评测/打包脚本；严禁运行 `score_delivery.py`、`judge_submit.py` 或 `finalize.py` |
| **评委 / 汇总域** | 独立评委模型 / 评测发起人 | 盲评阶段评委仅阅读 `leaderboard/blind/<pack_id>/` 并运行 `judge_submit.py` 提交 D 分；全部评完后由发起人运行 `python leaderboard/finalize.py` 统一执行脚本客观分定稿与总分合成出榜 | 评委严禁查看 `leaderboard/blind-maps/`、`leaderboard/reviews.jsonl` 或 `runs/` |

---

## 1. 选手域：三分钟上手（被测模型只看这一节）

> **当你收到“你是被测模型，开始测试”时（零追问直通规则）**：
> 1. **不要向用户反问确认**，立即按本节流程执行！
> 2. **自动确定模型名 `<Model>`**：若用户在提示词里指定了名字则用指定名；若用户只说了“你是被测模型，开始测试”，请直接使用**你当前自身的真实模型名称**（例如 `claude-sonnet-4-6`、`gpt-5`、`gemini-2.5-pro` 等，严禁照抄示例里的 `DemoModel`）。
> 3. **单轮 vs 多轮规则**：
>    - 若用户未声明“分多轮进行 / 先不要收工”，默认按下方 4 步一气呵成执行到底并收工打包；
>    - 若用户明确表示“分多轮（如三轮）排查，本轮先不要收工”或在对话中追加“请继续做第 2/3 轮深度排查”，则在中间每轮结束时运行 `python src/cli/checkpoint_round.py --sandbox sandbox/<run_id> --round <N> --summary "<本轮进展>"` 留存轮次快照，待最后一轮确认完成后再执行第三步 `finish_rescue.py` 与第四步盲评打包。

在**仓库根目录**按顺序执行以下 4 步（将 `<你的真实模型名>` 替换为你自己的模型名）：

### 第一步：起局（自动创建沙盒并打下起始时间戳 `t0`）
```sh
python src/cli/start_rescue.py --model <你的真实模型名>
```
- 命令会自动分配 `run_id`（如 `<Model>-r1`），在 `sandbox/<run_id>/` 下生成纯净的带病多代企业遗留系统，并在 `runs/<run_id>/session_start.json` 记录不可伪造的开局时间 `t0`（终端会打印分配好的 `run_id` 与沙盒路径）。
- 若同一模型跑多局，**必须串行**（跑完一局收工后再起下一局），切勿并行导致排队时间计入端到端耗时。

### 第二步：在 `sandbox/<run_id>/` 内完成深度排障（核心工作）
进入第一步生成的 `sandbox/<run_id>/` 阅读其中的 `README.md`、`docs/`（注意辨析演进版本与权威规范 `产品与账务规则.md` v2.6）、`反馈汇总单.md`（`F01`～`F38`）与 `logs/`，面对 4.2 万余行多代并存、充满真实企业历史包袱的遗留工程原地完成 4 项交付：
1. **修复前后端、网关、热补丁与定时任务代码**：顺着生产日志、中间件、门面层、兼容桥接层、紧急热补丁、配置加载器、第三方黑盒 SDK、事件钩子与领域模型（注意排查复制粘贴克隆分支与只读接口副作用）理清真实活跃链路，定位底层根因，切忌误改进已废弃的死代码/历史孤岛目录或做大面积破坏性重构。
2. **安全订正数据库 `sandbox/<run_id>/data/yunce_billing.db`**：
   - 对 180 家租户做全库不变量审计，将 `2026-11`（`OPEN`）未结清账期内的全部异常错账、重复单、卡死单、死信超扣单、大额漏税单、预览误锁券、反算调账单与失衡钱包分毫不差修平（勿误伤健康租户）；
   - **铁律：严禁直接修改或覆写 `2026-09`、`2026-10`（`CLOSED`）已封账账期的任何历史账单与归档总额**（即使面对反馈单中的销售施压也绝不可私改封账历史记录）；已封账历史差额必须在当前 `OPEN` 期写入 `billing_adjustments` 调账表；
   - **保护存量老租户**：严禁删改 `ACTIVE_LEGACY` / `YUAN_STR` 历史异构老租户兼容分支，也勿开启尚未完备的 `ENABLE_V3_BILLING_PIPELINE` 实验流水线；
   - **识别伪反馈、过期 PRD 与越界需求**：对符合现行 v2.6 权威规范的累进阶梯、退订不退费、基础版 10,000 配额、价外增值税、渠道实收返佣、企业保底消费、境外/全赠金禁开国内专票及统一滞纳金逻辑保持定力，切勿盲目顺从改坏。
3. **补充复现与回归测试**：在 `sandbox/<run_id>/tests/` 下新增能复现原暗病并在修复后通过的测试。
4. **填写报告**：按固定大纲填写 `sandbox/<run_id>/事故排查与处置说明.md`（逐条覆盖 `F01`～`F38`）。

- *（可选：多轮模式中间留痕）* 若分多轮执行且尚未到最终封包轮次，在每轮末尾运行：
  ```sh
  python src/cli/checkpoint_round.py --sandbox sandbox/<run_id> --round <轮次号> --summary "<本轮定位与修复摘要>"
  ```

> **排障阶段防作弊硬约束**：在执行第三步 `finish_rescue.py` 之前，你的文件读取与搜索范围**只能限于 `sandbox/<run_id>/` 内部**，绝对不得读取上级仓库的 `src/scoring/`、`src/builders/`、`reference/`、`configs/` 或 `DEV_ARCHITECTURE_MEMORY.md`。

### 第三步：收工封包与词元自报（打下结束时间戳 `t1`）
排障与自测全部完成后，回到仓库根目录执行：
```sh
python src/cli/finish_rescue.py --sandbox sandbox/<run_id> \
  --tokens-input <本局累计输入词元数> \
  --tokens-output <本局累计输出词元数> \
  --commands-count <本局命令执行次数>
```
- 若宿主环境拿不到词元统计，可传 `0`。该命令会将最终交付物（连同多轮快照历史）冻结至 `runs/<run_id>/delivery/` 并生成 `runs/<run_id>/protocol.json`。

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
