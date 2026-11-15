# 评测流转与出榜手册（v4.0 三轮定性门禁 + 硬锚点盲评统一定稿制）

本基准采用**三轮预发定性门禁 + 单次执行者收尾 + 盲评后统一定稿模式**：无需专职主控人员代敲沙盒命令，由被测模型自行完成从起局计时到生成匿名盲评包的全过程（选手阶段绝不提前生成正式得分），独立评委依据客观覆盖率硬锚点表完成盲评后，由评测发起人一键统一完成脚本客观分定稿与总分合成。

## 1. 被测模型自己完成的流程（选手域 · 含最多 3 轮预发定性门禁）
1. **起局**：`python src/cli/start_rescue.py --model <Model>`（自动分配 `sandbox/<Model-r1>` 并记录不可伪造的起始时间锚点 `t0`）。
2. **沙盒排障与三轮预发门禁巡检**：
   - 仅在 `sandbox/<Model-r1>/` 内排查修复 60 个独立跨层暗病（含 24 个零工单潜伏暗病）、自主编写全库对账脚本安全订正 `data/yunce_billing.db` 中 `2026-11` 开放期 44 处行级脏账 + 3 大子账本与 2 笔跨期调账单、补充细粒度 `tests/` 回归测试、填写完整覆盖 `F01`～`F68` 的 `事故排查与处置说明.md`（期间严禁读取 `src/scoring/`、`src/builders/`、`reference/`、`configs/`、`runs/`、`leaderboard/`、`DEV_ARCHITECTURE_MEMORY.md`）。
   - 每轮完成后运行 `python src/cli/checkpoint_round.py --sandbox sandbox/<Model-r1> --round <1|2|3> --summary "..."`（最多 3 轮）：系统自动冻结当前轮次快照、记录单轮耗时与累计耗时，并仅返回**七大业务域**的「已闭环 / 仍有异常未闭环」定性信号（隐去题目分母，且严格屏蔽伪反馈陷阱与封账红线状态）。首轮一次闭环计 `1.00x`，第 2 轮补齐项计 `0.85x`，第 3 轮或最终封包补齐项计 `0.70x`。若第 1 轮七大域已全部闭环，可直接进入下一步收工封包。
3. **收工封包**：`python src/cli/finish_rescue.py --sandbox sandbox/<Model-r1> --tokens-input <N> --tokens-output <N> --commands-count <N>`。
4. **计时校验与盲评打包**（仅提取脱敏探针状态与客观覆盖率硬锚点表，不落盘 `评分.json`）：
   - `python src/scoring/timing_audit.py runs --strict`
   - `python src/scoring/judge_pack.py --runs runs/<Model-r1>`

## 2. 评委与评测发起人完成的 2 步（评委/汇总域）
1. **盲评阶段**：仅将 `leaderboard/blind/<pack_id>/` 发给独立评委，评委严格遵守包内 `JUDGE_README.md` 与 `case-XX.md` 顶部的**客观覆盖率硬锚点封顶表**，运行 `src/scoring/judge_submit.py` 提交 `D1`/`D2`/`D3` 至 `leaderboard/reviews.jsonl`。
2. **最终一键定稿出榜**：所有评委提交后，手动运行 `python leaderboard/finalize.py`，系统将从头对冻结交付快照与各轮门禁快照执行官方脚本客观分定稿（按 `1.00 / 0.85 / 0.70` 轮次系数与新耗时半衰期产出 `runs/<Model-r1>/评分.json` 的 80 分客观分），并与盲评 20 分统一合成输出 `leaderboard/verdicts/<Model>.json` 与总榜 `leaderboard/scores.md`。

## 3. 仓库基准自检（维护者校准使用）
```sh
python reference/verify_benchmark.py
```
