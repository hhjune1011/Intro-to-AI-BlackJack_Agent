"""실제 Tk 위젯/이벤트 루프 검사. python gui_smoke.py (디스플레이 필요)."""
import time
import tkinter as tk
from copy import deepcopy
from gui import App


def wait(root, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError('GUI 이벤트 대기 시간 초과')
        root.update()
        time.sleep(0.005)
    root.update()


def main():
    root = tk.Tk()
    app = App(root)
    try:
        for field in ('depth_a', 'depth_b', 'samples_a', 'samples_b'):
            app.inputs[field].set('1')
        app.inputs['speed'].set('20')
        app.start_button.invoke()
        wait(root, lambda: len(app.history) == 1)
        root.focus_force()
        root.update()
        root.event_generate('<Right>')
        wait(root, lambda: len(app.history) == 2)
        state = deepcopy(app.game.state)
        root.event_generate('<Left>')
        root.update()
        assert app.cursor == 0 and app.game.state == state
        root.event_generate('<Right>')
        root.update()
        assert app.cursor == 1 and app.game.state == state
        root.event_generate('<Up>')
        wait(root, lambda: len(app.history) >= 5)
        root.event_generate('<Down>')
        root.update()
        assert not app.auto
        wait(root, lambda: app.future is None)
        root.event_generate('<space>')
        root.update()
        assert app.auto
        wait(root, lambda: app.game.state['game_over'] and app.future is None, timeout=60)
        assert len(app.record_table.get_children()) == 10
        assert app.graph.find_all()
        assert app.tree_canvas.find_all()
        assert '최종' in app.result_label.cget('text') or '무승부' in app.result_label.cget('text')
        root.event_generate('<Key-r>')
        root.update()
        assert app.game is None and not app.history
        print('GUI PASS: start, arrows, history isolation, auto/pause, Space, 5 rounds, graphs, reset')
    finally:
        app.close()


if __name__ == '__main__':
    main()
