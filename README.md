# Interstate private jet planner

An educational Streamlit app using fictional aircraft specifications and synthetic interstate passenger requests. No JETNET account or external data service is required.

## Start on Windows

Open this directory in a terminal and run:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

Or double-click `run_app.bat` if dependencies are already installed. Streamlit opens a local browser app, normally at http://localhost:8501. Stop it with Ctrl+C in the terminal. The app has been tested using the installed Python and Streamlit environment; it has not been published or started as a persistent server.

## Using the app

1. Select airports, fleet size, requests, horizon, and a data seed in the sidebar; generate a scenario.
2. Edit aircraft and requests directly or import CSV files using the sample schemas in `sample_data`.
3. Adjust population, generations, mutation, crossover, elite fraction, runtime, and search seed.
4. Set turnaround, delay tolerance, aircraft block-hour limits, and penalty weights. Choose a UTC start date.
5. Optimize and compare against the greedy baseline. Download the flight schedule and full run JSON.

All minute inputs are offsets from midnight UTC on the schedule date, even across time zones. For multiple days, minute 1500 is 01:00 UTC the next day. Airport codes are restricted to the 14 listed airports in 14 U.S. states. They are representative locations, not comprehensive coverage of every U.S. state. Aircraft IDs beginning DEMO are fictional identifiers.

## Model

A chromosome contains a request-order permutation and one aircraft index per request. Tournament selection picks parents. Order crossover preserves a valid request permutation; uniform crossover combines assignment genes. Mutation swaps request positions and independently changes aircraft assignments. Elitism keeps leading solutions. The chronological greedy baseline is a seed and an objective benchmark, so the returned GA objective cannot be worse than the baseline.

The decoder appends requests to aircraft routes, inserts empty repositioning legs, and uses the earliest departure no earlier than requested. It enforces seats, initial availability, aircraft location continuity, turnaround, nonstop range on each passenger/reposition leg, delay tolerance, planning horizon, and cumulative aircraft block hours. Rejected requests leave aircraft state unchanged and incur a penalty. Unserved reasons relate to the chosen aircraft and route order; they do not certify global infeasibility. The decoder does not insert flights into existing gaps or implement refueling stops.

Objective, minimized:

`sum(passenger and reposition block hours * aircraft hourly cost) + sum(delay minutes * delay weight * request priority) + sum(unserved penalty * request priority)`

Block time is great-circle distance / speed plus 15 minutes per nonzero leg. Range limits and costs are fictional simplifications. The block-hour cap is aircraft utilization, not a regulatory crew-duty calculation. The model omits crew/rest, maintenance, weather, airport capacity, runway compatibility, reserves, refueling, and return-to-base requirements. It cannot certify an optimum or operational legality.

The timer starts before baseline construction. Baseline setup, population creation, rendering, and an in-progress generation operation can extend wall time beyond the requested search budget. The engine checks the deadline before each candidate evaluation. Generation-limited runs reproduce with the same seeds; time-limited runs depend on machine speed. Tables and parameters stored with results are snapshots of the last run.

## Files and verification

- `scheduler.py`: data classes, synthetic generator, input validation, decoder, greedy baseline, GA.
- `streamlit_app.py`: interactive UI and downloads.
- `test_scheduler.py`: constraint rejection, route continuity, objective accounting, crossover validity, seeded reproducibility, baseline guarantee, bad-input handling, timeout fallback.
- `test_app.py`: app render, optimization, scenario reset.
- `sample_data`: synthetic aircraft/requests CSV and example output JSON.

Run tests:

```powershell
python -m unittest -v test_scheduler test_app
```

## Public data

JETNET describes live and historical flight activity at https://www.jetnet.com/data/flight-activity . Its public charter-broker API documentation explicitly states that flight/history endpoints require subscription add-ons:
https://support.jetnet.com/hc/en-us/articles/42988907991437-API-for-Charter-Brokers-Flight-Event-History

No free public JETNET dataset of future private-jet schedules was identified. Historical movements should not be treated as confirmed charter availability or bookings.

For public airline scheduled and actual departure/arrival data, see BTS: https://transtats.bts.gov/ONTIME/ . These cover reporting airlines and are not a substitute for private-jet booking requests. Sources checked November 7, 2026. No proprietary data are included.
