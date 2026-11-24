#!/usr/bin/env python3
"""Stage 2: who is stable, in what sense (README-s4.md section 4). Reads OUT/mat-*.npz, writes OUT/s5/*.

  python s5_stability.py OUT

Outputs (OUT/s5/):
  transition_rates.csv      per run x group x iteration: change rates for every stability definition (+ log based for baseline)
  stability_windows.csv     past-window labels vs holdout instability, per run x window x definition x population
  time_change.csv           magnitude of per-person time changes between adjacent iterations (abs/relative, zero handling)
  crossseed.csv             label transfer between seeds of the same scenario, overlap vs stratified-random expectation
  opportunity.csv           baseline: innovative opportunities in a past window vs holdout instability
  proxy_check.json / .csv   baseline: alignment evidence + confusion matrix of the 'new plan' fingerprint proxy vs the log
  stability_summary.json    compact numbers used by the report
Dependent on reconcile.json gates (integrity + s3 reproduction); stops otherwise.
Population = persons that can re-plan (subpopulation man/nonman) unless stated; 'outside' (fixed plans) is separate.
Every statistic is relative to the observation window; none is a claim of permanent stability or a deployed predictor.
"""
import csv, json, sys, time
from pathlib import Path

import numpy as np

from s4_common import ITERS, SCENARIOS, SEEDS, all_runs, tag, log, write_json, load_mat, group_masks

WINDOWS = {  # name: (p0, p1, h0, h1, note)
    "main_P80-89_H90-99": (80, 89, 90, 99, "both select-only"),
    "roll_t84_P75-84_H85-89": (75, 84, 85, 89, "P includes innovation period (75-79)"),
    "roll_t89_P80-89_H90-94": (80, 89, 90, 94, "both select-only"),
    "roll_t94_P85-94_H95-99": (85, 94, 95, 99, "both select-only"),
    "cross_P70-79_H80-89": (70, 79, 80, 89, "innovation on -> select-only (expected to fail)"),
}
TAUS = (0.05, 0.10, 0.20)
DEFS = ["plan_fp", "timed_plan", "car_state", "car_count", "real_hash"] + \
       [f"secs_travel_rel{int(t * 100)}" for t in TAUS] + ["secs_travel_abs60"] + \
       [f"secs_car_rel{int(t * 100)}" for t in TAUS] + ["secs_car_abs60"]
SUBI = {"man": 0, "nonman": 1, "outside": 2}
QS = (0.5, 0.75, 0.9, 0.95, 0.99)


def tol_ok(prev, cur, tau=None, abs_=None):
    diff = np.abs(cur.astype(np.float32) - prev.astype(np.float32))
    if abs_ is not None:
        return diff <= abs_
    return (diff == 0) | (diff <= tau * prev.astype(np.float32))      # prev == 0 and cur > 0 -> not ok (no division)


def label_arrays(m, d, p0, p1, h0, h1):
    """(stable_in_P, H deviates from P-final state, H adjacent change) for definition d; all bool (n,)."""
    if d in ("plan_fp", "timed_plan", "car_state", "car_count", "real_hash"):
        X = {"plan_fp": m["choice"], "timed_plan": m["plan"], "car_state": m["car_legs"] > 0, "car_count": m["car_legs"],
             "real_hash": m["real"]}[d]
        stable = (X[:, p0 + 1:p1 + 1] == X[:, p0:p1]).all(1)
        hdev = (X[:, h0:h1 + 1] != X[:, p1:p1 + 1]).any(1)
        hadj = (X[:, h0 + 1:h1 + 1] != X[:, h0:h1]).any(1)
        return stable, hdev, hadj
    var = "trav_sec" if d.startswith("secs_travel") else "car_sec"
    X = m[var]
    tau = abs_ = None
    if d.endswith("abs60"):
        abs_ = 60.0
    else:
        tau = int(d.split("rel")[1]) / 100.0
    stable = tol_ok(X[:, p0:p1], X[:, p0 + 1:p1 + 1], tau, abs_).all(1)
    hdev = (~tol_ok(X[:, p1:p1 + 1], X[:, h0:h1 + 1], tau, abs_)).any(1)
    hadj = (~tol_ok(X[:, h0:h1], X[:, h0 + 1:h1 + 1], tau, abs_)).any(1)
    return stable, hdev, hadj


def car_pattern(U, p0, p1):
    s = U[:, p0:p1 + 1]
    return np.where(s.all(1), 0, np.where(~s.any(1), 1, 2))        # 0 always car, 1 never car, 2 mixed


def window_row(stable, hdev, hadj, strata, pop, pat, out_alleq, out_adjeq):
    N = int(pop.sum())
    lab = stable & pop
    unl = ~stable & pop
    nl, nu = int(lab.sum()), int(unl.sum())
    row = {"N": N, "n_stable": nl, "share_stable": nl / N if N else None, "n_unstable": nu}
    for nm, h in (("Hdev", hdev), ("Hadj", hadj)):
        a, b = int((h & lab).sum()), int((h & unl).sum())
        ra, rb = (a / nl if nl else None), (b / nu if nu else None)
        row.update({f"{nm}_n_stable": a, f"{nm}_rate_stable": ra, f"{nm}_n_unstable": b, f"{nm}_rate_unstable": rb,
                    f"{nm}_ratio_unl_over_lab": (rb / ra) if (ra and rb is not None) else None})
        # stratified-random reference: expected rate among nl persons drawn within strata of sub x cohort x car pattern
        K = int(strata.max()) + 1
        Ns = np.bincount(strata[pop], minlength=K).astype(float)
        Hs = np.bincount(strata[pop], weights=h[pop].astype(float), minlength=K)
        Ls = np.bincount(strata[lab], minlength=K).astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            ref = float(np.nansum(np.where(Ns > 0, Ls * Hs / Ns, 0.0)) / nl) if nl else None
        row[f"{nm}_ref_rate_stratified"] = ref
        row[f"{nm}_lab_over_ref"] = (ra / ref) if (ra is not None and ref) else None
    row["outcome_all_equal_H_among_stable"] = float(out_alleq[lab].mean()) if nl else None
    row["outcome_adj_all_equal_H_among_stable"] = float(out_adjeq[lab].mean()) if nl else None
    row["outcome_all_equal_H_among_all"] = float(out_alleq[pop].mean()) if N else None
    for pn, pv in (("always", 0), ("never", 1), ("mixed", 2)):
        sel = lab & (pat == pv)
        row[f"stable_pat_{pn}_n"] = int(sel.sum())
        row[f"stable_pat_{pn}_Hdev_rate"] = float(hdev[sel].mean()) if sel.sum() else None
    return row


def time_change_stats(X, mask, t_list, label):
    """Magnitude of adjacent-iteration changes pooled over transitions in t_list for persons in mask."""
    absd, reld = [], []
    both0 = from0 = to0 = pos = 0
    within = {"abs60": 0, "rel5": 0, "rel10": 0, "rel20": 0}
    n_nonzero_pairs = 0
    for t in t_list:
        a = X[mask, t - 1].astype(np.float32); b = X[mask, t].astype(np.float32)
        z0, z1 = a == 0, b == 0
        both0 += int((z0 & z1).sum()); from0 += int((z0 & ~z1).sum()); to0 += int((~z0 & z1).sum())
        nz = ~(z0 & z1)
        n_nonzero_pairs += int(nz.sum())
        d = np.abs(b - a)
        within["abs60"] += int(((d <= 60) & nz).sum())
        for tau, k in ((0.05, "rel5"), (0.10, "rel10"), (0.20, "rel20")):
            within[k] += int(((d <= tau * a) & nz).sum())
        both = ~z0 & ~z1
        pos += int(both.sum())
        absd.append(d[both][::7] if len(t_list) > 20 else d[both])   # thin the long innovation window; exact when <=20 transitions
        reld.append((d[both] / a[both])[::7] if len(t_list) > 20 else d[both] / a[both])
    absd = np.concatenate(absd) if absd else np.zeros(0, np.float32)
    reld = np.concatenate(reld) if reld else np.zeros(0, np.float32)
    row = {"label": label, "n_pairs": int(len(t_list) * mask.sum()), "both_zero": both0, "from_zero": from0, "to_zero": to0,
           "both_positive": pos, "pairs_with_any_nonzero": n_nonzero_pairs,
           "frac_equal_zero_diff_among_both_positive": float((absd == 0).mean()) if len(absd) else None,
           "thinned_quantile_sample": bool(len(t_list) > 20)}
    for k, v in within.items():
        row[f"frac_within_{k}_among_nonzero_pairs"] = v / n_nonzero_pairs if n_nonzero_pairs else None
    for q in QS:
        row[f"abs_sec_q{int(q * 100)}"] = float(np.quantile(absd, q)) if len(absd) else None
        row[f"rel_q{int(q * 100)}"] = float(np.quantile(reld, q)) if len(reld) else None
    return row


def transition_rows(name, sc, seed, m, lg, innov_ids):
    n = m["choice"].shape[0]
    sub, coh = m["sub"], m["coh"]
    masks = {"replanners": sub != "outside", "outside": sub == "outside", "all": np.ones(n, bool)}
    for s in ("man", "nonman"):
        for c in ("related", "unrelated"):
            masks[f"{s}:{c}"] = (sub == s) & (coh == c)
    C, P, R, O, K = m["choice"], m["plan"], m["real"], m["outcome"], m["car_legs"]
    U = K > 0
    chg = {"choice_changed": np.zeros((n, ITERS), bool)}
    chg["choice_changed"][:, 1:] = C[:, 1:] != C[:, :-1]
    chg["plan_changed"] = np.zeros((n, ITERS), bool); chg["plan_changed"][:, 1:] = P[:, 1:] != P[:, :-1]
    chg["only_time_changed"] = chg["plan_changed"] & ~chg["choice_changed"]
    chg["car_state_changed"] = np.zeros((n, ITERS), bool); chg["car_state_changed"][:, 1:] = U[:, 1:] != U[:, :-1]
    chg["car_count_changed"] = np.zeros((n, ITERS), bool); chg["car_count_changed"][:, 1:] = K[:, 1:] != K[:, :-1]
    chg["real_changed"] = np.zeros((n, ITERS), bool); chg["real_changed"][:, 1:] = R[:, 1:] != R[:, :-1]
    chg["outcome_changed"] = np.zeros((n, ITERS), bool); chg["outcome_changed"][:, 1:] = O[:, 1:] != O[:, :-1]
    for var, nm in (("trav_sec", "travel"), ("car_sec", "car")):
        X = m[var]
        for tau in TAUS:
            a = np.zeros((n, ITERS), bool); a[:, 1:] = ~tol_ok(X[:, :-1], X[:, 1:], tau=tau); chg[f"{nm}_sec_rel_gt{int(tau * 100)}"] = a
        a = np.zeros((n, ITERS), bool); a[:, 1:] = ~tol_ok(X[:, :-1], X[:, 1:], abs_=60.0); chg[f"{nm}_sec_abs_gt60"] = a
    newP = np.zeros((n, ITERS), bool); newC = np.zeros((n, ITERS), bool)
    for t in range(1, ITERS):
        newP[:, t] = ~(P[:, :t] == P[:, t, None]).any(1)
        newC[:, t] = ~(C[:, :t] == C[:, t, None]).any(1)
    chg["new_timed_fp_proxy"] = newP; chg["new_choice_fp_proxy"] = newC
    if lg is not None:
        inn = np.isin(lg["strategy"], innov_ids)
        chg["log_innovative_strategy"] = inn
        chg["log_new_plan_executed"] = (lg["plan_created"] == np.arange(ITERS)[None, :]) & lg["logged"]
    rows = []
    for g, mk in masks.items():
        cnt = int(mk.sum())
        for t in range(1, ITERS):
            r = {"run": name, "scenario": sc, "seed": seed, "group": g, "iteration": t, "n": cnt}
            for k, A in chg.items():
                r[k] = float(A[mk, t].mean())
            rows.append(r)
    return rows, chg, masks


def proxy_check(name, sc, seed, m, lg, strat):
    """Alignment evidence + confusion matrix of 'new timed fingerprint' vs log 'plan_created == iteration' (baseline)."""
    n = m["choice"].shape[0]
    rep = m["sub"] != "outside"
    P, C = m["plan"], m["choice"]
    created = lg["plan_created"]; logged = lg["logged"]
    T = np.arange(ITERS)
    lognew = (created == T[None, :]) & logged
    newP = np.zeros((n, ITERS), bool); newC = np.zeros((n, ITERS), bool)
    for t in range(1, ITERS):
        newP[:, t] = ~(P[:, :t] == P[:, t, None]).any(1)
        newC[:, t] = ~(C[:, :t] == C[:, t, None]).any(1)
    res = {"run": name}
    # 1. alignment: executed_score (log) vs persons score, same iteration vs lagged
    sc_mat = m["score"]; es = lg["executed_score"].astype(np.float64)
    al = {}
    for lag in (-1, 0, 1):
        a_idx = np.arange(max(0, -lag), ITERS - max(0, lag))
        eq = []
        for t in a_idx[::5]:
            ok = logged[:, t] & rep & ~np.isnan(es[:, t])
            b = sc_mat[:, t + lag]
            eq.append(float((np.abs(es[ok, t] - b[ok]) <= 1e-5 + 1e-5 * np.abs(b[ok])).mean()))
        al[f"executed_score_matches_persons_score_lag{lag}"] = float(np.mean(eq))
    # plan id switch (log) vs fingerprint change, same iteration
    pid = lg["plan_id"]
    sw = np.zeros((n, ITERS), bool); sw[:, 1:] = (pid[:, 1:] != pid[:, :-1]) & (pid[:, 1:] >= 0) & (pid[:, :-1] >= 0)
    chgC = np.zeros((n, ITERS), bool); chgC[:, 1:] = C[:, 1:] != C[:, :-1]
    chgP = np.zeros((n, ITERS), bool); chgP[:, 1:] = P[:, 1:] != P[:, :-1]
    al["P(choice_fp_changed | log plan_id switched)"] = float(chgC[rep][sw[rep]].mean())
    al["P(timed_fp_changed | log plan_id switched)"] = float(chgP[rep][sw[rep]].mean())
    al["P(log plan_id switched | timed_fp_changed)"] = float(sw[rep][chgP[rep]].mean())
    res["alignment_score"] = al
    # 2. lag comparison for plan_created==t vs proxy
    lagres = {}
    for lag in (-1, 0, 1):
        ts = np.arange(max(1, 1 - lag), ITERS - max(0, lag))
        a = lognew[:, ts][rep]; b = newP[:, ts + lag][rep]
        tp = int((a & b).sum()); fp = int((~a & b).sum()); fn = int((a & ~b).sum()); tn = int((~a & ~b).sum())
        lagres[f"lag{lag}"] = {"agreement": (tp + tn) / (tp + fp + fn + tn), "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1)}
    res["lag_comparison_timed_fp_proxy"] = lagres
    best_lag = max((-1, 0, 1), key=lambda L: lagres[f"lag{L}"]["agreement"])
    res["best_lag"] = best_lag
    # 3. confusion matrices at lag 0 (proxy and the s3-style choice-only proxy), by phase
    conf = {}
    for pname, ts in (("1-99", range(1, 100)), ("1-79_innovation_on", range(1, 80)), ("80-99_select_only", range(80, 100))):
        ts = list(ts)
        a = lognew[:, ts][rep]
        for pk, Px in (("timed_fp", newP), ("choice_fp", newC)):
            b = Px[:, ts][rep]
            tp = int((a & b).sum()); fp = int((~a & b).sum()); fn = int((a & ~b).sum()); tn = int((~a & ~b).sum())
            conf[f"{pname}|{pk}"] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "agreement": (tp + tn) / (tp + fp + fn + tn),
                                     "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1), "log_new_events": tp + fn}
    res["confusion_lag0"] = conf
    # log-new plans missed by the choice-only proxy but caught by the timed proxy (only-time changes)
    miss_c = lognew & ~newC & rep[:, None]
    res["log_new_missed_by_choice_proxy"] = int(miss_c[:, 1:].sum())
    res["of_which_caught_by_timed_proxy"] = int((miss_c & newP)[:, 1:].sum())
    # 4. per strategy (this run's own strategy ids)
    per = []
    desc = {int(r["strategy"]): (r["description"], int(r["innovative"])) for r in strat}
    S = lg["strategy"]
    for sid, (dsc, inn) in sorted(desc.items()):
        sel = (S == sid) & rep[:, None] & (np.arange(ITERS)[None, :] >= 1)
        nev = int(sel.sum())
        ln = int((sel & lognew).sum())
        px = int((sel & lognew & newP).sum())
        pxo = int((sel & ~lognew & newP).sum())
        per.append({"strategy_id": sid, "description": dsc, "innovative": inn, "person_iterations": nev, "log_new_plan": ln,
                    "proxy_detects_log_new": px, "recall": px / ln if ln else None, "proxy_flags_without_log_new": pxo})
    res["per_strategy"] = per
    return res


def crossseed_rows(sc, store, strata_store):
    rows = []
    for (wname, d), per_seed in store.items():
        for a in SEEDS:
            for b in SEEDS:
                if a == b:
                    continue
                La, Lb = per_seed[a]["stable"] & per_seed[a]["rep"], per_seed[b]["stable"] & per_seed[b]["rep"]
                rep = per_seed[a]["rep"]
                N = int(rep.sum())
                oa, ob, ov = int(La.sum()), int(Lb.sum()), int((La & Lb).sum())
                # expected overlap if labels were independent draws within sub x cohort strata (analytic)
                s1 = strata_store[sc][a]["subcoh"]
                K = int(s1.max()) + 1
                Ns = np.bincount(s1[rep], minlength=K).astype(float)
                ea = np.bincount(s1[La], minlength=K).astype(float); eb = np.bincount(s1[Lb], minlength=K).astype(float)
                exp1 = float(np.sum(np.where(Ns > 0, ea * eb / Ns, 0.0)))
                # also within sub x cohort x car pattern of both seeds
                s2 = strata_store[sc][a]["subcoh"] * 9 + strata_store[sc][a]["pat"][wname] * 3 + strata_store[sc][b]["pat"][wname]
                K2 = int(s2.max()) + 1
                Ns2 = np.bincount(s2[rep], minlength=K2).astype(float)
                ea2 = np.bincount(s2[La], minlength=K2).astype(float); eb2 = np.bincount(s2[Lb], minlength=K2).astype(float)
                exp2 = float(np.sum(np.where(Ns2 > 0, ea2 * eb2 / Ns2, 0.0)))
                hb = per_seed[b]["hdev"]
                nLa = int(La.sum())
                row = {"scenario": sc, "window": wname, "definition": d, "label_seed": a, "test_seed": b, "N": N, "n_label_a": oa, "n_label_b": ob,
                       "overlap": ov, "jaccard": ov / max(oa + ob - ov, 1), "expected_overlap_subcoh": exp1,
                       "overlap_over_expected_subcoh": ov / exp1 if exp1 else None, "expected_overlap_subcoh_carpattern": exp2,
                       "overlap_over_expected_subcoh_carpattern": ov / exp2 if exp2 else None,
                       "Hdev_rate_b_among_label_a": float(hb[La].mean()) if nLa else None,
                       "Hdev_rate_b_among_not_label_a": float(hb[rep & ~La].mean()) if (rep & ~La).sum() else None,
                       "Hdev_rate_b_among_label_b": float(hb[Lb].mean()) if ob else None}
                rows.append(row)
    return rows


def main():
    out = Path(sys.argv[1])
    rec = json.loads((out / "reconcile.json").read_text())
    gates = rec["gates"]
    need = ("integrity_all_runs_complete", "s3_curves_and_histograms_reproduced")
    s5 = out / "s5"; s5.mkdir(exist_ok=True)
    if not all(gates.get(k) for k in need):
        write_json(s5 / "stability_blocked.json", {"blocked": True, "gates": gates, "needed": need})
        log("BLOCKED: required reconciliation gates failed; see reconcile.json"); return
    t0 = time.time()
    trans_rows, win_rows, tc_rows, proxy_all, opp_rows = [], [], [], {}, []
    summary = {}
    for sc in SCENARIOS:
        store = {}
        strata_store = {sc: {}}
        for seed in SEEDS:
            name = tag(sc, seed)
            log(f"{name}: loading")
            m = load_mat(out, sc, seed, ["sub", "coh", "choice", "plan", "real", "outcome", "car_legs", "car_sec", "trav_sec", "plans_mem", "score"])
            lg = None; strat = innov = None
            if sc == "baseline":
                with np.load(out / f"log-baseline-{seed}.npz") as z:
                    lg = {k: z[k] for k in ("strategy", "plan_created", "plan_id", "executed_score", "logged")}
                chk = json.loads((out / f"mat-{name}.check.json").read_text())
                strat = chk["replanning_log"]["strategies_csv"]; innov = chk["replanning_log"]["innovative_ids"]
            n = m["choice"].shape[0]
            sub, coh = m["sub"], m["coh"]
            rep = sub != "outside"
            subcoh = ((sub == "nonman") * 1 + (sub == "outside") * 2) * 2 + (coh == "unrelated")
            strata_store[sc][seed] = {"subcoh": subcoh, "pat": {}}
            rows, chg, masks = transition_rows(name, sc, seed, m, lg, innov)
            trans_rows += rows
            log(f"{name}: transition rates done ({time.time() - t0:.0f}s)")
            if sc == "baseline":
                proxy_all[name] = proxy_check(name, sc, seed, m, lg, strat)
                log(f"{name}: proxy check done")
            U = m["car_legs"] > 0
            # time-change magnitude
            for var in ("trav_sec", "car_sec"):
                for pop in ("replanners", "outside"):
                    for lab, ts in (("transitions_2-79_innovation_on", list(range(2, 80))), ("transitions_81-89_select_only", list(range(81, 90))),
                                    ("transitions_91-99_select_only", list(range(91, 100)))):
                        r = time_change_stats(m[var], masks[pop], ts, lab)
                        r.update({"run": name, "scenario": sc, "seed": seed, "variable": var, "population": pop})
                        tc_rows.append(r)
            log(f"{name}: time-change magnitude done ({time.time() - t0:.0f}s)")
            for wname, (p0, p1, h0, h1, note) in WINDOWS.items():
                pat = car_pattern(U, p0, p1)
                strata_store[sc][seed]["pat"][wname] = pat
                strata = subcoh * 3 + pat
                out_alleq = (m["outcome"][:, h0:h1 + 1] == m["outcome"][:, p1:p1 + 1]).all(1)
                out_adjeq = (m["outcome"][:, h0 + 1:h1 + 1] == m["outcome"][:, h0:h1]).all(1)
                mem2 = m["plans_mem"][:, p1] >= 2
                pops = {"replanners": rep, "man:related": (sub == "man") & (coh == "related"), "man:unrelated": (sub == "man") & (coh == "unrelated"),
                        "nonman:related": (sub == "nonman") & (coh == "related"), "nonman:unrelated": (sub == "nonman") & (coh == "unrelated"),
                        "replanners_mem2_at_Pend": rep & mem2, "replanners_mem1_at_Pend": rep & ~mem2, "outside": sub == "outside"}
                for d in DEFS:
                    stable, hdev, hadj = label_arrays(m, d, p0, p1, h0, h1)
                    store.setdefault((wname, d), {})[seed] = {"stable": stable, "hdev": hdev, "rep": rep}
                    for pn, pm in pops.items():
                        r = window_row(stable, hdev, hadj, strata, pm, pat, out_alleq, out_adjeq)
                        r.update({"run": name, "scenario": sc, "seed": seed, "window": wname, "window_note": note,
                                  "definition": d, "population": pn})
                        win_rows.append(r)
                # baseline: opportunities in P
                if sc == "baseline":
                    stable, hdev, hadj = label_arrays(m, "plan_fp", p0, p1, h0, h1)
                    opps = chg["log_innovative_strategy"][:, p0:p1 + 1].sum(1)
                    for k in range(0, int(opps.max()) + 1):
                        sel = rep & (opps == k)
                        if sel.sum():
                            opp_rows.append({"run": name, "window": wname, "n_innovative_opportunities_in_P": k, "N": int(sel.sum()),
                                             "n_plan_fp_stable_in_P": int((sel & stable).sum()),
                                             "Hdev_rate_among_stable": float(hdev[sel & stable].mean()) if (sel & stable).sum() else None,
                                             "Hdev_rate_among_unstable": float(hdev[sel & ~stable].mean()) if (sel & ~stable).sum() else None})
            log(f"{name}: window tables done ({time.time() - t0:.0f}s)")
            del m, lg, chg
        cs = crossseed_rows(sc, store, strata_store)
        summary.setdefault("crossseed_rows", 0); summary["crossseed_rows"] += len(cs)
        with open(s5 / f"crossseed-{sc}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(cs[0])); w.writeheader(); w.writerows(cs)
        del store
    def dump(rows, fname):
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(s5 / fname, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    dump(trans_rows, "transition_rates.csv")
    dump(win_rows, "stability_windows.csv")
    dump(tc_rows, "time_change.csv")
    if opp_rows:
        dump(opp_rows, "opportunity.csv")
    # pooled proxy gate (baseline, three seeds); exploratory thresholds: agreement >= 0.95 and recall >= 0.80
    pooled = {}
    for key in ("1-99|timed_fp", "1-79_innovation_on|timed_fp", "80-99_select_only|timed_fp", "1-99|choice_fp", "1-79_innovation_on|choice_fp"):
        tp = sum(v["confusion_lag0"][key]["tp"] for v in proxy_all.values()); fp = sum(v["confusion_lag0"][key]["fp"] for v in proxy_all.values())
        fn = sum(v["confusion_lag0"][key]["fn"] for v in proxy_all.values()); tn = sum(v["confusion_lag0"][key]["tn"] for v in proxy_all.values())
        pooled[key] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "agreement": (tp + tn) / (tp + fp + fn + tn), "precision": tp / max(tp + fp, 1),
                       "recall": tp / max(tp + fn, 1)}
    lag_ok = all(v["best_lag"] == 0 for v in proxy_all.values())
    gate_key = "1-79_innovation_on|timed_fp"
    gate = {"exploratory_thresholds": {"agreement_ge": 0.95, "recall_ge": 0.80, "not_a_formal_acceptance_criterion": True},
            "all_runs_best_lag_is_same_iteration": lag_ok, "pooled_innovation_on_timed_fp": pooled[gate_key],
            "passed": bool(lag_ok and pooled[gate_key]["agreement"] >= 0.95 and pooled[gate_key]["recall"] >= 0.80)}
    write_json(s5 / "proxy_check.json", {"per_run": proxy_all, "pooled_lag0": pooled, "gate": gate})
    summary["proxy_gate"] = gate
    write_json(s5 / "stability_summary.json", summary)
    log(f"s5 finished in {time.time() - t0:.0f}s; proxy gate passed={gate['passed']}")


if __name__ == "__main__":
    main()
