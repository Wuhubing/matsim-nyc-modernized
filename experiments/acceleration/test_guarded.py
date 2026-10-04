import gzip,tempfile,unittest
from pathlib import Path
import xml.etree.ElementTree as E
from guarded_transfer import transfer
class GuardedTests(unittest.TestCase):
    def test_noninnovating_group_keeps_cold_plan(self):
        def person(pid,group,mode):
            return f'<person id="{pid}"><attributes><attribute name="subpopulation">{group}</attribute></attributes><plan selected="yes"><leg mode="{mode}"/></plan></person>'
        with tempfile.TemporaryDirectory() as d:
            cold,warm,out=[Path(d)/s for s in ['cold.xml','warm.xml','out.xml.gz']]
            cold.write_text('<population>'+person('1','outside','car')+person('2','man','walk')+'</population>')
            warm.write_text('<population>'+person('1','outside','taxi')+person('2','man','pt')+'</population>')
            result=transfer(cold,warm,out)
            with gzip.open(out) as f:root=E.parse(f).getroot()
            self.assertEqual(result['persons'],2);self.assertEqual(result['replaced_with_cold'],1)
            self.assertEqual(root.find("person[@id='1']/plan/leg").get('mode'),'car')
            self.assertEqual(root.find("person[@id='2']/plan/leg").get('mode'),'pt')
if __name__=='__main__':unittest.main()
