#!/usr/bin/env python3
"""Section 2 of docs/original-runs-analysis-plan.md: where time goes, and seed noise.

Reads only the nine original runs (known paths, no directory traversal).

  python s2_time_noise.py time      OUT          # stopwatch + research-logging seconds, all 9 runs
  python s2_time_noise.py aggregate OUT          # all/group level noise, iterations 90-99
  python s2_time_noise.py persons   OUT SCENARIO # person level noise between the 3 seeds
  python s2_time_noise.py links     OUT SCENARIO # car link x hour noise between the 3 seeds
  python s2_time_noise.py report    OUT          # markdown tables from the above

Needs Python 3.9+ and numpy.
"""
import csv, gzip, json, os, sys, itertools, statistics
from pathlib import Path

import numpy as np

BASE = Path("/orcd/scratch/orcd/006/weibingw/matsim-work")
RUNS = {
    "baseline": "rq1/baseline-s{seed}-100it-rq1",
    "schema1": "policy/schema1-s{seed}-100it",
    "schema2": "policy/schema2-s{seed}-100it",
}
SEEDS = (4711, 4712, 4713)
ITERS = 100
PLAN_DUMPS = {0, 1} | set(range(10, 100, 10)) | {99}
FINAL = range(90, 100)
LINK_ITERS = range(95, 100)
TOP_PHASES = ["iterationStartsListeners", "replanning", "beforeMobsimListeners", "prepareForMobsim",
              "mobsim", "afterMobsimListeners", "scoring", "iterationEndsListeners"]
NESTED = {"dump all plans": "beforeMobsimListeners", "compare with counts": "iterationEndsListeners"}


def sim(scenario, seed):
    return BASE / RUNS[scenario].format(seed=seed) / "simulation"


def hms(s):
    if not s:
        return 0.0
    h, m, x = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(x)


def opengz(p):
    return open(p, newline="") if not str(p).endswith(".gz") else gzip.open(p, "rt", newline="")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True))


# ---------------------------------------------------------------- time
def stopwatch(path):
    with open(path, newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    head = rows[0]
    gap = head.index("")
    names = head[gap + 1:]
    out = {}
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        it = int(r[0])
        out[it] = {n: hms(v) for n, v in zip(names, r[gap + 1:])}
    return out


def cmd_time(out):
    res = {}
    for sc in RUNS:
        for seed in SEEDS:
            d = sim(sc, seed)
            sw = stopwatch(d / "BUILT.stopwatch.csv")
            rows = []
            for it in range(ITERS):
                ph = sw.get(it)
                if ph is None:
                    continue
                diag = d / "research" / f"diagnostics-{it}.json"
                rs = json.loads(diag.read_text()) if diag.exists() else {}
                row = {"iteration": it, "total": ph.get("iteration", 0.0)}
                for p in TOP_PHASES + list(NESTED):
                    row[p] = ph.get(p, 0.0)
                row["residual"] = row["total"] - sum(row[p] for p in TOP_PHASES)
                row["research_output"] = float(rs.get("research_output_seconds", 0.0))
                row["plan_fingerprint"] = float(rs.get("plan_fingerprint_seconds", 0.0))
                rows.append(row)
            run = json.loads((d.parent / "run.json").read_text())
            res[f"{sc}-{seed}"] = {"rows": rows, "replanning_log": bool(run.get("replanning_log")),
                                   "innovation_until": run.get("innovation_until")}
    write_json(out / "time.json", res)


# ---------------------------------------------------------------- aggregate
def read_groups(d, it):
    with opengz(d / "research" / f"groups-{it}.csv.gz") as f:
        g = {r["group"]: {k: float(v) for k, v in r.items() if k != "group"} for r in csv.DictReader(f)}
    with opengz(d / "research" / f"group-modes-{it}.csv.gz") as f:
        gm = {}
        for r in csv.DictReader(f):
            gm.setdefault(r["group"], {})[r["leg_mode"]] = {k: float(v) for k, v in r.items()
                                                           if k not in ("group", "leg_mode")}
    return g, gm


def indicators(d, it):
    g, gm = read_groups(d, it)
    m = json.loads((d / f"iteration-metrics-{it}.json").read_text())
    out = {}
    for grp, v in g.items():
        n = v["persons"]
        out[f"score_mean|{grp}"] = v["score_sum"] / max(v["scored_persons"], 1)
        out[f"unfinished|{grp}"] = v["unfinished"]
        out[f"legs_car|{grp}"] = v["completed_car_legs"]
        out[f"toll_revenue|{grp}"] = v["toll_revenue"]
        out[f"choice_changed_frac|{grp}"] = v["choice_changed"] / max(v["compared_persons"], 1)
        out[f"plan_changed_frac|{grp}"] = v["plan_changed"] / max(v["compared_persons"], 1)
        out[f"entry_crossings|{grp}"] = v["private_car_entry_crossings"]
        modes = gm.get(grp, {})
        tot = sum(x["departures"] for x in modes.values())
        for mode, x in modes.items():
            out[f"share_{mode}|{grp}"] = x["departures"] / tot if tot else 0.0
        out[f"car_leg_seconds|{grp}"] = (modes.get("car", {}).get("completed_seconds", 0.0)
                                         / max(modes.get("car", {}).get("completed", 0.0), 1))
    out["wait_person_hours|all"] = m.get("censored_wait_person_hours", 0.0)
    return out


def cmd_aggregate(out):
    res = {}
    for sc in RUNS:
        for seed in SEEDS:
            d = sim(sc, seed)
            per_it = {it: indicators(d, it) for it in range(ITERS)}
            keys = sorted(set().union(*[set(v) for v in per_it.values()]))
            final = {k: statistics.fmean(per_it[it].get(k, 0.0) for it in FINAL) for k in keys}
            res[f"{sc}-{seed}"] = {"final_mean": final,
                                   "by_iteration": {k: [per_it[it].get(k, 0.0) for it in range(ITERS)]
                                                    for k in keys if k.endswith("|all") or "charging:" in k}}
    write_json(out / "aggregate.json", res)


# ---------------------------------------------------------------- persons
def read_persons(d, it, cols):
    with opengz(d / "research" / f"persons-{it}.csv.gz") as f:
        r = csv.reader(f)
        head = next(r)
        idx = [head.index(c) for c in cols]
        ids, vals = [], []
        for row in r:
            ids.append(row[0])
            vals.append([row[i] for i in idx])
    return ids, vals


def cmd_persons(out, sc):
    choice99, car, score, meta = {}, {}, {}, None
    for seed in SEEDS:
        d = sim(sc, seed)
        ids, v = read_persons(d, 99, ["choice_sha256", "subpopulation", "charging_cohort"])
        order = np.argsort(np.array(ids, dtype=object))
        ids_sorted = [ids[i] for i in order]
        if meta is None:
            meta = {"ids": ids_sorted, "sub": [v[i][1] for i in order], "coh": [v[i][2] for i in order]}
        elif meta["ids"] != ids_sorted:
            raise SystemExit(f"person ids differ between seeds in {sc}")
        choice99[seed] = np.array([v[i][0] for i in order], dtype=object)
        csum = np.zeros(len(ids)); ssum = np.zeros(len(ids)); within = None
        for it in FINAL:
            ids_i, vi = read_persons(d, it, ["completed_car_legs", "score", "choice_sha256"])
            o = np.argsort(np.array(ids_i, dtype=object))
            csum += np.array([float(vi[i][0]) for i in o])
            ssum += np.array([float(vi[i][1]) for i in o])
            if it == 90:
                within = np.array([vi[i][2] for i in o], dtype=object)
        car[seed] = csum / len(FINAL)
        score[seed] = ssum / len(FINAL)
        choice99[(seed, "same_as_90")] = float(np.mean(within == choice99[seed]))
    sub = np.array(meta["sub"], dtype=object); coh = np.array(meta["coh"], dtype=object)
    groups = {"all": np.ones(len(sub), bool), "charging:related": coh == "related",
              "charging:unrelated": coh == "unrelated"}
    for s in sorted(set(meta["sub"])):
        groups[f"subpopulation:{s}"] = sub == s
    res = {"persons": len(sub), "within_run_same_choice_90_vs_99": {str(s): choice99[(s, "same_as_90")] for s in SEEDS},
           "pairs": {}}
    for a, b in itertools.combinations(SEEDS, 2):
        same = choice99[a] == choice99[b]
        dc = car[a] - car[b]
        ds = score[a] - score[b]
        pr = {}
        for g, mask in groups.items():
            pr[g] = {
                "n": int(mask.sum()),
                "same_choice_99": float(same[mask].mean()),
                "car_legs_absdiff_mean": float(np.abs(dc[mask]).mean()),
                "car_legs_diff_gt_0.5_frac": float((np.abs(dc[mask]) > 0.5).mean()),
                "car_legs_any_in_both_frac": float(((car[a][mask] > 0) & (car[b][mask] > 0)).mean()),
                "car_legs_any_in_one_only_frac": float(((car[a][mask] > 0) != (car[b][mask] > 0)).mean()),
                "score_absdiff_median": float(np.median(np.abs(ds[mask]))),
                "score_absdiff_p90": float(np.quantile(np.abs(ds[mask]), 0.9)),
            }
        res["pairs"][f"{a}-{b}"] = pr
    all3 = (choice99[SEEDS[0]] == choice99[SEEDS[1]]) & (choice99[SEEDS[1]] == choice99[SEEDS[2]])
    res["same_choice_99_all_three"] = {g: float(all3[m].mean()) for g, m in groups.items()}
    write_json(out / f"persons-{sc}.json", res)


# ---------------------------------------------------------------- links
def read_links(d, it, acc):
    with opengz(d / "research" / f"link-hours-{it}.csv.gz") as f:
        r = csv.reader(f)
        next(r)
        for link, hour, mode, entries, done, secs in r:
            if mode != "car":
                continue
            k = (link, int(hour))
            a = acc.get(k)
            if a is None:
                acc[k] = [float(entries), float(done), float(secs)]
            else:
                a[0] += float(entries); a[1] += float(done); a[2] += float(secs)


def cmd_links(out, sc):
    per = {}
    for seed in SEEDS:
        acc = {}
        for it in LINK_ITERS:
            read_links(sim(sc, seed), it, acc)
        per[seed] = acc
    n_it = len(LINK_ITERS)
    bins = [(1, 10), (10, 50), (50, 200), (200, 1000), (1000, 10**9)]  # mean entries per iteration
    res = {"iterations": list(LINK_ITERS), "cells": {str(s): len(per[s]) for s in SEEDS}, "pairs": {}}
    for a, b in itertools.combinations(SEEDS, 2):
        keys = set(per[a]) | set(per[b])
        flow_rel, tt_rel, wts = [], [], []
        only_one = 0
        for k in keys:
            x, y = per[a].get(k), per[b].get(k)
            if x is None or y is None:
                only_one += 1
                continue
            if x[1] <= 0 or y[1] <= 0:
                continue
            fx, fy = x[0] / n_it, y[0] / n_it
            tx, ty = x[2] / x[1], y[2] / y[1]
            m = (fx + fy) / 2
            flow_rel.append((fx - fy) / m)
            tt_rel.append((tx - ty) / ((tx + ty) / 2))
            wts.append(m)
        flow_rel = np.array(flow_rel); tt_rel = np.array(tt_rel); wts = np.array(wts)
        pr = {"cells_in_one_seed_only": only_one, "cells_compared": int(len(wts)), "by_flow": {}}
        for lo, hi in bins:
            m = (wts >= lo) & (wts < hi)
            if m.sum() == 0:
                continue
            pr["by_flow"][f"{lo}-{hi}"] = {
                "cells": int(m.sum()),
                "flow_rel_absdiff_median": float(np.median(np.abs(flow_rel[m]))),
                "flow_rel_absdiff_p90": float(np.quantile(np.abs(flow_rel[m]), 0.9)),
                "tt_rel_absdiff_median": float(np.median(np.abs(tt_rel[m]))),
                "tt_rel_absdiff_p90": float(np.quantile(np.abs(tt_rel[m]), 0.9)),
            }
        # daily link flow RMSE (PSim-style comparison in charter 3.1)
        la, lb = {}, {}
        for (link, _), v in per[a].items():
            la[link] = la.get(link, 0.0) + v[0] / n_it
        for (link, _), v in per[b].items():
            lb[link] = lb.get(link, 0.0) + v[0] / n_it
        links = set(la) | set(lb)
        diff = np.array([la.get(l, 0.0) - lb.get(l, 0.0) for l in links])
        pr["daily_link_flow_rmse"] = float(np.sqrt(np.mean(diff ** 2)))
        pr["daily_link_flow_mean"] = float(np.mean([(la.get(l, 0.0) + lb.get(l, 0.0)) / 2 for l in links]))
        res["pairs"][f"{a}-{b}"] = pr
    write_json(out / f"links-{sc}.json", res)


# ---------------------------------------------------------------- report
def cmd_report(out):
    lines = []
    t = json.loads((out / "time.json").read_text())
    lines.append("## Time\n")
    cols = TOP_PHASES + ["residual"]
    lines.append("| run | iterations | total h | " + " | ".join(cols) + " | research_output | plan_fingerprint |")
    lines.append("|" + "---|" * (len(cols) + 5))
    def block(rows, label, name):
        if not rows:
            return
        tot = sum(r["total"] for r in rows)
        cells = [f"{100 * sum(r[c] for r in rows) / tot:.1f}%" for c in cols]
        ro = 100 * sum(r["research_output"] for r in rows) / tot
        pf = 100 * sum(r["plan_fingerprint"] for r in rows) / tot
        lines.append(f"| {name} | {label} | {tot / 3600:.2f} | " + " | ".join(cells) + f" | {ro:.1f}% | {pf:.1f}% |")
    medians = {}
    for name, v in t.items():
        rows = v["rows"]
        block(rows, "all", name)
        block([r for r in rows if r["iteration"] not in PLAN_DUMPS and 1 < r["iteration"] < 80], "2-79 no dump", name)
        block([r for r in rows if r["iteration"] not in PLAN_DUMPS and r["iteration"] >= 80], "80-98 no dump", name)
        medians[name] = {
            "innov_median_s": statistics.median(r["total"] for r in rows if r["iteration"] not in PLAN_DUMPS and 1 < r["iteration"] < 80),
            "select_median_s": statistics.median(r["total"] for r in rows if r["iteration"] not in PLAN_DUMPS and r["iteration"] >= 80),
            "dump_median_s": statistics.median(r["total"] for r in rows if r["iteration"] in PLAN_DUMPS),
        }
    # original-equivalent: drop research logging and the every-10-iteration plan dump
    lines.append("\n| run | total h | orig-eq h | mobsim | replanning | other | bound no replanning | bound no mobsim |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name, v in t.items():
        rows = v["rows"]
        T = sum(r["total"] for r in rows)
        To = T - sum(r["research_output"] + r["plan_fingerprint"] + r["dump all plans"] for r in rows)
        mob = sum(r["mobsim"] for r in rows) / To
        rep = sum(r["replanning"] for r in rows) / To
        lines.append(f"| {name} | {T / 3600:.2f} | {To / 3600:.2f} | {100 * mob:.1f}% | {100 * rep:.1f}% | "
                     f"{100 * (1 - mob - rep):.1f}% | {1 / (1 - rep):.2f}x | {1 / (1 - mob):.2f}x |")
    lines.append("\n| run | median s/iter 2-79 | median s/iter 80-98 | median s/iter with plan dump |")
    lines.append("|---|---|---|---|")
    for name, m in medians.items():
        lines.append(f"| {name} | {m['innov_median_s']:.0f} | {m['select_median_s']:.0f} | {m['dump_median_s']:.0f} |")
    write_json(out / "time-summary.json", medians)

    a = json.loads((out / "aggregate.json").read_text())
    lines.append("\n## Aggregate / group noise (iterations 90-99 mean; across 3 seeds)\n")
    keys = [k for k in a["baseline-4711"]["final_mean"]
            if k.split("|")[1] in ("all", "charging:related", "charging:unrelated")
            and k.split("|")[0] in ("share_car", "share_pt", "share_walk", "legs_car", "score_mean",
                                    "unfinished", "toll_revenue", "entry_crossings", "car_leg_seconds",
                                    "choice_changed_frac", "wait_person_hours")]
    for sc in RUNS:
        lines.append(f"\n### {sc}\n\n| indicator | mean | sd | max-min |\n|---|---|---|---|")
        for k in keys:
            vals = [a[f"{sc}-{s}"]["final_mean"].get(k, 0.0) for s in SEEDS]
            lines.append(f"| {k} | {statistics.fmean(vals):.6g} | {statistics.stdev(vals):.3g} | {max(vals) - min(vals):.3g} |")
    for sc in RUNS:
        p = out / f"persons-{sc}.json"
        if p.exists():
            v = json.loads(p.read_text())
            lines.append(f"\n## Persons {sc}\n\n```\n{json.dumps(v, indent=1)}\n```")
        p = out / f"links-{sc}.json"
        if p.exists():
            v = json.loads(p.read_text())
            lines.append(f"\n## Links {sc}\n\n```\n{json.dumps(v, indent=1)}\n```")
    (out / "s2-report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    {"time": lambda: cmd_time(out), "aggregate": lambda: cmd_aggregate(out),
     "persons": lambda: cmd_persons(out, sys.argv[3]), "links": lambda: cmd_links(out, sys.argv[3]),
     "report": lambda: cmd_report(out)}[cmd]()
