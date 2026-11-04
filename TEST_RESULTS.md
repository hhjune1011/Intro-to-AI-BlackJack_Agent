# 실행 검증 결과

환경: Windows, Python 3.14.7, 표준 라이브러리 Tkinter/unittest.

## HTML UI 및 순차 턴 업데이트 검증

- `python -m unittest tests test_web -v`: **31개 통과**, 실행 시간 1.382초.
- 고정 카드 덱으로 실제 추가 카드 순서가 **A → A → B → B → 딜러**인지 확인했습니다. A/B 각각 두 번 Hit하고 Stand한 뒤에만 딜러가 Hit합니다.
- 모든 라운드에서 첫 플레이어 TURN_START → 다음 플레이어 TURN_START → 딜러 TURN_START 순서를 검사하고, 딜러 이벤트 시 A/B가 이미 Stand/Bust/참가 불가인지 확인했습니다.
- HTML 정적 파일, 입력 검증, 연결 토큰 검증, API를 통한 전체 게임과 초기화를 검사했습니다. 초기화 전의 오래된 게임 요청은 거부됩니다.
- 실제 브라우저에서 설정 제출, → 한 단계 진행, ← 과거 기록, ↑ 자동 실행, ↓ 일시정지, Space 재개, R 초기화 및 새 게임을 실행했습니다.
- 브라우저에서 기본 깊이 2·32표본·시드 42, 이벤트 간격 20ms로 5라운드를 완료했습니다. **160개 이벤트, 결과 기록 10행, 그래프 3개**, A=1,100 / B=1,250, 오류 메시지 없음.
- 390px 모바일 폭과 1440px 데스크톱 폭에서 DOM의 페이지 너비를 측정하여 전체 가로 넘침이 없음을 확인했습니다. 모바일 조작 버튼도 화면 폭 안에 위치했습니다. 모든 DPI/브라우저의 육안 검증을 수행한 것은 아닙니다.
- 브라우저 검사 초기에 이전 테스트 세션의 게임 식별자 불일치가 관찰됐습니다. 독립된 새 테스트 서버에서 초기화·재개와 전체 실행을 재검증했고 정상 완료했습니다. 서버는 한 게임을 공유하므로 여러 탭에서 새 게임을 시작하면 이전 탭의 진행 요청은 거부됩니다.

아래는 이전 Tkinter 버전에서 수행한 검증 기록입니다. 기본 실행 화면은 현재 HTML UI입니다.

## 실제 실행한 검사

| 검사 | 실행 결과 |
|---|---|
| `python -m unittest tests -v` | **26개 통과**, unittest 실행 시간 0.160초 |
| `python gui_smoke.py` | **통과**: 실제 Tk 창, 이벤트 루프, 시작 버튼, 방향키, 과거 조회 격리, 자동 실행/정지, Space, 5라운드 종료, 기록 표, 그래프 요소, R 초기화 |
| `python main.py --headless --seed 42 --depth 2 --samples 32` | **완료**: 5라운드 정산 및 최종 B 승리 |
| 에디터 Problems 검사 | 오류 없음 |

에디터의 테스트 실행 도구는 테스트를 발견하지 못하여, 실제 Python 인터프리터의 unittest 명령으로 실행했습니다.

## 기본 설정 콘솔 실행 결과

초기 자본 각 1,000 / 베팅 50~200, 단위 50 / 깊이 A=B=2 / 말단당 표본 A=B=32 / 시드 42.

| 라운드 | A Reward | B Reward | A 정산 자본 | B 정산 자본 |
|---|---:|---:|---:|---:|
| 1 | -150 | -150 | 850 | 850 |
| 2 | +50 | +200 | 900 | 1,050 |
| 3 | +200 | +50 | 1,100 | 1,100 |
| 4 | +150 | +200 | 1,250 | 1,300 |
| 5 | -150 | -50 | 1,100 | 1,250 |

**최종 B 승리, 자본 차이 150칩.** 이 단일 실행은 특정 에이전트 설정의 일반적인 우월성을 의미하지 않습니다.

## 요청한 20가지 검증 항목과 근거

| # | 검증 항목 | 실제 검사 |
|---|---|---|
| 1 | 중복 없는 52장 | `test_unique_deck` |
| 2 | 순서에 따른 2회 배분 | `test_deal_order_and_shuffle` |
| 3 | 매 라운드 새 덱과 셔플 | `test_deal_order_and_shuffle`: 공개 기록 초기화, 52장 재설정, 배분 결과 차이 |
| 4 | A=1, J/Q/K=10 | `test_card_values` |
| 5 | Hit 결과 즉시 Bust | `test_bust_and_stand_prevent_hit` |
| 6 | Stand 후 Hit 불가 | `test_stand_transition`, `test_bust_and_stand_prevent_hit` |
| 7 | 딜러 17 기준 | `test_dealer` |
| 8 | 딜러 Bust 승리, 플레이어도 Bust이면 패배 | `test_outcomes` |
| 9 | 동일 합계 무승부 | `test_outcomes` |
| 10 | 승/패/무 자본 정산과 중복 차감 차단 | `test_all_settlement_returns`, `test_bet_deducted_once`, `test_settlement_and_rewards` |
| 11 | 베팅 하한/상한/단위/현금 제한 | `test_bet_bounds`, `test_invalid_settings`, `test_bet_deducted_once` |
| 12 | 부족 자본 참가 제한 | `test_insufficient_capital`, `test_one_player_inactive` |
| 13 | 자본 우위 우선 | `test_order` |
| 14 | 동률 역순 | `test_order` |
| 15 | 정확히 5라운드 및 최종 비교 | `test_exactly_five_rounds_and_records` |
| 16 | 실제 Expectimax MAX/Chance | `test_both_agents_evaluate_bets_and_cards`, `test_exact_chance_weighting_and_max`, `test_depth_and_samples_applied` |
| 17 | 미래 실제 덱 비노출 | `test_public_observation_isolation`, `test_hidden_deck_does_not_change_decision` |
| 18 | 키보드 단계/자동 진행 | 실제 Tk `gui_smoke.py`의 이벤트 생성 및 상태 검증 |
| 19 | 로그와 상태 일치 | `test_transition_log_matches_state`, GUI 기록 격리 검사 |
| 20 | 동일 시드 재현 | `test_seed_reproducibility`: 모든 이벤트와 분석 결과의 동일성 비교 |

추가로, Chance의 분기 효용 가중합이 Hit의 EU와 일치하는지, 최종 효용이 절대 자본이 아닌 상대 순위인지, 잘못된 단계의 행동이 거부되는지도 검증했습니다.

## 검증의 한계

- GUI 자동 검사는 실제 동작과 캔버스 요소 생성을 확인했습니다. 모든 화면 크기·DPI에서의 육안 레이아웃 검사는 수행하지 않았습니다.
- 단위 테스트는 작고 빠른 깊이 1·2표본 설정을 주로 사용합니다. 기본 깊이 2·32표본은 별도 전체 게임을 실행했습니다. 최대 깊이 3·512표본의 장시간 성능은 측정하지 않았습니다.
- 모든 가능한 카드 순서 또는 모든 자본 조합을 완전 탐색하지 않았습니다.
- 근사 EU의 실제 승률 대비 오차나 A/B의 장기 승률 비교 실험은 수행하지 않았습니다. 상대 및 미래 정책 모델의 한계는 [README.md](README.md)에 설명했습니다.
- Python 3.14.7 이외의 버전과 다른 운영체제에서는 실행 검증하지 않았습니다.
