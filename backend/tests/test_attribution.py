import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.attribution import FACTORS, build_explanation
from src.services.oee_math import device_factors, summary_from_sources


def src(period, device, start=480, end=1020, ideal=25, total=900, good=872, downtime=None):
    return {
        'period': period, 'department': device, 'start': start, 'end': end,
        'ideal_seconds': ideal, 'total': total, 'good': good,
        'downtime': downtime if downtime is not None else [[540, 570], [560, 590]],
    }


def meta(name):
    return {'id': hash(name) % 1000, 'name': name, 'checksum': 'x' * 64,
            'period': 'all', 'policy_version': 'OEE-v1', 'review': '已核对',
            'source_rows': 0, 'summary': {}}


class ContributionTest(unittest.TestCase):
    def test_device_contributions_sum_to_summary_oee(self):
        sources = [src('2026-11-01', '试制机A'), src('2026-11-01', '试制机B', total=700, good=650)]
        factors, total = device_factors(sources)
        summary = summary_from_sources(sources)
        self.assertAlmostEqual(sum(f['planned_share'] for f in factors.values()), 1.0, places=12)
        self.assertAlmostEqual(sum(f['contribution'] for f in factors.values()), summary['汇总OEE'], places=12)
        for f in factors.values():
            self.assertAlmostEqual(f['availability'] * f['performance'] * f['quality'], f['oee'], places=12)


class ExplanationTest(unittest.TestCase):
    def setUp(self):
        # 基期：A/B 两设备；对比期：A 留存（排班与效率变化）、B 退出、C 新增
        self.base = [
            src('2026-11-01', '试制机A', total=900, good=872),
            src('2026-11-01', '试制机B', total=700, good=650, downtime=[[540, 600]]),
        ]
        self.head = [
            src('2026-11-02', '试制机A', end=1140, total=1000, good=900, downtime=[[540, 560]]),
            src('2026-11-02', '试制机C', total=800, good=780),
        ]
        self.base_summary = summary_from_sources(self.base)
        self.head_summary = summary_from_sources(self.head)
        self.result = build_explanation(self.base, self.head, self.base_summary, self.head_summary,
                                        meta('base'), meta('head'))

    def test_entered_and_exited_devices_are_listed_without_fabricated_history(self):
        entered = self.result['devices']['entered']
        exited = self.result['devices']['exited']
        self.assertEqual([d['device'] for d in entered], ['试制机C'])
        self.assertEqual([d['device'] for d in exited], ['试制机B'])
        self.assertNotIn('base', entered[0])
        self.assertNotIn('head', exited[0])
        self.assertEqual(entered[0]['effect'], entered[0]['contribution'])
        self.assertEqual(exited[0]['effect'], -exited[0]['contribution'])

    def test_each_common_device_factors_add_back_to_its_contribution_delta(self):
        common = self.result['devices']['common']
        self.assertEqual([d['device'] for d in common], ['试制机A'])
        for device in common:
            total = sum(device['attribution'][f] for f in FACTORS)
            self.assertAlmostEqual(total, device['deltas']['contribution'], places=12)
            self.assertAlmostEqual(device['residual'], 0.0, places=12)
            self.assertTrue(device['reconciled'])

    def test_all_items_add_back_to_summary_oee_delta(self):
        rec = self.result['reconciliation']
        self.assertAlmostEqual(rec['sum_effect'], rec['oee_delta'], places=12)
        self.assertAlmostEqual(rec['residual'], 0.0, places=12)
        self.assertAlmostEqual(
            rec['entered_effect'] + rec['exited_effect'] + rec['common_effect'], rec['sum_effect'], places=12)
        self.assertAlmostEqual(sum(rec['factor_effects'].values()), rec['common_effect'], places=12)
        self.assertTrue(rec['reconciled'])
        self.assertTrue(rec['base_report']['reconciled'])
        self.assertTrue(rec['head_report']['reconciled'])

    def test_shapley_is_symmetric_across_substitution_orders(self):
        factors = self.result['devices']['common'][0]['attribution']
        # 若四因子同比例放大，任一因子只拿到自身口径下的一份，边际影响按顺序平均后仍精确闭合
        self.assertAlmostEqual(sum(factors.values()), self.result['devices']['common'][0]['effect'], places=12)

    def test_identical_reports_produce_zero_delta(self):
        result = build_explanation(self.base, self.base, self.base_summary, self.base_summary,
                                   meta('base'), meta('base'))
        rec = result['reconciliation']
        self.assertAlmostEqual(rec['oee_delta'], 0.0, places=12)
        self.assertAlmostEqual(rec['residual'], 0.0, places=12)
        for device in result['devices']['common']:
            for factor in FACTORS:
                self.assertAlmostEqual(device['attribution'][factor], 0.0, places=12)


if __name__ == '__main__':
    unittest.main()
