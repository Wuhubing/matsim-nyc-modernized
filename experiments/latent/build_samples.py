#!/usr/bin/env python3
"""Training samples: one per innovated plan (docs/latent-choice-plan.md, step 4).

  build_samples.py --plans DIR --city city.npz --runs SEED=RUN_DIR ... --its 10,20,... --cohorts COHORTS.csv.gz --out FILE.npz

A sample is an agent who innovated in iteration k (replanning-log/agents-k: innovative strategy,
plan_created == k, a parent plan). Label: executed score of the new plan in k minus the stored score of the
parent in the snapshot of k (both from before the parent could be re-scored in k). City state: road congestion
of iteration k-1 (what the router used). Arrays, padded with -1 / 0:
- plan tokens for the new and the parent plan: mode, departure hour, origin cell, destination cell,
  origin and destination activity type (int, [n, T, 6]); departure in hours (float, [n, T]);
- agent tokens from the parent plan's activities: type, cell, end hour (int, [n, A, 3]);
- agent summary: subpopulation one-hot, trips, plans in memory, best/mean stored score, main-mode shares of
  the stored plans (float);
- parent score, label, innovation type (0 mode, 1 time, 2 route), city state index, related cohort flag,
  validation flag (crc32(person) % 10 == 0), seed."""
import argparse, csv, gzip, math, pickle, zlib
import numpy as np

MODES = ['car', 'taxi', 'FHV', 'pt', 'ride', 'bike', 'cb', 'walk']
ACTS = ['Home', 'Work', 'Secondary', 'School', 'University']
SUBPOPS = ['man', 'nonman', 'outside']
T, A = 10, 11


def kind(desc):
    if 'SubtourModeChoice' in desc: return 0
    if 'TimeAllocation' in desc: return 1
    if 'ReRoute' in desc: return 2
    return -1


def act_id(t): return ACTS.index(t) if t in ACTS else len(ACTS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plans', required=True); ap.add_argument('--city', required=True)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--its', required=True)
    ap.add_argument('--cohorts', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    city = np.load(a.city)
    x0, y0, size, nx, ny = city['grid']; ny = int(ny)
    cell_index = {int(c): i for i, c in enumerate(city['cells'])}
    other = len(cell_index)
    states = {s: i for i, s in enumerate(city['states'])}

    def cell(x, y):
        return cell_index.get(int((x - x0) // size) * ny + int((y - y0) // size), other)

    with gzip.open(a.cohorts, 'rt') as f:
        related = {r['person_id']: r['charging_cohort'] == 'related' for r in csv.DictReader(f)}

    def plan_tokens(plan):
        tok = np.full((T, 6), -1, np.int16); dep = np.zeros(T, np.float32)
        for j, (m, d, ox, oy, dx, dy, ot, dt) in enumerate(plan['trips'][:T]):
            h = 0 if math.isnan(d) else min(int(d // 3600), 29)
            tok[j] = (MODES.index(m), h, cell(ox, oy), cell(dx, dy), act_id(ot), act_id(dt))
            dep[j] = 0 if math.isnan(d) else d / 3600
        return tok, dep

    out = {k: [] for k in ('new', 'new_dep', 'par', 'par_dep', 'act', 'summ', 'par_score', 'label', 'kind',
                            'state', 'related', 'val', 'seed')}
    for seed, run in (r.split('=', 1) for r in a.runs):
        log = f'{run}/replanning-log'
        with gzip.open(f'{log}/persons.csv.gz', 'rt') as f:
            pid = {r['person']: r['person_id'] for r in csv.DictReader(f)}
        with open(f'{log}/strategies.csv') as f:
            strat = {r['strategy']: (r['innovative'] == '1', kind(r['description'])) for r in csv.DictReader(f)}
        for k in (int(x) for x in a.its.split(',')):
            with open(f'{a.plans}/s{seed}-it{k}.pkl', 'rb') as f: agents = pickle.load(f)
            st = states[f'{seed}-{k - 1}']
            n0 = len(out['label'])
            with gzip.open(f'{log}/agents-{k}.csv.gz', 'rt') as f:
                for r in csv.DictReader(f):
                    innov, kd = strat.get(r['strategy'], (False, -1))
                    if not innov or kd < 0 or r['plan_created'] != str(k) or not r['parent_plan_id']: continue
                    p = pid[r['person']]; ag = agents.get(p)
                    if ag is None or not r['executed_score']: continue
                    # In the snapshot the new plan still carries its parent's planId and copied score (the new id is
                    # assigned later): it is the selected plan created in k; the parent has the id but was created earlier.
                    new = next((pl for pl in ag['plans'] if pl['created'] == k and pl['selected']), None)
                    par = next((pl for pl in ag['plans'] if pl['id'] == r['parent_plan_id'] and pl['created'] != k), None)
                    if new is None or par is None or math.isnan(par['score']): continue
                    stored = [pl for pl in ag['plans'] if pl is not new and not math.isnan(pl['score'])]
                    mix = np.zeros(len(MODES), np.float32)
                    for pl in stored:
                        for tr in pl['trips']: mix[MODES.index(tr[0])] += 1
                    mix /= max(mix.sum(), 1)
                    act = np.full((A, 3), -1, np.int16)
                    trs = par['trips'][:A - 1]
                    for j, tr in enumerate(trs):
                        act[j] = (act_id(tr[6]), cell(tr[2], tr[3]), 0 if math.isnan(tr[1]) else min(int(tr[1] // 3600), 29))
                    if trs: act[len(trs)] = (act_id(trs[-1][7]), cell(trs[-1][4], trs[-1][5]), 30)
                    sub = np.eye(len(SUBPOPS), dtype=np.float32)[SUBPOPS.index(ag['subpop'])] if ag['subpop'] in SUBPOPS else np.zeros(3, np.float32)
                    scores = [pl['score'] for pl in stored]
                    summ = np.concatenate([sub, [len(par['trips']), len(stored), max(scores), float(np.mean(scores))], mix]).astype(np.float32)
                    nt, nd = plan_tokens(new); pt, pd = plan_tokens(par)
                    for key, v in (('new', nt), ('new_dep', nd), ('par', pt), ('par_dep', pd), ('act', act), ('summ', summ),
                                   ('par_score', par['score']), ('label', float(r['executed_score']) - par['score']),
                                   ('kind', kd), ('state', st), ('related', related.get(p, False)),
                                   ('val', zlib.crc32(p.encode()) % 10 == 0), ('seed', int(seed))):
                        out[key].append(v)
            print(f'seed {seed} it {k}: {len(out["label"]) - n0} samples', flush=True)
    np.savez_compressed(a.out, **{k: np.array(v) for k, v in out.items()}, n_cells=np.array(other + 1))
    lab = np.array(out['label']); kd = np.array(out['kind'])
    print(f'{len(lab)} samples; better share {np.mean(lab > 0):.3f}; by kind',
          {k: (int((kd == k).sum()), round(float(np.mean(lab[kd == k] > 0)), 3)) for k in range(3)})


if __name__ == '__main__':
    main()
