import math
import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title='Formational EV Soccer', page_icon='⚽', layout='wide')
st.title('⚽ Formational EV Soccer')
st.caption('Formation-specific probability analysis · In-memory calculations · No database')


def osr(rank, league_size):
    return 1 + 0.5 * ((league_size + 1) / 2 - rank) / ((league_size - 1) / 2)


def parse_games(raw, current_ranks, league_size):
    games = []
    errors = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        # Format: GF,GA,rank or GF,GA,live:Team
        bits = [p.strip() for p in line.split(',')]
        if len(bits) != 3:
            errors.append(f'Line {line_no}: use GF,GA,rank or GF,GA,live:Team')
            continue
        try:
            gf, ga = int(bits[0]), int(bits[1])
            if gf < 0 or ga < 0:
                raise ValueError('negative goals')
            rank_text = bits[2]
            if rank_text.lower().startswith('live:'):
                opponent = rank_text[5:].strip().lower()
                if opponent not in current_ranks:
                    raise ValueError(f'No current rank supplied for {opponent}')
                rank = current_ranks[opponent]
            else:
                rank = int(rank_text)
            if not 1 <= rank <= league_size:
                raise ValueError(f'rank {rank} outside 1–{league_size}')
            strength = osr(rank, league_size)
            games.append(dict(GF=gf, GA=ga, Rank=rank, OSR=strength,
                              Adjusted_GF=gf*strength, Adjusted_GA=ga/strength,
                              Total=gf+ga, BTTS=int(gf>0 and ga>0)))
        except (ValueError, KeyError) as exc:
            errors.append(f'Line {line_no}: {exc}')
    return pd.DataFrame(games), errors


def poisson(lam, max_goals=18):
    return [math.exp(-lam) * lam**k / math.factorial(k) for k in range(max_goals+1)]


def american_to_decimal(odds):
    return 1 + odds/100 if odds > 0 else 1 + 100/abs(odds)


def decimal_to_american(decimal):
    return round((decimal-1)*100) if decimal >= 2 else round(-100/(decimal-1))


def ranks_from_text(raw):
    result = {}
    problems = []
    for i, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.rsplit(',', 1)
        try:
            if len(parts) != 2 or not parts[0].strip():
                raise ValueError('use Team,rank')
            result[parts[0].strip().lower()] = int(parts[1].strip())
        except ValueError as exc:
            problems.append(f'Rank line {i}: {exc}')
    return result, problems

with st.sidebar:
    st.header('Model settings')
    edge_min = st.number_input('Minimum edge (percentage points)', min_value=0.0, max_value=50.0, value=8.0, step=0.5)
    base_stake = st.number_input('Base stake at minimum edge ($)', min_value=0.0, value=150.0, step=10.0)
    bankroll = st.number_input('Bankroll ($)', min_value=1.0, value=5000.0, step=100.0)
    max_bankroll_pct = st.number_input('Maximum stake (% of bankroll)', min_value=0.5, max_value=20.0, value=3.0, step=0.5)
    exponent = st.slider('Stake scaling exponent', 0.0, 1.0, 0.65, 0.05)
    st.caption('Stake guidance is illustrative. Small historical samples can produce unreliable edges.')

left, right = st.columns(2)
with left:
    st.subheader('Team A')
    name_a = st.text_input('Team A name', 'Juventus')
    formation_a = st.text_input('Opponent formation faced by Team A', '4-3-3')
    size_a = st.selectbox('Team A league size', [20, 18], index=0)
    rank_a = st.number_input('Team A current rank', 1, size_a, 8)
    ranks_a_text = st.text_area('Current opponent ranks (Team,rank; one per line)', 'Lazio,2\nAtalanta,11\nFrosinone,6', height=95, key='ra')
    games_a_text = st.text_area('Historical matches (GF,GA,rank or GF,GA,live:Team)',
        '0,3,live:Lazio\n2,0,live:Atalanta\n1,0,live:Frosinone\n0,2,15\n2,0,8\n1,1,11\n2,2,9\n3,0,11\n1,1,17', height=220, key='ga')
with right:
    st.subheader('Team B')
    name_b = st.text_input('Team B name', 'Rennes')
    formation_b = st.text_input('Opponent formation faced by Team B', '4-2-3-1')
    size_b = st.selectbox('Team B league size', [20, 18], index=1)
    rank_b = st.number_input('Team B current rank', 1, size_b, 6)
    ranks_b_text = st.text_area('Current opponent ranks (Team,rank; one per line)', 'PSG,2\nLyon,1\nMarseille,9\nAngers,15', height=95, key='rb')
    games_b_text = st.text_area('Historical matches (GF,GA,rank or GF,GA,live:Team)',
        '3,4,live:PSG\n0,4,live:Lyon\n1,0,live:Marseille\n2,1,live:Angers\n1,3,5\n2,1,11\n2,4,4\n3,0,8\n4,3,12\n0,0,18\n1,2,3\n4,0,16\n2,0,3', height=220, key='gb')

st.caption('Enter goals from the perspective of the named team. For example, a 3–0 loss is 0,3,rank. “live:Team” uses the rank entered above; otherwise the typed historical rank is used. The example rows are editable.')

rankmap_a, err_a = ranks_from_text(ranks_a_text)
rankmap_b, err_b = ranks_from_text(ranks_b_text)
da, errors_a = parse_games(games_a_text, rankmap_a, size_a)
db, errors_b = parse_games(games_b_text, rankmap_b, size_b)
errors = err_a + err_b + errors_a + errors_b
for error in errors:
    st.error(error)
if errors or da.empty or db.empty:
    st.warning('Correct input errors and provide at least one valid match per team to calculate.')
    st.stop()

st.divider()
league_adj = st.number_input('Optional Team A league multiplier (1.00 = no premium)', min_value=0.50, max_value=1.50, value=1.00, step=0.01)
base_a = (da.Adjusted_GF.mean() + db.Adjusted_GA.mean())/2
base_b = (db.Adjusted_GF.mean() + da.Adjusted_GA.mean())/2
relative = math.sqrt(osr(rank_a,size_a)/osr(rank_b,size_b))
xa = base_a*relative*league_adj
xb = base_b/relative/league_adj
pa, pb = poisson(xa), poisson(xb)
score_probs = {(a,b):pa[a]*pb[b] for a in range(len(pa)) for b in range(len(pb))}


def prob(fn):
    return sum(p for (a,b),p in score_probs.items() if fn(a,b))

markets = {
    f'{name_a} ML':prob(lambda a,b:a>b),
    'Draw':prob(lambda a,b:a==b),
    f'{name_b} ML':prob(lambda a,b:b>a),
    f'{name_a} or Draw (1X)':prob(lambda a,b:a>=b),
    f'{name_b} or Draw (X2)':prob(lambda a,b:b>=a),
    'Either team wins (12)':prob(lambda a,b:a!=b),
    'BTTS Yes':prob(lambda a,b:a>0 and b>0),
    'BTTS No':prob(lambda a,b:a==0 or b==0),
}
for t in (0.5,1.5,2.5,3.5,4.5):
    markets[f'Over {t} total'] = prob(lambda a,b,t=t:a+b>t)
    markets[f'Under {t} total'] = prob(lambda a,b,t=t:a+b<t)
for team, which in ((name_a,0),(name_b,1)):
    for t in (0.5,1.5,2.5):
        markets[f'{team} Over {t} goals'] = prob(lambda a,b,t=t,w=which:(a,b)[w]>t)
        markets[f'{team} Under {t} goals'] = prob(lambda a,b,t=t,w=which:(a,b)[w]<t)
for team, which in ((name_a,0),(name_b,1)):
    for margin in (1.5,2.5):
        markets[f'{team} -{margin}'] = prob(lambda a,b,w=which,m=margin:(a-b if w==0 else b-a)>m)
        markets[f'{team} +{margin}'] = prob(lambda a,b,w=which,m=margin:(a-b if w==0 else b-a)>-m)

c1,c2,c3=st.columns(3)
c1.metric(f'{name_a} projected xG',f'{xa:.3f}')
c2.metric(f'{name_b} projected xG',f'{xb:.3f}')
c3.metric('Total projected xG',f'{xa+xb:.3f}')
most_likely=max(score_probs,key=score_probs.get)
st.info(f'Most likely score: {name_a} {most_likely[0]}–{most_likely[1]} {name_b} ({score_probs[most_likely]*100:.2f}%)')

with st.expander('Adjusted historical stats and match-level data'):
    summary=pd.DataFrame([
        {'Team':name_a,'Matches':len(da),'GF/game':da.GF.mean(),'GA/game':da.GA.mean(),'Adjusted GF':da.Adjusted_GF.mean(),'Adjusted GA':da.Adjusted_GA.mean(),'Current OSR':osr(rank_a,size_a)},
        {'Team':name_b,'Matches':len(db),'GF/game':db.GF.mean(),'GA/game':db.GA.mean(),'Adjusted GF':db.Adjusted_GF.mean(),'Adjusted GA':db.Adjusted_GA.mean(),'Current OSR':osr(rank_b,size_b)}])
    st.dataframe(summary.round(3),hide_index=True,use_container_width=True)
    st.write(name_a)
    st.dataframe(da.round(3),hide_index=True,use_container_width=True)
    st.write(name_b)
    st.dataframe(db.round(3),hide_index=True,use_container_width=True)

st.subheader('All model probabilities and fair odds')
model_table=[]
for market,p in markets.items():
    fair=1/p if p>0 else math.inf
    threshold=1/(p-edge_min/100) if p>edge_min/100 else math.inf
    model_table.append({'Market':market,'Probability %':round(p*100,2),
                        'Fair American':decimal_to_american(fair) if math.isfinite(fair) else None,
                        'Fair Decimal':round(fair,2) if math.isfinite(fair) else None,
                        'Min decimal for edge':math.ceil(threshold*100)/100 if math.isfinite(threshold) else None})
st.dataframe(pd.DataFrame(model_table),hide_index=True,use_container_width=True)

st.subheader('Compare sportsbook odds')
st.caption('Select a market and enter its American odds. Add as many lines as needed. Positive odds: +140; negative odds: -150.')
if 'bets' not in st.session_state:
    st.session_state.bets=pd.DataFrame([{'Market':f'{name_b} or Draw (X2)','American odds':140}])
entered=st.data_editor(st.session_state.bets,num_rows='dynamic',hide_index=True,use_container_width=True,
    column_config={'Market':st.column_config.SelectboxColumn('Market',options=list(markets),required=True),
                   'American odds':st.column_config.NumberColumn('American odds',step=1,required=True)})
results=[]
for _,r in entered.iterrows():
    m=r.get('Market')
    try:
        odds=int(r.get('American odds'))
    except (ValueError,TypeError):
        continue
    if m not in markets or -100<odds<100:
        continue
    p=markets[m]
    dec=american_to_decimal(odds)
    implied=1/dec
    edge=(p-implied)*100
    roi=(p*dec-1)*100
    if edge >= edge_min and edge_min>0:
        raw_stake=base_stake*(edge/edge_min)**exponent
        stake=round(min(raw_stake,bankroll*max_bankroll_pct/100)/5)*5
    elif edge>=edge_min and edge_min==0:
        stake=min(base_stake,bankroll*max_bankroll_pct/100)
    else:
        stake=0
    results.append({'Market':m,'American odds':odds,'Model %':round(p*100,2),
                    'Implied %':round(implied*100,2),'Edge pp':round(edge,2),
                    'Expected ROI %':round(roi,2),'Passes rule':edge>=edge_min,
                    'Illustrative stake $':round(stake,2)})
if results:
    results_df=pd.DataFrame(results).sort_values('Expected ROI %',ascending=False)
    st.dataframe(results_df,hide_index=True,use_container_width=True)
    st.download_button('Export comparison as CSV',results_df.to_csv(index=False),'soccer_ev_comparison.csv','text/csv')

st.subheader('Most likely scorelines')
score_table=[{'Score':f'{name_a} {a}–{b} {name_b}','Probability %':round(p*100,2)}
             for (a,b),p in sorted(score_probs.items(),key=lambda item:item[1],reverse=True)[:10]]
st.dataframe(pd.DataFrame(score_table),hide_index=True,use_container_width=True)

st.caption('Research tool only. Probabilities are estimates, not guarantees. Historical samples, independence assumptions and market differences can make apparent value misleading. No match data is written to a database.')
