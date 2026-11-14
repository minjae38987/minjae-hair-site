import unittest
from datetime import date
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'local_seo_intelligence.py'
spec = importlib.util.spec_from_file_location('local_seo_intelligence', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TestLocalSEOIntelligence(unittest.TestCase):
    def setUp(self):
        self.source = {'competitors': [{'designer_id': 'x', 'name': '테스트', 'salon': '예시',
            'observed_at': '2026-11-09', 'source_type': 'third_party_mirror',
            'claims': ['모질별 상담'], 'styles': ['필러스컷', '다운펌'],
            'review_count': None, 'styling_count': None}]}

    def test_source_and_overlap(self):
        result = module.audit(self.source, date(2026, 11, 15))
        row = result['individuals'][0]
        self.assertEqual(row['source_grade'], 'D')
        self.assertTrue(row['requires_recheck'])
        self.assertIn('다운펌', row['overlap_terms'])
        self.assertIsNone(row['review_count_observed'])
        self.assertFalse(result['safety']['auto_publish'])

    def test_no_false_rank_claim(self):
        result = module.audit(self.source, date(2026, 11, 15))
        self.assertIn('실제 검색순위', result['not_measured'])
        self.assertFalse(result['keyword_clusters_hypotheses'][0]['serp_overlap_verified'])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            module.audit({'competitors': self.source['competitors'] * 2}, date(2026, 11, 15))

    def test_future_observation_rejected(self):
        with self.assertRaises(ValueError):
            module.audit(self.source, date(2026, 11, 1))

if __name__ == '__main__':
    unittest.main()
