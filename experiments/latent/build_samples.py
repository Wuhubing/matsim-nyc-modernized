#!/usr/bin/env python3
"""Training samples: one per innovated plan (docs/latent-choice-plan.md, step 4).

  build_samples.py --plans DIR --city city.npz --runs LABEL=RUN_DIR ... --its 10,20,... --cohorts COHORTS.csv.gz --out FILE.npz
                   [--agents agents_cold.pkl]

LABEL is SEED (baseline; plans DIR/sSEED-itK.pkl, city state SEED-(k-1)) or SCHEMA-SEED (schema1 / schema2; plans
DIR/SCHEMA-SEED-itK.pkl, no city state: index 0, unused by the structure-only versions).

A sample is an agent who innovated in iteration k (replanning-log/agents-k: innovative strategy,
plan_created == k, a parent plan). Runs without a replanning log (the policy runs): the new plan is the
selected plan created in k, its parent the plan with the same planId created earlier, the type from the new plan's
planMutator, and the executed score from research/persons-k (equal to the log's executed score to < 3e-5 on the
baseline). Label: executed score of the new plan in k minus the stored score of the
parent in the snapshot of k (both from before the parent could be re-scored in k). City state: road congestion
of iteration k-1 (what the router used). Arrays, padded with -1 / 0:
- plan tokens for the new and the parent plan: mode, departure hour, origin cell, destination cell,
  origin and destination activity type (int, [n, T, 6]); departure hours, planned travel hours, route km / 10
  and legs (float, [n, T, 4], 0 where missing; extract_plans.py);
- agent memory, only what the plan tokens do not carry: one token per stored plan other than the new one
  (float, [n, M, 17]): main-mode shares of its trips, score minus parent score, age in iterations / 10, is the
  parent, which strategy made it (initial, mode, time, route), mean absolute departure shift from the parent in
  hours and whether it has the parent's number of trips (shift 0 otherwise);
- agent summary: subpopulation one-hot, trips, plans in memory, best and mean stored score minus parent score;
- parent score, label, innovation type (0 mode, 1 time, 2 route), city state index, related cohort flag,
  validation flag (crc32(person) % 10 == 0), person group crc32(person) % 10 (group 1 is never trained on in
  train4.py: people the network has not seen), seed, scenario (0 baseline, 1 schema1, 2 schema2);
- tolls per trip of the new and the parent plan (float, [n, T, 2]): tolled links crossed and dollars at the
  scenario's price (peak 6-10, 14-20, 30-34 h, else $3.06; departure hour of the trip), when the plans carry
  crossings (extract_plans.py --links); money utility of the person's subpopulation;
- with --agents (city_static.py): the person's own day from the initial plan, independent of any run: activity
  tokens (type, cell) (int, [n, A, 2]) and (start, end, duration) / 24 (float, [n, A, 3], 0 where missing)."""
import argparse, csv, gzip, math, pickle, zlib
import numpy as np

MODES = ['car', 'taxi', 'FHV', 'pt', 'ride', 'bike', 'cb', 'walk']
ACTS = ['Home', 'Work', 'Secondary', 'School', 'University']
SUBPOPS = ['man', 'nonman', 'outside']
PEAK = {'baseline': 0.0, 'schema1': 9.18, 'schema2': 14.0}
LAMBDA = {'man': 0.062227, 'outside': 0.062227, 'nonman': 0.0543894}
A = 12
T, M = 10, 5
MUTATORS = ['initialPlan', 'SubtourModeChoice', 'TimeAllocation', 'ReRoute']


def amount(dep, peak):
    if peak == 0: return 0.0
    h = 0 if math.isnan(dep) else dep / 3600
    return peak if (6 <= h < 10 or 14 <= h < 20 or 30 <= h < 34) else 3.06


def kind(desc):
    if not desc: return -1
    if 'SubtourModeChoice' in desc: return 0
    if 'TimeAllocation' in desc: return 1
    if 'ReRoute' in desc: return 2
    return -1


def act_id(t): return ACTS.index(t) if t in ACTS else len(ACTS)


def mutator_id(m):
    return next((i for i, x in enumerate(MUTATORS) if m and x in m), 0)   # SubtourModeChoice_ReRoute is a mode change


def memory(stored, par, k):
    mem = np.zeros((M, 9 + 4 + 4), np.float32)
    pdep = np.array([tr[1] for tr in par['trips']], float)
    for i, pl in enumerate(sorted(stored, key=lambda pl: -pl['score'])[:M]):
        mix = np.zeros(len(MODES), np.float32)
        for tr in pl['trips']: mix[MODES.index(tr[0])] += 1
        mem[i, :8] = mix / max(mix.sum(), 1)
        mem[i, 8] = pl['score'] - par['score']
        mem[i, 9] = (k - pl['created']) / 10
        mem[i, 10] = pl is par
        mem[i, 11 + mutator_id(pl['mutator'])] = 1
        same = len(pl['trips']) == len(pdep)
        if same and len(pdep):
            d = np.abs(np.array([tr[1] for tr in pl['trips']], float) - pdep) / 3600
            mem[i, 15] = float(np.nanmean(d)) if np.isfinite(d).any() else 0
        mem[i, 16] = same
    return mem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plans', required=True); ap.add_argument('--city', required=True)
    ap.add_argument('--runs', nargs='+', required=True); ap.add_argument('--its', required=True)
    ap.add_argument('--cohorts', required=True); ap.add_argument('--out', required=True); ap.add_argument('--agents')
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

    cold = {}
    if a.agents:
        with open(a.agents, 'rb') as f: cold = pickle.load(f)

    def own_day(p):
        tok = np.full((A, 2), -1, np.int16); x = np.zeros((A, 3), np.float32)
        for j, (t, c, st, en) in enumerate(cold.get(p, {}).get('acts', [])[:A]):
            tok[j] = (act_id(t), min(c, other))
            st = 0 if math.isnan(st) else st; en = 30 if math.isnan(en) else en
            x[j] = (st / 24, en / 24, max(en - st, 0) / 24)
        return tok, x

    def tolls(plan, peak):
        out = np.zeros((T, 2), np.float32)
        for j, tr in enumerate(plan['trips'][:T]):
            if len(tr) > 11: out[j] = (tr[11], tr[11] * amount(tr[1], peak))
        return out

    def plan_tokens(plan):
        tok = np.full((T, 6), -1, np.int16); x = np.zeros((T, 4), np.float32)
        for j, (m, d, ox, oy, dx, dy, ot, dt, tt, dist, legs) in enumerate(tr[:11] for tr in plan['trips'][:T]):
            h = 0 if math.isnan(d) else min(int(d // 3600), 29)
            tok[j] = (MODES.index(m), h, cell(ox, oy), cell(dx, dy), act_id(ot), act_id(dt))
            x[j] = [0 if math.isnan(v) else v for v in (d / 3600, tt / 3600, dist / 10000, legs)]
        return tok, x

    out = {k: [] for k in ('new', 'new_x', 'par', 'par_x', 'mem', 'summ', 'par_score', 'label', 'kind',
                            'state', 'related', 'val', 'seed', 'grp', 'scen', 'new_toll', 'par_toll', 'lam', 'ag_tok', 'ag_x')}
    for label, run in (r.split('=', 1) for r in a.runs):
        scen = label.split('-')[0] if '-' in label else 'baseline'; seed = int(label.split('-')[-1]); peak = PEAK[scen]
        log = f'{run}/replanning-log'
        has_log = scen == 'baseline'
        if has_log:
            with gzip.open(f'{log}/persons.csv.gz', 'rt') as f:
                pid = {r['person']: r['person_id'] for r in csv.DictReader(f)}
            with open(f'{log}/strategies.csv') as f:
                strat = {r['strategy']: (r['innovative'] == '1', kind(r['description'])) for r in csv.DictReader(f)}
        for k in (int(x) for x in a.its.split(',')):
            name = f's{seed}-it{k}' if scen == 'baseline' else f'{label}-it{k}'
            with open(f'{a.plans}/{name}.pkl', 'rb') as f: agents = pickle.load(f)
            st = states[f'{seed}-{k - 1}'] if scen == 'baseline' else 0
            n0 = len(out['label'])
            if has_log:
                rows = []
                with gzip.open(f'{log}/agents-{k}.csv.gz', 'rt') as f:
                    for r in csv.DictReader(f):
                        innov, kd = strat.get(r['strategy'], (False, -1))
                        if not innov or kd < 0 or r['plan_created'] != str(k) or not r['parent_plan_id'] or not r['executed_score']: continue
                        rows.append((pid[r['person']], kd, r['parent_plan_id'], float(r['executed_score'])))
            else:
                with gzip.open(f'{run}/research/persons-{k}.csv.gz', 'rt') as f:
                    executed = {r['person_id']: float(r['score']) for r in csv.DictReader(f) if r['score']}
                rows = []
                for p, ag in agents.items():
                    new = next((pl for pl in ag['plans'] if pl['created'] == k and pl['selected']), None)
                    if new is None or p not in executed or kind(new['mutator']) < 0: continue
                    rows.append((p, kind(new['mutator']), new['id'], executed[p]))
            for p, kd, parent_id, executed_score in rows:
                    ag = agents.get(p)
                    if ag is None: continue
                    # In the snapshot the new plan still carries its parent's planId and copied score (the new id is
                    # assigned later): it is the selected plan created in k; the parent has the id but was created earlier.
                    new = next((pl for pl in ag['plans'] if pl['created'] == k and pl['selected']), None)
                    par = next((pl for pl in ag['plans'] if pl['id'] == parent_id and pl['created'] != k), None)
                    if new is None or par is None or math.isnan(par['score']): continue
                    stored = [pl for pl in ag['plans'] if pl is not new and not math.isnan(pl['score'])]
                    sub = np.eye(len(SUBPOPS), dtype=np.float32)[SUBPOPS.index(ag['subpop'])] if ag['subpop'] in SUBPOPS else np.zeros(3, np.float32)
                    scores = [pl['score'] for pl in stored]
                    summ = np.concatenate([sub, [len(par['trips']), len(stored), max(scores) - par['score'],
                                                 float(np.mean(scores)) - par['score']]]).astype(np.float32)
                    nt, nd = plan_tokens(new); pt, pd = plan_tokens(par); gt, gx = own_day(p)
                    for key, v in (('new', nt), ('new_x', nd), ('par', pt), ('par_x', pd), ('mem', memory(stored, par, k)), ('summ', summ),
                                   ('par_score', par['score']), ('label', executed_score - par['score']),
                                   ('kind', kd), ('state', st), ('related', related.get(p, False)),
                                   ('val', zlib.crc32(p.encode()) % 10 == 0), ('seed', seed), ('grp', zlib.crc32(p.encode()) % 10), ('scen', ['baseline', 'schema1', 'schema2'].index(scen)),
                                   ('new_toll', tolls(new, peak)), ('par_toll', tolls(par, peak)), ('lam', LAMBDA.get(ag['subpop'], 0.062227)),
                                   ('ag_tok', gt), ('ag_x', gx)):
                        out[key].append(v)
            print(f'{label} it {k}: {len(out["label"]) - n0} samples', flush=True)
    np.savez_compressed(a.out, **{k: np.array(v) for k, v in out.items()}, n_cells=np.array(other + 1))
    lab = np.array(out['label']); kd = np.array(out['kind'])
    print(f'{len(lab)} samples; better share {np.mean(lab > 0):.3f}; by kind',
          {k: (int((kd == k).sum()), round(float(np.mean(lab[kd == k] > 0)), 3)) for k in range(3)})


if __name__ == '__main__':
    main()
