# -*- coding: utf-8 -*-
"""企业会计准则第 14 号——合同变更（Contract Modification）三种会计处理判定与累计追补调整（Cumulative Catch-Up）计算器：
情形 A：新增可明确区分商品且新增对价反映单独售价（SSP）-> 作为单独新合同处理；
情形 B：未履行部分与已履行部分可明确区分，但对价未反映 SSP -> 终止原合同并将未确认对价与新增对价合并按未来剩余期前瞻法分摊；
情形 C：不可明确区分 -> 视为原合同组成部分，在合同变更日进行当期收入累计追补调整（Catch-Up）。
"""
from typing import Any, Dict


def evaluate_ifrs15_contract_modification(
    original_total_price_cents: int,
    original_total_months: int,
    elapsed_months: int,
    already_recognized_rev_cents: int,
    added_price_cents: int,
    added_months: int,
    is_distinct_remaining_service: bool = True,
    priced_at_standalone_ssp: bool = False,
) -> Dict[str, Any]:
    orig_p = max(0, int(original_total_price_cents))
    orig_m = max(1, int(original_total_months))
    done_m = max(0, min(orig_m, int(elapsed_months)))
    rec_so_far = max(0, int(already_recognized_rev_cents))
    add_p = int(added_price_cents)
    add_m = max(0, int(added_months))

    if is_distinct_remaining_service and priced_at_standalone_ssp and add_p > 0 and add_m > 0:
        return {
            "treatment_code": "CASE_A_SEPARATE_CONTRACT",
            "modification_date_catchup_cents": 0,
            "prospective_monthly_rev_original_cents": int(round(orig_p / float(orig_m))),
            "prospective_monthly_rev_addon_cents": int(round(add_p / float(add_m))),
            "remaining_months": max(orig_m - done_m, add_m),
        }

    rem_months = max(1, (orig_m - done_m) + add_m)
    unrecognized_orig = max(0, orig_p - rec_so_far)

    if is_distinct_remaining_service:
        blended_pool = max(0, unrecognized_orig + add_p)
        prospect_monthly = int(round(blended_pool / float(rem_months)))
        return {
            "treatment_code": "CASE_B_PROSPECTIVE_TERMINATION_AND_REPLACEMENT",
            "modification_date_catchup_cents": 0,
            "blended_unrecognized_pool_cents": blended_pool,
            "prospective_monthly_rev_cents": prospect_monthly,
            "remaining_months": rem_months,
        }

    revised_total_price = max(0, orig_p + add_p)
    revised_total_months = max(1, orig_m + add_m)
    pct_complete_bps = int((done_m * 10000) // revised_total_months)
    cumulative_should_be = (revised_total_price * pct_complete_bps) // 10000
    catch_up = cumulative_should_be - rec_so_far
    future_monthly = int(round(max(0, revised_total_price - cumulative_should_be) / float(max(1, revised_total_months - done_m))))
    return {
        "treatment_code": "CASE_C_CUMULATIVE_CATCH_UP",
        "completion_percentage_bps": pct_complete_bps,
        "modification_date_catchup_cents": catch_up,
        "prospective_monthly_rev_cents": future_monthly,
        "remaining_months": max(1, revised_total_months - done_m),
    }
