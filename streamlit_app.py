"""Run: python -m streamlit run streamlit_app.py"""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import altair as alt
import pandas as pd
import streamlit as st
from scheduler import AIRPORTS, Settings, synthetic_data, parse_records, optimize

st.set_page_config(page_title='Interstate jet planner', page_icon=':material/flight:', layout='wide')
st.title('Interstate jet planner')
st.caption('A genetic algorithm lab for private aircraft dispatch across U.S. states · Synthetic data')
st.info('Assign jets to passenger requests while balancing operating cost, departure delays, and unserved flights. All times use one UTC clock.')

@st.cache_data(max_entries=12, show_spinner=False)
def make_scenario(fleet_size, count, horizon, seed, airports):
    fleet, requests = synthetic_data(fleet_size, count, horizon, seed, airports)
    return pd.DataFrame([asdict(a) for a in fleet]), pd.DataFrame([asdict(r) for r in requests])

with st.sidebar:
    st.header('Scenario')
    with st.form('scenario'):
        fleet_size=st.slider('Number of aircraft',1,20,6)
        count=st.slider('Flight requests',5,100,24,step=1)
        horizon=st.selectbox('Planning horizon (hours)',[12,24,48,72],index=1)
        scenario_seed=st.number_input('Data seed',0,1000000,42)
        airports=st.multiselect('Airports / states',list(AIRPORTS),default=list(AIRPORTS),format_func=lambda a:f'{a} · {AIRPORTS[a][0]}')
        generate=st.form_submit_button('Generate scenario',icon=':material/refresh:')
    st.caption('Generating a scenario replaces edited tables and clears previous results.')

if 'fleet_data' not in st.session_state or generate:
    try:
        fleet_df, requests_df=make_scenario(fleet_size,count,horizon,scenario_seed,tuple(airports))
    except ValueError as error:
        st.error(str(error)); st.stop()
    st.session_state.update(fleet_data=fleet_df,requests_data=requests_df,horizon=horizon,
                            revision=st.session_state.get('revision',0)+1,result=None)
st.session_state.setdefault('result',None)
active_horizon=st.session_state.horizon
st.caption(f'Active scenario horizon: {active_horizon} hours. Set up the sidebar and select Generate scenario to change it.')

with st.expander('Edit aircraft and flight requests',expanded=True):
    st.markdown('Minutes are measured from the schedule start. `available_min` is the earliest aircraft departure; `priority` weights delay and unserved penalties.')
    fleet_tab,request_tab,import_tab=st.tabs(['Aircraft','Flight requests','Import / export'])
    with fleet_tab:
        fleet_edit=st.data_editor(st.session_state.fleet_data,num_rows='dynamic',hide_index=True,
            key=f'fleet_editor_{st.session_state.revision}',
            column_config={'base':st.column_config.SelectboxColumn(options=list(AIRPORTS))})
    with request_tab:
        requests_edit=st.data_editor(st.session_state.requests_data,num_rows='dynamic',hide_index=True,
            key=f'request_editor_{st.session_state.revision}',
            column_config={k:st.column_config.SelectboxColumn(options=list(AIRPORTS)) for k in ['origin','destination']})
    with import_tab:
        st.caption('Use the downloads as CSV templates. Airports must be in the airport list below.')
        st.download_button('Download aircraft CSV',fleet_edit.to_csv(index=False),'aircraft.csv','text/csv')
        st.download_button('Download requests CSV',requests_edit.to_csv(index=False),'requests.csv','text/csv')
        aircraft_upload=st.file_uploader('Aircraft CSV',type='csv')
        request_upload=st.file_uploader('Flight requests CSV',type='csv')
        if st.button('Load uploaded CSVs'):
            try:
                new_fleet=pd.read_csv(aircraft_upload) if aircraft_upload else fleet_edit
                new_requests=pd.read_csv(request_upload) if request_upload else requests_edit
                parse_records(new_fleet.to_dict('records'),new_requests.to_dict('records'),Settings(horizon_hours=active_horizon))
                st.session_state.update(fleet_data=new_fleet,requests_data=new_requests,revision=st.session_state.revision+1,result=None)
                st.rerun()
            except (ValueError,KeyError,pd.errors.ParserError) as error:
                st.error(f'CSV input: {error}')

st.subheader('Search and scheduling settings')
with st.form('optimization'):
    left,right=st.columns(2)
    with left:
        st.markdown('**Genetic algorithm**')
        pop=st.slider('Population size',20,500,100,step=10)
        generations=st.slider('Maximum generations',10,500,100,step=10)
        mutation=st.slider('Mutation rate',0.0,1.0,0.15,step=.01)
        cross=st.slider('Crossover rate',0.0,1.0,.9,step=.05)
        elite=st.slider('Elite fraction',.01,.30,.05,step=.01)
        seconds=st.slider('Search time budget (seconds)',1,60,10)
        seed=st.number_input('Search seed',0,1000000,42)
    with right:
        st.markdown('**Operating assumptions**')
        start=st.date_input('Schedule start date (UTC)',value=datetime.now(timezone.utc).date())
        turnaround=st.slider('Turnaround time (minutes)',0,120,30,step=5)
        delay=st.slider('Maximum departure delay (minutes)',0,720,180,step=15)
        hours=st.slider('Maximum aircraft block hours',1,72,10)
        delay_cost=st.number_input('Delay penalty ($ / minute / priority)',0,10000,50)
        penalty=st.number_input('Unserved penalty ($ / request / priority)',1000,1000000,100000,step=1000)
        st.caption('Block time includes cruise plus 15 minutes per leg. Range is a simplified nonstop limit. Passenger requests never depart early.')
    submitted=st.form_submit_button('Optimize schedule',type='primary',icon=':material/flight_takeoff:')

if submitted:
    settings=Settings(horizon_hours=active_horizon,turnaround_min=turnaround,max_delay_min=delay,
        max_flight_hours=hours,delay_cost_per_min=delay_cost,unserved_penalty=penalty,population_size=pop,
        generations=generations,mutation_rate=mutation,crossover_rate=cross,elitism=elite,
        time_limit_seconds=seconds,seed=seed)
    try:
        fleet,requests=parse_records(fleet_edit.to_dict('records'),requests_edit.to_dict('records'),settings)
        bar=st.progress(0,text='Building baseline and searching...')
        result=optimize(fleet,requests,settings,lambda fraction,score:bar.progress(min(1.0,fraction),text=f'Best objective: ${score:,.0f}'))
        bar.empty()
        st.session_state.result={'run':result,'start':str(start),'fleet':[asdict(a) for a in fleet],
                                 'requests':[asdict(r) for r in requests]}
    except (ValueError,KeyError,TypeError) as error:
        st.error(f'Please check the input tables: {error}')

saved=st.session_state.result
if saved:
    result=saved['run']; best=result['best']; baseline=result['baseline']
    st.subheader('Schedule results')
    st.caption('Results belong to the last optimization run. Changes to inputs take effect when you optimize again.')
    with st.container(horizontal=True):
        st.metric('Served requests',f"{best['served']} / {len(saved['requests'])}",border=True)
        st.metric('Operating cost',f"${best['operating_cost']:,.0f}",border=True)
        st.metric('Departure delay',f"{best['delay_minutes']:,.0f} min",border=True)
        st.metric('Empty repositioning',f"{best['reposition_minutes']/60:.1f} h",border=True)
    improvement=baseline['objective']-best['objective']
    st.success(f"Objective ${best['objective']:,.0f} · ${improvement:,.0f} improvement over greedy baseline · {result['elapsed_seconds']:.2f} s · {result['stopped']}")
    st.caption('Objective includes passenger and repositioning block costs, priority-weighted delay penalties, and priority-weighted unserved penalties. A lower objective need not serve more flights when penalty weights are low.')
    timeline,compare,details=st.tabs(['Aircraft timeline','Search performance','Tables and downloads'])
    with timeline:
        legs=pd.DataFrame(best['legs'])
        if not legs.empty:
            anchor=pd.Timestamp(saved['start'],tz='UTC')
            legs['departure_utc']=anchor+pd.to_timedelta(legs.start_min,unit='m')
            legs['arrival_utc']=anchor+pd.to_timedelta(legs.end_min,unit='m')
            chart=alt.Chart(legs).mark_bar(cornerRadius=3).encode(
                x=alt.X('departure_utc:T',title='UTC time',scale=alt.Scale(type='utc'),axis=alt.Axis(format='%b %d %H:%M')),
                x2='arrival_utc:T',y=alt.Y('aircraft:N',title='Aircraft'),
                color=alt.Color('kind:N',scale=alt.Scale(domain=['Passenger','Reposition'],range=['#167D9A','#EDA64B'])),
                tooltip=['aircraft','request_id','kind','origin','destination','departure_utc:T','arrival_utc:T','delay_min:Q']).properties(height=max(240,45*len(saved['fleet'])))
            st.altair_chart(chart)
        else: st.warning('No requests could be scheduled. Review the fleet, request times, and limits.')
        if best['unserved']:
            st.warning('Unserved reasons describe the chosen assignment and decoding order; they do not prove that a request is impossible for every aircraft.')
            st.dataframe(pd.DataFrame(best['unserved']),hide_index=True)
    with compare:
        st.line_chart(pd.DataFrame(result['history']),x='generation',y='best_objective',y_label='Best objective ($)')
        comparison=pd.DataFrame([{'Method':name,**{k:r[k] for k in ['objective','served','unserved_count','operating_cost','delay_minutes','reposition_minutes']}} for name,r in [('Greedy baseline',baseline),('Genetic algorithm',best)]])
        st.dataframe(comparison,hide_index=True)
        st.caption(f"{result['evaluations']:,} candidate evaluations. Same seed reproduces generation-limited runs; time-limited runs can vary with machine speed. Baseline setup and one in-progress operation can extend elapsed time beyond the budget.")
    with details:
        st.dataframe(legs,hide_index=True)
        st.download_button('Download schedule CSV',legs.to_csv(index=False),'schedule.csv','text/csv')
        st.download_button('Download complete run JSON',json.dumps(saved,indent=2),'aircraft_schedule_run.json','application/json')
        with st.expander('Parameters used for this run'):
            st.json(result['settings'])
else:
    st.caption('Edit the synthetic scenario, then select Optimize schedule to see the result.')

with st.expander('How the model works and where to find data'):
    st.markdown('''The chromosome contains a permutation of requests and an aircraft assignment for each request. Tournament selection, order crossover, uniform aircraft-gene crossover, swap mutation, assignment mutation, and elitism evolve the schedule. A greedy schedule seeds the population and provides the baseline.

The decoder appends flights to each aircraft route, inserts empty repositioning legs, and respects location continuity, availability, seats, nonstop range, turnaround, departure-delay limits, horizon, and aircraft block-hour limits. Requests that violate a limit remain unserved. The search is a heuristic and does not certify an optimum.

This educational model omits crew duty/rest rules, maintenance, weather, airport slots, runway compatibility, fuel reserves, refueling stops, and return-to-base requirements. Aircraft parameters and requests are fictional. The block-hour limit is an aircraft utilization setting, not a crew legality check.

**Data sources:** [JETNET flight activity](https://www.jetnet.com/data/flight-activity) describes live and historical activity. Its [charter-broker API documentation](https://support.jetnet.com/hc/en-us/articles/42988907991437-API-for-Charter-Brokers-Flight-Event-History) states that flight and history endpoints require subscription add-ons. Historical movement data do not establish future charter availability. No free public JETNET future-schedule dataset was identified.

[BTS on-time data](https://transtats.bts.gov/ONTIME/) offer public scheduled and actual times for reporting airlines; these are useful for airline experiments, rather than private-jet booking requests. This app makes no external API calls.
''')
    st.dataframe(pd.DataFrame([dict(airport=a,state=v[0],latitude=v[1],longitude=v[2]) for a,v in AIRPORTS.items()]),hide_index=True)
