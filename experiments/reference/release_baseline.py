#!/usr/bin/env python3
"""Validate the finished batch and bind permission to run 100 iterations to this exact snapshot."""
import argparse,hashlib,json,math
from pathlib import Path
from check_validation import check

def release(snapshot,output):
    marker=output/'validation/release-100.json'
    # Invalidate a previous success before checking changed/incomplete evidence.
    if marker.exists():marker.unlink()
    report=check(output/'validation')
    estimate=report['projected_100_iteration_hours_with_30pct_margin']
    if estimate is None or not math.isfinite(estimate) or estimate>8:
        raise ValueError(f'100-iteration estimate {estimate} hours exceeds/does not establish the 8-hour limit')
    expected=json.loads((snapshot/'snapshot.json').read_text())
    for run in report['runs'].values():
        meta=json.loads((Path(run)/'run.json').read_text())
        if meta.get('provenance')!=expected:raise ValueError('Validation results were produced by another snapshot')
    data={'passed':True,'snapshot_sha256':hashlib.sha256((snapshot/'snapshot.json').read_bytes()).hexdigest(),
          'scenario':'baseline','iterations':100,'seeds':[4711,4712,4713],
          'projected_hours_with_30pct_margin':estimate,'validation':report}
    marker.write_text(json.dumps(data,indent=2)+'\n')
    print('PASS: validation complete; releasing 3 baseline seeds x 100 iterations.',flush=True)
    return data

def assert_release(snapshot,output):
    data=json.loads((output/'validation/release-100.json').read_text())
    digest=hashlib.sha256((snapshot/'snapshot.json').read_bytes()).hexdigest()
    if data.get('passed') is not True or data.get('snapshot_sha256')!=digest or data.get('scenario')!='baseline' or data.get('iterations')!=100 or data.get('seeds')!=[4711,4712,4713]:
        raise ValueError('Missing/invalid release for this baseline snapshot')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('snapshot',type=Path);p.add_argument('output',type=Path);p.add_argument('--assert-only',action='store_true');a=p.parse_args()
    (assert_release if a.assert_only else release)(a.snapshot.resolve(),a.output.resolve())
