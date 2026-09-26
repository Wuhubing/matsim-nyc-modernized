"""Measure actual cordon car link entries and completed car-leg travel times."""
import collections
import csv
import json
import re
import sys
from pathlib import Path
import zstandard

source, cordon_file, output = map(Path, sys.argv[1:4])
with cordon_file.open() as f:
    cordon = {row['id'].encode(): row['direction'] for row in csv.DictReader(f)}
pattern = re.compile(rb'(\w+)="([^"]*)"')
drivers, departing = {}, {}
crossings = collections.Counter()
crossings_by_hour = collections.defaultdict(collections.Counter)
payers = set()
money_counts = collections.Counter()
money_amounts = collections.Counter()
car_daily_payments = collections.Counter()
private_payers = set()
private_payments = 0
toll_amount_counts = collections.Counter()
duration_sum = completed = 0
with zstandard.open(source, 'rb') as stream:
    import io
    for line in io.BufferedReader(stream):
        if b'type="entered link"' in line:
            link = line.split(b'link="', 1)[1].split(b'"', 1)[0]
            if link not in cordon:
                continue
            e = dict(pattern.findall(line))
            person = drivers.get(e[b'vehicle'])
            if person is not None:
                crossings[cordon[link]] += 1
                crossings_by_hour[str(int(float(e[b'time'])//3600))][cordon[link]] += 1
                payers.add(person)
        elif b'type="personMoney"' in line:
            e = dict(pattern.findall(line))
            if e.get(b'purpose') == b'toll':
                reference = e.get(b'reference', b'unspecified').decode()
                amount = -float(e[b'amount'])
                money_counts[reference] += 1
                money_amounts[reference] += amount
                toll_amount_counts[f'{reference}: {amount:.2f}'] += 1
                if amount>0 and (e.get(b'transactionPartner') != b'NYC2025' or reference.startswith('car-entry')):
                    private_payers.add(e[b'person'])
                    private_payments += 1
                if reference.startswith('car-entry'):
                    car_daily_payments[(e[b'person'], int(float(e[b'time']) // 86400))] += 1
        elif b'type="vehicle enters traffic"' in line:
            e = dict(pattern.findall(line))
            if e.get(b'networkMode') == b'car' and not e[b'person'].startswith(b'pt_'):
                drivers[e[b'vehicle']] = e[b'person']
        elif b'type="vehicle leaves traffic"' in line:
            e = dict(pattern.findall(line))
            drivers.pop(e[b'vehicle'], None)
        elif b'legMode="car"' in line and (b'type="departure"' in line or b'type="arrival"' in line):
            e = dict(pattern.findall(line))
            person = e[b'person']
            if person.startswith(b'pt_'):
                continue
            if e[b'type'] == b'departure':
                departing[person] = float(e[b'time'])
            else:
                start = departing.pop(person, None)
                if start is not None:
                    completed += 1
                    duration_sum += float(e[b'time']) - start
result = dict(source=str(source), cordon_car_link_entries=dict(crossings),
              cordon_car_crossings_by_hour={k:dict(v) for k,v in sorted(crossings_by_hour.items(),key=lambda kv:int(kv[0]))},
              unique_cordon_drivers=len(payers), completed_car_legs=completed,
              mean_completed_car_leg_minutes=duration_sum / completed / 60 if completed else None,
              unfinished_car_legs=len(departing),
              toll_event_counts_by_reference=dict(money_counts),
              toll_revenue_by_reference={k:round(v,2) for k,v in money_amounts.items()},
              max_private_car_payments_per_person_day=max(car_daily_payments.values(),default=0),
              unique_private_car_payers=len(private_payers),
              private_car_payment_events=private_payments,
              toll_amount_counts=dict(toll_amount_counts),
              definition='Cordon crossings count entered-link events on reconstructed directed links. Travel times cover completed car legs only, excluding transit drivers; not a fixed-trip congestion index.')
output.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
