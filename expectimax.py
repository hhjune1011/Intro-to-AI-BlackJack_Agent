"""MAX / 정확한 카드 Chance 확률 / 말단 Monte Carlo 평가."""
from copy import deepcopy
import random
from concurrent.futures import CancelledError
from threading import Event
from game import bets, value, total, outcome, order_for


def remaining_counts(observation):
    counts = [0] + [4] * 9 + [16]
    for card in observation['public']:
        counts[value(card)] -= 1
    return tuple(counts)


def utility(capitals, player):
    other = 'B' if player == 'A' else 'A'
    return 1.0 if capitals[player] > capitals[other] else 0.5 if capitals[player] == capitals[other] else 0.0


class Expectimax:
    def __init__(self, settings, player, depth, samples, seed):
        self.settings, self.player = settings, player
        self.depth, self.samples = depth, samples
        self.rng = random.Random(seed)
        self.nodes = self.rollouts = 0
        self.cancelled = Event()
        self.chance_outcomes = []

    def evaluate(self, observation, betting=False):
        self.nodes = self.rollouts = 0
        self.chance_outcomes = []
        self.eval_seed = self.rng.randrange(2**63)
        self.obs = observation
        counts = remaining_counts(observation)
        if betting:
            actions = bets(observation['capital'][self.player], self.settings)
            scores = {amount: self.leaf(counts, bet=amount) for amount in actions}
        else:
            _, scores = self.max_node(total(observation['hands'][self.player]), counts, self.depth)
        self.nodes += 1
        selected = max(scores, key=scores.get)
        n = sum(counts)
        return dict(player=self.player, selected=selected, utilities=scores,
                    reason='MAX: 5라운드 최종 U의 근사 기댓값이 가장 큰 행동 (동률은 먼저 표시된 행동)',
                    depth=self.depth, nodes=self.nodes, samples=self.samples, rollouts=self.rollouts,
                    probabilities={str(v): c / n for v, c in enumerate(counts) if c},
                    chance_outcomes=self.chance_outcomes,
                    observation=deepcopy(observation), approximate=True,
                    model='말단/상대: 17 미만 Hit, 최소 베팅. 최종 승=1, 무=0.5, 패=0.')

    def max_node(self, score, counts, depth):
        self.nodes += 1
        if score >= 21 or depth == 0:
            return self.leaf(counts, score=score, stand=score >= 21), {}
        scores = {'STAND': self.leaf(counts, score=score, stand=True),
                  'HIT': self.chance_node(score, counts, depth)}
        return max(scores.values()), scores

    def chance_node(self, score, counts, depth):
        self.nodes += 1
        n = sum(counts)
        if not n:
            return self.leaf(counts, score=score, stand=True)
        expected = 0.0
        for card, count in enumerate(counts):
            if count:
                rest = list(counts)
                rest[card] -= 1
                child, _ = self.max_node(score + card, tuple(rest), depth - 1)
                expected += count / n * child
                if depth == self.depth:
                    self.chance_outcomes.append(dict(card=card, probability=count/n,
                                                     next_total=score+card, expected_utility=child))
        return expected

    def leaf(self, counts, score=None, stand=False, bet=None):
        self.nodes += 1
        result = 0.0
        # 후보 간 같은 난수열을 사용해 비교 분산을 줄인다.
        rng = random.Random(self.eval_seed)
        for _ in range(self.samples):
            if self.cancelled.is_set():
                raise CancelledError()
            self.rollouts += 1
            result += self.rollout(counts, rng, score, stand, bet)
        return result / self.samples

    def rollout(self, counts, rng, score, stand, bet):
        o, cfg, me = self.obs, self.settings, self.player
        capital = o['capital'].copy()
        wagers = o['bets'].copy()
        order = o['order'][:]
        scores = {p: total(o['hands'][p]) for p in ('A', 'B', 'D')}
        statuses = o['status'].copy()
        deck = [v for v, n in enumerate(counts) for _ in range(n)]
        rng.shuffle(deck)
        if bet is not None:
            capital[me] -= bet
            wagers[me] = bet
            for p in order:
                if not wagers[p] and bets(capital[p], cfg):
                    wagers[p] = bets(capital[p], cfg)[0]
                    capital[p] -= wagers[p]
            active = [p for p in order if wagers[p]]
            for _ in range(2):
                for p in active + (['D'] if active else []):
                    scores[p] += deck.pop()
            statuses = {p: 'Active' for p in ('A', 'B', 'D')}
        else:
            scores[me] = score
            statuses[me] = 'Stand' if stand else 'Active'
        self.finish_round(capital, wagers, scores, statuses, order, deck)
        for _ in range(o['round'] + 1, 6):
            order = order_for(capital, order, rng)
            wagers = {p: (bets(capital[p], cfg) or [0])[0] for p in order}
            for p in order:
                capital[p] -= wagers[p]
            deck = [v for v in range(1, 10) for _ in range(4)] + [10] * 16
            rng.shuffle(deck)
            scores = dict(A=0, B=0, D=0)
            active = [p for p in order if wagers[p]]
            for _ in range(2):
                for p in active + (['D'] if active else []):
                    scores[p] += deck.pop()
            self.finish_round(capital, wagers, scores, dict(A='Active', B='Active', D='Active'), order, deck)
        return utility(capital, me)

    @staticmethod
    def finish_round(capital, wagers, scores, statuses, order, deck):
        for p in order:
            if wagers[p] and statuses[p] == 'Active':
                while scores[p] < 17 and deck:
                    scores[p] += deck.pop()
        if any(wagers[p] and scores[p] <= 21 for p in order):
            while scores['D'] < 17 and deck:
                scores['D'] += deck.pop()
        for p in order:
            capital[p] += wagers[p] * (outcome(scores[p], scores['D']) + 1)
