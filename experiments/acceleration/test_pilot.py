import gzip, tempfile, unittest
from pathlib import Path
import xml.etree.ElementTree as E
import pilot

class PilotTests(unittest.TestCase):
    def test_selected_plan_transfer_drops_stale_scores_and_alternatives(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'source.xml';dst=Path(d)/'result.xml.gz'
            src.write_text('<population><person id="1"><attributes><attribute name="subpopulation">man</attribute></attributes><plan selected="no" score="100"><activity type="Home"/></plan><plan selected="yes" score="-9"><activity type="Home" end_time="08:00:00"/><leg mode="car"><route>1 2</route></leg><activity type="Work"/></plan></person></population>')
            result=pilot.selected_only(src,dst)
            with gzip.open(dst) as f:r=E.parse(f).getroot()
            plans=r.findall('person/plan')
            self.assertEqual(result['persons'],1);self.assertEqual(len(plans),1)
            self.assertNotIn('score',plans[0].attrib)
            self.assertEqual(plans[0].find('leg/route').text,'1 2')
            self.assertEqual(plans[0].find('activity').get('end_time'),'08:00:00')
    def test_stability_needs_all_metrics_and_three_observations(self):
        row=dict(score=-10,car_share=.2,pt_share=.4,unfinished=40000)
        self.assertFalse(pilot.stable([row,row]))
        self.assertTrue(pilot.stable([row,row,row]))
        self.assertFalse(pilot.stable([row,row,dict(row,unfinished=42000)]))
        self.assertFalse(pilot.stable([row,row,dict(row,score=float('nan'))]))
    def test_ambiguous_selected_plan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.xml';p.write_text('<population><person id="1"><plan selected="yes"/><plan selected="yes"/></person></population>')
            with self.assertRaises(ValueError):pilot.selected_only(p,Path(d)/'x.gz')

if __name__=='__main__':unittest.main()
