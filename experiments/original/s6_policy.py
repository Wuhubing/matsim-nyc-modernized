#!/usr/bin/env python3
"""Stage 3: when the policy differences form and who contributes (README-s4.md section 5). Reads OUT/*, writes OUT/s6/*.

  python s6_policy.py OUT

Outputs (OUT/s6/):
  policy_delta_by_iteration.csv   per seed/mean x policy/D x metric x iteration: single, trailing-10, cumulative-from-80, reference, eps
  policy_delta_summary.csv        first-crossing and sustained entry into the charter tolerance, per variant; reference self-uncertainty
  contribution_by_group.csv       person-level (completed car legs, all-mode departures) pos/neg/net/gross/cancel + group residual
                                  + share numerator/denominator terms; baseline cross-seed pairs as noise reference
  contribution_by_stratum_iteration.csv   per-iteration contribution of strata (fixed groups, baseline past-window labels)
  concentration.csv / lorenz.csv  concentration of |delta_i| and of the negative part (not of the net)
  keyperson_overlap.csv           top-k persons by seed vs other seeds vs random, policy vs baseline-pair null
  pairing_diagnostics.json        paired/unpaired variance ratios; same-seed vs cross-seed plan fingerprint equality
Stops if the integrity / charter / residual gates did not pass. Individual deltas are a descriptive decomposition,
not individual causal effects; same seed is a label alignment, not common random numbers.
"""
import csv, json, sys, time, statistics, itertools
from pathlib import Path

import numpy as np

from s4_common import (ITERS, SCENARIOS, SEEDS, all_runs, tag, log, write_json, load_mat, load_grp, run_metrics, group_masks, CHARTER, FINAL, charter_print_rounding_ok)

POLICIES = ("schema1", "schema2")
METRICS = ("legs_car_charging_related", "share_car", "share_pt")
REPORT_ONLY = ("legs_car_completed_charging_related", "stuck_car_charging_related")
JOINT = ["joint:man:related", "joint:man:unrelated", "joint:nonman:related", "joint:nonman:unrelated", "joint:outside:related", "joint:outside:unrelated"]
GROUPS_P = ["all", "charging:related", "charging:unrelated"] + JOINT
LO, HI = FINAL
TOPS = (0.01, 0.05, 0.10, 0.20)


def sustained_entry(inside, tmin):
    """first t >= tmin inside; and smallest t0 such that every t in [t0, 99] is inside (None if the last point is outside)."""
    first = next((t for t in range(tmin, ITERS) if inside[t]), None)
    if not inside[ITERS - 1]:
        return first, None
    t0 = ITERS - 1
    while t0 - 1 >= tmin and inside[t0 - 1]:
        t0 -= 1
    return first, t0


def curves(out):
    M = {tag(sc, s): run_metrics(load_grp(out, sc, s)) for sc, s in all_runs()}
    rows, summ = [], []
    eps_of = {m: {"schema1": CHARTER[m]["schema1"][2], "schema2": CHARTER[m]["schema2"][2], "D": CHARTER[m]["D"][2]} for m in METRICS}
    allm = METRICS + REPORT_ONLY
    ref = {}
    series = {}                                    # (metric, policy, seed) -> single delta array
    for m in allm:
        for s in SEEDS:
            b = M[tag("baseline", s)][m]
            d1 = M[tag("schema1", s)][m] - b; d2 = M[tag("schema2", s)][m] - b
            series[(m, "schema1", s)] = d1; series[(m, "schema2", s)] = d2; series[(m, "D", s)] = d1 - d2
        for pol in ("schema1", "schema2", "D"):
            series[(m, pol, "mean")] = np.mean([series[(m, pol, s)] for s in SEEDS], axis=0)
    def trailing(x):
        out_ = np.full(ITERS, np.nan)
        for t in range(9, ITERS):
            out_[t] = x[t - 9:t + 1].mean()
        return out_
    def cum80(x):
        out_ = np.full(ITERS, np.nan)
        for t in range(80, ITERS):
            out_[t] = x[80:t + 1].mean()
        return out_
    for m in allm:
        for pol in ("schema1", "schema2", "D"):
            seeds_ = list(SEEDS) + ["mean"]
            refmean = float(np.mean([series[(m, pol, s)][LO:HI + 1].mean() for s in SEEDS]))
            ref[(m, pol)] = refmean
            eps = eps_of[m][pol] if m in METRICS else None
            for s in seeds_:
                x = series[(m, pol, s)]
                tr, cu = trailing(x), cum80(x)
                own = float(x[LO:HI + 1].mean())
                variants = {"trailing10": tr, "cum_from80": cu, "single": x}
                inside = {}
                for vn, v in variants.items():
                    if eps is not None:
                        inside[vn] = np.array([(not np.isnan(a)) and abs(a - refmean) <= eps for a in v])
                        inside[vn + "_own"] = np.array([(not np.isnan(a)) and abs(a - own) <= eps for a in v])
                for t in range(ITERS):
                    r = {"seed": s, "policy": pol, "metric": m, "iteration": t, "delta_single": x[t], "trailing10": tr[t], "cum_from80": cu[t],
                         "ref_mean_3seed_final": refmean, "own_final_window_mean": own, "eps": eps,
                         "trailing10_crosses_79_80": bool(80 <= t <= 88)}
                    if eps is not None:
                        for vn in variants:
                            r[f"within_eps_{vn}"] = bool(inside[vn][t]); r[f"within_eps_{vn}_own_ref"] = bool(inside[vn + "_own"][t])
                    rows.append(r)
                if eps is not None:
                    for vn, tmin in (("trailing10", 9), ("cum_from80", 80), ("single", 0)):
                        for refname, key in (("3seed_final", vn), ("own_final", vn + "_own")):
                            f, sus = sustained_entry(inside[key], tmin)
                            summ.append({"metric": m, "policy": pol, "seed": s, "variant": vn, "reference": refname, "first_within_eps": f,
                                         "sustained_within_eps_from": sus, "final_window_mean": own, "ref_mean": refmean, "eps": eps,
                                         "note": "trailing10 windows ending 79..88 mix innovation and select-only iterations" if vn == "trailing10" else ""})
                x_ = series[(m, pol, s)]
                summ.append({"metric": m, "policy": pol, "seed": s, "variant": "reference_self_uncertainty", "reference": "",
                             "first_within_eps": None, "sustained_within_eps_from": None, "final_window_mean": own, "ref_mean": refmean, "eps": eps,
                             "note": json.dumps({"mean_90_94_minus_95_99": float(x_[90:95].mean() - x_[95:100].mean()),
                                                 "mean_80_89_minus_90_99": float(x_[80:90].mean() - x_[90:100].mean())})})
            signs = [np.sign(series[(m, pol, s)][LO:HI + 1].mean()) for s in SEEDS]
            summ.append({"metric": m, "policy": pol, "seed": "3seeds", "variant": "direction", "reference": "", "first_within_eps": None,
                         "sustained_within_eps_from": None, "final_window_mean": refmean, "ref_mean": refmean, "eps": eps,
                         "note": f"same sign in {max(signs.count(1.0), signs.count(-1.0))}/3 seeds"})
    return rows, summ, M


def dstats(d, mask):
    x = d[mask]
    pos = float(x[x > 0].sum()); neg = float(x[x < 0].sum())
    net = pos + neg; gross = pos - neg
    return {"n_persons": int(mask.sum()), "n_nonzero": int((x != 0).sum()), "n_pos_persons": int((x > 0).sum()), "n_neg_persons": int((x < 0).sum()),
            "pos": pos, "neg": neg, "net": net, "gross": gross, "cancel": (1 - abs(net) / gross) if gross > 0 else None}


def concentration(d, mask, rng):
    x = d[mask]
    a = np.abs(x) + rng.random(len(x)) * 1e-9          # random tie-break
    order = np.argsort(-a)
    res = {}
    gross = float(np.abs(x).sum())
    negs = -x[x < 0]
    nsum = float(negs.sum())
    for q in TOPS:
        k = max(1, int(round(q * len(x))))
        res[f"top{int(q * 100)}pct_share_of_gross"] = float(np.abs(x)[order[:k]].sum() / gross) if gross else None
        kn = max(1, int(round(q * len(negs)))) if len(negs) else 0
        res[f"top{int(q * 100)}pct_of_negative_persons_share_of_negative_part"] = (float(np.sort(negs)[::-1][:kn].sum() / nsum) if (kn and nsum) else None)
    res["share_persons_nonzero"] = float((x != 0).mean())
    return res


def lorenz(d, mask, n_pts=101):
    a = np.sort(np.abs(d[mask]))
    cs = np.cumsum(a); tot = cs[-1] if len(cs) else 0
    if not tot:
        return None
    idx = np.linspace(0, len(a), n_pts).astype(int)
    return [(float(i) / len(a), float(cs[i - 1] / tot) if i > 0 else 0.0) for i in idx]


def pat_label(U, p0, p1):
    s = U[:, p0:p1 + 1]
    return np.where(s.all(1), 0, np.where(~s.any(1), 1, 2))


def decomposition(out, M):
    rng = np.random.default_rng(20261124)
    rows_c, rows_conc, rows_lor, rows_strat, rows_key = [], [], [], [], []
    pair_diag = {"same_seed_vs_cross_seed_plan_fp_equal_at_99": {}, "paired_vs_unpaired_variance": {}}
    base = {}
    for s in SEEDS:
        mm = load_mat(out, "baseline", s, ["sub", "coh", "car_legs", "dep", "choice"])
        base[s] = {"y": mm["car_legs"], "dep": mm["dep"], "choice99": mm["choice"][:, 99].copy(),
                   "choice_P": None, "sub": mm["sub"], "coh": mm["coh"], "U_P": mm["car_legs"][:, 80:90] > 0, "choice_Pconst": (mm["choice"][:, 81:90] == mm["choice"][:, 80:89]).all(1)}
        del mm
    sub, coh = base[SEEDS[0]]["sub"], base[SEEDS[0]]["coh"]
    assert all((base[s]["sub"] == sub).all() and (base[s]["coh"] == coh).all() for s in SEEDS)
    masks = group_masks(sub, coh)
    masks_g = {g: masks[g] for g in GROUPS_P}
    rep = sub != "outside"
    gtab = {tag(sc, s): load_grp(out, sc, s) for sc, s in all_runs()}
    # ---------------- noise reference: baseline cross-seed pairs
    wmean = lambda a: a[:, LO:HI + 1].mean(1, dtype=np.float64)
    for a_, b_ in itertools.combinations(SEEDS, 2):
        d = wmean(base[a_]["y"]) - wmean(base[b_]["y"])
        for g, mk in masks_g.items():
            r = {"kind": "person_completed_car_legs", "seed": f"{a_}-{b_}", "policy": "baseline_pair_null", "group": g}
            r.update(dstats(d, mk)); rows_c.append(r)
        dd = wmean(base[a_]["dep"]) - wmean(base[b_]["dep"])
        for g, mk in masks_g.items():
            r = {"kind": "person_all_mode_departures", "seed": f"{a_}-{b_}", "policy": "baseline_pair_null", "group": g}
            r.update(dstats(dd, mk)); rows_c.append(r)
        for g in ("all", "charging:related", "charging:unrelated"):
            r = {"policy": "baseline_pair_null", "seed": f"{a_}-{b_}", "group": g, "diff_variable": "completed_car_legs"}
            r.update(concentration(d, masks_g[g], rng)); rows_conc.append(r)
        same = float((base[a_]["choice99"][rep] == base[b_]["choice99"][rep]).mean())
        pair_diag["same_seed_vs_cross_seed_plan_fp_equal_at_99"][f"baseline {a_} vs {b_} (replanners)"] = same
    # ---------------- policy vs baseline per seed
    for pol in POLICIES:
        tops = {}
        for s in SEEDS:
            mp = load_mat(out, pol, s, ["car_legs", "dep", "choice", "sub", "coh"])
            assert (mp["sub"] == sub).all() and (mp["coh"] == coh).all()
            yP = mp["car_legs"]; depP = mp["dep"]
            yB, depB = base[s]["y"], base[s]["dep"]
            d = wmean(yP) - wmean(yB)
            dT = wmean(depP) - wmean(depB)
            gP, gmP = gtab[tag(pol, s)]; gB, gmB = gtab[tag("baseline", s)]
            eps_car = CHARTER["legs_car_charging_related"][pol][2]
            for g, mk in masks_g.items():
                st = dstats(d, mk)
                tab = float(np.mean([gP[it][g]["completed_car_legs"] - gB[it][g]["completed_car_legs"] for it in range(LO, HI + 1)]))
                dep_delta = float(np.mean([gmP[it][g]["car"]["departures"] - gmB[it][g]["car"]["departures"] for it in range(LO, HI + 1)]))
                comp_delta = float(np.mean([gmP[it][g]["car"]["completed"] - gmB[it][g]["car"]["completed"] for it in range(LO, HI + 1)]))
                r = {"kind": "person_completed_car_legs", "seed": s, "policy": pol, "group": g}
                r.update(st)
                r.update({"group_table_completed_delta": tab, "reconstruction_diff": st["net"] - tab, "reconstruction_ok": abs(st["net"] - tab) < 1e-6 * max(1, abs(tab)) + 1e-6,
                          "group_modes_departures_delta": dep_delta, "group_modes_completed_delta": comp_delta,
                          "residual_departures_minus_completed_delta": dep_delta - comp_delta,
                          "eps_charter_legs_related": eps_car if g == "charging:related" else None,
                          "net_ge_eps": (abs(st["net"]) >= eps_car) if g == "charging:related" else None})
                rows_c.append(r)
                sd = dstats(dT, mk)
                r2 = {"kind": "person_all_mode_departures", "seed": s, "policy": pol, "group": g}
                r2.update(sd)
                tabT = float(np.mean([sum(x["departures"] for x in gmP[it][g].values()) - sum(x["departures"] for x in gmB[it][g].values()) for it in range(LO, HI + 1)]))
                r2.update({"group_table_departures_delta": tabT, "reconstruction_diff": sd["net"] - tabT, "reconstruction_ok": abs(sd["net"] - tabT) < 1e-6 * max(1, abs(tabT)) + 1e-6})
                rows_c.append(r2)
            for g in ("all", "charging:related", "charging:unrelated"):
                r = {"policy": pol, "seed": s, "group": g, "diff_variable": "completed_car_legs"}
                r.update(concentration(d, masks_g[g], rng)); rows_conc.append(r)
                L = lorenz(d, masks_g[g])
                if L:
                    for x, yv in L:
                        rows_lor.append({"policy": pol, "seed": s, "group": g, "cum_person_share": x, "cum_abs_delta_share": yv})
            # shares: numerator / denominator terms by joint group (window means of group-table departures; ratio-of-means identity)
            for mname, mode in (("share_car", "car"), ("share_pt", "pt")):
                def wm(gm_, grp, md=None):
                    if md is None:
                        return float(np.mean([sum(x["departures"] for x in gm_[it][grp].values()) for it in range(LO, HI + 1)]))
                    return float(np.mean([gm_[it][grp][md]["departures"] for it in range(LO, HI + 1)]))
                TP, TB = wm(gmP, "all"), wm(gmB, "all")
                CP, CB = wm(gmP, "all", mode), wm(gmB, "all", mode)
                SB, SP = CB / TB, CP / TP
                total = SP - SB
                charter_delta = float(np.mean([gmP[it]["all"][mode]["departures"] / sum(x["departures"] for x in gmP[it]["all"].values()) -
                                               gmB[it]["all"][mode]["departures"] / sum(x["departures"] for x in gmB[it]["all"].values())
                                               for it in range(LO, HI + 1)]))
                acc = 0.0
                for g in JOINT + ["charging:related", "charging:unrelated"]:
                    dC = wm(gmP, g, mode) - wm(gmB, g, mode); dTg = wm(gmP, g) - wm(gmB, g)
                    num, den = dC / TP, -SB * dTg / TP
                    if g in JOINT:
                        acc += num + den
                    rows_c.append({"kind": "share_group_terms", "seed": s, "policy": pol, "group": g, "metric": mname, "numerator_term": num,
                                   "denominator_term": den, "net": num + den, "total_share_delta_ratio_of_means": total,
                                   "charter_share_delta_mean_of_ratios": charter_delta})
                rows_c.append({"kind": "share_identity_check", "seed": s, "policy": pol, "group": "sum_of_joint_groups", "metric": mname,
                               "net": acc, "total_share_delta_ratio_of_means": total, "charter_share_delta_mean_of_ratios": charter_delta,
                               "reconstruction_diff": acc - total, "reconstruction_ok": abs(acc - total) < 1e-12})
            # stratified contributions by baseline past-window labels (car-use state in 80-89) and fixed groups, per iteration
            patB = pat_label(base[s]["U_P"], 0, 9)
            patP = pat_label(mp["car_legs"][:, 80:90] > 0, 0, 9)
            dI = yP.astype(np.int32) - yB.astype(np.int32)           # n x 100, exact integers
            strata = {"all": np.ones(len(sub), bool)}
            for g in GROUPS_P[1:]:
                strata[f"fixed:{g}"] = masks_g[g]
            for nm, pv in (("always_car", 0), ("never_car", 1), ("mixed", 2)):
                strata[f"baselineP80-89 label (replanners):{nm}"] = rep & (patB == pv)
                strata[f"policyP80-89 own label (policy-affected, replanners):{nm}"] = rep & (patP == pv)
            strata["outside (fixed plans)"] = ~rep
            strata["baselineP80-89 plan_fp constant (replanners)"] = rep & base[s]["choice_Pconst"]
            strata["baselineP80-89 plan_fp not constant (replanners)"] = rep & ~base[s]["choice_Pconst"]
            for nm, mk in strata.items():
                contrib = dI[mk].sum(0, dtype=np.int64)                # sum over persons of (policy - baseline) per iteration
                tr = np.array([np.nan if t < 9 else contrib[t - 9:t + 1].mean() for t in range(ITERS)])
                final = contrib[LO:HI + 1].mean()
                st = dstats(d, mk)
                for t in range(ITERS):
                    rows_strat.append({"seed": s, "policy": pol, "stratum": nm, "n_persons": int(mk.sum()), "iteration": t, "contribution_single": float(contrib[t]),
                                       "contribution_trailing10": None if np.isnan(tr[t]) else float(tr[t]), "stratum_final_window_net": float(final),
                                       "stratum_final_pos": st["pos"], "stratum_final_neg": st["neg"]})
            # top-k persons by negative delta (largest reductions) for the cross-seed key-person check
            for q in (0.05,):
                k = int(round(q * rep.sum()))
                score = np.where(rep, -d, -np.inf) + rng.random(len(d)) * 1e-9
                tops[(s, q)] = np.argsort(-score)[:k]
            pair_diag["same_seed_vs_cross_seed_plan_fp_equal_at_99"][f"{pol} vs baseline same seed {s} (replanners)"] = float((mp["choice"][rep, 99] == base[s]["choice99"][rep]).mean())
            del mp, yP, depP, dI
        # key persons: cross-seed overlap of top 5% reductions vs random
        q = 0.05
        for a_, b_ in itertools.permutations(SEEDS, 2):
            A, B = tops[(a_, q)], tops[(b_, q)]
            ov = len(np.intersect1d(A, B)); N = int(rep.sum()); k = len(A)
            rows_key.append({"policy": pol, "seed_a": a_, "seed_b": b_, "top_frac": q, "n_top": k, "overlap": ov, "expected_random": k * k / N,
                             "ratio_over_random": ov / (k * k / N)})
    # variance pairing (metrics from group tables)
    Mr = {tag(sc, s): run_metrics(gtab[tag(sc, s)]) for sc, s in all_runs()}
    for m in METRICS + REPORT_ONLY:
        for pol in POLICIES:
            B = [Mr[tag("baseline", s)][m][LO:HI + 1].mean() for s in SEEDS]
            P = [Mr[tag(pol, s)][m][LO:HI + 1].mean() for s in SEEDS]
            dl = [p - b for p, b in zip(P, B)]
            vp, vu = statistics.variance(dl), statistics.variance(P) + statistics.variance(B)
            pair_diag["paired_vs_unpaired_variance"][f"{m}|{pol}"] = {"var_paired_delta": vp, "var_unpaired_sum": vu, "ratio": vp / vu if vu else None}
    return rows_c, rows_conc, rows_lor, rows_strat, rows_key, pair_diag


def dump(rows, path):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)


def main():
    out = Path(sys.argv[1])
    rec = json.loads((out / "reconcile.json").read_text())
    s6 = out / "s6"; s6.mkdir(exist_ok=True)
    need = ("integrity_all_runs_complete", "departures_eq_completed_plus_stuck_all_rows")
    # charter gate: the strict preregistered check (half unit of the last printed digit) missed by 0.03 sample units on one mean
    # (schema1 car departures, charging:related: -8716.47 vs -8717). The documented cause (original print '+.5g' then rounded again)
    # is checked explicitly; both results are recorded and the decision to continue is flagged as post hoc.
    ch = rec["charter"]
    strict = all(v["mean_ok_rounding"] for v in ch.values() if isinstance(v, dict) and "mean_ok_rounding" in v)
    explained = all(v["mean_ok_rounding"] or charter_print_rounding_ok(v["recomputed_mean"], v["charter_mean"], k.split("|")[0])
                    for k, v in ch.items() if isinstance(v, dict) and "mean_ok_rounding" in v)
    write_json(s6 / "charter_gate_used.json", {"strict_gate_passed": strict, "passed_with_documented_print_rounding_explanation": explained,
                                              "note": "post hoc: continuation relies on the explanation, not on a changed tolerance; charter eps unchanged"})
    if not (all(rec["gates"].get(k) for k in need) and explained):
        write_json(s6 / "policy_blocked.json", {"blocked": True, "gates": rec["gates"], "needed": need})
        log("BLOCKED: required gates failed; see reconcile.json"); return
    t0 = time.time()
    rows, summ, M = curves(out)
    dump(rows, s6 / "policy_delta_by_iteration.csv"); dump(summ, s6 / "policy_delta_summary.csv")
    log(f"curves done ({time.time() - t0:.0f}s)")
    rows_c, rows_conc, rows_lor, rows_strat, rows_key, pair_diag = decomposition(out, M)
    dump(rows_c, s6 / "contribution_by_group.csv"); dump(rows_conc, s6 / "concentration.csv"); dump(rows_lor, s6 / "lorenz.csv")
    dump(rows_strat, s6 / "contribution_by_stratum_iteration.csv"); dump(rows_key, s6 / "keyperson_overlap.csv")
    bad = [r for r in rows_c if r.get("reconstruction_ok") is False]
    pair_diag["reconstruction_failures"] = len(bad)
    write_json(s6 / "pairing_diagnostics.json", pair_diag)
    log(f"s6 finished in {time.time() - t0:.0f}s; reconstruction failures: {len(bad)}")
    if bad:
        write_json(s6 / "reconstruction_failures.json", bad[:50])


if __name__ == "__main__":
    main()
