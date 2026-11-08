"""Private jet scheduling example: synthetic specifications, common UTC clock."""
from dataclasses import dataclass, asdict
from math import radians, sin, cos, asin, sqrt, ceil, isfinite
import random
import time

AIRPORTS = {
    'TEB': ('NJ',40.85,-74.06), 'HPN': ('NY',41.07,-73.71),
    'BED': ('MA',42.47,-71.29), 'IAD': ('VA',38.95,-77.46),
    'PDK': ('GA',33.88,-84.30), 'OPF': ('FL',25.91,-80.28),
    'DAL': ('TX',32.85,-96.85), 'APA': ('CO',39.57,-104.85),
    'SDL': ('AZ',33.62,-111.91), 'VNY': ('CA',34.21,-118.49),
    'LAS': ('NV',36.08,-115.15), 'BFI': ('WA',47.53,-122.30),
    'MDW': ('IL',41.79,-87.75), 'BNA': ('TN',36.13,-86.68),
}

@dataclass(frozen=True)
class Aircraft:
    aircraft_id: str
    base: str
    seats: int
    range_nm: float
    speed_knots: float
    cost_per_hour: float
    available_min: int = 0

@dataclass(frozen=True)
class Request:
    request_id: str
    origin: str
    destination: str
    requested_min: int
    passengers: int
    priority: int = 1

@dataclass(frozen=True)
class Settings:
    horizon_hours: float = 24
    turnaround_min: int = 30
    max_delay_min: int = 180
    max_flight_hours: float = 10
    delay_cost_per_min: float = 50
    unserved_penalty: float = 100000
    population_size: int = 100
    generations: int = 100
    mutation_rate: float = .15
    crossover_rate: float = .9
    elitism: float = .05
    time_limit_seconds: float = 10
    seed: int = 42

def distance_nm(origin, destination):
    _, x1, y1 = AIRPORTS[origin]
    _, x2, y2 = AIRPORTS[destination]
    a,b = radians(x1),radians(x2)
    h = sin((b-a)/2)**2+cos(a)*cos(b)*sin(radians(y2-y1)/2)**2
    return 6880.13*asin(min(1,sqrt(h)))

def block_minutes(distance, aircraft):
    return 0 if distance == 0 else ceil(distance/aircraft.speed_knots*60+15)

def synthetic_data(fleet_size=6, request_count=24, horizon_hours=24, seed=42, airports=None):
    rng = random.Random(seed)
    airports = list(AIRPORTS) if airports is None else list(airports)
    if len(airports)<2 or len({AIRPORTS[a][0] for a in airports})<2:
        raise ValueError('Select airports in at least two states.')
    fleet=[]
    for i in range(fleet_size):
        seats,ran,speed,cost = rng.choice([(7,1800,400,2600),(9,3000,450,4200),(13,5000,480,6500)])
        fleet.append(Aircraft(f'DEMO-{i+1:02}',rng.choice(airports),seats,ran,speed,cost))
    requests=[]
    for i in range(request_count):
        origin=rng.choice(airports)
        dest=rng.choice([a for a in airports if AIRPORTS[a][0]!=AIRPORTS[origin][0]])
        requests.append(Request(f'REQ-{i+1:03}',origin,dest,rng.randrange(max(1,int(horizon_hours*60)-180)),rng.randint(2,10),rng.choice([1,1,2,3])))
    return fleet,sorted(requests,key=lambda r:r.requested_min)

def _number(value,name,low,high,integer=False):
    try: result=float(value)
    except (TypeError,ValueError): raise ValueError(f'{name} must be numeric.') from None
    if not isfinite(result) or not low<=result<=high or (integer and not result.is_integer()):
        raise ValueError(f'{name} must be a finite {"integer" if integer else "number"} between {low} and {high}.')
    return int(result) if integer else result

def parse_records(fleet_rows,request_rows,settings):
    if not 1<=len(fleet_rows)<=30 or not 1<=len(request_rows)<=150:
        raise ValueError('Provide 1-30 aircraft and 1-150 requests.')
    fleet=[]; requests=[]
    for row in fleet_rows:
        a=Aircraft(str(row['aircraft_id']).strip(),str(row['base']).strip().upper(),
            _number(row['seats'],'Seats',1,100,True),_number(row['range_nm'],'Range',1,10000),
            _number(row['speed_knots'],'Speed',100,700),_number(row['cost_per_hour'],'Hourly cost',1,100000),
            _number(row['available_min'],'Availability',0,settings.horizon_hours*60,True))
        if a.base not in AIRPORTS: raise ValueError(f'Unknown base: {a.base}')
        fleet.append(a)
    for row in request_rows:
        r=Request(str(row['request_id']).strip(),str(row['origin']).strip().upper(),str(row['destination']).strip().upper(),
            _number(row['requested_min'],'Requested departure',0,settings.horizon_hours*60-1,True),
            _number(row['passengers'],'Passengers',1,100,True),_number(row['priority'],'Priority',1,10,True))
        if r.origin not in AIRPORTS or r.destination not in AIRPORTS: raise ValueError(f'Unknown airport in {r.request_id}.')
        if AIRPORTS[r.origin][0]==AIRPORTS[r.destination][0]: raise ValueError(f'{r.request_id}: choose different states.')
        requests.append(r)
    for records,field in [(fleet,'aircraft_id'),(requests,'request_id')]:
        ids=[getattr(r,field) for r in records]
        if any(not x or x.lower() in ('nan','none') for x in ids) or len(set(ids))!=len(ids):
            raise ValueError(f'{field} values must be nonempty and unique.')
    return fleet,requests

class Problem:
    def __init__(self,fleet,requests,settings):
        self.fleet,self.requests,self.s=fleet,requests,settings
        self.dist={(a,b):distance_nm(a,b) for a in AIRPORTS for b in AIRPORTS}

    def decode(self,chromosome,detail=False):
        order,assignment=chromosome
        locations=[a.base for a in self.fleet]
        ready=[a.available_min for a in self.fleet]
        flown=[0]*len(self.fleet)
        legs=[]; unserved=[]
        cost=operating=delay_total=ferry_total=0.0
        served=0
        for idx in order:
            r=self.requests[idx]; j=assignment[idx]; a=self.fleet[j]
            ferry_dist=self.dist[locations[j],r.origin]; trip_dist=self.dist[r.origin,r.destination]
            ferry=block_minutes(ferry_dist,a); trip=block_minutes(trip_dist,a)
            departure=max(r.requested_min,ready[j]+ferry+(self.s.turnaround_min if ferry else 0))
            arrival=departure+trip; delay=departure-r.requested_min
            reason=None
            if r.passengers>a.seats: reason='Seat capacity'
            elif max(ferry_dist,trip_dist)>a.range_nm: reason='Nonstop range'
            elif delay>self.s.max_delay_min: reason='Departure delay limit'
            elif arrival>self.s.horizon_hours*60: reason='Planning horizon'
            elif flown[j]+ferry+trip>self.s.max_flight_hours*60: reason='Aircraft block-hour limit'
            if reason:
                cost+=self.s.unserved_penalty*r.priority
                if detail: unserved.append({**asdict(r),'assigned_aircraft':a.aircraft_id,'reason':reason})
                continue
            operation=(ferry+trip)/60*a.cost_per_hour
            cost+=operation+delay*self.s.delay_cost_per_min*r.priority
            operating+=operation; delay_total+=delay; ferry_total+=ferry; served+=1
            if detail:
                if ferry: legs.append(dict(aircraft=a.aircraft_id,request_id=r.request_id,kind='Reposition',origin=locations[j],destination=r.origin,start_min=ready[j],end_min=ready[j]+ferry,delay_min=0,passengers=0))
                legs.append(dict(aircraft=a.aircraft_id,request_id=r.request_id,kind='Passenger',origin=r.origin,destination=r.destination,start_min=departure,end_min=arrival,delay_min=delay,passengers=r.passengers))
            locations[j]=r.destination; ready[j]=arrival+self.s.turnaround_min; flown[j]+=ferry+trip
        return dict(objective=cost,operating_cost=operating,delay_minutes=delay_total,reposition_minutes=ferry_total,
                    served=served,unserved_count=len(self.requests)-served,legs=legs,unserved=unserved)

    def greedy(self):
        order=sorted(range(len(self.requests)),key=lambda i:self.requests[i].requested_min)
        assignment=[0]*len(order); prefix=[]
        for idx in order:
            prefix.append(idx); costs=[]
            for j in range(len(self.fleet)):
                assignment[idx]=j
                costs.append(self.decode((prefix,assignment))['objective'])
            assignment[idx]=min(range(len(costs)),key=costs.__getitem__)
        return order,assignment

def crossover(first,second,rng):
    n=len(first[0]); left,right=sorted(rng.sample(range(n+1),2))
    segment=first[0][left:right]; used=set(segment)
    remaining=[v for v in second[0] if v not in used]
    return remaining[:left]+segment+remaining[left:],[rng.choice([a,b]) for a,b in zip(first[1],second[1])]

def optimize(fleet,requests,settings,progress=None):
    if not fleet or not requests: raise ValueError('Fleet and requests cannot be empty.')
    if not 4<=settings.population_size<=500: raise ValueError('Population must be 4-500.')
    if not 0<=settings.mutation_rate<=1 or not 0<=settings.crossover_rate<=1: raise ValueError('Rates must be between zero and one.')
    if not 0<settings.elitism<1 or settings.generations<1 or settings.time_limit_seconds<=0: raise ValueError('Invalid search limits.')
    started=time.perf_counter(); rng=random.Random(settings.seed)
    problem=Problem(fleet,requests,settings)
    baseline=problem.greedy(); best=(baseline[0][:],baseline[1][:])
    best_score=problem.decode(best)['objective']; history=[dict(generation=0,best_objective=best_score)]
    population=[best]
    for _ in range(settings.population_size-1):
        order=list(range(len(requests))); rng.shuffle(order)
        population.append((order,[rng.randrange(len(fleet)) for _ in requests]))
    elite_count=max(1,int(settings.population_size*settings.elitism)); evaluations=0; stopped='Generation limit'
    for generation in range(1,settings.generations+1):
        scored=[]
        for chromosome in population:
            if time.perf_counter()-started>=settings.time_limit_seconds:
                stopped='Time budget'; break
            score=problem.decode(chromosome)['objective']; scored.append((score,chromosome)); evaluations+=1
            if score<best_score: best_score,best=score,(chromosome[0][:],chromosome[1][:])
        history.append(dict(generation=generation,best_objective=best_score))
        if progress: progress(generation/settings.generations,best_score)
        if stopped=='Time budget': break
        scored.sort(key=lambda pair:pair[0])
        population=[(c[0][:],c[1][:]) for _,c in scored[:elite_count]]
        while len(population)<settings.population_size:
            parents=[min(rng.choices(scored,k=3),key=lambda pair:pair[0])[1] for _ in range(2)]
            child=crossover(*parents,rng) if rng.random()<settings.crossover_rate else (parents[0][0][:],parents[0][1][:])
            if len(requests)>1 and rng.random()<settings.mutation_rate:
                i,j=rng.sample(range(len(requests)),2); child[0][i],child[0][j]=child[0][j],child[0][i]
            for i in range(len(requests)):
                if rng.random()<settings.mutation_rate: child[1][i]=rng.randrange(len(fleet))
            population.append(child)
    return dict(best=problem.decode(best,True),baseline=problem.decode(baseline,True),history=history,
                elapsed_seconds=time.perf_counter()-started,evaluations=evaluations,stopped=stopped,settings=asdict(settings))
