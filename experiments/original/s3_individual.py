#!/usr/bin/env python3
"""Section 3 of docs/original-runs-analysis-plan.md: does individual behaviour change over iterations?

  python s3_individual.py run    OUT SCENARIO SEED   # one run -> OUT/s3-SCENARIO-SEED.json and .npz
  python s3_individual.py report OUT                 # markdown summary over the nine runs

Definitions are in the plan (section 3, "补充定义"). Needs numpy.
"""
import csv, gzip, json, sys
from pathlib import Path

import numpy as np

from s2_time_noise import sim, RUNS, SEEDS

ITERS = 100
FINAL0 = 90


def u64(s):
    return int(s) if s else 0


def read_persons(d, it, index):
    """choice fingerprint (first 64 bits), realized mode hash, and it-0 extras, in `index` order."""
    with gzip.open(d / "research" / f"persons-{it}.csv.gz", "rt", newline="") as f:
        r = csv.reader(f)
        h = next(r)
        ic, im = h.index("choice_sha256"), h.index("realized_choice_hash64")
        ie, isub, icoh = h.index("private_car_entry_crossings"), h.index("subpopulation"), h.index("charging_cohort")
        icar = h.index("completed_car_legs")
        rows = list(r)
    if index is None:
        return rows, (ic, im, ie, isub, icoh)
    n = len(index)
    c = np.zeros(n, np.uint64); m = np.zeros(n, np.uint64); car = np.zeros(n, np.int16)
    for row in rows:
        k = index[row[0]]
        c[k] = int(row[ic][:16], 16)
        m[k] = u64(row[im])
        car[k] = int(row[icar])
    return c, m, car


def run(out, sc, seed):
    d = sim(sc, seed)
    rows, (ic, im, ie, isub, icoh) = read_persons(d, 0, None)
    ids = [r[0] for r in rows]
    index = {p: i for i, p in enumerate(ids)}
    n = len(ids)
    sub = np.array([r[isub] for r in rows], dtype=object)
    coh = np.array([r[icoh] for r in rows], dtype=object)
    entered0 = np.array([float(r[ie]) > 0 for r in rows])
    del rows
    C = np.zeros((n, ITERS), np.uint64); M = np.zeros((n, ITERS), np.uint64); K = np.zeros((n, ITERS), np.int16)
    for it in range(ITERS):
        C[:, it], M[:, it], K[:, it] = read_persons(d, it, index)
    U = K > 0  # used a car (completed car leg) this iteration

    has_log = (d / "replanning-log" / "agents-1.csv.gz").exists()
    S = NEWLOG = None
    if has_log:
        with gzip.open(d / "replanning-log" / "persons.csv.gz", "rt", newline="") as f:
            r = csv.reader(f); next(r)
            logmap = {int(a): index[b] for a, b, _ in r}
        with open(d / "replanning-log" / "strategies.csv", newline="") as f:
            innovative = {int(r["strategy"]) for r in csv.DictReader(f) if r["innovative"] == "1"}  # ids differ between runs
        S = np.full((n, ITERS), -1, np.int8); NEWLOG = np.zeros((n, ITERS), bool)
        for it in range(ITERS):
            with gzip.open(d / "replanning-log" / f"agents-{it}.csv.gz", "rt", newline="") as f:
                r = csv.reader(f); next(r)
                for row in r:
                    k = logmap[int(row[0])]
                    S[k, it] = int(row[1])
                    NEWLOG[k, it] = int(row[3]) == it

    chgC = np.zeros((n, ITERS), bool); chgM = np.zeros((n, ITERS), bool)
    chgC[:, 1:] = C[:, 1:] != C[:, :-1]; chgM[:, 1:] = M[:, 1:] != M[:, :-1]
    chgU = np.zeros((n, ITERS), bool); chgU[:, 1:] = U[:, 1:] != U[:, :-1]
    newC = np.zeros((n, ITERS), bool); newM = np.zeros((n, ITERS), bool)
    newC[:, 0] = True; newM[:, 0] = True
    for t in range(1, ITERS):
        newC[:, t] = ~(C[:, :t] == C[:, t, None]).any(1)
        newM[:, t] = ~(M[:, :t] == M[:, t, None]).any(1)
    inFC = (C[:, None, FINAL0:] == C[:, :, None]).any(2)  # n x ITERS: choice at t is in final repertoire
    inFM = (M[:, None, FINAL0:] == M[:, :, None]).any(2)

    def last_true(mask, default=0):
        rev = mask[:, ::-1]
        any_ = rev.any(1)
        return np.where(any_, ITERS - 1 - rev.argmax(1), default)

    def distinct(X):
        s = np.sort(X[:, FINAL0:], axis=1)
        return 1 + (np.diff(s, axis=1) != 0).sum(1)

    per = {
        "settle_choice": np.where((~inFC).any(1), last_true(~inFC) + 1, 0),
        "settle_mode": np.where((~inFM).any(1), last_true(~inFM) + 1, 0),
        "last_change_choice": last_true(chgC),
        "last_change_mode": last_true(chgM),
        "last_new_choice": last_true(newC),
        "last_new_mode": last_true(newM),
        "n_choice_final": distinct(C),
        "n_mode_final": distinct(M),
        "last_change_car_use": last_true(chgU),
        "car_use_flips_in_final": (chgU[:, FINAL0 + 1:].any(1)).astype(int),
        "car_use_final_frac_x10": U[:, FINAL0:].sum(1),
    }
    if has_log:
        per["last_new_plan_log"] = last_true(NEWLOG)

    groups = {"all": np.ones(n, bool), "charging:related": coh == "related", "charging:unrelated": coh == "unrelated",
              "entered_zone_by_car_it0": entered0, "not_entered_it0": ~entered0}
    for s in sorted(set(sub)):
        groups[f"subpopulation:{s}"] = sub == s
    replanners = sub != "outside"
    groups["replanners"] = replanners

    def summ(v, mask):
        x = v[mask]
        return {"n": int(mask.sum()), "mean": float(x.mean()),
                "q10": float(np.quantile(x, .1)), "q25": float(np.quantile(x, .25)), "median": float(np.median(x)),
                "q75": float(np.quantile(x, .75)), "q90": float(np.quantile(x, .9)),
                "hist": np.bincount(x.astype(int), minlength=ITERS + 1).tolist()}

    res = {"scenario": sc, "seed": seed, "persons": n, "has_log": has_log,
           "per_person": {k: {g: summ(v, m) for g, m in groups.items()} for k, v in per.items()}}
    curves = {}
    for g in ("all", "replanners", "charging:related", "charging:unrelated", "subpopulation:man", "subpopulation:nonman"):
        m = groups[g]
        curves[g] = {"choice_changed": chgC[m].mean(0).tolist(), "mode_changed": chgM[m].mean(0).tolist(),
                     "car_use_changed": chgU[m].mean(0).tolist(), "car_use": U[m].mean(0).tolist(),
                     "new_choice": newC[m].mean(0).tolist(), "new_mode": newM[m].mean(0).tolist(),
                     "in_final_choice_set": inFC[m].mean(0).tolist(), "in_final_mode_set": inFM[m].mean(0).tolist()}
        if has_log:
            inn = np.isin(S[m], list(innovative))
            sel = ~inn
            curves[g]["innovative_frac"] = inn.mean(0).tolist()
            curves[g]["choice_changed_given_innovative"] = (np.where(inn, chgC[m], False).sum(0) / np.maximum(inn.sum(0), 1)).tolist()
            curves[g]["choice_changed_given_select"] = (np.where(sel, chgC[m], False).sum(0) / np.maximum(sel.sum(0), 1)).tolist()
            curves[g]["car_use_changed_given_select"] = (np.where(sel, chgU[m], False).sum(0) / np.maximum(sel.sum(0), 1)).tolist()
            curves[g]["car_use_changed_given_innovative"] = (np.where(inn, chgU[m], False).sum(0) / np.maximum(inn.sum(0), 1)).tolist()
            curves[g]["mode_changed_given_select"] = (np.where(sel, chgM[m], False).sum(0) / np.maximum(sel.sum(0), 1)).tolist()
            curves[g]["share_of_choice_changes_from_select"] = (np.where(sel, chgC[m], False).sum(0) / np.maximum(chgC[m].sum(0), 1)).tolist()
            curves[g]["new_plan_log"] = NEWLOG[m].mean(0).tolist()
    res["curves"] = curves
    if has_log:  # how good is the fingerprint proxy for "executed a newly created plan"
        a, b = NEWLOG[:, 1:], newC[:, 1:]
        res["proxy_vs_log"] = {"both": float((a & b).mean()), "log_only": float((a & ~b).mean()),
                               "proxy_only": float((~a & b).mean()), "neither": float((~a & ~b).mean()),
                               "agreement": float((a == b).mean()),
                               "log_new_and_same_as_an_earlier_choice": float((a & ~b).sum() / max(a.sum(), 1))}
        inn = np.isin(S[:, 1:], list(innovative))
        res["innovative_new_plan_executed"] = float((inn & a).sum() / max(inn.sum(), 1))
    out.mkdir(parents=True, exist_ok=True)
    (out / f"s3-{sc}-{seed}.json").write_text(json.dumps(res))
    np.savez_compressed(out / f"s3-{sc}-{seed}.npz", ids=np.array(ids), sub=sub.astype(str), coh=coh.astype(str),
                        entered0=entered0, **per)


def report(out):
    L = []
    def row(label, v):
        return f"| {label} | {v['n']} | {v['q10']:.0f} | {v['q25']:.0f} | {v['median']:.0f} | {v['q75']:.0f} | {v['q90']:.0f} | {v['mean']:.1f} |"
    for sc in RUNS:
        for seed in SEEDS:
            p = out / f"s3-{sc}-{seed}.json"
            if not p.exists():
                continue
            r = json.loads(p.read_text())
            L.append(f"\n## {sc} {seed}\n")
            L.append("| quantity / group | n | q10 | q25 | median | q75 | q90 | mean |\n|---|---|---|---|---|---|---|---|")
            for k, byg in r["per_person"].items():
                for g in ("replanners", "subpopulation:man", "subpopulation:nonman", "charging:related",
                          "charging:unrelated", "entered_zone_by_car_it0"):
                    L.append(row(f"{k} / {g}", byg[g]))
            c = r["curves"]["replanners"]
            L.append("\n| iteration | car use | car use changed |" + (" car changed if select | car changed if innovative |" if r["has_log"] else ""))
            L.append("|---" * (3 + (2 if r["has_log"] else 0)) + "|")
            for t in (1, 5, 10, 20, 40, 60, 79, 80, 81, 85, 90, 99):
                s = f"| {t} | {c['car_use'][t]:.3f} | {c['car_use_changed'][t]:.3f} |"
                if r["has_log"]:
                    s += f" {c['car_use_changed_given_select'][t]:.3f} | {c['car_use_changed_given_innovative'][t]:.3f} |"
                L.append(s)
            L.append("\n| iteration | choice changed | mode changed | new choice | new mode | in final choice set | in final mode set |"
                     + (" innovative | changed if select | mode changed if select | new plan (log) |" if r["has_log"] else ""))
            L.append("|---" * (7 + (4 if r["has_log"] else 0)) + "|")
            for t in (1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 78, 79, 80, 81, 85, 90, 95, 99):
                s = (f"| {t} | {c['choice_changed'][t]:.3f} | {c['mode_changed'][t]:.3f} | {c['new_choice'][t]:.3f} | "
                     f"{c['new_mode'][t]:.3f} | {c['in_final_choice_set'][t]:.3f} | {c['in_final_mode_set'][t]:.3f} |")
                if r["has_log"]:
                    s += (f" {c['innovative_frac'][t]:.3f} | {c['choice_changed_given_select'][t]:.3f} | "
                          f"{c['mode_changed_given_select'][t]:.3f} | {c['new_plan_log'][t]:.3f} |")
                L.append(s)
            if r["has_log"]:
                L.append(f"\nproxy vs log: {json.dumps(r['proxy_vs_log'])}; innovative strategy -> executed new plan: {r['innovative_new_plan_executed']:.3f}")
    (out / "s3-report.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2])
    if cmd == "run":
        run(out, sys.argv[3], int(sys.argv[4]))
    else:
        report(out)
