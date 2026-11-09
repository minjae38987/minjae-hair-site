import copy
import unittest
from chatcut.brand_strategy_v1 import analyze,validate,ROLES
from pathlib import Path
import json
FIXTURE=json.loads((Path(__file__).resolve().parent / "fixtures" / "individual_brand_evidence_20261109.json").read_text(encoding="utf8"))
class BrandStrategyTests(unittest.TestCase):
    def test_six_roles_preserved(self):
        out=analyze(FIXTURE)
        self.assertEqual(set(out["roles"]),set(ROLES))
        self.assertFalse(out["auto_publish"])
        self.assertFalse(out["roles"]["editor"]["video_rendered"])
    def test_individual_not_salon(self):
        out=analyze(FIXTURE)
        self.assertEqual(len(out["individual_competitors"]),5)
        self.assertEqual(len({x["designer_id"] for x in out["individual_competitors"]}),5)
        self.assertIsNone(out["individual_competitors"][0]["booking_performance"])
    def test_uncertainty_remains(self):
        out=analyze(FIXTURE)
        self.assertFalse(out["quality"]["pass"])
        self.assertFalse(out["brand"]["unique_skill_proven"])
        self.assertIsNone(out["conversion"]["paid_new_customers"])
        self.assertIn("mirror_based_comparisons_need_official_confirmation",out["quality"]["blockers"])
    def test_channel_constraints(self):
        out=analyze(FIXTURE)["channel_copy"]
        self.assertEqual(len(out),5)
        self.assertEqual(len(out["instagram"]["hashtags"]),5)
        self.assertEqual(len(set(out["instagram"]["hashtags"])),5)
        self.assertIn("프로필",out["youtube_shorts"]["cta"])
        self.assertIn("booking.naver.com",out["naver_place"]["booking_url"])
    def test_no_guaranteed_claims(self):
        o=analyze(FIXTURE)
        for row in o["channel_copy"].values():
            self.assertNotIn("100% 보장",row["body"])
    def test_duplicate_designer_rejected(self):
        x=copy.deepcopy(FIXTURE);x["competitors"].append(copy.deepcopy(x["competitors"][0]))
        with self.assertRaises(ValueError):validate(x)
    def test_fake_count_rejected(self):
        x=copy.deepcopy(FIXTURE);x["competitors"][0]["review_count"]=True
        with self.assertRaises(ValueError):validate(x)
    def test_missing_evidence_rejected(self):
        x=copy.deepcopy(FIXTURE);x["competitors"][0]["source_url"]="http://example.com"
        with self.assertRaises(ValueError):validate(x)
    def test_invalid_date_rejected(self):
        x=copy.deepcopy(FIXTURE);x["competitors"][0]["observed_at"]="2026-11-33"
        with self.assertRaises(ValueError):validate(x)
    def test_customer_segments(self):
        o=analyze(FIXTURE)
        self.assertEqual(len(o["customer_segments"]),3)
        self.assertTrue(all(not x["result_proven"] for x in o["customer_segments"]))
if __name__=="__main__":unittest.main()
