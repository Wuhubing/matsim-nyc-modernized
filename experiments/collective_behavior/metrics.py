import math
import statistics as S
from environment import costs, parameters


def summarize(rows, config):
    post = [r for r in rows if r['day'] >= config.onset]
    person = [sum(r['costs'][r['actions'][i]] for r in post) for i in range(config.population)]
    switches = [sum(a != b for a, b in zip(p['actions'], r['actions'])) / config.population for p, r in zip(rows, rows[1:]) if r['day'] >= config.onset]
    shares = [r['endogenous_flow'][0]/config.population for r in post]
    # System-optimal allocation is a descriptive lower bound, not an attainable policy baseline.
    lower_bound = sum(min(k*costs(k, config.population, *parameters(config, r['day']))[0] +
                          (config.population-k)*costs(k, config.population, *parameters(config, r['day']))[1]
                          for k in range(config.population+1)) / config.population for r in post)
    recovery = None
    for j in range(len(post)-2):
        if post[j]['day'] < config.onset+config.duration:
            continue
        if all(abs(post[t]['endogenous_flow'][0]/config.population - 2/3) <= .125 for t in range(j,j+3)):
            recovery = post[j]['day']-(config.onset+config.duration)
            break
    return {'post_mean_cost': S.mean(person), 'post_p90_person_cost': sorted(person)[math.ceil(.9*len(person))-1],
            'switch_fraction': S.mean(switches) if switches else 0.,
            'flow_volatility': S.pstdev(shares), 'mean_abs_flow_change': S.mean(abs(b-a) for a,b in zip(shares,shares[1:])) if len(shares)>1 else 0.,
            'system_lower_bound': lower_bound, 'excess_cost': S.mean(person)-lower_bound,
            'recovery_days': recovery, 'complete': len(rows)==config.days}


def interval(values):
    """Descriptive run-level mean and normal-approximation interval; not confirmatory."""
    n=len(values); mean=S.mean(values)
    radius=1.96*S.stdev(values)/math.sqrt(n) if n>1 else 0
    return {'n':n,'mean':mean,'low':mean-radius,'high':mean+radius}
