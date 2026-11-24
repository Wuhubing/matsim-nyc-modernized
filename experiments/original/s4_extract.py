#!/usr/bin/env python3
"""Stage 2 extraction: person x iteration matrices + group tables + integrity/reconciliation for the nine original runs.

  python s4_extract.py run OUT SCENARIO SEED [--iters 0,1,99] [--nproc 4]   # one run (partial iterations = test mode)
  python s4_extract.py all OUT [--nproc 4]                                  # nine runs, sequential, reuses verified cache

For every run it writes (atomically, tmp + rename):
  OUT/mat-{sc}-{seed}.npz     person x iteration arrays, aligned by person_id to cohorts.csv.gz order (never by row number)
  OUT/mat-{sc}-{seed}.check.json   per-file integrity records for all persons-N files + person-vs-group reconciliation
  OUT/grp-{sc}-{seed}.json    groups-N and group-modes-N, every column, every iteration
  OUT/log-baseline-{seed}.npz (baseline only) replanning-log aligned to the same person order; strategy ids resolved
                              with the run's OWN strategies.csv. Policy runs have no replanning-log and none is required.

Fingerprints: choice_sha256 / plan_sha256 are read as SHA-256 hex; the first 128 bits are used for a collision test
(a equal but b different), then only the first 64 bits are stored. realized_choice_hash64 / outcome_hash64 are
64-bit rolling hashes by definition (possible collisions, per research/schema.json).
A cache is reused only if check.json says complete, its source fingerprint (size+mtime+gzip CRC of every source
file) is unchanged and the NPZ has the expected arrays; otherwise the run is re-extracted.
"""
import csv, gzip, io, json, os, resource, struct, sys, time, hashlib
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from s4_common import (ITERS, MODES, GROUPS, SEEDS, SCENARIOS, RUNS, sim, run_dir, all_runs, tag, log, write_json,
                       sha256_file, group_masks)

EXTRACT_SCHEMA = 3
PERSON_COLS = ["person_id", "subpopulation", "charging_cohort", "score", "score_delta", "plans_in_memory",
               "choice_sha256", "plan_sha256", "choice_changed", "plan_changed", "realized_choice_hash64",
               "outcome_hash64", "departures", "completed", "unfinished", "stuck", "completed_travel_seconds",
               "completed_car_legs", "completed_car_seconds", "wait_segments", "waiting_at_cutoff",
               "censored_wait_seconds", "toll_revenue", "private_car_entry_crossings"]
INT_COLS = ["plans_in_memory", "departures", "completed", "unfinished", "stuck", "completed_car_legs",
            "private_car_entry_crossings"]
FLOAT_COLS = ["score", "completed_travel_seconds", "completed_car_seconds", "toll_revenue",
              "wait_segments", "waiting_at_cutoff", "censored_wait_seconds"]
MAT_KEYS = ["ids", "sub", "coh", "present", "choice", "plan", "real", "outcome", "score", "plans_mem", "dep", "comp",
            "stuck", "unf", "car_legs", "car_sec", "trav_sec", "toll", "entry", "chg_c", "chg_p"]
MASK64 = (1 << 64) - 1

# set in the parent before forking the pool
_COHORT = None


def gz_trailer(path):
    with open(path, "rb") as f:
        f.seek(-8, 2)
        crc, isize = struct.unpack("<II", f.read(8))
    return crc, isize


def hex_to_u64_pairs(s):
    """first 32 hex chars of each SHA-256 -> (a, b) uint64 arrays; returns (a, b, n_bad_len)."""
    ln = s.str.len()
    bad = int((ln != 64).sum())
    s = s.where(ln == 64, "0" * 64)
    buf = bytes.fromhex("".join(s.str.slice(0, 32)))
    arr = np.frombuffer(buf, dtype=">u8").reshape(-1, 2).astype(np.uint64)
    return arr[:, 0].copy(), arr[:, 1].copy(), bad


def to_u64(s):
    try:
        return s.astype("uint64").to_numpy(), 0
    except (ValueError, OverflowError, TypeError):
        vals = np.zeros(len(s), np.uint64)
        bad = 0
        for i, x in enumerate(s.to_list()):
            try:
                vals[i] = int(x) & MASK64
            except (ValueError, TypeError):
                bad += 1
        return vals, bad


def parse_persons(job):
    """Parse one persons-N file, align by person_id to the cohort order. Returns (it, arrays, record)."""
    path, it = job
    t0 = time.time()
    st = os.stat(path)
    crc, isize = gz_trailer(path)
    rec = {"iteration": it, "path": str(path), "bytes": st.st_size, "mtime": int(st.st_mtime), "gz_crc32": crc,
           "gz_isize_mod32": isize}
    n = len(_COHORT)
    df = pd.read_csv(path, compression="gzip", dtype=str, keep_default_na=False, na_values=[], low_memory=False)
    rec["columns_ok"] = list(df.columns) == PERSON_COLS
    rec["columns_missing"] = [c for c in PERSON_COLS if c not in df.columns]
    rec["columns_extra"] = [c for c in df.columns if c not in PERSON_COLS]
    rec["n_rows"] = int(len(df))
    ids = df["person_id"]
    pos = _COHORT.get_indexer(pd.Index(ids))
    unknown = pos < 0
    rec["n_unknown_ids"] = int(unknown.sum())
    dup = pd.Series(pos).duplicated(keep="first").to_numpy() & ~unknown
    rec["n_duplicate_rows"] = int(dup.sum())
    rec["n_unique_ids"] = int(len(set(pos[~unknown].tolist())))
    keep = ~unknown & ~dup
    rec["order_identical_to_cohort"] = bool(len(df) == n and np.array_equal(pos, np.arange(n)))
    idx = pos[keep]
    present = np.zeros(n, bool)
    present[idx] = True
    rec["n_missing_ids"] = int(n - present.sum())

    def put(col, dtype, values):
        a = np.zeros(n, dtype)
        a[idx] = values[keep]
        return a

    a = {}
    bad_parse = {}
    # numeric columns (strict parse; NaN/empty counted as parse errors, not silently zeroed)
    num = {}
    for c in INT_COLS + FLOAT_COLS:
        v = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=np.float64)
        bad_parse[c] = int(np.isnan(v).sum())
        num[c] = v
    rec["bad_numeric"] = {c: k for c, k in bad_parse.items() if k}
    nonint = {c: int(((num[c] != np.floor(num[c])) & ~np.isnan(num[c])).sum()) for c in INT_COLS}
    rec["non_integer_counts"] = {c: k for c, k in nonint.items() if k}
    rec["negative_values"] = {c: int((num[c] < 0).sum()) for c in INT_COLS + ["completed_travel_seconds", "completed_car_seconds"]
                              if int((num[c] < 0).sum())}
    for c in INT_COLS:
        num[c] = np.nan_to_num(num[c])
    for c in FLOAT_COLS:
        num[c] = np.nan_to_num(num[c])
    a["score"] = put("score", np.float64, num["score"])
    a["plans_mem"] = put("plans_mem", np.int8, num["plans_in_memory"])
    a["dep"] = put("dep", np.int16, num["departures"])
    a["comp"] = put("comp", np.int16, num["completed"])
    a["stuck"] = put("stuck", np.int16, num["stuck"])
    a["unf"] = put("unf", np.int8, num["unfinished"])
    a["car_legs"] = put("car_legs", np.int16, num["completed_car_legs"])
    a["car_sec"] = put("car_sec", np.float32, num["completed_car_seconds"])
    a["trav_sec"] = put("trav_sec", np.float32, num["completed_travel_seconds"])
    a["toll"] = put("toll", np.float32, num["toll_revenue"])
    a["entry"] = put("entry", np.int16, num["private_car_entry_crossings"])
    # also keep sums needed for reconciliation of columns that are not stored per person
    rec["sums_unstored"] = {c: float(num[c][keep].sum()) for c in ("wait_segments", "waiting_at_cutoff", "censored_wait_seconds")}
    # hashes
    ca, cb, bad_c = hex_to_u64_pairs(df["choice_sha256"])
    pa, pb, bad_p = hex_to_u64_pairs(df["plan_sha256"])
    rec["bad_sha_length"] = {"choice": bad_c, "plan": bad_p}
    ra, bad_r = to_u64(df["realized_choice_hash64"])
    oa, bad_o = to_u64(df["outcome_hash64"])
    rec["bad_hash64"] = {"realized": bad_r, "outcome": bad_o}
    a["choice"] = put("choice", np.uint64, ca)
    a["choice_b"] = put("choice_b", np.uint64, cb)
    a["plan"] = put("plan", np.uint64, pa)
    a["plan_b"] = put("plan_b", np.uint64, pb)
    a["real"] = put("real", np.uint64, ra)
    a["outcome"] = put("outcome", np.uint64, oa)
    for c, k in (("choice_changed", "chg_c"), ("plan_changed", "chg_p")):
        s = df[c].str.lower()
        rec[f"{c}_values"] = {"true": int((s == "true").sum()), "false": int((s == "false").sum()),
                              "empty_or_other": int((~s.isin(["true", "false"])).sum())}
        a[k] = put(k, bool, (s == "true").to_numpy())
    # sub / coh as in the file vs cohort file
    sub = df["subpopulation"].to_numpy(); coh = df["charging_cohort"].to_numpy()
    rec["cohort_label_mismatch"] = int(((sub[keep] != _COHORT_SUB[idx]) | (coh[keep] != _COHORT_COH[idx])).sum())
    # within-file consistency (on present rows)
    d, c_, s_, u = (a[k][present].astype(np.int64) for k in ("dep", "comp", "stuck", "unf"))
    rec["dep_ne_comp_plus_stuck"] = int((d != c_ + s_).sum())
    rec["unfinished_not_01"] = int(((u != 0) & (u != 1)).sum())
    rec["car_legs_gt_dep"] = int((a["car_legs"][present] > a["dep"][present]).sum())
    a["present"] = present
    rec["seconds"] = round(time.time() - t0, 2)
    return it, a, rec


def parse_log(job):
    """Parse one replanning-log agents-N file (baseline) aligned through persons.csv.gz index -> person_id."""
    path, it, logmap = job
    n = len(_COHORT)
    df = pd.read_csv(path, compression="gzip", dtype=str, keep_default_na=False, na_values=[])
    rec = {"iteration": it, "n_rows": int(len(df)), "columns": list(df.columns)}
    pidx = pd.to_numeric(df["person"]).to_numpy(np.int64)
    pos = np.where(pidx < len(logmap), logmap[np.minimum(pidx, len(logmap) - 1)], -1)
    unknown = pos < 0
    dup = pd.Series(pos).duplicated(keep="first").to_numpy() & ~unknown
    keep = ~unknown & ~dup
    idx = pos[keep]
    rec["n_unknown"] = int(unknown.sum()); rec["n_duplicate"] = int(dup.sum()); rec["n_missing"] = int(n - len(idx))
    out = {"logged": np.zeros(n, bool), "strategy": np.full(n, -2, np.int8), "plan_created": np.full(n, -1, np.int16),
           "plan_id": np.full(n, -1, np.int64), "executed_score": np.full(n, np.nan, np.float32)}
    out["logged"][idx] = True
    out["strategy"][idx] = pd.to_numeric(df["strategy"]).to_numpy()[keep].astype(np.int8)
    out["plan_created"][idx] = pd.to_numeric(df["plan_created"]).to_numpy()[keep].astype(np.int16)
    out["executed_score"][idx] = pd.to_numeric(df["executed_score"], errors="coerce").to_numpy()[keep].astype(np.float32)
    bad = 0
    pid = np.empty(len(df), np.int64)
    for i, x in enumerate(df["plan_id"].to_list()):
        try:
            pid[i] = int(x, 36)
        except ValueError:
            pid[i] = -1; bad += 1
    out["plan_id"][idx] = pid[keep]
    rec["bad_plan_id"] = bad
    return it, out, rec


def source_files(sc, seed, iters):
    d = sim(sc, seed)
    r = d / "research"
    fs = [r / "cohorts.csv.gz"]
    for it in iters:
        fs += [r / f"persons-{it}.csv.gz", r / f"groups-{it}.csv.gz", r / f"group-modes-{it}.csv.gz"]
    if sc == "baseline":
        L = d / "replanning-log"
        fs += [L / "persons.csv.gz", L / "strategies.csv"] + [L / f"agents-{it}.csv.gz" for it in iters]
    return fs


def source_fingerprint(files):
    h = hashlib.sha256()
    for p in files:
        st = os.stat(p)
        crc = gz_trailer(p)[0] if str(p).endswith(".gz") else 0
        h.update(f"{p}|{st.st_size}|{int(st.st_mtime)}|{crc}\n".encode())
    return h.hexdigest()


def read_group_tables(sc, seed, iters):
    r = sim(sc, seed) / "research"
    g, gm, chk = {}, {}, {"groups_missing_cols": 0, "gm_dep_ne_comp_plus_stuck": 0, "partition_violations": 0,
                          "unexpected_groups": 0, "missing_groups": 0}
    for it in iters:
        df = pd.read_csv(r / f"groups-{it}.csv.gz", compression="gzip", keep_default_na=False)
        g[it] = {row["group"]: {k: float(v) for k, v in row.items() if k != "group"} for row in df.to_dict("records")}
        dm = pd.read_csv(r / f"group-modes-{it}.csv.gz", compression="gzip", keep_default_na=False)
        d = {}
        for row in dm.to_dict("records"):
            d.setdefault(row["group"], {})[row["leg_mode"]] = {k: float(v) for k, v in row.items() if k not in ("group", "leg_mode")}
            if row["departures"] != row["completed"] + row["stuck"]:
                chk["gm_dep_ne_comp_plus_stuck"] += 1
        gm[it] = d
        chk["unexpected_groups"] += len(set(g[it]) - set(GROUPS)) + len(set(d) - set(GROUPS))
        chk["missing_groups"] += len(set(GROUPS) - set(g[it])) + len(set(GROUPS) - set(d))
        # partition: joint groups add up to all / charging:* / subpopulation:*
        for mode in MODES:
            def dep(grp):
                return d.get(grp, {}).get(mode, {}).get("departures", 0.0)
            parts = {"all": sum(dep(f"joint:{s}:{c}") for s in ("man", "nonman", "outside") for c in ("related", "unrelated")),
                     "charging:related": sum(dep(f"joint:{s}:related") for s in ("man", "nonman", "outside")),
                     "charging:unrelated": sum(dep(f"joint:{s}:unrelated") for s in ("man", "nonman", "outside"))}
            for s in ("man", "nonman", "outside"):
                parts[f"subpopulation:{s}"] = dep(f"joint:{s}:related") + dep(f"joint:{s}:unrelated")
            for grp, tot in parts.items():
                if abs(tot - dep(grp)) > 0.5:
                    chk["partition_violations"] += 1
    return g, gm, chk


def reconcile_persons_groups(M, grp, iters, sub, coh):
    """Sum persons per group x iteration and compare with groups-N / group-modes-N."""
    masks = group_masks(sub, coh)
    q = {  # persons-sum key -> (matrix key, groups column)
        "score_sum": ("score", "score_sum"), "unfinished": ("unf", "unfinished"),
        "completed_car_legs": ("car_legs", "completed_car_legs"), "completed_car_seconds": ("car_sec", "completed_car_seconds"),
        "toll_revenue": ("toll", "toll_revenue"), "choice_changed": ("chg_c", "choice_changed"),
        "plan_changed": ("chg_p", "plan_changed"), "private_car_entry_crossings": ("entry", "private_car_entry_crossings")}
    res = {}
    g, gm = grp
    for name, (mk, gc) in q.items():
        worst_abs = worst_rel = 0.0
        n_bad = 0
        for gname, m in masks.items():
            X = M[mk][m]
            for it in iters:
                col = X[:, it]
                v = float(col.astype(np.float64).sum())
                ref = g[it][gname][gc]
                diff = abs(v - ref)
                rel = diff / max(abs(ref), 1.0)
                tol_rel = 1e-6 if mk == "toll" else 1e-9          # toll is stored as float32
                if name in ("choice_changed", "plan_changed") and it == 0:
                    continue                                      # no previous iteration to compare with
                worst_abs = max(worst_abs, diff); worst_rel = max(worst_rel, rel)
                if diff > max(tol_rel * abs(ref), 1e-6):
                    n_bad += 1
        res[name] = {"max_abs_diff": worst_abs, "max_rel_diff": worst_rel, "n_mismatch": n_bad}
    # persons counts and all-mode departures/completed/stuck vs group-modes
    for key, (mk, gmk) in {"departures": ("dep", "departures"), "completed": ("comp", "completed"), "stuck": ("stuck", "stuck")}.items():
        worst, n_bad = 0.0, 0
        for gname, m in masks.items():
            X = M[mk][m]
            for it in iters:
                v = float(X[:, it].astype(np.float64).sum())
                ref = sum(x[gmk] for x in gm[it][gname].values())
                worst = max(worst, abs(v - ref)); n_bad += int(abs(v - ref) > 0.5)
        res[f"allmode_{key}_vs_group_modes"] = {"max_abs_diff": worst, "n_mismatch": n_bad}
    # persons per group: count of present rows
    worst, n_bad = 0.0, 0
    for gname, m in masks.items():
        for it in iters:
            v = float(M["present"][m][:, it].sum()); ref = g[it][gname]["persons"]
            worst = max(worst, abs(v - ref)); n_bad += int(abs(v - ref) > 0.5)
    res["persons_count"] = {"max_abs_diff": worst, "n_mismatch": n_bad}
    return res


def collision_test(a, b, present):
    """persons x iterations where first-64-bit equal but next-64-bit differ; and distinct counts."""
    A = np.where(present, a, np.uint64(0)); B = np.where(present, b, np.uint64(0))
    order = np.argsort(A, axis=1, kind="stable")
    As = np.take_along_axis(A, order, 1); Bs = np.take_along_axis(B, order, 1)
    eqa = As[:, 1:] == As[:, :-1]
    return int((eqa & (Bs[:, 1:] != Bs[:, :-1])).sum()), int(eqa.sum())


def extract_run(out, sc, seed, iters, nproc):
    global _COHORT, _COHORT_SUB, _COHORT_COH
    t_start = time.time()
    partial = list(iters) != list(range(ITERS))
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    name = tag(sc, seed)
    d = sim(sc, seed)
    r = d / "research"
    files = source_files(sc, seed, iters)
    fp = source_fingerprint(files)
    chk_path = out / f"mat-{name}.check.json"
    if not partial and chk_path.exists() and (out / f"mat-{name}.npz").exists() and (out / f"grp-{name}.json").exists():
        try:
            old = json.loads(chk_path.read_text())
            ok = old.get("extract_schema") == EXTRACT_SCHEMA and old.get("source_fingerprint") == fp and old.get("complete") is True
            if sc == "baseline":
                ok = ok and (out / f"log-baseline-{seed}.npz").exists()
            if ok:
                with np.load(out / f"mat-{name}.npz") as z:
                    ok = set(MAT_KEYS) <= set(z.files) and z["present"].shape == (old["n_persons"], ITERS)
            if ok:
                log(f"{name}: verified cache reused (source fingerprint {fp[:12]})")
                return {"run": name, "reused": True, "seconds": 0.0}
        except Exception as e:  # unreadable cache -> rebuild
            log(f"{name}: cache check failed ({e}); re-extracting")
    log(f"{name}: extracting {len(iters)} iterations, nproc={nproc}, partial={partial}")
    coh_df = pd.read_csv(r / "cohorts.csv.gz", compression="gzip", dtype=str, keep_default_na=False)
    ids = coh_df["person_id"].to_numpy()
    n = len(ids)
    _COHORT = pd.Index(ids)
    _COHORT_SUB = coh_df["subpopulation"].to_numpy(); _COHORT_COH = coh_df["charging_cohort"].to_numpy()
    dup_c = int(pd.Index(ids).duplicated().sum())
    shape = (n, ITERS)
    dtypes = {"present": bool, "choice": np.uint64, "choice_b": np.uint64, "plan": np.uint64, "plan_b": np.uint64,
              "real": np.uint64, "outcome": np.uint64, "score": np.float64, "plans_mem": np.int8, "dep": np.int16,
              "comp": np.int16, "stuck": np.int16, "unf": np.int8, "car_legs": np.int16, "car_sec": np.float32,
              "trav_sec": np.float32, "toll": np.float32, "entry": np.int16, "chg_c": bool, "chg_p": bool}
    M = {k: np.zeros(shape, t) for k, t in dtypes.items()}
    recs = {}
    with Pool(nproc) as pool:
        for it, a, rec in pool.imap_unordered(parse_persons, [(r / f"persons-{it}.csv.gz", it) for it in iters]):
            for k in dtypes:
                M[k][:, it] = a[k]
            recs[it] = rec
            if len(recs) % 20 == 0:
                log(f"  {name}: {len(recs)}/{len(iters)} persons files parsed")
    files_rec = [recs[it] for it in sorted(recs)]
    # alignment-safe derived checks
    M["sub"] = _COHORT_SUB; M["coh"] = _COHORT_COH
    present = M["present"]
    chk = {"extract_schema": EXTRACT_SCHEMA, "run": name, "scenario": sc, "seed": seed, "n_persons": n, "iterations": list(iters),
           "partial": partial, "source_fingerprint": fp, "cohorts_file_sha256": sha256_file(r / "cohorts.csv.gz"),
           "cohort_duplicate_ids": dup_c, "files": files_rec}
    run_json = json.loads((run_dir(sc, seed) / "run.json").read_text())
    chk["run_json"] = {k: run_json.get(k) for k in ("commit", "worktree_dirty", "seed", "iterations", "innovation_until", "events",
                                                       "replanning_log", "expected_persons", "plans", "threads")}
    # hash-derived flags vs writer flags
    for key, flag, hkey in (("choice", "chg_c", "choice"), ("plan", "chg_p", "plan")):
        H = M[hkey]
        derived = np.zeros(shape, bool)
        derived[:, 1:] = H[:, 1:] != H[:, :-1]
        both = present[:, 1:] & present[:, :-1]
        sel = np.zeros(shape, bool); sel[:, 1:] = both
        mism = int((derived[sel] != M[flag][sel]).sum())
        chk[f"{flag}_writer_flag_vs_64bit_hash_mismatch"] = {"n": mism, "of": int(sel.sum())}
        del derived, sel
    coll = {}
    for key, bkey in (("choice", "choice_b"), ("plan", "plan_b")):
        n_coll, n_eq = collision_test(M[key], M[bkey], present)
        coll[key] = {"first64_equal_second64_differ": n_coll, "first64_equal_pairs": n_eq}
        del M[bkey]
    chk["hash_collision_test_128bit"] = coll
    chk["hash_collision_risk_note"] = ("64-bit truncation: expected collision pairs per run <= n*C(100,2)/2^64 = %.2e; realized/outcome hashes "
                                       "are 64-bit rolling hashes by definition (possible collisions)" % (n * 4950 / 2.0 ** 64))
    # group tables + reconciliation
    g, gm, gchk = read_group_tables(sc, seed, iters)
    chk["group_tables"] = gchk
    chk["person_vs_group"] = reconcile_persons_groups(M, (g, gm), iters, M["sub"], M["coh"])
    write_json(out / f"grp-{name}.json", {"groups": {str(k): v for k, v in g.items()}, "group_modes": {str(k): v for k, v in gm.items()}})
    # replanning log (baseline only)
    if sc == "baseline":
        L = d / "replanning-log"
        lp = pd.read_csv(L / "persons.csv.gz", compression="gzip", dtype=str, keep_default_na=False)
        mp = _COHORT.get_indexer(pd.Index(lp["person_id"]))
        logmap = np.full(int(pd.to_numeric(lp["person"]).max()) + 1, -1, np.int64)
        logmap[pd.to_numeric(lp["person"]).to_numpy(np.int64)] = mp
        strat = pd.read_csv(L / "strategies.csv", dtype={"strategy": int, "innovative": int})
        innov_ids = sorted(strat.loc[strat["innovative"] == 1, "strategy"].tolist())
        S = {k: np.zeros(shape, t) for k, t in (("logged", bool), ("strategy", np.int8), ("plan_created", np.int16),
                                                ("plan_id", np.int64), ("executed_score", np.float32))}
        S["strategy"][:] = -2; S["plan_created"][:] = -1; S["plan_id"][:] = -1; S["executed_score"][:] = np.nan
        lrecs = []
        with Pool(nproc) as pool:
            for it, a, rec in pool.imap_unordered(parse_log, [(L / f"agents-{it}.csv.gz", it, logmap) for it in iters]):
                for k in S:
                    S[k][:, it] = a[k]
                lrecs.append(rec)
        S["innovative"] = np.isin(S["strategy"], innov_ids)
        chk["replanning_log"] = {"strategies_csv": strat.to_dict("records"), "innovative_ids": innov_ids,
                                 "persons_csv_unknown_ids": int((mp < 0).sum()),
                                 "persons_csv_rows": int(len(lp)),
                                 "files": sorted(lrecs, key=lambda x: x["iteration"]),
                                 "strategies_csv_sha256": sha256_file(L / "strategies.csv"),
                                 "persons_csv_sha256": sha256_file(L / "persons.csv.gz")}
        tmp = out / f"log-baseline-{seed}.tmp.npz"
        np.savez(tmp, **S)
        os.replace(tmp, out / f"log-baseline-{seed}.npz")
        del S
    # completeness verdict (all files, no silent repair)
    bad = []
    for rec in files_rec:
        for k in ("n_unknown_ids", "n_duplicate_rows", "n_missing_ids", "cohort_label_mismatch", "dep_ne_comp_plus_stuck", "unfinished_not_01"):
            if rec[k]:
                bad.append((rec["iteration"], k, rec[k]))
        if not rec["columns_ok"] or rec["bad_numeric"] or rec["non_integer_counts"] or rec["negative_values"]:
            bad.append((rec["iteration"], "format", {k: rec[k] for k in ("columns_ok", "bad_numeric", "non_integer_counts", "negative_values")}))
        if any(rec["bad_sha_length"].values()) or any(rec["bad_hash64"].values()):
            bad.append((rec["iteration"], "hash_format", {k: rec[k] for k in ("bad_sha_length", "bad_hash64")}))
    pg = chk["person_vs_group"]
    if any(v["n_mismatch"] for v in pg.values()):
        bad.append(("person_vs_group", "mismatch", {k: v for k, v in pg.items() if v["n_mismatch"]}))
    if gchk["gm_dep_ne_comp_plus_stuck"] or gchk["partition_violations"] or gchk["unexpected_groups"] or gchk["missing_groups"]:
        bad.append(("group_tables", "inconsistent", gchk))
    chk["issues"] = bad[:200]
    chk["n_issues"] = len(bad)
    chk["complete"] = (len(bad) == 0) and not partial and dup_c == 0 and n == run_json.get("expected_persons")
    chk["rows_per_file_all_equal_n"] = all(rec["n_rows"] == n for rec in files_rec)
    chk["order_identical_files"] = int(sum(rec["order_identical_to_cohort"] for rec in files_rec))
    chk["seconds"] = round(time.time() - t_start, 1)
    chk["maxrss_gb_parent"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 2)
    # matrices: save uncompressed (hashes do not compress)
    tmp = out / f"mat-{name}.tmp.npz"
    np.savez(tmp, ids=ids.astype(str), sub=M["sub"].astype(str), coh=M["coh"].astype(str),
             **{k: M[k] for k in dtypes if k not in ("choice_b", "plan_b")})
    os.replace(tmp, out / f"mat-{name}.npz")
    write_json(chk_path, chk)
    log(f"{name}: done in {chk['seconds']}s, complete={chk['complete']}, issues={len(bad)}, parent maxrss={chk['maxrss_gb_parent']} GB")
    return {"run": name, "reused": False, "seconds": chk["seconds"], "complete": chk["complete"], "issues": len(bad)}


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd, out = a[0], Path(a[1])
    nproc = 4
    iters = list(range(ITERS))
    rest = a[2:]
    if "--nproc" in rest:
        nproc = int(rest[rest.index("--nproc") + 1])
    if "--iters" in rest:
        iters = sorted({int(x) for x in rest[rest.index("--iters") + 1].split(",")})
    prog = out / "extract-progress.jsonl"
    out.mkdir(parents=True, exist_ok=True)
    if cmd == "run":
        sc, seed = rest[0], int(rest[1])
        res = extract_run(out, sc, seed, iters, nproc)
        with open(prog, "a") as f:
            f.write(json.dumps(res) + "\n")
    elif cmd == "all":
        for sc, seed in all_runs():
            res = extract_run(out, sc, seed, list(range(ITERS)), nproc)
            res["maxrss_gb_all_so_far"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576, 2)
            with open(prog, "a") as f:
                f.write(json.dumps(res) + "\n")
    else:
        raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
