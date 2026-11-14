# 评测流转与出榜手册（支持单轮直通与多轮递进深挖）

本基准采用与 `silicon-rider-xiaonuo` 一致的**单次执行者收尾 + 盲评后统一定稿模式**：无需专职主控人员代敲沙盒命令，由被测模型自行完成从起局到生成匿名盲评包的全过程（不提前生成得分），评委盲评后由评测发起人一键统一完成脚本定稿与总分合成。

## 1. 被测模型自己完成的流程（选手域 · 含最多 3 轮预发定性门禁）
1. **起局**：`python src/cli/start_rescue.py --model <Model>`（自动分配 `sandbox/<Model-r1>` 并记录不可伪造的起始时间锚点 `t0`）。
2. **沙盒排障与三轮预发门禁巡检**：
   - 仅在 `sandbox/<Model-r1>/` 内修复 15 处跨层代码缺陷、安全订正 `data/yunce_billing.db` 中 11 处开放期脏账与 1 笔跨期调账、补充 `tests/` 回归测试、填写覆盖 `F01`～`F38` 的 `事故排查与处置说明.md`（期间严禁读取 `src/scoring/`、`src/builders/`、`reference/`、`configs/`、`runs/`、`DEV_ARCHITECTURE_MEMORY.md`）。
   - 每轮完成后运行 `python src/cli/checkpoint_round.py --sandbox sandbox/<Model-r1> --round <1|2|3>`（最多 3 轮）：系统自动冻结当前轮次快照、记录单轮耗时与累计耗时，并仅返回五大业务域的「已闭环 / 仍有异常未闭环」定性信号（不报题目分母，且严格隐藏伪反馈陷阱与封账红线状态）。首轮一次修通计 `1.0x`，第 2 轮补齐项计 `0.9x`，第 3 轮补齐项计 `0.8x`。若第 1 轮已全部闭环，可直接进入下一步收工封包。
3. **收工封包**：`python src/cli/finish_rescue.py --sandbox sandbox/<Model-r1> --tokens-input <N> --tokens-output <N> --commands-count <N>`。
4. **计时校验与盲评打包**（仅提取脱敏事实卡，不落盘 `评分.json`）：
   - `python src/scoring/timing_audit.py runs --strict`
   - `python src/scoring/judge_pack.py --runs runs/<Model-r1>`

## 2. 评委与评测发起人完成的 2 步（评委/汇总域）
1. **盲评阶段**：仅将 `leaderboard/blind/<pack_id>/` 发给独立评委，评委按包内 `JUDGE_README.md` 运行 `src/scoring/judge_submit.py` 提交 `D1`/`D2`/`D3` 至 `leaderboard/reviews.jsonl`。
2. **最终一键定稿出榜**：所有评委提交后，手动运行 `python leaderboard/finalize.py`，系统将从头对冻结交付快照执行官方脚本客观分定稿（产出 `runs/<Model-r1>/评分.json` 的 80 分客观分），并与盲评 20 分统一合成输出 `leaderboard/verdicts/<Model>.json` 与总榜 `leaderboard/scores.md`。

## 3. 仓库基准自检（维护者使用）
```sh
python reference/verify_benchmark.py
```
