"""공개 상태와 숨겨진 덱을 분리한 이벤트 기반 블랙잭 엔진."""
from copy import deepcopy
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Settings:
    minimum: int = 50
    maximum: int = 200
    unit: int = 50
    speed: int = 500
    depth_a: int = 2
    depth_b: int = 2
    samples_a: int = 32
    samples_b: int = 32
    seed: int = 42

    def validate(self):
        if not 1 <= self.minimum <= self.maximum:
            raise ValueError('베팅 한도는 1 ≤ 하한 ≤ 상한이어야 합니다.')
        if self.unit < 1 or self.speed < 20:
            raise ValueError('베팅 단위는 1 이상, 속도는 20ms 이상이어야 합니다.')
        if len(range(self.minimum, self.maximum + 1, self.unit)) > 100:
            raise ValueError('베팅 후보는 100개 이하로 설정하세요.')
        for depth, samples in ((self.depth_a, self.samples_a), (self.depth_b, self.samples_b)):
            if not 1 <= depth <= 3 or not 1 <= samples <= 512:
                raise ValueError('깊이는 1~3, 샘플 수는 1~512로 설정하세요.')


def new_deck():
    return [suit + rank for suit in '♥♠♦♣' for rank in
            ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')]


def value(card):
    rank = card[1:]
    return 1 if rank == 'A' else 10 if rank in ('J', 'Q', 'K') else int(rank)


def total(cards):
    return sum(map(value, cards))


def bets(capital, settings):
    return list(range(settings.minimum, min(capital, settings.maximum) + 1, settings.unit))


def order_for(capitals, previous, rng):
    if not previous:
        return rng.sample(['A', 'B'], 2)
    if capitals['A'] == capitals['B']:
        return previous[::-1]
    return sorted(capitals, key=capitals.get, reverse=True)


def outcome(player, dealer):
    if player > 21:
        return -1
    if dealer > 21:
        return 1
    return (player > dealer) - (player < dealer)


def blank_state():
    return dict(round=0, phase='준비', actor='', order=[], capital={'A': 1000, 'B': 1000},
                bets={'A': 0, 'B': 0}, hands={'A': [], 'B': [], 'D': []},
                status={'A': '대기', 'B': '대기', 'D': '대기'}, public=[], remaining=52,
                hits={'A': 0, 'B': 0}, round_over=False, game_over=False,
                records=[], reward={'A': 0, 'B': 0}, results={})


class Game:
    def __init__(self, settings, agents):
        from agents import DealerAgent
        settings.validate()
        self.settings, self.agents = settings, agents
        self.rng = random.Random(settings.seed)
        self.dealer = DealerAgent()
        self.state = blank_state()
        self._deck = []
        self.events = self._play()

    def observation(self):
        observation = deepcopy(self.state)
        observation['totals'] = {p: total(cards) for p, cards in self.state['hands'].items()}
        return observation

    def cancel(self):
        for agent in self.agents.values():
            agent.search.cancelled.set()

    def event(self, action, transition, before=None, analysis=None):
        return dict(before=before if before is not None else self.observation(),
                    state=self.observation(), action=action, transition=transition,
                    analysis=analysis)

    def draw(self, who, initial=False):
        s = self.state
        expected_phase = '딜러 행동' if who == 'D' else '플레이어 행동'
        if not initial and (s['phase'] != expected_phase or s['actor'] != who):
            raise ValueError('현재 Hit 차례가 아닙니다.')
        if not initial and s['status'][who] != 'Active':
            raise ValueError('Active 상태에서만 Hit할 수 있습니다.')
        before = self.observation()
        old = total(s['hands'][who])
        card = self._deck.pop()
        s['hands'][who].append(card)
        s['public'].append(card)
        s['remaining'] = len(self._deck)
        if not initial and who != 'D':
            s['hits'][who] += 1
        score = total(s['hands'][who])
        s['status'][who] = 'Bust' if score > 21 else 'Stand' if score == 21 else 'Active'
        return self.event('DEAL' if initial else 'HIT',
                          f'{who}: {card} 획득 / {old} → {score} / {s["status"][who]}', before)

    def place_bet(self, who, amount):
        if self.state['phase'] != '베팅' or self.state['actor'] != who:
            raise ValueError('현재 베팅 차례가 아닙니다.')
        if self.state['bets'][who] or amount not in bets(self.state['capital'][who], self.settings):
            raise ValueError('유효하지 않거나 중복된 베팅입니다.')
        self.state['capital'][who] -= amount
        self.state['bets'][who] = amount

    def stand(self, who):
        if (self.state['phase'] != '플레이어 행동' or self.state['actor'] != who
                or self.state['status'][who] != 'Active'):
            raise ValueError('현재 Stand를 선택할 수 없습니다.')
        self.state['status'][who] = 'Stand'

    def _decision(self, who, betting=False):
        report = self.agents[who].decide(self.observation(), betting)
        yield self.event('EXPECTIMAX', f'{who}: 행동별 근사 기대 효용 평가', analysis=report)
        yield self.event(str(report['selected']), f'{who}: 최대 기대 효용 행동 선택', analysis=report)
        before = self.observation()
        action = report['selected']
        if betting:
            self.place_bet(who, action)
            yield self.event(f'BET({action})', f'{who}: 베팅금 {action} 차감', before, report)
        elif action == 'HIT':
            event = self.draw(who)
            event['analysis'] = report
            yield event
        else:
            self.stand(who)
            yield self.event('STAND', f'{who}: 턴 종료', before, report)

    def _play(self):
        s = self.state
        for rnd in range(1, 6):
            before = self.observation()
            s.update(round=rnd, phase='라운드 시작', round_over=False,
                     bets={'A': 0, 'B': 0}, hands={'A': [], 'B': [], 'D': []},
                     hits={'A': 0, 'B': 0}, public=[], remaining=52, results={},
                     reward={'A': 0, 'B': 0})
            self._deck = new_deck()
            self.rng.shuffle(self._deck)
            s['order'] = order_for(s['capital'], s['order'], self.rng)
            active = [p for p in s['order'] if bets(s['capital'][p], self.settings)]
            s['status'] = {p: 'Active' if p in active or p == 'D' else '참가 불가' for p in ('A', 'B', 'D')}
            s['actor'] = ''
            yield self.event('ORDER', f'순서: {" → ".join(s["order"])} / 자본 차이 {s["capital"]["A"] - s["capital"]["B"]}', before)
            s['phase'] = '베팅'
            for who in active:
                s['actor'] = who
                yield from self._decision(who, True)
            s['phase'] = '최초 배분'
            if active:
                for _ in range(2):
                    for who in active + ['D']:
                        s['actor'] = who
                        yield self.draw(who, initial=True)
            s['phase'] = '플레이어 행동'
            for who in active:
                s['actor'] = who
                yield self.event('TURN_START', f'{who} 턴 시작: Stand 또는 Bust까지 같은 플레이어가 계속 판단합니다.')
                while s['status'][who] == 'Active':
                    yield from self._decision(who)
                yield self.event('TURN_END', f'{who} 턴 종료: {s["status"][who]} / 합계 {total(s["hands"][who])}')
            if any(s['status'][p] not in ('Stand', 'Bust') for p in active):
                raise RuntimeError('모든 참가 플레이어가 턴을 종료해야 딜러가 행동할 수 있습니다.')
            s['phase'], s['actor'] = '딜러 행동', 'D'
            yield self.event('TURN_START', '모든 플레이어의 턴 종료 → 딜러 턴 시작')
            if any(s['status'][p] != 'Bust' for p in active):
                while self.dealer.decide(total(s['hands']['D'])) == 'HIT':
                    yield self.event('HIT', '딜러: 17 미만이므로 Hit')
                    yield self.draw('D')
                before = self.observation()
                s['status']['D'] = 'Bust' if total(s['hands']['D']) > 21 else 'Stand'
                yield self.event('BUST' if s['status']['D'] == 'Bust' else 'STAND', f'딜러: {s["status"]["D"]}', before)
            s['phase'], s['actor'] = '승패 판정', ''
            before = self.observation()
            s['results'] = {p: outcome(total(s['hands'][p]), total(s['hands']['D'])) for p in active}
            yield self.event('RESULT', str(s['results']), before)
            before = self.observation()
            s['phase'] = '자본 정산'
            for who in ('A', 'B'):
                result = s['results'].get(who, 0)
                bet = s['bets'][who]
                s['capital'][who] += bet * (result + 1)
                s['reward'][who] = bet * result
                s['records'].append(dict(round=rnd, player=who, bet=bet, hits=s['hits'][who],
                                         result={-1: '패', 0: '무', 1: '승'}[result] if who in active else '불참',
                                         capital=s['capital'][who], reward=bet * result))
            s['round_over'] = True
            yield self.event('SETTLE', f'라운드 Reward: {s["reward"]}', before)
        before = self.observation()
        s.update(phase='게임 종료', game_over=True, actor='')
        a, b = s['capital']['A'], s['capital']['B']
        yield self.event('FINAL', '무승부' if a == b else f'{"A" if a > b else "B"} 최종 승리', before)
