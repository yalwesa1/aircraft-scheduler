import unittest
import random
from dataclasses import asdict, replace
from scheduler import *

class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.a=Aircraft('TEST','TEB',9,5000,450,3000)
        self.r=Request('R1','TEB','OPF',60,4)
        self.s=Settings(population_size=20,generations=8,time_limit_seconds=20)

    def test_constraint_rejections(self):
        for aircraft,request,settings,reason in [
            (replace(self.a,seats=2),self.r,self.s,'Seat capacity'),
            (replace(self.a,range_nm=20),self.r,self.s,'Nonstop range'),
            (replace(self.a,available_min=500),self.r,self.s,'Departure delay limit'),
            (self.a,self.r,replace(self.s,horizon_hours=1),'Planning horizon'),
            (self.a,self.r,replace(self.s,max_flight_hours=.1),'Aircraft block-hour limit')]:
            result=Problem([aircraft],[request],settings).decode(([0],[0]),True)
            self.assertEqual(result['unserved'][0]['reason'],reason)
            self.assertFalse(result['legs'])

    def test_chaining_and_objective(self):
        requests=[self.r,Request('R2','DAL','VNY',400,3)]
        result=Problem([self.a],requests,replace(self.s,max_delay_min=720,max_flight_hours=24)).decode(([0,1],[0,0]),True)
        legs=result['legs']
        self.assertEqual(result['served'],2)
        self.assertEqual([r['kind'] for r in legs],['Passenger','Reposition','Passenger'])
        self.assertEqual(legs[0]['destination'],legs[1]['origin'])
        self.assertEqual(legs[1]['destination'],legs[2]['origin'])
        for first,second in zip(legs,legs[1:]):
            self.assertGreaterEqual(second['start_min'],first['end_min']+self.s.turnaround_min)
        expected=sum((r['end_min']-r['start_min'])/60*self.a.cost_per_hour for r in legs)+result['delay_minutes']*self.s.delay_cost_per_min
        self.assertAlmostEqual(result['objective'],expected)

    def test_crossover_is_permutation(self):
        rng=random.Random(42)
        for n in (1,2,25):
            for _ in range(50):
                first=(list(range(n)),[0]*n); second=(list(reversed(range(n))),[1]*n)
                child=crossover(first,second,rng)
                self.assertEqual(sorted(child[0]),list(range(n)))
                self.assertTrue(all(v in (0,1) for v in child[1]))

    def test_ga_baseline_reproducibility_and_routes(self):
        fleet,requests=synthetic_data()
        result=optimize(fleet,requests,self.s)
        duplicate=optimize(fleet,requests,self.s)
        self.assertEqual(result['best'],duplicate['best'])
        self.assertLessEqual(result['best']['objective'],result['baseline']['objective'])
        scores=[h['best_objective'] for h in result['history']]
        self.assertEqual(scores,sorted(scores,reverse=True))
        self.assertEqual(result['best']['served']+result['best']['unserved_count'],len(requests))
        by_id={r.request_id:r for r in requests}
        for a in fleet:
            legs=[l for l in result['best']['legs'] if l['aircraft']==a.aircraft_id]
            location=a.base; ready=a.available_min; total=0
            for leg in legs:
                self.assertEqual(location,leg['origin'])
                self.assertGreaterEqual(leg['start_min'],ready)
                self.assertLessEqual(distance_nm(leg['origin'],leg['destination']),a.range_nm)
                self.assertLessEqual(leg['end_min'],self.s.horizon_hours*60)
                if leg['kind']=='Passenger':
                    r=by_id[leg['request_id']]
                    self.assertLessEqual(r.passengers,a.seats)
                    self.assertGreaterEqual(leg['start_min'],r.requested_min)
                    self.assertLessEqual(leg['delay_min'],self.s.max_delay_min)
                total+=leg['end_min']-leg['start_min']
                ready=leg['end_min']+self.s.turnaround_min; location=leg['destination']
            self.assertLessEqual(total,self.s.max_flight_hours*60)

    def test_input_validation_and_timeout(self):
        rows=[asdict(self.a)]; requests=[asdict(self.r)]
        for value in [float('nan'),-1,2.5]:
            with self.assertRaises(ValueError): parse_records([{**rows[0],'seats':value}],requests,self.s)
        with self.assertRaises(ValueError): parse_records(rows,requests*2,self.s)
        result=optimize([self.a],[self.r],replace(self.s,time_limit_seconds=.000001))
        self.assertEqual(result['stopped'],'Time budget')
        self.assertEqual(result['best'],result['baseline'])

if __name__=='__main__': unittest.main()
