#!/usr/bin/env python3
"""Figures (PNG + PDF) from the real s5/s6 outputs. Plots only what exists; no synthetic or placeholder data.

  python s4_figures.py OUT        # writes OUT/figures/*.png and *.pdf
Palette: reference categorical slots 1-3 (blue, orange, aqua), validated adjacent/all-pairs for <=3 series; text in ink tokens.
"""
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from s4_common import SEEDS, CHARTER, FINAL

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
GREY = "#a9a8a2"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "text.color": INK, "axes.facecolor": SURF, "figure.facecolor": SURF, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})
NAMES = {"legs_car_charging_related": "Car departures, charging:related", "share_car": "Car share of departures", "share_pt": "PT share of departures"}


def save(fig, out, name):
    d = Path(out) / "figures"; d.mkdir(exist_ok=True)
    fig.savefig(d / f"{name}.png", dpi=160, bbox_inches="tight"); fig.savefig(d / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_delta(out):
    p = Path(out) / "s6" / "policy_delta_by_iteration.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    fig, ax = plt.subplots(3, 3, figsize=(11, 8), sharex=True)
    for i, m in enumerate(("legs_car_charging_related", "share_car", "share_pt")):
        for j, pol in enumerate(("schema1", "schema2", "D")):
            a = ax[i, j]
            sub = df[(df.metric == m) & (df.policy == pol)]
            mean = sub[sub.seed == "mean"].sort_values("iteration")
            ref, eps = mean.ref_mean_3seed_final.iloc[0], mean.eps.iloc[0]
            a.axhspan(ref - eps, ref + eps, color=C3, alpha=0.18, lw=0)
            a.axhline(ref, color=INK2, lw=0.8, ls=":")
            for s in SEEDS:
                x = sub[sub.seed == str(s)].sort_values("iteration")
                a.plot(x.iteration, x.trailing10, color=GREY, lw=0.9)
            a.plot(mean.iteration, mean.trailing10, color=C1, lw=2)
            a.axvline(79.5, color=C2, lw=0.8, ls="--")
            a.set_title(f"{NAMES[m]}\n{'D = schema1 - schema2' if pol == 'D' else pol + ' - baseline'}", fontsize=8.5, color=INK2, loc="left")
            if j == 0:
                a.set_ylabel("delta, trailing 10-iteration mean")
            if i == 2:
                a.set_xlabel("iteration")
    fig.suptitle("Policy differences by iteration (trailing 10-iteration means; windows ending 80-88 mix innovation and select-only)", fontsize=10, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.text(0.01, 0.005, "blue: 3-seed mean; grey: single seeds; green band: charter tolerance (eps) around the final-window mean; orange dashed: innovation off after iteration 79. "
             "Note: the share_pt band is as wide as the effect itself.", fontsize=7.5, color=INK2)
    save(fig, out, "fig1_policy_delta_by_iteration")


def fig_rates(out):
    p = Path(out) / "s5" / "transition_rates.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    rep = df[df.group == "replanners"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    base = rep[rep.scenario == "baseline"].groupby("iteration").mean(numeric_only=True)
    for col, c, lab in (("choice_changed", C1, "plan fingerprint (no times)"), ("plan_changed", C2, "plan fingerprint incl. times"),
                        ("car_state_changed", C3, "car use yes/no"), ("travel_sec_rel_gt10", GREY, "travel seconds changed >10%")):
        ax[0].plot(base.index, base[col], color=c, lw=1.6, label=lab)
    ax[0].axvline(79.5, color=INK2, lw=0.8, ls="--")
    ax[0].set_title("Baseline, persons that can re-plan (mean of 3 seeds)", loc="left", fontsize=9, color=INK2)
    ax[0].set_xlabel("iteration"); ax[0].set_ylabel("share changed vs previous iteration"); ax[0].legend(fontsize=7.5)
    for sc, c in (("baseline", C1), ("schema1", C2), ("schema2", C3)):
        x = rep[rep.scenario == sc].groupby("iteration").mean(numeric_only=True)
        ax[1].plot(x.index, x["car_state_changed"], color=c, lw=1.6, label=sc)
    ax[1].axvline(79.5, color=INK2, lw=0.8, ls="--")
    ax[1].set_title("Car use yes/no changed, by scenario", loc="left", fontsize=9, color=INK2)
    ax[1].set_xlabel("iteration"); ax[1].legend(fontsize=8)
    fig.tight_layout(); save(fig, out, "fig2_transition_rates")


def fig_labels(out):
    p = Path(out) / "s5" / "stability_windows.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    d = df[(df.window == "main_P80-89_H90-99") & (df.population == "replanners") & (df.scenario == "baseline")]
    defs = ["plan_fp", "timed_plan", "car_state", "car_count", "secs_travel_rel10", "secs_car_rel10"]
    g = d[d.definition.isin(defs)].groupby("definition").mean(numeric_only=True).reindex(defs)
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    y = np.arange(len(defs)); h = 0.26
    ax.barh(y - h, g.Hdev_rate_stable, h - 0.03, color=C1, label="labelled stable in P (80-89)")
    ax.barh(y, g.Hdev_ref_rate_stratified, h - 0.03, color=GREY, label="stratified random reference (same count)")
    ax.barh(y + h, g.Hdev_rate_unstable, h - 0.03, color=C2, label="not stable in P")
    ax.set_yticks(y); ax.set_yticklabels(defs); ax.invert_yaxis(); ax.set_xlim(0, 1)
    ax.set_xlabel("share whose state in H (90-99) differs from the state at iteration 89")
    ax.set_title("Baseline, persons that can re-plan, mean of 3 seeds: holdout instability by past-window label", loc="left", fontsize=9, color=INK2)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3); fig.tight_layout(); save(fig, out, "fig3_label_holdout_instability")


def fig_contrib(out):
    p = Path(out) / "s6" / "contribution_by_group.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    df = df[df.kind == "person_completed_car_legs"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    groups = ["charging:related", "charging:unrelated"]
    for j, pol in enumerate(("schema1", "schema2")):
        a = ax[j]
        x = np.arange(len(groups)); w = 0.18
        for k, (col, c, lab) in enumerate((("pos", C1, "sum of positive person deltas"), ("neg", C2, "sum of negative person deltas"), ("net", INK, "net"))):
            vals = [df[(df.policy == pol) & (df.group == g)][col].mean() for g in groups]
            a.bar(x + (k - 1) * w, vals, w - 0.02, color=c, label=lab if j == 0 else None)
        nul = df[df.policy == "baseline_pair_null"]
        for k, g in enumerate(groups):
            r = nul[nul.group == g]
            a.hlines([r.pos.mean(), r.neg.mean()], k - 1.5 * w, k + 0.5 * w, colors=INK2, lw=1.2, linestyles="--", label="baseline-vs-baseline null (mean of 3 pairs)" if (j == 0 and k == 0) else None)
        a.set_xticks(x); a.set_xticklabels(groups); a.axhline(0, color=INK2, lw=0.8)
        a.set_title(f"{pol} - baseline, same seed; mean of 3 seeds", loc="left", fontsize=9, color=INK2)
    ax[0].set_ylabel("sum of person deltas, completed car legs\n(mean of iterations 90-99, sample units)")
    ax[0].legend(fontsize=7.5)
    fig.tight_layout(); save(fig, out, "fig4_contribution_pos_neg_net")


def fig_strata(out):
    p = Path(out) / "s6" / "contribution_by_stratum_iteration.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.9))
    strata = [("fixed:joint:man:related", C1, "man, related"), ("fixed:joint:man:unrelated", C2, "man, unrelated"),
              ("fixed:joint:nonman:unrelated", C3, "nonman, unrelated")]
    rest = ["fixed:joint:nonman:related", "fixed:joint:outside:related", "fixed:joint:outside:unrelated"]
    for j, pol in enumerate(("schema1", "schema2")):
        for st, c, lab in strata:
            x = df[(df.policy == pol) & (df.stratum == st)].groupby("iteration").contribution_trailing10.mean()
            ax[j].plot(x.index, x.values, color=c, lw=1.8, label=lab)
        for k, st in enumerate(rest):
            x = df[(df.policy == pol) & (df.stratum == st)].groupby("iteration").contribution_trailing10.mean()
            ax[j].plot(x.index, x.values, color=GREY, lw=1.0, label="other fixed groups (nonman related, outside)" if k == 0 else None)
        x = df[(df.policy == pol) & (df.stratum == "all")].groupby("iteration").contribution_trailing10.mean()
        ax[j].plot(x.index, x.values, color=INK, lw=1.2, ls="--", label="all persons")
        ax[j].axvline(79.5, color=INK2, lw=0.8, ls="--"); ax[j].axhline(0, color=INK2, lw=0.6)
        ax[j].set_title(f"{pol} - baseline: completed car legs, fixed cohorts (mean of 3 seeds)", loc="left", fontsize=8.5, color=INK2)
        ax[j].set_xlabel("iteration")
    ax[0].set_ylabel("sum over group of (policy - baseline),\ntrailing 10-iteration mean"); ax[0].legend(fontsize=7)
    fig.text(0.01, -0.03, "Strata defined from the baseline's own car use (in contribution_by_stratum_iteration.csv) are NOT plotted: conditioning on a baseline outcome "
             "produces mechanical opposite-signed contributions (about +/-78,000) that cancel and are not a policy effect.", fontsize=7.5, color=INK2)
    fig.tight_layout(); save(fig, out, "fig5_contribution_by_fixed_group_over_iterations")


def fig_lorenz(out):
    p = Path(out) / "s6" / "lorenz.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    fig, ax = plt.subplots(1, 2, figsize=(9.5, 4))
    for j, g in enumerate(("charging:related", "all")):
        for pol, c in (("schema1", C1), ("schema2", C2)):
            x = df[(df.policy == pol) & (df.group == g)].groupby("cum_person_share").cum_abs_delta_share.mean()
            ax[j].plot(x.index, x.values, color=c, lw=1.8, label=pol)
        ax[j].plot([0, 1], [0, 1], color=GREY, lw=0.8, ls=":")
        ax[j].set_title(f"Lorenz curve of |person delta|, {g}\n(mean of 3 seeds)", loc="left", fontsize=8.5, color=INK2)
        ax[j].set_xlabel("cumulative share of persons (smallest |delta| first)")
    ax[0].set_ylabel("cumulative share of gross |delta|"); ax[0].legend(fontsize=8)
    fig.tight_layout(); save(fig, out, "fig6_lorenz")


def fig_proxy(out):
    p = Path(out) / "s5" / "proxy_check.json"
    if not p.exists():
        return
    d = json.loads(p.read_text())["pooled_lag0"]
    keys = [("1-79_innovation_on|timed_fp", "innovation on, timed fp"), ("1-79_innovation_on|choice_fp", "innovation on, choice-only fp"),
            ("80-99_select_only|timed_fp", "select-only, timed fp")]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    x = np.arange(len(keys)); w = 0.26
    for k, (m, c) in enumerate((("agreement", C1), ("precision", C2), ("recall", C3))):
        ax.bar(x + (k - 1) * w, [d[kk][m] for kk, _ in keys], w - 0.02, color=c, label=m)
    ax.set_xticks(x); ax.set_xticklabels([l for _, l in keys], fontsize=8); ax.set_ylim(0, 1.05)
    ax.axhline(0.95, color=INK2, lw=0.7, ls=":"); ax.axhline(0.80, color=INK2, lw=0.7, ls=":")
    ax.set_title("New-plan fingerprint proxy vs replanning log (3 baseline runs pooled); dotted: exploratory 0.95 / 0.80", loc="left", fontsize=8.5, color=INK2)
    ax.legend(fontsize=8, ncol=3); fig.tight_layout(); save(fig, out, "fig7_new_plan_proxy_vs_log")


if __name__ == "__main__":
    out = sys.argv[1]
    for f in (fig_delta, fig_rates, fig_labels, fig_contrib, fig_strata, fig_lorenz, fig_proxy):
        f(out)
