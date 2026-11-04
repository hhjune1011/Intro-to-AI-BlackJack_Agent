'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const token = location.hash.slice(1);
const format = n => Number(n).toLocaleString('ko-KR');
const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const initial = () => ({round:0, phase:'준비', actor:'', order:['A','B'], hands:{A:[],B:[],D:[]}, totals:{A:0,B:0,D:0}, status:{A:'대기',B:'대기',D:'대기'}, capital:{A:1000,B:1000}, bets:{A:0,B:0}, hits:{A:0,B:0}, remaining:52, reward:{A:0,B:0}, records:[], game_over:false});
let history = [], cursor = -1, reports = {}, player = 'A', settings = {}, running = false, busy = false, timer = null, generation = 0, gameId=0, starting=false;

async function api(path, data={}) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-Session-Token':token}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.');
  return result;
}
function error(message) { $('#error').textContent=message; $('#error').hidden=!message; }
function pause() { running=false; clearTimeout(timer); timer=null; renderControls(); }
function append(event) {
  if (!event) { pause(); return; }
  if (event.analysis) reports={...reports,[event.analysis.player]:event.analysis};
  event.reports=reports;
  const wasLive=cursor===history.length-1;
  history.push(event);
  if(wasLive) cursor=history.length-1;
  if(event.state.game_over) pause();
  render();
}
async function step() {
  clearTimeout(timer); timer=null;
  if(busy || !history.length) return;
  if(cursor<history.length-1) {cursor++; render(); return;}
  if(history.at(-1).state.game_over) {pause(); return;}
  const version=generation;
  busy=true; renderControls(); error('');
  try { const data=await api('/api/step',{game_id:gameId}); if(version===generation) append(data.event); }
  catch(e) {if(version===generation) {pause(); error(e.message);}}
  finally {
    if(version===generation) {
      busy=false; renderControls();
      if(running) timer=setTimeout(step,settings.speed);
    }
  }
}
function resume() {
  if(!history.length) {$('#settings-dialog').showModal(); return;}
  if(history.at(-1).state.game_over) return;
  cursor=history.length-1; running=true; render();
  if(!busy) step();
}
function previous() {pause(); cursor=Math.max(0,cursor-1); render();}
function selectTab(name) {
  $$('.tab').forEach(button=>{const active=button.dataset.tab===name;button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));});
  $$('.tab-panel').forEach(panel=>panel.hidden=panel.id!==`panel-${name}`);
}
function renderControls() {
  const done=history.at(-1)?.state.game_over;
  const past=history.length && cursor<history.length-1;
  $('#run-status').textContent=busy?'AI 계산 중…':past?'과거 기록 조회':done?'시뮬레이션 완료':running?'자동 진행 중':history.length?'일시정지':'시작 전';
  $('#history-position').textContent=`이벤트 ${history.length?cursor+1:0} / ${history.length}`;
  $('#run-dot').classList.toggle('running',running);
  $('#play').textContent=running?'Ⅱ 일시정지':'▶ 자동 실행';
  $('#play').disabled=Boolean(done);
  $('#next').disabled=busy || !history.length || (done && !past);
  $('#previous').disabled=cursor<=0;
  $('#live').disabled=!past;
  $('#export').disabled=!history.length;
  $('#settings-form [type="submit"]').disabled=busy||starting;
}
function phaseIndex(s) {
  if(s.phase==='베팅') return 0;
  if(s.phase==='최초 배분') return 1;
  if(s.phase==='플레이어 행동') return s.actor===s.order[0]?2:3;
  if(s.phase==='딜러 행동') return 4;
  if(['승패 판정','자본 정산','게임 종료'].includes(s.phase)) return 5;
  return -1;
}
function render() {
  const event=history[cursor], s=event?.state || initial();
  $('#round').innerHTML=`${s.round||'—'} <small>/ 5</small>`;
  const phases=['AI 베팅','최초 배분',`${s.order[0]} 턴 종료까지`,`${s.order[1]} 턴 종료까지`,'딜러 턴','정산'];
  const phase=phaseIndex(s);
  $('#flow').innerHTML=phases.map((name,i)=>`<div class="flow-item ${i===phase?'active':i<phase?'done':''}"><span class="number">${i<phase?'✓':i+1}</span>${esc(name)}</div>${i<5?'<span class="flow-arrow">›</span>':''}`).join('');
  $('#remaining').textContent=`남은 카드 ${s.remaining} / 52`;
  for(const who of ['A','B','D']) {
    const seat=$(`#agent-${who}`), status=s.status[who];
    const active=s.actor===who && !s.game_over && ['베팅','최초 배분','플레이어 행동','딜러 행동'].includes(s.phase);
    seat.classList.toggle('current',active);
    seat.classList.toggle('busted',status==='Bust');
    const badge=seat.querySelector('.status');
    let label=status==='Active'?'대기':status==='Stand'?'Stand · 종료':status==='Bust'?'Bust · 종료':status;
    if(active && status==='Active') label=s.phase==='최초 배분'?'카드 배분':s.phase==='베팅'?'베팅 중':'판단 중';
    badge.textContent=label;
    badge.className=`status ${status==='Bust'?'bust':status==='Stand'?'stand':''}`;
    const previousCount=event?.before.hands[who].length || 0;
    seat.querySelector('.cards').innerHTML=s.hands[who].length?s.hands[who].map((card,i)=>`<div class="card ${'♥♦'.includes(card[0])?'red':''} ${i>=previousCount?'new':''}" aria-label="${esc(card)}"><span class="rank">${esc(card.slice(1))}</span><span class="suit">${esc(card[0])}</span></div>`).join(''):'<div class="card-placeholder">♠</div><div class="card-placeholder">♠</div>';
    seat.querySelector('.score').textContent=s.totals[who];
    if(who!=='D') {seat.querySelector('.capital').textContent=format(s.capital[who]);seat.querySelector('.bet').textContent=s.bets[who]?format(s.bets[who]):'—';seat.querySelector('.hit-count').textContent=`Hit ${s.hits[who]}회`;}
  }
  let banner='설정을 확인하고 시뮬레이션을 시작하세요.';
  if(event) {
    if(s.game_over) banner=`${event.transition} · A ${format(s.capital.A)} / B ${format(s.capital.B)}칩`;
    else if(s.phase==='최초 배분') banner='최초 배분 중 · 두 장씩 모두 받은 다음 플레이어 턴이 시작됩니다.';
    else if(s.phase==='플레이어 행동') banner=event.action==='TURN_END'?event.transition:`${s.actor}의 턴 · Hit 이후에도 같은 플레이어가 계속 판단합니다.`;
    else if(s.phase==='딜러 행동') banner='A와 B의 턴 종료 · 이제 딜러가 17 이상이 될 때까지 진행합니다.';
    else banner=event.transition;
  }
  $('#turn-banner').textContent=banner;
  $('#action').textContent=event?.action || 'READY';
  $('#transition').textContent=event?.transition || '베팅과 Hit / Stand는 AI가 직접 선택합니다.';
  $('#reward').textContent=`라운드 Reward · A ${s.reward.A>=0?'+':''}${format(s.reward.A)} / B ${s.reward.B>=0?'+':''}${format(s.reward.B)}`;
  $('#difference').textContent=`자본 차이 A−B · ${format(s.capital.A-s.capital.B)}칩`;
  $('#before-state').textContent=event?'이전 State\n'+JSON.stringify(event.before,null,2):'—';
  $('#after-state').textContent=event?'다음 State\n'+JSON.stringify(s,null,2):'—';
  renderAnalysis(event);
  renderHistory(); renderResults(s); renderControls();
}
function actionLabel(action) {return action==='HIT'?'Hit · 한 장 더':action==='STAND'?'Stand · 턴 종료':`Bet · ${format(action)}칩`;}
function renderAnalysis(event) {
  const report=event?.reports[player];
  $('[data-player="A"]').classList.toggle('selected',player==='A');
  $('[data-player="B"]').classList.toggle('selected',player==='B');
  $('#decision').hidden=!report;
  if(!report) {
    $('#analysis-context').textContent='첫 의사결정을 기다리고 있습니다.';
    $('#utilities').innerHTML='<div class="empty">AI의 행동별 기대 효용이<br>여기에 표시됩니다.</div>';
    for(const id of ['depth','nodes','samples','report']) $(`#${id}`).textContent='—';
    $('#probabilities').innerHTML=''; $('#search-tree').textContent='MAX → Chance → 다음 상태'; return;
  }
  $('#analysis-context').textContent=`Round ${report.observation.round} · Player ${player} · ${report.observation.phase}에서 계산한 마지막 평가`;
  $('#utilities').innerHTML=Object.entries(report.utilities).map(([action,eu])=>`<div class="utility ${String(report.selected)===action?'chosen':''}"><div class="utility-label"><span>${actionLabel(action)}${String(report.selected)===action?'<em>선택됨</em>':''}</span><strong>${eu.toFixed(3)}</strong></div><div class="bar-track"><div class="bar" style="width:${eu*100}%"></div></div></div>`).join('');
  $('#decision').textContent=`${actionLabel(report.selected)} 선택 · 모델이 예측한 최종 효용의 기댓값이 가장 큽니다. 동률이면 Stand 또는 작은 베팅을 우선합니다.`;
  $('#depth').textContent=report.depth; $('#nodes').textContent=format(report.nodes); $('#samples').textContent=format(report.samples);
  $('#probabilities').innerHTML=Object.entries(report.probabilities).map(([card,p])=>`<div class="probability"><b>${card==='1'?'A':card}</b><span>${(p*100).toFixed(1)}%</span></div>`).join('');
  const actions=Object.entries(report.utilities);
  const children=report.chance_outcomes.slice(0,3);
  $('#search-tree').innerHTML=`<div class="tree-root">MAX · Player ${player}</div><div class="tree-actions">${actions.slice(0,4).map(([a,u])=>`<div class="tree-node ${String(report.selected)===a?'selected':''}">${a}<br>EU ≈ ${u.toFixed(3)}</div>`).join('')}</div>${children.length?`<p class="muted">Hit → Chance → 다음 상태 / MAX</p><div class="tree-children">${children.map(c=>`<div class="tree-child">카드 ${c.card} · P ${(c.probability*100).toFixed(1)}%<br>합계 ${c.next_total}<br>EU ≈ ${c.expected_utility.toFixed(3)}</div>`).join('')}</div>`:'<p class="muted">Chance: 가상 공용 덱 → 5라운드 최종 U 평균</p>'}<p class="muted">총 ${format(report.rollouts)} rollout · ${children.length?'처음 3개 카드 분기':'처음 4개 후보'} 표시</p>`;
  $('#report').textContent=JSON.stringify(report,null,2);
}
function renderHistory() {
  $('#event-list').innerHTML=history.map((event,i)=>`<li><button data-event="${i}" class="${i===cursor?'selected':''}"><b>${i+1}. R${event.state.round} · ${event.state.actor || '환경'} · ${esc(event.action)}</b><span>${esc(event.transition)}</span></button></li>`).join('');
}
function chart(title, series) {
  const colors=['#5278d5','#c47e43'];
  const values=series.flatMap(line=>line.values), low=Math.min(0,...values), high=Math.max(1,...values);
  const x=i=>40+i*52, y=v=>115-(v-low)/(high-low)*88;
  return `<div class="chart"><h3>${title}</h3><svg viewBox="0 0 330 145" role="img" aria-label="${title}"><path d="M40 23V115H310" fill="none" stroke="#e1e6e3"/><text x="2" y="29">${high}</text><text x="2" y="118">${low}</text>${Array.from({length:6},(_,i)=>`<text x="${x(i)-3}" y="135">${i}</text>`).join('')}${series.map((line,k)=>`<polyline fill="none" stroke="${colors[k]}" stroke-width="2.5" points="${line.values.map((v,i)=>`${x(i)},${y(v)}`).join(' ')}"/>${line.values.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="${colors[k]}"><title>${line.name} R${i}: ${v}</title></circle>`).join('')}`).join('')}</svg><div class="chart-legend">${series.map((line,i)=>`<span style="color:${colors[i]}">● ${line.name}</span>`).join('　')} · 가로축: 라운드</div></div>`;
}
function renderResults(s) {
  $('#winner').textContent=s.game_over?(s.capital.A===s.capital.B?'최종 무승부':`플레이어 ${s.capital.A>s.capital.B?'A':'B'} 최종 승리`):'5라운드의 여정';
  $('#result-summary').textContent=['A','B'].map(p=>{const rows=s.records.filter(r=>r.player===p);return `${p}: ${format(s.capital[p])}칩 · ${['승','패','무','불참'].map(result=>`${rows.filter(r=>r.result===result).length}${result}`).join(' ')}`;}).join(' / ');
  const capitals=['A','B'].map(p=>({name:p,values:[1000,...s.records.filter(r=>r.player===p).map(r=>r.capital)]}));
  const bets=['A','B'].map(p=>({name:p,values:[0,...s.records.filter(r=>r.player===p).map(r=>r.bet)]}));
  const diff=[{name:'A−B',values:capitals[0].values.map((v,i)=>v-capitals[1].values[i])}];
  $('#charts').innerHTML=chart('정산 자본 변화',capitals)+chart('라운드별 베팅',bets)+chart('자본 차이',diff);
  $('#records').innerHTML=s.records.map(r=>`<tr><td>${r.round}</td><td>${r.player}</td><td>${r.bet}</td><td>${r.hits}</td><td>${r.result}</td><td>${format(r.capital)}</td></tr>`).join('');
}
$('#settings-form').addEventListener('submit',async event=>{
  event.preventDefault(); if(busy||starting) return; pause(); starting=true;
  const version=++generation;
  const form=event.currentTarget;
  const values=Object.fromEntries(new FormData(form).entries());
  if(!values.seed.trim()) values.seed=crypto.getRandomValues(new Uint32Array(1))[0];
  const cfg=Object.fromEntries(Object.entries(values).map(([k,v])=>[k,Number(v)]));
  const submit=form.querySelector('[type="submit"]'); submit.disabled=true;
  $('#settings-error').hidden=true;
  try {
    const result=await api('/api/start',{settings:cfg});
    if(version!==generation) return;
    history=[]; cursor=-1; reports={}; busy=false; settings=result.settings; gameId=result.game_id;
    form.elements.seed.value=settings.seed;
    error(''); append(result.event); $('#settings-dialog').close(); selectTab('analysis');
  } catch(e) {$('#settings-error').textContent=e.message;$('#settings-error').hidden=false;}
  finally {starting=false;submit.disabled=false;if(version===generation){busy=false;renderControls();}}
});
async function reset() {
  pause(); const version=++generation; busy=true; renderControls();
  try {
    await api('/api/reset');
    if(version===generation) {history=[];cursor=-1;reports={};error('');render();$('#settings-dialog').showModal();}
  } catch(e) {if(version===generation) error(e.message);}
  finally {if(version===generation){busy=false;renderControls();}}
}
$('#settings-button').onclick=()=>{pause();$('#settings-dialog').showModal();};
$('#close-settings').onclick=()=>$('#settings-dialog').close();
$('#next').onclick=step;
$('#previous').onclick=previous;
$('#play').onclick=()=>running?pause():resume();
$('#live').onclick=()=>{cursor=history.length-1;render();};
$$('.tab').forEach(button=>button.onclick=()=>selectTab(button.dataset.tab));
$$('[data-player]').forEach(button=>button.onclick=()=>{player=button.dataset.player;renderAnalysis(history[cursor]);});
$('#event-list').onclick=event=>{const button=event.target.closest('[data-event]');if(button){pause();cursor=Number(button.dataset.event);render();}};
$('#export').onclick=()=>{
  const blob=new Blob([JSON.stringify({settings,events:history},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob), link=document.createElement('a');
  link.href=url;link.download=`blackjack-seed-${settings.seed}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
document.addEventListener('keydown',event=>{
  if($('#settings-dialog').open || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
  const actions={ArrowRight:step,ArrowLeft:previous,ArrowUp:resume,ArrowDown:pause,' ':()=>running?pause():resume(),r:reset,R:reset};
  if(actions[event.key]) {event.preventDefault();actions[event.key]();}
});
render();
$('#settings-dialog').showModal();
