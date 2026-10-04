"""All decisions are functions of public observations and private RNG only."""
import math
import random
from environment import equilibrium_probability

BASELINES = ('random', 'smooth', 'estimate')
CAUSES = ('none', 'capacity', 'background', 'both', 'insufficient')


def estimate(obs):
    """Identifiability-aware arithmetic baseline using latest observed A cost/total flow.

    Assumes only A can change; persistence forecast, no access to the event schedule.
    Estimates can be stale after unobserved changes. This is deliberately a strong baseline.
    """
    capacity, background = 1., 0.
    identified = False
    for row in obs['history']:
        flows = row.get('total_route_flows')
        if flows is not None:
            background = max(0., sum(flows)-obs['population'])
            if row['route'] == 0 and flows[0] > 0 and row['travel_time'] > 10:
                capacity = .5 * flows[0] / (row['travel_time']-10)
                identified = True
    if not identified:
        return capacity, background, 'insufficient'
    changed_c = abs(capacity-1) > .02
    cause = 'both' if changed_c and background > .01 else 'capacity' if changed_c else 'background' if background > .01 else 'none'
    return capacity, background, cause


class Policy:
    def __init__(self, name, seed):
        if name not in BASELINES:
            raise ValueError(name)
        self.name = name
        self.rng = random.Random(seed)

    def decide(self, obs):
        means = [18., 18.]
        for row in obs['history']:
            r = row['route']
            means[r] = .65 * means[r] + .35 * row['travel_time']
        cause = 'insufficient'
        if self.name == 'random':
            p = .5
        elif self.name == 'smooth' or obs['information'] == 'time':
            p = 1 / (1 + math.exp(max(-50, min(50, (means[0]-means[1])/2))))
        else:
            capacity, background, cause = estimate(obs)
            p = equilibrium_probability(obs['population'], capacity, background)
            others = obs['population'] - 1
            means = [10 + .5 * (others*p + 1 + background) / capacity,
                     16 + .25 * (others*(1-p) + 1)]
        return {'route': 0 if self.rng.random() < p else 1,
                'cause': cause, 'confidence': 0. if cause == 'insufficient' else 1.,
                'predicted_costs': means, 'valid': True}

    def update(self, feedback):
        # Stateless replay reconstruction avoids hidden differences in policy memory.
        pass


def fallback(obs, seed):
    return obs['history'][-1]['route'] if obs['history'] else random.Random(seed).randrange(2)


def validate_choice(value):
    if not isinstance(value, dict) or type(value.get('route')) is not int or value['route'] not in (0, 1):
        raise ValueError('Invalid route')
    if value.get('cause') not in CAUSES:
        raise ValueError('Invalid cause')
    c = value.get('confidence')
    predictions = value.get('predicted_costs')
    if type(c) not in (int, float) or not math.isfinite(c) or not 0 <= c <= 1:
        raise ValueError('Invalid confidence')
    if not isinstance(predictions, list) or len(predictions) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1000 for x in predictions):
        raise ValueError('Invalid predictions')
    return value
