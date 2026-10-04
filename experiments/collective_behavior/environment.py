"""Small simultaneous congestion game. Ground truth never goes to policies."""
from dataclasses import dataclass, asdict
import math

SCENARIOS = ('none', 'capacity', 'background', 'both')

@dataclass(frozen=True)
class Config:
    population: int = 24
    days: int = 30
    onset: int = 11
    duration: int = 10
    scenario: str = 'none'
    strength: int = 1

    def __post_init__(self):
        if self.scenario not in SCENARIOS or self.strength not in (1, 2):
            raise ValueError('Unknown scenario/strength')
        if self.population < 2 or self.days < 1 or self.duration < 1 or self.onset < 1:
            raise ValueError('Invalid horizon/population')


def parameters(config, day):
    active = config.onset <= day < config.onset + config.duration
    capacity = (2/3 if config.strength == 1 else .5) if active and config.scenario in ('capacity', 'both') else 1.
    background = (8 if config.strength == 1 else 16) if active and config.scenario in ('background', 'both') else 0
    return capacity, background


def costs(n_a, population=24, capacity=1., background=0.):
    return [10 + .5 * (n_a + background) / capacity, 16 + .25 * (population - n_a)]


def equilibrium_probability(population, capacity, background):
    # Mixed population target; this is an aggregate approximation, not an oracle for individual play.
    n_a = (6 + .25 * population - .5 * background / capacity) / (.5 / capacity + .25)
    return min(1., max(0., n_a / population))


class Environment:
    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self, seed=0):
        self.day = 1
        self.history = []
        return self

    def step(self, actions):
        if self.day > self.config.days:
            raise ValueError('Episode ended')
        if set(actions) != set(range(self.config.population)) or any(type(x) is not int or x not in (0, 1) for x in actions.values()):
            raise ValueError('Exactly one valid action per agent required')
        capacity, background = parameters(self.config, self.day)
        n_a = sum(x == 0 for x in actions.values())
        travel = costs(n_a, self.config.population, capacity, background)
        row = {'day': self.day, 'actions': [actions[i] for i in range(self.config.population)],
               'costs': travel, 'endogenous_flow': [n_a, self.config.population-n_a],
               'total_flow': [n_a+background, self.config.population-n_a],
               'truth': {'capacity': capacity, 'background': background,
                         'cause': self.config.scenario if capacity != 1 or background else 'none'}}
        self.history.append(row)
        self.day += 1
        return row
