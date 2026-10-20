#!/usr/bin/env python3
"""Synthetic check for plan_change.py with hand-computable answers.

Six persons, 0-2 related and 3-5 unrelated. Baselines (W0, X1, RQ1) never change: every person keeps choice 'a' and
2 car legs. In each policy run, person 0 pays a toll at iteration 0, switches choice and drops to 0 car legs from
iteration 5; person 3 (unrelated, not charged) switches and drops to 1 car leg from iteration 50.
Expected, both policies: excess switch share at k=10 is 1/3 for related and 0 for unrelated; at k=99 1/3 for both;
car-leg difference in the window -3, of which related 2/3, unrelated 1/3, charged 2/3; X1 never switches."""
import csv, gzip, json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEAD = ['person_id', 'subpopulation', 'charging_cohort', 'score', 'score_delta', 'plans_in_memory', 'choice_sha256',
        'plan_sha256', 'choice_changed', 'plan_changed', 'realized_choice_hash64', 'outcome_hash64', 'departures',
        'completed', 'unfinished', 'stuck', 'completed_travel_seconds', 'completed_car_legs', 'completed_car_seconds',
        'wait_segments', 'waiting_at_cutoff', 'censored_wait_seconds', 'toll_revenue', 'private_car_entry_crossings']
A, B = 'a' * 64, 'b' * 64


def write_run(d, n_it, policy, reverse=False):
    r = d/'simulation'/'research'; r.mkdir(parents=True)
    for it in range(n_it):
        rows = []
        for p in range(6):
            ch, car, toll = A, 2, 0.0
            if policy and p == 0:
                toll = 9.18 if it == 0 else 0.0
                if it >= 5:
                    ch, car = B, 0
            if policy and p == 3 and it >= 50:
                ch, car = B, 1
            row = dict.fromkeys(HEAD, '')
            row.update(person_id=str(p), subpopulation='man', charging_cohort='related' if p < 3 else 'unrelated',
                       choice_sha256=ch, completed_car_legs=str(car), toll_revenue=str(toll),
                       private_car_entry_crossings=str(car if p < 3 else 0))
            rows.append([row[h] for h in HEAD])
        if reverse:
            rows = rows[::-1]
        with gzip.open(r/f'persons-{it}.csv.gz', 'wt', newline='') as f:
            w = csv.writer(f); w.writerow(HEAD); w.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t); s = '4711'
        write_run(root/'policy'/f'warm-baseline-s{s}-100it', 100, False)
        write_run(root/'policy'/f'x1-baseline-s{s}-from99-50it', 50, False)
        write_run(root/'rq1'/f'baseline-s{s}-100it-rq1', 100, False, reverse=True)   # different person order
        for p in ('schema1', 'schema2'):
            write_run(root/'policy'/f'warm-{p}-s{s}-100it', 100, True)
            write_run(root/'policy'/f'{p}-s{s}-100it', 100, True)
        out = root/'o.json'
        subprocess.run([sys.executable, str(HERE/'plan_change.py'), '--root', str(root), '--out', str(out),
                        '--seeds', s, '--jobs', '2'], check=True, stdout=subprocess.DEVNULL)
        o = json.loads(out.read_text())['seeds'][s]
        assert o['n_persons'] == 6
        assert all(v == 1.0 for v in o['start_identical'].values()), o['start_identical']
        for p in ('schema1', 'schema2'):
            q = o['policies'][p]
            assert q['group_size']['charged'] == 1 and q['group_size']['related & charged'] == 1
            sw = q['switch']
            assert abs(sw['related']['10']['excess'] - 1/3) < 1e-9 and sw['unrelated']['10']['excess'] == 0
            assert abs(sw['related']['99']['excess'] - 1/3) < 1e-9 and abs(sw['unrelated']['99']['excess'] - 1/3) < 1e-9
            assert sw['related']['1']['excess'] == 0
            assert all(v == 0 for v in sw['all']['X1'].values())
            for key in ('effect_warm', 'effect_cold'):
                e = q[key]
                assert e['all']['diff'] == -3
                assert abs(e['related']['share_of_diff'] - 2/3) < 1e-9
                assert abs(e['unrelated']['share_of_diff'] - 1/3) < 1e-9
                assert abs(e['charged']['share_of_diff'] - 2/3) < 1e-9
                assert abs(e['charged']['share_of_persons'] - 1/6) < 1e-9
            assert q['cordon_warm']['all']['diff'] == -2
            assert q['effect_warm_path']['10']['related']['diff'] == -2
            assert q['effect_warm_path']['3']['all']['diff'] == 0
    print('plan_change.py synthetic check passed')


if __name__ == '__main__':
    main()
