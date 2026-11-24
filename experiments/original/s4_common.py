"""Shared constants and helpers for the s4 (extract), s5 (stability) and s6 (policy) analyses.

Reads only the nine original runs at known paths. Needs numpy + pandas (miniforge 25.11.0-0 python 3.12 on ORCD).
No directory traversal: every path is built from RUNS / BASE below.
"""
import hashlib, json, os, sys, time
from pathlib import Path

import numpy as np

ANALYSIS_VERSION = "s4-s6 v1 (2026-11-24)"
BASE = Path("/orcd/scratch/orcd/006/weibingw/matsim-work")
RUNS = {
    "baseline": "rq1/baseline-s{seed}-100it-rq1",
    "schema1": "policy/schema1-s{seed}-100it",
    "schema2": "policy/schema2-s{seed}-100it",
}
SCENARIOS = tuple(RUNS)
SEEDS = (4711, 4712, 4713)
ITERS = 100
INNOV_OFF_FROM = 80          # run.json innovation_until=79: iterations >= 80 select only
FINAL = (90, 99)             # charter acceptance window (inclusive)
MODES = ("FHV", "bike", "car", "cb", "pt", "ride", "taxi", "walk")
GROUPS = ("all", "charging:related", "charging:unrelated",
          "joint:man:related", "joint:man:unrelated", "joint:nonman:related", "joint:nonman:unrelated",
          "joint:outside:related", "joint:outside:unrelated",
          "subpopulation:man", "subpopulation:nonman", "subpopulation:outside")

# charter 3.1 / acceptance-protocol 6.1-6.2 (reference values, not changed here)
CHARTER = {  # metric -> {policy: (mean, sd, eps)}, D: (mean, sd, eps_D)
    "legs_car_charging_related": {"schema1": (-8717, 356, 712), "schema2": (-11053, 368, 736), "D": (2336, 263, 526)},
    "share_car": {"schema1": (-0.00250, 0.00022, 0.0005), "schema2": (-0.00332, 0.00014, 0.0005), "D": (0.00081, 0.00008, 0.0005)},
    "share_pt": {"schema1": (0.00057, 0.00015, 0.0005), "schema2": (0.00084, 0.00011, 0.0005), "D": (-0.00027, 0.00017, 0.0005)},
}


def sim(scenario, seed):
    return BASE / RUNS[scenario].format(seed=seed) / "simulation"


def run_dir(scenario, seed):
    return BASE / RUNS[scenario].format(seed=seed)


def all_runs():
    return [(sc, s) for sc in SCENARIOS for s in SEEDS]


def tag(sc, seed):
    return f"{sc}-{seed}"


def log(msg, fh=None):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    if fh:
        fh.write(line + "\n"); fh.flush()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=_jsonable))
    os.replace(tmp, path)


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def load_mat(outdir, sc, seed, keys=None):
    """Load a person x iteration matrix NPZ (only the requested arrays)."""
    p = Path(outdir) / f"mat-{sc}-{seed}.npz"
    with np.load(p, allow_pickle=False) as z:
        ks = keys or z.files
        return {k: z[k] for k in ks}


def group_masks(sub, coh):
    m = {"all": np.ones(len(sub), bool),
         "charging:related": coh == "related", "charging:unrelated": coh == "unrelated"}
    for s in ("man", "nonman", "outside"):
        m[f"subpopulation:{s}"] = sub == s
        for c in ("related", "unrelated"):
            m[f"joint:{s}:{c}"] = (sub == s) & (coh == c)
    return m


def last_true(mask, default=0):
    rev = mask[:, ::-1]
    any_ = rev.any(1)
    return np.where(any_, mask.shape[1] - 1 - rev.argmax(1), default)


def load_grp(outdir, sc, seed):
    d = json.loads((Path(outdir) / f"grp-{sc}-{seed}.json").read_text())
    return ({int(k): v for k, v in d["groups"].items()}, {int(k): v for k, v in d["group_modes"].items()})


def run_metrics(grp):
    """Charter metrics per iteration from the group tables. departures (charter) and completed (s2 'legs_car') kept apart."""
    g, gm = grp
    its = sorted(gm)
    out = {k: np.zeros(ITERS) for k in ("legs_car_charging_related", "legs_car_completed_charging_related", "stuck_car_charging_related",
                                        "share_car", "share_pt", "total_departures", "car_departures_all", "pt_departures_all",
                                        "car_completed_all", "car_stuck_all")}
    for it in its:
        tot = sum(x["departures"] for x in gm[it]["all"].values())
        out["legs_car_charging_related"][it] = gm[it]["charging:related"]["car"]["departures"]
        out["legs_car_completed_charging_related"][it] = gm[it]["charging:related"]["car"]["completed"]
        out["stuck_car_charging_related"][it] = gm[it]["charging:related"]["car"]["stuck"]
        out["total_departures"][it] = tot
        out["car_departures_all"][it] = gm[it]["all"]["car"]["departures"]
        out["pt_departures_all"][it] = gm[it]["all"]["pt"]["departures"]
        out["car_completed_all"][it] = gm[it]["all"]["car"]["completed"]
        out["car_stuck_all"][it] = gm[it]["all"]["car"]["stuck"]
        out["share_car"][it] = gm[it]["all"]["car"]["departures"] / tot
        out["share_pt"][it] = gm[it]["all"]["pt"]["departures"] / tot
    return out


def window_mean(x, lo, hi):
    return float(np.mean(x[lo:hi + 1]))


def charter_print_rounding_ok(mean, ref, metric):
    """Documented explanation for a +-half-unit miss: the original compute_deltas.py printed means with '+.5g' and the
    charter table was typed from that print (legs metric rounded again to an integer, half away from zero).
    Returns True if re-doing that double rounding gives the charter value. Used ONLY as an explicit, flagged secondary check."""
    from decimal import Decimal, ROUND_HALF_UP
    printed = Decimal(f"{mean:.5g}")
    q = Decimal("1") if metric.startswith("legs") else Decimal("0.00001")
    return printed.quantize(q, rounding=ROUND_HALF_UP) == Decimal(str(ref)).quantize(q, rounding=ROUND_HALF_UP)


def manifest(out, stage):
    """Write OUT/run-manifest-<jobid>-<stage>.json: version, scripts hashes, python stack, Slurm resources, run commits."""
    here = Path(__file__).resolve().parent
    import pandas, platform
    m = {"analysis_version": ANALYSIS_VERSION, "stage": stage, "time": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
         "python": sys.version.split()[0], "numpy": np.__version__, "pandas": pandas.__version__, "host": platform.node(),
         "slurm": {k: os.environ.get(k) for k in ("SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_JOB_PARTITION", "SLURM_CPUS_PER_TASK",
                                                   "SLURM_MEM_PER_NODE", "SLURM_RESTART_COUNT", "SLURM_JOB_NODELIST")},
         "scripts": {p.name: sha256_file(p) for p in sorted(here.glob("s[456]*.py")) + sorted(here.glob("s4*.sbatch"))},
         "repo_head_when_written": "df776c3 (research/cleanup); s4-s6 scripts are new and uncommitted",
         "data_root": str(BASE), "runs": {}}
    for sc, seed in all_runs():
        rj = json.loads((run_dir(sc, seed) / "run.json").read_text())
        m["runs"][tag(sc, seed)] = {"path": str(run_dir(sc, seed)), "commit": rj.get("commit"), "dirty": rj.get("worktree_dirty")}
    write_json(Path(out) / f"run-manifest-{os.environ.get('SLURM_JOB_ID', 'local')}-{stage}.json", m)


if __name__ == "__main__":
    if sys.argv[1] == "manifest":
        manifest(sys.argv[2], sys.argv[3])
