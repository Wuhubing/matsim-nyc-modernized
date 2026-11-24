#!/usr/bin/env python3
"""Reconciliation gate (README-s4.md section 3).

  python s4_reconcile.py OUT

Writes OUT/reconcile.json, OUT/reconcile-report.md, OUT/charter_reproduction.csv.
 1. integrity of all 900 persons files (from the check.json of each run) -> integrity_report.md / .csv
 2. charter nine deltas recomputed from group-modes departures vs the charter table (rounding precision)
 3. departures - completed vs stuck for every group x mode x iteration (exact residual; 'stuck' only if exact)
 4. s3 curves and per-person histograms recomputed from the matrices vs out-s3/*.json
 5. s2 aggregate.json completed car legs / share curves vs recomputed

A failed gate is reported, never repaired by changing a tolerance. Exit code 0 even when a gate fails (the verdict is in
reconcile.json 'gates'); s5 / s6 read the verdicts and stop their dependent parts.
"""
import csv, json, os, statistics, sys
from pathlib import Path

import numpy as np

from s4_common import (ITERS, SCENARIOS, SEEDS, all_runs, tag, log, write_json, load_mat, load_grp, run_metrics,
                       group_masks, CHARTER, FINAL, last_true, charter_print_rounding_ok)

S3_DIR = Path(os.environ.get("S3_DIR", os.path.expanduser("~/matsim-work/original-analysis/out-s3")))
S2_DIR = Path(os.environ.get("S2_DIR", os.path.expanduser("~/matsim-work/original-analysis/out-s2")))
ROUND = {"legs_car_charging_related": 0.5, "share_car": 5e-6, "share_pt": 5e-6}  # half unit of the last printed digit


def integrity(out):
    rows, summ = [], {}
    for sc, seed in all_runs():
        chk = json.loads((Path(out) / f"mat-{tag(sc, seed)}.check.json").read_text())
        files = chk["files"]
        summ[tag(sc, seed)] = {k: chk[k] for k in ("complete", "n_persons", "n_issues", "order_identical_files", "rows_per_file_all_equal_n",
                                                    "hash_collision_test_128bit", "cohorts_file_sha256", "person_vs_group", "group_tables")}
        summ[tag(sc, seed)]["files"] = len(files)
        summ[tag(sc, seed)]["writer_flag_mismatch"] = {k: chk[k] for k in chk if k.endswith("vs_64bit_hash_mismatch")}
        summ[tag(sc, seed)]["commit"] = chk["run_json"]["commit"]
        if "replanning_log" in chk:
            summ[tag(sc, seed)]["replanning_log"] = {"innovative_ids": chk["replanning_log"]["innovative_ids"],
                                                     "strategies_csv_sha256": chk["replanning_log"]["strategies_csv_sha256"],
                                                     "persons_csv_unknown_ids": chk["replanning_log"]["persons_csv_unknown_ids"],
                                                     "agents_files": len(chk["replanning_log"]["files"]),
                                                     "agents_issues": sum(1 for f in chk["replanning_log"]["files"]
                                                                          if f["n_unknown"] or f["n_duplicate"] or f["n_missing"] or f["bad_plan_id"])}
        for f in files:
            rows.append({"run": tag(sc, seed), "iteration": f["iteration"], "bytes": f["bytes"], "gz_crc32": f["gz_crc32"],
                         "n_rows": f["n_rows"], "n_unique_ids": f["n_unique_ids"], "duplicates": f["n_duplicate_rows"],
                         "unknown_ids": f["n_unknown_ids"], "missing_ids": f["n_missing_ids"],
                         "order_identical": f["order_identical_to_cohort"], "columns_ok": f["columns_ok"],
                         "bad_numeric": sum(f["bad_numeric"].values()), "dep_ne_comp_plus_stuck": f["dep_ne_comp_plus_stuck"],
                         "cohort_label_mismatch": f["cohort_label_mismatch"]})
    return rows, summ


def charter_gate(out):
    M = {tag(sc, s): run_metrics(load_grp(out, sc, s)) for sc, s in all_runs()}
    lo, hi = FINAL
    res, table = {}, []
    for metric in ("legs_car_charging_related", "share_car", "share_pt"):
        w = {(sc, s): float(np.mean(M[tag(sc, s)][metric][lo:hi + 1])) for sc, s in all_runs()}
        d1 = [w[("schema1", s)] - w[("baseline", s)] for s in SEEDS]
        d2 = [w[("schema2", s)] - w[("baseline", s)] for s in SEEDS]
        dd = [a - b for a, b in zip(d1, d2)]
        for key, vals in (("schema1", d1), ("schema2", d2), ("D", dd)):
            mean, sd1 = statistics.fmean(vals), statistics.stdev(vals)
            sd0 = statistics.pstdev(vals)
            ref_mean, ref_sd, eps = CHARTER[metric][key]
            tol = ROUND[metric]
            ok_mean = abs(mean - ref_mean) <= tol
            ok_print = charter_print_rounding_ok(mean, ref_mean, metric)
            ok_sd1 = abs(sd1 - ref_sd) <= tol
            ok_sd0 = abs(sd0 - ref_sd) <= tol
            same_sign = all(v > 0 for v in vals) or all(v < 0 for v in vals)
            res[f"{metric}|{key}"] = {"recomputed_mean": mean, "charter_mean": ref_mean, "mean_ok_rounding": ok_mean,
                                      "mean_ok_via_original_print_5g_double_rounding": ok_print, "abs_diff_to_charter": abs(mean - ref_mean),
                                      "recomputed_sd_ddof1": sd1, "recomputed_sd_ddof0": sd0, "charter_sd": ref_sd,
                                      "sd_ok_ddof1": ok_sd1, "sd_ok_ddof0": ok_sd0, "per_seed": vals, "same_sign_3of3": same_sign,
                                      "eps": eps, "rounding_tolerance": tol}
            table.append({"metric": metric, "contrast": key, "seed4711": vals[0], "seed4712": vals[1], "seed4713": vals[2],
                          "mean": mean, "charter_mean": ref_mean, "mean_ok": ok_mean, "mean_ok_via_print_5g": ok_print, "abs_diff": abs(mean - ref_mean), "sd_ddof1": sd1, "sd_ddof0": sd0,
                          "charter_sd": ref_sd, "eps": eps, "same_sign_3of3": same_sign})
        # completed vs departures (s2 'legs_car') kept apart
    comp = {}
    for sc, s in all_runs():
        mm = M[tag(sc, s)]
        comp[tag(sc, s)] = {"final_mean_departures_car_related": float(np.mean(mm["legs_car_charging_related"][lo:hi + 1])),
                            "final_mean_completed_car_related": float(np.mean(mm["legs_car_completed_charging_related"][lo:hi + 1])),
                            "final_mean_stuck_car_related": float(np.mean(mm["stuck_car_charging_related"][lo:hi + 1]))}
    c1 = [comp[tag("schema1", s)]["final_mean_completed_car_related"] - comp[tag("baseline", s)]["final_mean_completed_car_related"] for s in SEEDS]
    c2 = [comp[tag("schema2", s)]["final_mean_completed_car_related"] - comp[tag("baseline", s)]["final_mean_completed_car_related"] for s in SEEDS]
    res["completed_car_related_delta_s1_mean"] = statistics.fmean(c1)
    res["completed_car_related_delta_s2_mean"] = statistics.fmean(c2)
    entries = [v for k, v in res.items() if isinstance(v, dict) and "mean_ok_rounding" in v]
    passed = all(v["mean_ok_rounding"] for v in entries)
    res["strict_gate_passed"] = passed
    res["gate_passed_with_documented_explanation"] = all(v["mean_ok_rounding"] or v["mean_ok_via_original_print_5g_double_rounding"] for v in entries)
    return res, table, passed, comp


def residual_gate(out):
    """departures - completed == stuck at every group x mode x iteration (row level) for all nine runs."""
    n_rows = n_bad = 0
    car_rel_resid = {}
    for sc, s in all_runs():
        g, gm = load_grp(out, sc, s)
        for it, d in gm.items():
            for grp, modes in d.items():
                for mode, x in modes.items():
                    n_rows += 1
                    n_bad += int(abs(x["departures"] - x["completed"] - x["stuck"]) > 0.5)
        car_rel_resid[tag(sc, s)] = float(np.mean([gm[it]["charging:related"]["car"]["departures"] - gm[it]["charging:related"]["car"]["completed"]
                                                  for it in range(*(FINAL[0], FINAL[1] + 1))]))
    return {"rows_checked": n_rows, "rows_departures_ne_completed_plus_stuck": n_bad, "passed": n_bad == 0,
            "final_mean_car_related_departures_minus_completed": car_rel_resid}


def s3_recompute(m, log_):
    """Re-implementation of s3_individual.py's quantities from the person x iteration matrices."""
    C, Mh, K = m["choice"], m["real"], m["car_legs"]
    n = C.shape[0]
    U = K > 0
    chgC = np.zeros((n, ITERS), bool); chgM = np.zeros((n, ITERS), bool); chgU = np.zeros((n, ITERS), bool)
    chgC[:, 1:] = C[:, 1:] != C[:, :-1]; chgM[:, 1:] = Mh[:, 1:] != Mh[:, :-1]; chgU[:, 1:] = U[:, 1:] != U[:, :-1]
    newC = np.zeros((n, ITERS), bool); newM = np.zeros((n, ITERS), bool)
    newC[:, 0] = True; newM[:, 0] = True
    for t in range(1, ITERS):
        newC[:, t] = ~(C[:, :t] == C[:, t, None]).any(1)
        newM[:, t] = ~(Mh[:, :t] == Mh[:, t, None]).any(1)
    F0 = FINAL[0]
    inFC = (C[:, None, F0:] == C[:, :, None]).any(2)
    inFM = (Mh[:, None, F0:] == Mh[:, :, None]).any(2)

    def distinct(X):
        s = np.sort(X[:, F0:], axis=1)
        return 1 + (np.diff(s, axis=1) != 0).sum(1)

    per = {"settle_choice": np.where((~inFC).any(1), last_true(~inFC) + 1, 0),
           "settle_mode": np.where((~inFM).any(1), last_true(~inFM) + 1, 0),
           "last_change_choice": last_true(chgC), "last_change_mode": last_true(chgM),
           "last_new_choice": last_true(newC), "last_new_mode": last_true(newM),
           "n_choice_final": distinct(C), "n_mode_final": distinct(Mh),
           "last_change_car_use": last_true(chgU),
           "car_use_flips_in_final": (chgU[:, F0 + 1:].any(1)).astype(int),
           "car_use_final_frac_x10": U[:, F0:].sum(1)}
    if log_ is not None:
        per["last_new_plan_log"] = last_true(log_["plan_created"] == np.arange(ITERS)[None, :])
    return dict(chgC=chgC, chgM=chgM, chgU=chgU, newC=newC, newM=newM, inFC=inFC, inFM=inFM, U=U), per


def compare_s3(out, sc, seed, tol=1e-9):
    p = S3_DIR / f"s3-{sc}-{seed}.json"
    if not p.exists():
        return {"status": "s3 json not found", "path": str(p)}
    ref = json.loads(p.read_text())
    m = load_mat(out, sc, seed, ["ids", "sub", "coh", "present", "choice", "real", "car_legs"])
    log_ = None
    if sc == "baseline":
        with np.load(Path(out) / f"log-baseline-{seed}.npz") as z:
            log_ = {k: z[k] for k in ("plan_created", "strategy", "logged")}
    sub, coh = m["sub"], m["coh"]
    st, per = s3_recompute(m, log_)
    masks = group_masks(sub, coh)
    masks["replanners"] = sub != "outside"
    res = {"persons": {"mine": int(len(sub)), "s3": ref["persons"]}, "curves": {}, "per_person": {}, "n_curve_series": 0, "n_curve_mismatch": 0,
           "n_hist_checked": 0, "n_hist_mismatch": 0}
    curve_map = {"choice_changed": st["chgC"], "mode_changed": st["chgM"], "car_use_changed": st["chgU"], "car_use": st["U"],
                 "new_choice": st["newC"], "new_mode": st["newM"], "in_final_choice_set": st["inFC"], "in_final_mode_set": st["inFM"]}
    worst = 0.0
    for g in ("all", "replanners", "charging:related", "charging:unrelated", "subpopulation:man", "subpopulation:nonman"):
        for k, X in curve_map.items():
            a = np.array(ref["curves"][g][k]); b = X[masks[g]].mean(0)
            diff = float(np.max(np.abs(a - b)))
            worst = max(worst, diff); res["n_curve_series"] += 1
            if diff > tol:
                res["n_curve_mismatch"] += 1
                res["curves"][f"{g}|{k}"] = {"max_abs_diff": diff, "at_iteration": int(np.argmax(np.abs(a - b)))}
    res["worst_curve_abs_diff"] = worst
    if ref.get("has_log") and log_ is not None:
        strat_csv = json.loads((Path(out) / f"mat-baseline-{seed}.check.json").read_text())["replanning_log"]
        inn = np.isin(log_["strategy"], strat_csv["innovative_ids"])
        sel = ~inn & log_["logged"]
        for g in ("replanners", "charging:related"):
            m_ = masks[g]
            for k, X in (("choice_changed_given_select", st["chgC"]), ("car_use_changed_given_select", st["chgU"])):
                a = np.array(ref["curves"][g][k])
                b = np.where(sel[m_], X[m_], False).sum(0) / np.maximum(sel[m_].sum(0), 1)
                diff = float(np.max(np.abs(a - b))); res["n_curve_series"] += 1
                if diff > tol:
                    res["n_curve_mismatch"] += 1; res["curves"][f"{g}|{k}"] = {"max_abs_diff": diff}
            a = np.array(ref["curves"][g]["innovative_frac"]); b = inn[m_].mean(0)
            diff = float(np.max(np.abs(a - b))); res["n_curve_series"] += 1
            if diff > tol:
                res["n_curve_mismatch"] += 1; res["curves"][f"{g}|innovative_frac"] = {"max_abs_diff": diff}
    for k, v in per.items():
        for g in ("all", "replanners", "charging:related", "charging:unrelated", "subpopulation:man", "subpopulation:nonman"):
            x = v[masks[g]]
            h = np.bincount(x.astype(int), minlength=ITERS + 1).tolist()
            r = ref["per_person"][k][g]
            res["n_hist_checked"] += 1
            ok = (h == r["hist"]) and abs(float(x.mean()) - r["mean"]) < 1e-9
            if not ok:
                res["n_hist_mismatch"] += 1
                res["per_person"][f"{k}|{g}"] = {"mean_mine": float(x.mean()), "mean_s3": r["mean"]}
    res["status"] = "ok" if res["n_curve_mismatch"] == 0 and res["n_hist_mismatch"] == 0 and res["persons"]["mine"] == res["persons"]["s3"] else "MISMATCH"
    res["replanners_n"] = int(masks["replanners"].sum())
    return res


def compare_s2(out):
    p = S2_DIR / "aggregate.json"
    if not p.exists():
        return {"status": "s2 aggregate.json not found"}
    ref = json.loads(p.read_text())
    res = {"checked": 0, "mismatch": 0, "detail": {}, "worst_abs_share_diff": 0.0, "worst_abs_legs_diff": 0.0}
    for sc, s in all_runs():
        grp = load_grp(out, sc, s)
        g, gm = grp
        r = ref[tag(sc, s)]["by_iteration"]
        for gname in ("all", "charging:related", "charging:unrelated"):
            a = np.array(r[f"legs_car|{gname}"]); b = np.array([g[it][gname]["completed_car_legs"] for it in range(ITERS)])
            d = float(np.max(np.abs(a - b))); res["worst_abs_legs_diff"] = max(res["worst_abs_legs_diff"], d); res["checked"] += 1
            if d > 1e-6:
                res["mismatch"] += 1; res["detail"][f"{tag(sc, s)}|legs_car|{gname}"] = d
            for mode in ("car", "pt", "walk"):
                key = f"share_{mode}|{gname}"
                if key not in r:
                    continue
                a = np.array(r[key]); tot = [sum(x["departures"] for x in gm[it][gname].values()) for it in range(ITERS)]
                b = np.array([gm[it][gname][mode]["departures"] / tot[it] for it in range(ITERS)])
                d = float(np.max(np.abs(a - b))); res["worst_abs_share_diff"] = max(res["worst_abs_share_diff"], d); res["checked"] += 1
                if d > 1e-12:
                    res["mismatch"] += 1; res["detail"][f"{tag(sc, s)}|{key}"] = d
    res["status"] = "ok" if res["mismatch"] == 0 else "MISMATCH"
    return res


def main():
    out = Path(sys.argv[1])
    R = {"gates": {}}
    rows, summ = integrity(out)
    with open(out / "integrity_files.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    R["integrity"] = summ
    R["gates"]["integrity_all_runs_complete"] = all(v["complete"] for v in summ.values())
    R["integrity_files_total"] = len(rows)
    R["integrity_files_with_any_issue"] = sum(1 for r in rows if r["duplicates"] or r["unknown_ids"] or r["missing_ids"] or not r["columns_ok"]
                                              or r["bad_numeric"] or r["dep_ne_comp_plus_stuck"] or r["cohort_label_mismatch"] or r["n_rows"] != 389301)
    log(f"integrity: {len(rows)} persons files, complete runs: {sum(v['complete'] for v in summ.values())}/9")
    cres, table, passed, comp = charter_gate(out)
    R["charter"] = cres
    R["charter_completed_vs_departures"] = comp
    R["gates"]["charter_nine_deltas_means_reproduced"] = bool(passed)        # strict, preregistered: half unit of the last printed digit
    R["gates_secondary_post_hoc"] = {"charter_nine_deltas_reproduced_incl_documented_print_rounding": bool(cres["gate_passed_with_documented_explanation"])}
    with open(out / "charter_reproduction.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
    log(f"charter nine deltas reproduced within rounding: {passed}")
    rg = residual_gate(out)
    R["residual"] = rg
    R["gates"]["departures_eq_completed_plus_stuck_all_rows"] = rg["passed"]
    s3 = {}
    for sc, s in all_runs():
        s3[tag(sc, s)] = compare_s3(out, sc, s)
        log(f"s3 reconcile {tag(sc, s)}: {s3[tag(sc, s)]['status']} (curve mismatches {s3[tag(sc, s)].get('n_curve_mismatch')}, hist {s3[tag(sc, s)].get('n_hist_mismatch')})")
    R["s3"] = s3
    R["gates"]["s3_curves_and_histograms_reproduced"] = all(v["status"] == "ok" for v in s3.values())
    R["s2"] = compare_s2(out)
    R["gates"]["s2_completed_legs_and_shares_reproduced"] = R["s2"]["status"] == "ok"
    R["all_gates_passed"] = all(R["gates"].values())
    R["all_gates_passed_incl_post_hoc_explanation"] = all(v or (k == "charter_nine_deltas_means_reproduced" and R["gates_secondary_post_hoc"]["charter_nine_deltas_reproduced_incl_documented_print_rounding"]) for k, v in R["gates"].items())
    write_json(out / "reconcile.json", R)
    L = ["# 对账与完整性报告（自动生成）", "", f"- 持久 person 文件：{len(rows)}（应为 900）；出现任一问题的文件数：{R['integrity_files_with_any_issue']}",
         "", "## 门槛", ""]
    for k, v in R["gates"].items():
        L.append(f"- {k}: **{'通过' if v else '未通过'}**")
    L.append(f"- （事后追加的次级检查，不替代上面的严格门槛）总纲九项按原脚本 '+.5g' 打印再取整后复现：**{'是' if R['gates_secondary_post_hoc']['charter_nine_deltas_reproduced_incl_documented_print_rounding'] else '否'}**")
    L += ["", "## 总纲九项（重算 vs 总纲表）", "", "| 指标 | 对比 | 逐 seed | 重算均值 | 总纲均值 | 均值在舍入内 | sd(ddof=1) | sd(ddof=0) | 总纲 sd | ε | 3/3 同号 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in table:
        fmt = (lambda x: f"{x:.0f}") if t["metric"].startswith("legs") else (lambda x: f"{x:.6f}")
        L.append(f"| {t['metric']} | {t['contrast']} | {fmt(t['seed4711'])} / {fmt(t['seed4712'])} / {fmt(t['seed4713'])} | {fmt(t['mean'])} | {fmt(t['charter_mean'])} | {t['mean_ok']} | {t['sd_ddof1']:.6g} | {t['sd_ddof0']:.6g} | {t['charter_sd']} | {t['eps']} | {t['same_sign_3of3']} |")
    L += ["", f"- 完成段数（s2 口径）的收费区相关小汽车 Δ：schema1 {cres['completed_car_related_delta_s1_mean']:.1f}，schema2 {cres['completed_car_related_delta_s2_mean']:.1f}（总纲出发口径：{cres['legs_car_charging_related|schema1']['recomputed_mean']:.1f}，{cres['legs_car_charging_related|schema2']['recomputed_mean']:.1f}）",
          f"- departures−completed 与 stuck：{rg['rows_checked']} 个 组×方式×轮 行，不等的行数 {rg['rows_departures_ne_completed_plus_stuck']}",
          "", "## s3 / s2 对账", ""]
    for k, v in s3.items():
        L.append(f"- s3 {k}: {v['status']}；曲线 {v.get('n_curve_series')} 条不一致 {v.get('n_curve_mismatch')}；直方图 {v.get('n_hist_checked')} 个不一致 {v.get('n_hist_mismatch')}；最大曲线绝对差 {v.get('worst_curve_abs_diff')}")
    L.append(f"- s2 aggregate: {R['s2']['status']}，检查 {R['s2'].get('checked')} 条序列，不一致 {R['s2'].get('mismatch')}")
    (out / "reconcile-report.md").write_text("\n".join(L) + "\n")
    log(f"all gates passed: {R['all_gates_passed']}")


if __name__ == "__main__":
    main()
