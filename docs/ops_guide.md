# 评测流转与出榜手册

本基准采用与 `silicon-rider-xiaonuo` 一致的**单次执行者收尾 + 盲评后统一定稿模式**：无需专职主控人员代敲沙盒命令，由被测模型自行完成从起局到生成匿名盲评包的全过程（不提前生成得分），评委盲评后由评测发起人一键统一完成脚本定稿与总分合成。

## 1. 被测模型自己完成的 4 步（选手域）
1. **起局**：`python src/cli/start_rescue.py --model <Model>`（自动分配 `sandbox/<Model-r1>` 并记录起始时间锚点 `t0`）。
2. **排障**：仅在 `sandbox/<Model-r1>/` 内修复跨层代码、安全订正 `data/yunce_billing.db`、补充 `tests/` 回归测试、填写 `事故排查与处置说明.md`（期间严禁读取 `src/scoring/`、`src/builders/`、`reference/`、`configs/`）。
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
