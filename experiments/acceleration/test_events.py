import tempfile, unittest
from pathlib import Path
from event_metrics import measure
class EventTests(unittest.TestCase):
    def test_censored_wait_and_completed_leg(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'events.xml'
            p.write_text('''<events>
<event time="0" type="departure" person="a" legMode="pt" />
<event time="1" type="waitingForPt" person="a" />
<event time="0" type="departure" person="b" legMode="car" />
<event time="1" type="vehicle enters traffic" person="b" vehicle="v" networkMode="car" />
<event time="2" type="entered link" vehicle="v" link="entry" />
<event time="2" type="personMoney" person="b" amount="-9" purpose="toll" />
<event time="10" type="arrival" person="b" legMode="car" />
<event time="20" type="stuckAndAbort" person="a" legMode="pt" />
</events>''')
            r=measure(p,{b'a',b'b'},{b'entry'},20)
            self.assertEqual(r['errors'],{});self.assertEqual(r['unfinished_all'],1)
            self.assertAlmostEqual(r['censored_wait_person_hours'],19/3600)
            self.assertEqual(r['net_congestion_revenue'],9)
            self.assertEqual(r['private_car_entry_crossings'],1)
            self.assertEqual(r['mean_completed_car_leg_seconds'],10)
if __name__=='__main__':unittest.main()
