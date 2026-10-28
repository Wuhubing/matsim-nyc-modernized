#!/usr/bin/env python3
"""Initial plans for MATSim from the converged-plan network (docs/converged-plan-plan.md, section 6b).

  seed_plans.py COLD.xml.gz --cold-pkl ALL.pkl --city city.npz --static static.npz --cohorts COHORTS.csv.gz
                --models DIR [--version full --runs 3] --out-prefix PREFIX [--seed 0]

ALL.pkl: extract_plans.py of COLD.xml.gz for every person (--sample-keep 1000). The ensemble of DIR/{version}-{r}.pt
(train_conv.py) gives every trip's main-mode probabilities. Plans are sampled from them: car and bike are chain modes
in MATSim's SubtourModeChoice, so per tour (from leaving a Home activity to returning; the whole day if there is no
Home) the tour is car with probability mean P(car), else bike with probability mean P(bike), else every trip draws
its own mode from its probabilities without car and bike. Departure times, activities and everything else stay as in
COLD; legs carry only the mode (as in COLD) and MATSim routes them in iteration 0. The 'outside' subpopulation keeps
its initial plan: it has no innovation strategy, so its initial plan is its stable plan.
Writes PREFIX-1.xml.gz (one sampled plan per person) and PREFIX-3.xml.gz (up to three distinct sampled plans, the
first selected, none scored) and PREFIX-summary.json (mode shares of the initial, predicted and sampled plans)."""
import argparse, csv, gzip, json, pickle, sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
from conv_samples import MODES, T, grid, inputs                   # noqa: E402
from train_conv import Net                                        # noqa: E402

CAR, BIKE = MODES.index('car'), MODES.index('bike')


def tours(acts):
    """Trip indices grouped into tours that start where a Home activity ends."""
    out, cur = [], []
    for j in range(len(acts) - 1):
        if acts[j] == 'Home' and cur: out.append(cur); cur = []
        cur.append(j)
    if cur: out.append(cur)
    return out


def sample(P, acts, rng):
    modes = np.zeros(len(acts) - 1, int)
    for tour in tours(acts):
        pc = float(np.mean([P[j, CAR] for j in tour])); pb = float(np.mean([P[j, BIKE] for j in tour]))
        u = rng.random()
        if u < pc: modes[tour] = CAR
        elif u < pc + pb: modes[tour] = BIKE
        else:
            for j in tour:
                q = P[j].copy(); q[CAR] = q[BIKE] = 0; q = q / q.sum() if q.sum() > 0 else np.eye(len(MODES))[MODES.index('walk')]
                modes[j] = rng.choice(len(MODES), p=q)
    return modes


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cold')
    for k in ('--cold-pkl', '--city', '--static', '--cohorts', '--models', '--out-prefix'): ap.add_argument(k, required=True)
    ap.add_argument('--version', default='full'); ap.add_argument('--runs', type=int, default=3); ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args()
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    city = np.load(a.city); Z = np.load(a.static); cell, C = grid(city)
    with gzip.open(a.cohorts, 'rt') as f:
        related = {r['person_id']: r['charging_cohort'] == 'related' for r in csv.DictReader(f)}
    with open(a.cold_pkl, 'rb') as f: cold = pickle.load(f)
    pids = sorted(cold); D, _ = inputs(cold, pids, cell, C, related)
    print(f'{len(pids)} persons, device {dev}', flush=True)
    Tt = {k: torch.as_tensor(D[k], device=dev) for k in ('tok', 'x', 'init', 'sub')}
    Tt['tok'] = Tt['tok'].long(); Tt['init'] = Tt['init'].long()
    P = np.zeros((len(pids), T, len(MODES)), np.float32)
    for r in range(a.runs):
        model = Net(set(a.version.split('+')), torch.tensor(Z['road']), torch.tensor(Z['transit']),
                    torch.tensor(city['adj'], dtype=torch.long), len(city['cells'])).to(dev)
        model.load_state_dict(torch.load(f'{a.models}/{a.version}-{r}.pt', map_location=dev)); model.eval()
        with torch.no_grad():
            E = model.city()
            for i in range(0, len(pids), 8192):
                lm, _ = model(Tt['tok'][i:i + 8192], Tt['x'][i:i + 8192], Tt['init'][i:i + 8192], Tt['sub'][i:i + 8192], E)
                P[i:i + 8192] += torch.softmax(lm, -1).cpu().numpy() / a.runs
    row = {p: i for i, p in enumerate(pids)}
    rng = np.random.default_rng(a.seed)
    shares = {k: Counter() for k in ('initial', 'predicted', 'sampled')}
    outs = {k: gzip.open(f'{a.out_prefix}-{k}.xml.gz', 'wt') for k in (1, 3)}
    for f in outs.values():
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n<population>\n')
    changed = persons = 0
    with gzip.open(a.cold, 'rb') as f:
        it = ET.iterparse(f, events=('start', 'end')); _, root = next(it)
        for ev, el in it:
            if ev != 'end' or el.tag != 'person': continue
            persons += 1
            pid = el.get('id'); plan = el.find('plan')
            sub = el.find("attributes/attribute[@name='subpopulation']")
            legs = [x for x in plan if x.tag == 'leg']; acts = [x.get('type') for x in plan if x.tag == 'activity']
            for x in legs: shares['initial'][x.get('mode')] += 1
            plans = [plan]
            if (sub is None or sub.text != 'outside') and pid in row and 0 < len(legs) <= T:
                Pi = P[row[pid], :len(legs)]
                for j in range(len(legs)): shares['predicted'].update({MODES[m]: float(Pi[j, m]) for m in range(len(MODES))})
                seen, plans = set(), []
                for _ in range(20):
                    m = tuple(sample(Pi, acts, rng))
                    if m in seen: continue
                    seen.add(m); new = ET.fromstring(ET.tostring(plan))
                    for leg, k in zip([x for x in new if x.tag == 'leg'], m): leg.set('mode', MODES[k])
                    plans.append(new)
                    if len(plans) == 3: break
                changed += 1
            else:
                for x in legs: shares['predicted'][x.get('mode')] += 1
            for x in plans[0]:
                if x.tag == 'leg': shares['sampled'][x.get('mode')] += 1
            for k, f in outs.items():
                person = ET.Element('person', el.attrib)
                if el.find('attributes') is not None: person.append(el.find('attributes'))
                for i, pl in enumerate(plans[:k]):
                    pl = ET.fromstring(ET.tostring(pl)); pl.set('selected', 'yes' if i == 0 else 'no')
                    pl.attrib.pop('score', None); person.append(pl)
                f.write(ET.tostring(person, encoding='unicode') + '\n')
            el.clear(); root.clear()
    for f in outs.values(): f.write('</population>\n'); f.close()
    summary = {'persons': persons, 'changed': changed,
               **{k: {m: v / sum(c.values()) for m, v in sorted(c.items())} for k, c in shares.items()}}
    with open(f'{a.out_prefix}-summary.json', 'w') as f: json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == '__main__':
    main()
