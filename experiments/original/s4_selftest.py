#!/usr/bin/env python3
"""Logic self-test on SYNTHETIC data (3,000 persons) -- not real results. Exercises s4_reconcile / s5 / s6 code paths.

  python s4_selftest.py OUTDIR      # writes synthetic mat-*/grp-*/log-* files into OUTDIR, then runs the stages on them
Synthetic outputs must never be mixed with real ones: use a separate OUTDIR.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np

from s4_common import ITERS, SEEDS, SCENARIOS, all_runs, tag, write_json, group_masks, GROUPS, MODES

N = 3000


def make(out):
    out.mkdir(parents=True, exist_ok=True)
    rng0 = np.random.default_rng(1)
    sub = rng0.choice(["man", "nonman", "outside"], N, p=[.4, .4, .2])
    coh = rng0.choice(["related", "unrelated"], N, p=[.35, .65])
    ids = np.array([str(i) for i in range(N)])
    prop = rng0.random(N)                        # car propensity
    for sc, seed in all_runs():
        rng = np.random.default_rng(seed + hash(sc) % 1000)
        shift = {"baseline": 0.0, "schema1": -0.08, "schema2": -0.12}[sc]
        p = np.clip(prop + shift * (coh == "related"), 0, 1)
        pc = p[:, None] * np.ones((1, ITERS))
        use = rng.random((N, ITERS)) < np.clip(pc + 0.0, 0, 1)
        car_legs = np.where(use, rng.integers(1, 4, (N, ITERS)), 0).astype(np.int16)
        stuck_car = (rng.random((N, ITERS)) < 0.01).astype(np.int16) * (car_legs > 0)
        pt = rng.integers(0, 3, (N, ITERS)).astype(np.int16)
        walk = rng.integers(0, 4, (N, ITERS)).astype(np.int16)
        car_dep = car_legs + stuck_car
        dep = (car_dep + pt + walk).astype(np.int16)
        stuck = stuck_car
        comp = dep - stuck
        outside = (sub == "outside")
        base_hash = rng.integers(0, 2 ** 62, (N, 1), dtype=np.uint64)
        change = rng.random((N, ITERS)) < 0.3 * (~outside)[:, None] * (np.arange(ITERS)[None, :] < 80) + 0.1 * (~outside)[:, None]
        change[:, 0] = False
        ver = np.cumsum(change, axis=1).astype(np.uint64)
        choice = (base_hash + ver * np.uint64(7919)).astype(np.uint64)
        tchange = change | (rng.random((N, ITERS)) < 0.05)
        plan = (base_hash + np.cumsum(tchange, axis=1).astype(np.uint64) * np.uint64(104729)).astype(np.uint64)
        real = rng.integers(0, 2 ** 62, (N, ITERS), dtype=np.uint64)
        outcome = rng.integers(0, 2 ** 62, (N, ITERS), dtype=np.uint64)
        trav = (3000 + 600 * rng.standard_normal((N, ITERS))).astype(np.float32).clip(0)
        car_sec = np.where(car_legs > 0, 1500 + 200 * rng.standard_normal((N, ITERS)), 0).astype(np.float32).clip(0)
        score = rng.standard_normal((N, ITERS))
        unf = (stuck > 0).astype(np.int8)
        entry = np.zeros((N, ITERS), np.int16); toll = np.zeros((N, ITERS), np.float32)
        chg_c = np.zeros((N, ITERS), bool); chg_c[:, 1:] = choice[:, 1:] != choice[:, :-1]
        chg_p = np.zeros((N, ITERS), bool); chg_p[:, 1:] = plan[:, 1:] != plan[:, :-1]
        mem = np.clip(1 + np.cumsum(change, 1), 1, 5).astype(np.int8) * (~outside)[:, None] + outside[:, None] * np.int8(1)
        np.savez(out / f"mat-{tag(sc, seed)}.npz", ids=ids, sub=sub, coh=coh, present=np.ones((N, ITERS), bool), choice=choice, plan=plan,
                 real=real, outcome=outcome, score=score, plans_mem=mem.astype(np.int8), dep=dep, comp=comp.astype(np.int16), stuck=stuck, unf=unf,
                 car_legs=car_legs, car_sec=car_sec, trav_sec=trav, toll=toll, entry=entry, chg_c=chg_c, chg_p=chg_p)
        # group tables
        masks = group_masks(sub, coh)
        g, gm = {}, {}
        for it in range(ITERS):
            g[str(it)] = {}; gm[str(it)] = {}
            for gn, mk in masks.items():
                g[str(it)][gn] = {"persons": float(mk.sum()), "score_sum": float(score[mk, it].sum()), "unfinished": float(unf[mk, it].sum()),
                                  "completed_car_legs": float(car_legs[mk, it].sum()), "completed_car_seconds": float(car_sec[mk, it].sum()),
                                  "toll_revenue": 0.0, "choice_changed": float(chg_c[mk, it].sum()), "plan_changed": float(chg_p[mk, it].sum()),
                                  "private_car_entry_crossings": 0.0}
                gm[str(it)][gn] = {}
                for md, dd, cc in (("car", car_dep, car_legs), ("pt", pt, pt), ("walk", walk, walk)):
                    d_ = float(dd[mk, it].sum()); c_ = float(cc[mk, it].sum())
                    gm[str(it)][gn][md] = {"departures": d_, "completed": c_, "stuck": d_ - c_, "completed_seconds": 0.0}
        write_json(out / f"grp-{tag(sc, seed)}.json", {"groups": g, "group_modes": gm})
        chk = {"complete": True, "n_persons": N, "run_json": {"commit": "synthetic"}, "files": [], "n_issues": 0, "order_identical_files": 100,
               "rows_per_file_all_equal_n": True, "hash_collision_test_128bit": {}, "cohorts_file_sha256": "synthetic", "person_vs_group": {}, "group_tables": {}}
        if sc == "baseline":
            strategy = np.where(np.arange(ITERS)[None, :] < 80, rng.integers(0, 4, (N, ITERS)), rng.integers(0, 1, (N, ITERS))).astype(np.int8)
            strategy[:, 0] = -1
            innovative = np.isin(strategy, [1, 2, 3]) & (~outside)[:, None]
            created = np.where(innovative & change, np.arange(ITERS)[None, :], 0).astype(np.int16)
            np.savez(out / f"log-baseline-{seed}.npz", logged=np.ones((N, ITERS), bool), strategy=strategy, plan_created=created,
                     plan_id=np.cumsum(change, 1).astype(np.int64), executed_score=score.astype(np.float32), innovative=innovative)
            chk["replanning_log"] = {"strategies_csv": [{"strategy": i, "innovative": int(i in (1, 2, 3)), "description": f"synthetic{i}"} for i in range(4)],
                                     "innovative_ids": [1, 2, 3], "files": [], "strategies_csv_sha256": "synthetic", "persons_csv_unknown_ids": 0}
        write_json(out / f"mat-{tag(sc, seed)}.check.json", chk)
    write_json(out / "reconcile.json", {"gates": {"integrity_all_runs_complete": True, "s3_curves_and_histograms_reproduced": True,
                                                  "charter_nine_deltas_means_reproduced": True, "departures_eq_completed_plus_stuck_all_rows": True}})


if __name__ == "__main__":
    out = Path(sys.argv[1])
    make(out)
    here = Path(__file__).resolve().parent
    import s4_reconcile
    rows, summ = s4_reconcile.integrity(out)
    print("integrity rows (synthetic has no per-file records):", len(rows))
    cres, table, passed, comp = s4_reconcile.charter_gate(out)
    print("charter gate on synthetic (expected False):", passed, "| rows", len(table))
    rg = s4_reconcile.residual_gate(out)
    print("residual gate:", rg["passed"], rg["rows_checked"])
    for stage in ("s5_stability.py", "s6_policy.py"):
        print("running", stage, flush=True)
        r = subprocess.run([sys.executable, str(here / stage), str(out)], check=False)
        print(stage, "exit", r.returncode, flush=True)
        if r.returncode:
            sys.exit(r.returncode)
