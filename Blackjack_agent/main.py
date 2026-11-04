"""python main.py: HTML UI / --tk: Tkinter / --headless: 콘솔 실행."""
import argparse
import json
from agents import make_agents
from game import Game, Settings


def main():
    parser = argparse.ArgumentParser(description='Multi-Agent Blackjack · Expectimax')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--depth', type=int, default=2)
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--tk', action='store_true', help='이전 Tkinter 화면 실행')
    parser.add_argument('--port', type=int, default=0, help='HTML UI 로컬 서버 포트 (기본: 자동 할당)')
    parser.add_argument('--no-browser', action='store_true', help='브라우저를 자동으로 열지 않음')
    args = parser.parse_args()
    if args.headless:
        cfg = Settings(seed=args.seed, depth_a=args.depth, depth_b=args.depth,
                       samples_a=args.samples, samples_b=args.samples)
        game = Game(cfg, make_agents(cfg))
        for event in game.events:
            if event['action'] in ('SETTLE', 'FINAL'):
                print(json.dumps({'round': event['state']['round'], 'event': event['transition'],
                                  'capital': event['state']['capital']}, ensure_ascii=False))
    elif args.tk:
        from gui import launch
        launch()
    else:
        from web_ui import launch
        launch(port=args.port, open_browser=not args.no_browser)


if __name__ == '__main__':
    main()
