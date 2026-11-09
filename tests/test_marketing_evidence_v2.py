import csv, tempfile, unittest
from pathlib import Path
from scripts.marketing_evidence_v2 import FIELDS,load,compute,briefs
class EvidenceTests(unittest.TestCase):
    def rows(self,items):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.csv'
            with p.open('w',encoding='utf8',newline='') as f:
                w=csv.writer(f);w.writerow(FIELDS);w.writerows(items)
            return load(p)
    def test_missing_not_zero(self):
        r=compute(self.rows([['2026-11-08','website','','','17','','','','GA4','includes_tests']]))
        self.assertEqual(r['total']['booking_click_events'],17)
        self.assertIsNone(r['paid_target_pct'])
        self.assertTrue(r['contains_unverified_traffic'])
    def test_confirmed_zero(self):
        r=compute(self.rows([['2026-11-08','shop','0','0','0','0','0','0','shop data','measured']]))
        self.assertEqual(r['paid_target_pct'],0)
    def test_partial_is_unknown(self):
        r=compute(self.rows([['2026-11-08','website','','','17','','','','GA4','unknown'],['2026-11-09','website','','','','','','','GA4','unknown']]))
        self.assertIsNone(r['total']['booking_click_events'])
    def test_duplicate(self):
        row=['2026-11-08','website','','','17','','','','GA4','unknown']
        with self.assertRaises(ValueError):self.rows([row,row])
    def test_negative(self):
        with self.assertRaises(ValueError):self.rows([['2026-11-08','website','','','-1','','','','GA4','unknown']])
    def test_bad_scope(self):
        with self.assertRaises(ValueError):self.rows([['2026-11-08','website','','','17','','','','GA4','definitely_customer']])
    def test_no_auto_publish(self):
        b=briefs();self.assertFalse(b['publish_approved']);self.assertEqual(len(b['items']),3)
if __name__=='__main__':unittest.main()
