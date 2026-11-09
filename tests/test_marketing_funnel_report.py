import csv
import tempfile
import unittest
from pathlib import Path
from scripts.marketing_funnel_report import load_rows, report, FIELDS

class FunnelReportTest(unittest.TestCase):
    def test_aggregate_and_zero_denominator(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"input.csv"
            with path.open("w",encoding="utf-8",newline="") as f:
                w=csv.writer(f)
                w.writerow(FIELDS)
                w.writerow(["2026-11-09","instagram",100,20,3,2,1,1000])
                w.writerow(["2026-11-10","instagram",200,30,5,4,2,2000])
                w.writerow(["2026-11-10","unknown",0,0,0,0,1,0])
            output=report(load_rows(path))
            self.assertIn("4/100명",output)
            self.assertIn("300 | 50 | 8 | 6 | 3 | 3000",output)
            self.assertIn("N/A",report([]))

    def test_reject_negative_value(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.csv"
            path.write_text(",".join(FIELDS)+"\\n2026-11-09,instagram,0,0,0,0,-1,0\\n",encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rows(path)

if __name__ == "__main__":
    unittest.main()
