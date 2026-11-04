"""Tkinter UI. 탐색은 worker에서, 모든 위젯 갱신은 메인 스레드에서 실행."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from agents import make_agents
from game import Game, Settings, total


def pretty(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


class App:
    def __init__(self, root):
        self.root = root
        root.title('Multi-Agent Blackjack · Expectimax 실험실')
        root.geometry('1300x920')
        root.minsize(1000, 740)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.game = None
        self.history = []
        self.cursor = -1
        self.auto = False
        self.timer = None
        self.generation = 0
        self.reports = {}
        self.inputs = {}
        self.settings_frame = ttk.LabelFrame(root, text='시작 설정 · A=1 / 그림 카드=10 / 5라운드')
        self.settings_frame.pack(fill='x', padx=10, pady=6)
        fields = [('minimum', '최소 베팅', 50), ('maximum', '최대 베팅', 200),
                  ('unit', '베팅 단위', 50), ('speed', '자동 간격(ms)', 500),
                  ('depth_a', 'A 깊이(1~3)', 2), ('samples_a', 'A 말단 샘플', 32),
                  ('depth_b', 'B 깊이(1~3)', 2), ('samples_b', 'B 말단 샘플', 32),
                  ('seed', '시드(빈칸=랜덤)', 42)]
        self.entries = []
        for index, (key, label, default) in enumerate(fields):
            row, col = divmod(index, 5)
            cell = ttk.Frame(self.settings_frame)
            cell.grid(row=row, column=col, padx=7, pady=4, sticky='w')
            ttk.Label(cell, text=label).pack(side='left')
            var = tk.StringVar(value=str(default))
            entry = ttk.Entry(cell, textvariable=var, width=8)
            entry.pack(side='left', padx=4)
            self.entries.append(entry)
            self.inputs[key] = var
        self.start_button = ttk.Button(self.settings_frame, text='시뮬레이션 시작', command=self.start)
        self.start_button.grid(row=1, column=4, padx=8)
        self.banner = ttk.Label(root, text='설정을 확인하고 시작하세요.', font=('맑은 고딕', 12, 'bold'))
        self.banner.pack(fill='x', padx=12, pady=6)
        controls = ttk.Frame(root)
        controls.pack(fill='x', padx=10)
        for label, command in [('← 이전 기록', self.previous), ('→ 다음 단계', self.next_step),
                               ('↑ 자동 실행', self.resume), ('↓ 일시정지', self.pause),
                               ('현재 기록', self.live), ('R 초기화', self.reset),
                               ('JSON 기록 저장', self.export)]:
            ttk.Button(controls, text=label, command=command).pack(side='left', padx=3)
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill='both', expand=True, padx=10, pady=8)
        play = ttk.Frame(self.tabs)
        analysis = ttk.Frame(self.tabs)
        results = ttk.Frame(self.tabs)
        self.tabs.add(play, text='게임 · State / Action / Transition')
        self.tabs.add(analysis, text='Expectimax 분석')
        self.tabs.add(results, text='결과 · 그래프')
        table = ttk.Frame(play)
        table.pack(fill='x')
        self.agent_labels = {}
        for column, who in enumerate(('A', 'D', 'B')):
            box = ttk.LabelFrame(table, text='딜러 · Simple Reflex' if who == 'D' else f'Player {who} · Utility-based')
            box.grid(row=0, column=column, sticky='nsew', padx=5, pady=5)
            table.columnconfigure(column, weight=1, uniform='agents')
            label = ttk.Label(box, text='대기', font=('맑은 고딕', 11), wraplength=370, justify='left')
            label.pack(fill='both', padx=10, pady=12)
            self.agent_labels[who] = label
        self.transition = ttk.Label(play, text='', font=('맑은 고딕', 11), wraplength=1200)
        self.transition.pack(fill='x', padx=8, pady=8)
        panes = ttk.Panedwindow(play, orient='horizontal')
        panes.pack(fill='both', expand=True)
        state_box = ttk.LabelFrame(panes, text='이전 State → Action → 다음 State')
        log_box = ttk.LabelFrame(panes, text='이벤트 로그 · 과거 조회는 실제 상태를 변경하지 않습니다')
        panes.add(state_box, weight=1)
        panes.add(log_box, weight=1)
        self.state_text = self.text_widget(state_box)
        self.log_text = self.text_widget(log_box)
        bar = ttk.Frame(analysis)
        bar.pack(fill='x')
        ttk.Label(bar, text='분석할 플레이어:').pack(side='left', padx=8)
        self.selected_player = tk.StringVar(value='A')
        combo = ttk.Combobox(bar, textvariable=self.selected_player, values=('A', 'B'), state='readonly', width=5)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', lambda _: self.render())
        ttk.Label(bar, text='EU는 정책 모델에 따른 근사값이며 정확한 승률이 아닙니다.').pack(side='left', padx=15)
        self.tree_canvas = tk.Canvas(analysis, height=290, background='#f1f5f9', highlightthickness=0)
        self.tree_canvas.pack(fill='x', padx=6, pady=6)
        self.analysis_text = self.text_widget(analysis)
        self.result_label = ttk.Label(results, text='라운드 정산 후 기록이 표시됩니다.', font=('맑은 고딕', 12))
        self.result_label.pack(fill='x', padx=8, pady=8)
        columns = ('round', 'player', 'bet', 'hits', 'result', 'reward', 'capital')
        self.record_table = ttk.Treeview(results, columns=columns, show='headings', height=10)
        for key, title in zip(columns, ('Round', 'Player', 'Bet', 'Hit 수', '결과', 'Reward', '정산 자본')):
            self.record_table.heading(key, text=title)
            self.record_table.column(key, width=100, anchor='center')
        self.record_table.pack(fill='x', padx=8)
        self.graph = tk.Canvas(results, background='white', height=310, highlightthickness=0)
        self.graph.pack(fill='both', expand=True, padx=8, pady=8)
        self.graph.bind('<Configure>', lambda _: self.render_graph())
        for sequence, callback in [('<Right>', self.next_step), ('<Left>', self.previous),
                                   ('<Up>', self.resume), ('<Down>', self.pause),
                                   ('<space>', self.toggle), ('<Key-r>', self.reset), ('<Key-R>', self.reset)]:
            root.bind(sequence, lambda event, cb=callback: self.key(event, cb))
        root.protocol('WM_DELETE_WINDOW', self.close)

    @staticmethod
    def text_widget(parent):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, wrap='word', font=('맑은 고딕', 10), state='disabled', width=30, height=8)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        text.pack(fill='both', expand=True)
        return text

    @staticmethod
    def put(widget, content):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('end', content)
        widget.configure(state='disabled')

    def key(self, event, callback):
        if isinstance(event.widget, (ttk.Entry, ttk.Combobox)):
            return
        callback()
        return 'break'

    def start(self):
        if self.game:
            return
        try:
            data = {key: int(var.get()) if var.get().strip() else
                    (secrets.randbits(32) if key == 'seed' else 0) for key, var in self.inputs.items()}
            cfg = Settings(**data)
            cfg.validate()
        except ValueError as error:
            messagebox.showerror('설정 오류', str(error))
            return
        self.inputs['seed'].set(str(cfg.seed))
        self.game = Game(cfg, make_agents(cfg))
        for entry in self.entries:
            entry.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.root.focus_set()
        self.next_step()

    def next_step(self):
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        if not self.game or self.future:
            return
        if self.cursor < len(self.history) - 1:
            self.cursor += 1
            self.render()
            return
        if self.game.state['game_over']:
            self.pause()
            return
        self.banner.configure(text='Expectimax / 이벤트 계산 중… 일시정지와 기록 조회 가능')
        self.future = self.executor.submit(next, self.game.events, None)
        self.root.after(25, self.poll, self.generation)

    def poll(self, generation):
        if generation != self.generation:
            return
        if not self.future.done():
            self.root.after(25, self.poll, generation)
            return
        future, self.future = self.future, None
        try:
            event = future.result()
        except Exception as error:
            self.pause()
            messagebox.showerror('시뮬레이션 오류', str(error))
            return
        if event:
            if event['analysis']:
                self.reports[event['analysis']['player']] = event['analysis']
            event['reports'] = self.reports.copy()
            was_live = self.cursor == len(self.history) - 1
            self.history.append(event)
            if was_live:
                self.cursor = len(self.history) - 1
            self.render()
        if not event or self.game.state['game_over']:
            self.auto = False
            self.render()
        if self.auto:
            self.timer = self.root.after(self.game.settings.speed, self.auto_tick)

    def auto_tick(self):
        self.timer = None
        if self.auto:
            self.next_step()

    def resume(self):
        if not self.game:
            return
        self.live()
        self.auto = True
        if not self.future and not self.timer:
            self.next_step()

    def pause(self):
        self.auto = False
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.render()

    def toggle(self):
        self.pause() if self.auto else self.resume()

    def previous(self):
        self.pause()
        self.cursor = max(0, self.cursor - 1) if self.history else -1
        self.render()

    def live(self):
        self.cursor = len(self.history) - 1
        self.render()

    def reset(self):
        self.pause()
        self.generation += 1
        if self.game:
            self.game.cancel()
        if self.future:
            self.future.cancel()
        self.future = None
        self.game = None
        self.history = []
        self.cursor = -1
        self.reports = {}
        for entry in self.entries:
            entry.configure(state='normal')
        self.start_button.configure(state='normal')
        self.banner.configure(text='초기화 완료 · 설정 후 시작하세요.')
        for label in self.agent_labels.values():
            label.configure(text='대기')
        self.transition.configure(text='')
        for widget in (self.state_text, self.log_text, self.analysis_text):
            self.put(widget, '')
        self.tree_canvas.delete('all')
        self.record_table.delete(*self.record_table.get_children())
        self.graph.delete('all')
        self.result_label.configure(text='라운드 정산 후 기록이 표시됩니다.')

    def render(self):
        if self.cursor < 0 or not self.history:
            return
        event = self.history[self.cursor]
        s = event['state']
        mode = '자동 실행' if self.auto else '일시정지'
        view = '현재' if self.cursor == len(self.history) - 1 else '과거 조회'
        self.banner.configure(text=f'Round {s["round"]}/5 · 남은 라운드 {5-s["round"]} · 순서 {" → ".join(s["order"])} · {s["phase"]} · {mode} · {view} {self.cursor+1}/{len(self.history)}')
        for who, label in self.agent_labels.items():
            text = f'{"  ".join(s["hands"][who]) or "카드 없음"}\n합계 {total(s["hands"][who])} · {s["status"][who]}'
            if who != 'D':
                text += f'\n보유 {s["capital"][who]:,}칩 · 베팅 {s["bets"][who]:,}칩'
                report = event['reports'].get(who)
                if report:
                    text += '\n근사 EU: ' + ', '.join(f'{a}: {u:.3f}' for a, u in report['utilities'].items())
            label.configure(text=text)
        self.transition.configure(text=f'Action: {event["action"]}  |  Transition: {event["transition"]}\nReward: {s["reward"]} · A−B: {s["capital"]["A"]-s["capital"]["B"]:+,}칩')
        self.put(self.state_text, '이전 State\n' + pretty(event['before']) + '\n\nAction: ' + event['action'] + '\n\n다음 State\n' + pretty(s))
        self.put(self.log_text, '\n'.join(f'{i+1}. [R{e["state"]["round"]} / {e["state"]["actor"] or "환경"}] {e["action"]}: {e["transition"]}' for i, e in enumerate(self.history[:self.cursor+1])))
        self.log_text.see('end')
        self.render_analysis(event)
        self.render_results(s)

    def render_analysis(self, event):
        report = event['reports'].get(self.selected_player.get())
        self.tree_canvas.delete('all')
        if not report:
            self.put(self.analysis_text, '아직 이 플레이어의 의사결정이 없습니다.')
            return
        self.put(self.analysis_text, pretty(report) + '\n\n조회 중인 이벤트의 다음 State (위 평가 이후일 수 있음)\n' + pretty(event['state']) + '\n실제 Reward\n' + pretty(event['state']['reward']))
        canvas = self.tree_canvas
        width = max(canvas.winfo_width(), 800)
        canvas.create_text(width/2, 20, text=f'MAX · Player {report["player"]} · 선택 {report["selected"]}', font=('맑은 고딕', 12, 'bold'))
        actions = list(report['utilities'].items())
        shown = actions[:6]
        for i, (action, eu) in enumerate(shown):
            x = (i+1)*width/(len(shown)+1)
            canvas.create_line(width/2, 35, x, 65, fill='#64748b')
            canvas.create_rectangle(x-65, 65, x+65, 115, fill='#dbeafe' if action == report['selected'] else 'white', outline='#2563eb')
            canvas.create_text(x, 89, text=f'{action}\nEU ≈ {eu:.4f}')
            canvas.create_line(x, 115, x, 140, fill='#64748b')
            canvas.create_text(x, 155, text='Chance → MAX' if action == 'HIT' else 'Rollout Chance\n최종 U 평균')
            if action == 'HIT':
                children = report['chance_outcomes']
                for j, child in enumerate(children[:3]):
                    cx = x + (j-1)*125
                    canvas.create_line(x, 170, cx, 195, fill='#64748b')
                    canvas.create_text(cx, 218, text=f'카드 {child["card"]} · P={child["probability"]:.3f}\n합계 {child["next_total"]}\nEU≈{child["expected_utility"]:.3f}')
        probs = '  '.join(f'{v}: {p:.1%}' for v, p in report['probabilities'].items())
        canvas.create_text(width/2, 258, text='다음 카드 확률: ' + probs)
        canvas.create_text(width/2, 280, text=f'깊이 {report["depth"]} · 노드 {report["nodes"]} · 말단당 {report["samples"]}표본 · 총 {report["rollouts"]} rollout' + (' · 처음 6개 베팅 후보 표시' if len(actions) > 6 else ' · 카드 분기는 처음 3개 표시'))

    def render_results(self, s):
        self.record_table.delete(*self.record_table.get_children())
        for record in s['records']:
            self.record_table.insert('', 'end', values=[record[k] for k in ('round', 'player', 'bet', 'hits', 'result', 'reward', 'capital')])
        summaries = []
        for p in ('A', 'B'):
            count = Counter(r['result'] for r in s['records'] if r['player'] == p)
            summaries.append(f'{p}: {s["capital"][p]:,}칩 · {count["승"]}승 {count["패"]}패 {count["무"]}무 {count["불참"]}불참')
        a, b = s['capital']['A'], s['capital']['B']
        winner = ('무승부' if a == b else f'{"A" if a > b else "B"} 최종 승리') if s['game_over'] else '진행 중'
        self.result_label.configure(text=f'{winner} · 차이 {abs(a-b):,}칩\n' + '   |   '.join(summaries))
        self.render_graph()

    def render_graph(self):
        if self.cursor < 0 or not self.history:
            return
        records = self.history[self.cursor]['state']['records']
        capital = {p: [1000] + [r['capital'] for r in records if r['player'] == p] for p in ('A', 'B')}
        wagers = {p: [0] + [r['bet'] for r in records if r['player'] == p] for p in ('A', 'B')}
        diff = {'A−B': [a-b for a, b in zip(capital['A'], capital['B'])]}
        canvas = self.graph
        canvas.delete('all')
        width, height = max(900, canvas.winfo_width()), max(250, canvas.winfo_height())
        for index, (title, series) in enumerate((('자본 변화 · A 파랑 / B 주황', capital), ('라운드 베팅', wagers), ('자본 차이 A−B', diff))):
            left, right = index*width/3+45, (index+1)*width/3-20
            top, bottom = 50, height-40
            numbers = [n for values in series.values() for n in values]
            low, high = min(0, min(numbers)), max(1, max(numbers))
            canvas.create_text((left+right)/2, 18, text=title)
            canvas.create_line(left, top, left, bottom, right, bottom)
            for val in (low, high):
                y = bottom-(val-low)/(high-low)*(bottom-top)
                canvas.create_text(left-5, y, text=str(val), anchor='e')
            for rnd in range(6):
                canvas.create_text(left+rnd*(right-left)/5, bottom+15, text=str(rnd))
            for n, (name, values) in enumerate(series.items()):
                color = ('#2563eb', '#ea580c')[n % 2]
                points = [(left+i*(right-left)/5, bottom-(v-low)/(high-low)*(bottom-top)) for i, v in enumerate(values)]
                if len(points) > 1:
                    canvas.create_line(*[c for pt in points for c in pt], fill=color, width=2)
                for x, y in points:
                    canvas.create_oval(x-3, y-3, x+3, y+3, fill=color, outline=color)

    def export(self):
        if not self.history:
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as stream:
                    json.dump(dict(settings=vars(self.game.settings), events=self.history), stream, ensure_ascii=False, indent=2)
            except OSError as error:
                messagebox.showerror('저장 오류', str(error))

    def close(self):
        self.pause()
        self.generation += 1
        if self.game:
            self.game.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def launch():
    root = tk.Tk()
    App(root)
    root.mainloop()
