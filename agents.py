"""두 플레이어는 독립 난수열과 탐색 설정을 사용한다."""
from expectimax import Expectimax


class PlayerAgent:
    def __init__(self, settings, name):
        is_a = name == 'A'
        self.search = Expectimax(settings, name,
                                 settings.depth_a if is_a else settings.depth_b,
                                 settings.samples_a if is_a else settings.samples_b,
                                 settings.seed + (10001 if is_a else 20002))

    def decide(self, observation, betting=False):
        return self.search.evaluate(observation, betting)


class DealerAgent:
    @staticmethod
    def decide(score):
        return 'HIT' if score < 17 else 'STAND'


def make_agents(settings):
    return {name: PlayerAgent(settings, name) for name in ('A', 'B')}
