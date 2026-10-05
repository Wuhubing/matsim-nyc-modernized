"""Common error metrics so noise floor, persistence (PSim-style) and learned predictors are judged identically."""
import math


def link_errors(truth, pred_volume=None, pred_time=None):
    """truth/pred states: (link, hour) -> (entries, summed seconds). pred_volume: (link, hour) -> entries,
    pred_time: (link, hour) -> mean seconds. Weighted by true entries."""
    total = sum(v[0] for v in truth.values()); out = {}
    if pred_volume is not None:
        keys = truth.keys() | pred_volume.keys()
        abs_err = sum(abs(truth.get(k, (0, 0))[0] - pred_volume.get(k, 0)) for k in keys)
        out['volume_wape'] = abs_err / total
        out['volume_entries_within_10pct'] = sum(v[0] for k, v in truth.items()
                                                 if abs(v[0] - pred_volume.get(k, 0)) <= .1 * max(v[0], 1)) / total
    if pred_time is not None:
        num = within = covered = 0.0
        for k, v in truth.items():
            n = v[0]
            if not n or k not in pred_time:
                continue
            mean = v[1] / n; err = abs(pred_time[k] - mean) / max(mean, 1.0)
            num += n * err; covered += n; within += n * (err <= .1)
        out['time_weighted_ape'] = num / covered if covered else None
        out['time_entries_within_10pct'] = within / covered if covered else None
        out['time_coverage'] = covered / total
    return out


def mean_time(state):
    return {k: v[1] / v[0] for k, v in state.items() if v[0]}


def agent_errors(truth_legs, pred_legs):
    """Per person total network-leg seconds; persons present in both with the same leg count."""
    diffs = []
    for p, legs in truth_legs.items():
        q = pred_legs.get(p)
        if q is not None and len(q) == len(legs):
            diffs.append(abs(sum(q) - sum(legs)))
    diffs.sort(); n = len(diffs)
    if not n:
        return {'persons': 0}
    return {'persons': n, 'mae_seconds': sum(diffs) / n, 'median_seconds': diffs[n // 2], 'p90_seconds': diffs[int(.9 * n)],
            'within_60s': sum(d <= 60 for d in diffs) / n, 'within_300s': sum(d <= 300 for d in diffs) / n}


def fmt(d):
    return ', '.join(f'{k}={v:.3f}' if isinstance(v, float) else f'{k}={v}' for k, v in d.items())
