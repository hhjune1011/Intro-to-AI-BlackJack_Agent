"""표준 라이브러리 unittest: python -m unittest tests -v"""
from copy import deepcopy
import random
import unittest

from agents import DealerAgent, make_agents
from expectimax import Expectimax, remaining_counts, utility
from game import Game, Settings, bets, new_deck, order_for, outcome, total, value


def new_game(**changes):
    options = dict(depth_a=1, depth_b=1, samples_a=2, samples_b=2)
    options.update(changes)
    cfg = Settings(**options)
    return Game(cfg, make_agents(cfg))


class RulesTests(unittest.TestCase):
    def test_unique_deck(self):
        self.assertEqual(len(new_deck()), 52)
        self.assertEqual(len(set(new_deck())), 52)

    def test_card_values(self):
        self.assertEqual([value(c) for c in ('♥A', '♠J', '♦Q', '♣K', '♥9')], [1, 10, 10, 10, 9])
        self.assertEqual(total(['♥A', '♠A', '♦K']), 12)

    def test_dealer(self):
        self.assertEqual(DealerAgent.decide(16), 'HIT')
        for n in (17, 18, 21, 22):
            self.assertEqual(DealerAgent.decide(n), 'STAND')

    def test_outcomes(self):
        for p, d, result in [(22, 25, -1), (19, 22, 1), (18, 18, 0), (20, 18, 1), (15, 18, -1)]:
            self.assertEqual(outcome(p, d), result)

    def test_bet_bounds(self):
        cfg = Settings()
        self.assertEqual(bets(1000, cfg), [50, 100, 150, 200])
        self.assertEqual(bets(120, cfg), [50, 100])
        self.assertEqual(bets(49, cfg), [])
        self.assertEqual(bets(50, cfg), [50])

    def test_invalid_settings(self):
        for cfg in (Settings(minimum=0), Settings(maximum=10), Settings(unit=0), Settings(depth_a=4), Settings(samples_b=0)):
            with self.assertRaises(ValueError):
                cfg.validate()

    def test_order(self):
        rng = random.Random(1)
        self.assertEqual(order_for({'A': 900, 'B': 1000}, ['A', 'B'], rng), ['B', 'A'])
        self.assertEqual(order_for({'A': 1100, 'B': 1000}, ['B', 'A'], rng), ['A', 'B'])
        self.assertEqual(order_for({'A': 1000, 'B': 1000}, ['A', 'B'], rng), ['B', 'A'])
        self.assertEqual(set(order_for({'A': 1, 'B': 1}, [], rng)), {'A', 'B'})

    def test_bet_deducted_once(self):
        game = new_game()
        game.state.update(phase='베팅', actor='A')
        for invalid in (-50, 0, 25, 250):
            with self.assertRaises(ValueError):
                game.place_bet('A', invalid)
        game.place_bet('A', 200)
        self.assertEqual(game.state['capital']['A'], 800)
        with self.assertRaises(ValueError):
            game.place_bet('A', 200)

    def test_bust_and_stand_prevent_hit(self):
        game = new_game()
        game.state.update(phase='플레이어 행동', actor='A')
        game.state['hands']['A'] = ['♥K', '♥9']
        game.state['status']['A'] = 'Active'
        game._deck = ['♠5']
        event = game.draw('A')
        self.assertEqual(event['state']['status']['A'], 'Bust')
        with self.assertRaises(ValueError):
            game.draw('A')
        game.state['status']['A'] = 'Stand'
        with self.assertRaises(ValueError):
            game.draw('A')

    def test_wrong_phase_rejected(self):
        game = new_game()
        with self.assertRaises(ValueError):
            game.place_bet('A', 50)
        with self.assertRaises(ValueError):
            game.draw('A')
        with self.assertRaises(ValueError):
            game.stand('A')

    def test_stand_transition(self):
        game = new_game()
        game.state.update(phase='플레이어 행동', actor='A')
        game.state['status']['A'] = 'Active'
        game.stand('A')
        self.assertEqual(game.state['status']['A'], 'Stand')
        with self.assertRaises(ValueError):
            game.draw('A')


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = new_game()
        cls.events = list(cls.game.events)

    def test_deal_order_and_shuffle(self):
        starts = [e for e in self.events if e['action'] == 'ORDER']
        first_cards = []
        for start in starts:
            rnd = start['state']['round']
            deals = [e for e in self.events if e['action'] == 'DEAL' and e['state']['round'] == rnd]
            self.assertEqual([e['state']['actor'] for e in deals], (start['state']['order'] + ['D']) * 2)
            self.assertEqual(start['state']['remaining'], 52)
            self.assertEqual(start['state']['public'], [])
            first_cards.append(deals[-1]['state']['public'])
        self.assertGreater(len({tuple(cards) for cards in first_cards}), 1)

    def test_exactly_five_rounds_and_records(self):
        s = self.game.state
        self.assertTrue(s['game_over'])
        self.assertEqual(s['round'], 5)
        self.assertEqual(len(s['records']), 10)
        self.assertEqual(sum(e['action'] == 'SETTLE' for e in self.events), 5)
        expected = '무승부' if s['capital']['A'] == s['capital']['B'] else ('A' if s['capital']['A'] > s['capital']['B'] else 'B') + ' 최종 승리'
        self.assertEqual(self.events[-1]['transition'], expected)

    def test_settlement_and_rewards(self):
        capital = dict(A=1000, B=1000)
        for record in self.game.state['records']:
            p = record['player']
            multiplier = {'승': 1, '패': -1, '무': 0, '불참': 0}[record['result']]
            self.assertEqual(record['reward'], multiplier * record['bet'])
            capital[p] += record['reward']
            self.assertEqual(record['capital'], capital[p])
            self.assertGreaterEqual(capital[p], 0)

    def test_all_settlement_returns(self):
        for pscore, dscore, expected in [(20, 18, 1200), (18, 20, 800), (18, 18, 1000)]:
            cap = dict(A=800, B=1000)
            Expectimax.finish_round(cap, dict(A=200, B=0), dict(A=pscore, B=0, D=dscore),
                                    dict(A='Stand', B='Stand'), ['A', 'B'], [])
            self.assertEqual(cap['A'], expected)

    def test_insufficient_capital(self):
        game = new_game(minimum=1100, maximum=1200)
        events = list(game.events)
        self.assertEqual(game.state['capital'], dict(A=1000, B=1000))
        self.assertEqual(len(game.state['records']), 10)
        self.assertTrue(all(r['result'] == '불참' for r in game.state['records']))
        self.assertFalse(any(e['action'] == 'DEAL' for e in events))

    def test_one_player_inactive(self):
        game = new_game()
        game.state['capital']['B'] = 49
        list(game.events)
        self.assertEqual(game.state['capital']['B'], 49)
        self.assertTrue(all(r['result'] == '불참' for r in game.state['records'] if r['player'] == 'B'))

    def test_seed_reproducibility(self):
        again = list(new_game().events)
        self.assertEqual(self.events, again)

    def test_public_observation_isolation(self):
        obs = self.game.observation()
        self.assertNotIn('_deck', obs)
        self.assertNotIn('rng', obs)
        obs['capital']['A'] = -1
        self.assertNotEqual(self.game.state['capital']['A'], -1)
        self.assertTrue(all('_deck' not in e['state'] for e in self.events))

    def test_transition_log_matches_state(self):
        for event in self.events:
            s, before = event['state'], event['before']
            self.assertEqual(s['remaining'], 52-len(s['public']))
            if event['action'] in ('DEAL', 'HIT') and len(s['public']) > len(before['public']):
                who = s['actor']
                self.assertEqual(len(s['public']), len(before['public']) + 1)
                self.assertEqual(s['hands'][who][:-1], before['hands'][who])
                self.assertIn(s['public'][-1], event['transition'])

    def test_turns_finish_before_dealer(self):
        for rnd in range(1, 6):
            events = [e for e in self.events if e['state']['round'] == rnd]
            starts = [e['state']['actor'] for e in events if e['action'] == 'TURN_START']
            self.assertEqual(starts, events[0]['state']['order'] + ['D'])
            for event in events:
                if event['state']['phase'] == '딜러 행동':
                    self.assertTrue(all(event['state']['status'][p] in ('Stand', 'Bust', '참가 불가') for p in ('A', 'B')))

    def test_repeated_hits_are_not_interleaved(self):
        class ScriptedAgent:
            def decide(self, obs, betting=False):
                return {'selected': 50 if betting else 'HIT' if len(obs['hands'][obs['actor']]) < 4 else 'STAND'}

        class FixedDeck:
            def sample(self, values, count):
                return ['A', 'B']

            def shuffle(self, deck):
                front = ['♥2', '♥3', '♥4', '♠2', '♠3', '♠4', '♦2', '♦3', '♦4', '♣2', '♥9']
                deck[:] = list(reversed(front + [c for c in deck if c not in front]))

        game = Game(Settings(), {'A': ScriptedAgent(), 'B': ScriptedAgent()})
        game.rng = FixedDeck()
        hits, finished = [], []
        for event in game.events:
            if event['action'] == 'HIT' and len(event['state']['public']) > len(event['before']['public']):
                hits.append(event['state']['actor'])
            if event['action'] == 'TURN_END':
                finished.append(event['state']['actor'])
            if event['state']['phase'] == '딜러 행동':
                self.assertEqual(finished, ['A', 'B'])
            if event['action'] == 'SETTLE':
                break
        self.assertEqual(hits, ['A', 'A', 'B', 'B', 'D'])

    def test_both_agents_evaluate_bets_and_cards(self):
        reports = [e['analysis'] for e in self.events if e['action'] == 'EXPECTIMAX']
        for p in ('A', 'B'):
            own = [r for r in reports if r['player'] == p]
            self.assertTrue(any('HIT' in r['utilities'] for r in own))
            self.assertTrue(any(isinstance(r['selected'], int) for r in own))
        for report in reports:
            self.assertEqual(report['utilities'][report['selected']], max(report['utilities'].values()))
            self.assertGreater(report['nodes'], 1)
            self.assertGreater(report['rollouts'], 0)
            self.assertTrue(all(0 <= u <= 1 for u in report['utilities'].values()))


class AlgorithmTests(unittest.TestCase):
    def test_card_probabilities(self):
        obs = new_game().observation()
        self.assertEqual(remaining_counts(obs)[10], 16)
        obs['public'] = ['♥K', '♠Q', '♦A']
        counts = remaining_counts(obs)
        self.assertEqual(counts[10], 14)
        self.assertEqual(counts[1], 3)
        self.assertEqual(sum(counts), 49)

    def test_exact_chance_weighting_and_max(self):
        class KnownLeaf(Expectimax):
            def leaf(self, counts, score=None, stand=False, bet=None):
                return score / 30
        search = KnownLeaf(Settings(), 'A', 1, 1, 1)
        counts = (0, 1, 3) + (0,) * 8
        best, scores = search.max_node(10, counts, 1)
        self.assertAlmostEqual(scores['HIT'], (0.25*11 + 0.75*12)/30)
        self.assertEqual(scores['STAND'], 10/30)
        self.assertEqual(best, scores['HIT'])

    def test_final_utility_not_chip_maximum(self):
        self.assertEqual(utility(dict(A=200, B=100), 'A'), 1)
        self.assertEqual(utility(dict(A=10000, B=10001), 'A'), 0)
        self.assertEqual(utility(dict(A=500, B=500), 'B'), 0.5)

    def test_hidden_deck_does_not_change_decision(self):
        first, second = new_game(), new_game()
        next(first.events)
        next(second.events)
        second._deck.reverse()
        self.assertEqual(first.observation(), second.observation())
        who = first.state['order'][0]
        self.assertEqual(first.agents[who].decide(first.observation(), True),
                         second.agents[who].decide(second.observation(), True))

    def test_depth_and_samples_applied(self):
        game = new_game()
        next(game.events)
        o = game.observation()
        o['round'] = 5
        o['hands'] = dict(A=['♥5', '♠6'], B=['♦10', '♣7'], D=['♥10', '♠7'])
        o['public'] = sum(o['hands'].values(), [])
        o['bets'] = dict(A=50, B=50)
        o['capital'] = dict(A=950, B=950)
        shallow = Expectimax(Settings(), 'A', 1, 2, 1).evaluate(deepcopy(o))
        deep = Expectimax(Settings(), 'A', 2, 2, 1).evaluate(deepcopy(o))
        self.assertGreater(deep['nodes'], shallow['nodes'])
        self.assertEqual(deep['samples'], 2)
        self.assertAlmostEqual(sum(c['probability'] for c in deep['chance_outcomes']), 1)
        self.assertAlmostEqual(sum(c['probability'] * c['expected_utility'] for c in deep['chance_outcomes']),
                               deep['utilities']['HIT'])


if __name__ == '__main__':
    unittest.main()
