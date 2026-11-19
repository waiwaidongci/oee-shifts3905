import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

_TMP = tempfile.mkdtemp(prefix='oee-test-')
os.environ.setdefault('PROJECT_FILE', str(BACKEND / 'project.json'))
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + _TMP + '/test.db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6399/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')

sys.path.insert(0, str(BACKEND))

from fastapi import HTTPException  # noqa: E402
from src.config.database import Base, Session, engine  # noqa: E402
from src.models import identity, run  # noqa: E402
from src.models.identity import User  # noqa: E402
from src.models.run import Run, RunComparison  # noqa: E402
from src.services.calculation import calculate  # noqa: E402
from src.services.comparison import compare  # noqa: E402
from src.services.snapshot import checksum as snapshot_checksum  # noqa: E402

POLICY = {'version': 'OEE-v1', 'definition': '测试口径'}


def src(period, device, total=900, good=872, end=1020, downtime=None):
    return {
        'period': period, 'department': device, 'start': 480, 'end': end,
        'ideal_seconds': 25, 'total': total, 'good': good,
        'downtime': downtime if downtime is not None else [[540, 570], [560, 590]],
    }


class ComparisonTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)

    def setUp(self):
        with Session() as db:
            db.query(RunComparison).delete()
            db.query(Run).delete()
            db.query(User).delete()
            db.add_all([
                User(email='admin@demo.local', role='admin', password='x'),
                User(email='viewer@demo.local', role='viewer', password='x'),
            ])
            db.commit()

    def make_run(self, name, sources, approved=True, stored_summary=None, checksum_override=None, status='completed'):
        snapshot = {'policy': POLICY, 'sources': sources, 'period': '全部'}
        result = calculate(sources, POLICY)
        if stored_summary is not None:
            result['summary'] = stored_summary
        with Session() as db:
            obj = Run(
                name=name, status=status, snapshot=snapshot,
                checksum=checksum_override or snapshot_checksum(snapshot),
                result=result, created=1.0, approved=approved, review='已核对口径与业务结论',
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj.id

    def admin(self):
        with Session() as db:
            return db.query(User).filter_by(email='admin@demo.local').first()

    def pair(self):
        base_sources = [src('2026-11-01', '试制机A'), src('2026-11-01', '试制机B', total=700, good=650, downtime=[[540, 600]])]
        head_sources = [
            src('2026-11-02', '试制机A', end=1140, total=1000, good=900, downtime=[[540, 560]]),
            src('2026-11-02', '试制机C', total=800, good=780),
        ]
        return self.make_run('基期', base_sources), self.make_run('对比期', head_sources)

    def test_reconciled_comparison_persists_and_sums_back(self):
        base_id, head_id = self.pair()
        with Session() as db:
            obj = compare(db, self.admin(), base_id, head_id)
            self.assertEqual(obj.status, 'reconciled')
            rec = obj.result['reconciliation']
            self.assertTrue(rec['reconciled'])
            self.assertAlmostEqual(rec['sum_effect'], rec['oee_delta'], places=12)
            self.assertAlmostEqual(rec['residual'], 0.0, places=12)
            self.assertEqual([d['device'] for d in obj.result['devices']['entered']], ['试制机C'])
            self.assertEqual([d['device'] for d in obj.result['devices']['exited']], ['试制机B'])

    def test_rerun_reuses_single_conclusion(self):
        base_id, head_id = self.pair()
        with Session() as db:
            first = compare(db, self.admin(), base_id, head_id)
        with Session() as db:
            second = compare(db, self.admin(), base_id, head_id)
        self.assertEqual(first.id, second.id)
        with Session() as db:
            self.assertEqual(db.query(RunComparison).count(), 1)

    def test_reversed_and_concurrent_requests_share_one_conclusion(self):
        base_id, head_id = self.pair()
        with Session() as db:
            first = compare(db, self.admin(), base_id, head_id)
        with Session() as db:
            reversed_obj = compare(db, self.admin(), head_id, base_id)
        self.assertEqual(first.id, reversed_obj.id)
        with Session() as db:
            self.assertEqual(db.query(RunComparison).count(), 1)

    def test_tampered_snapshot_is_rejected(self):
        base_id, head_id = self.pair()
        with Session() as db:
            run_obj = db.get(Run, base_id)
            run_obj.snapshot = {'policy': POLICY, 'sources': [src('2026-11-01', '试制机A', total=1)], 'period': '全部'}
            db.commit()
        with Session() as db, self.assertRaises(HTTPException) as ctx:
            compare(db, self.admin(), base_id, head_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn('快照校验失效', ctx.exception.detail)
        with Session() as db:
            self.assertEqual(db.query(RunComparison).count(), 0)

    def test_stored_summary_that_cannot_be_reconciled_is_rejected(self):
        base_id, head_id = self.pair()
        with Session() as db:
            run_obj = db.get(Run, head_id)
            run_obj.result = dict(run_obj.result)
            run_obj.result['summary'] = dict(run_obj.result['summary'], 汇总OEE=0.123)
            db.commit()
        with Session() as db, self.assertRaises(HTTPException) as ctx:
            compare(db, self.admin(), base_id, head_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn('无法对账', ctx.exception.detail)

    def test_reuse_revalidates_snapshots_before_returning_prior(self):
        base_id, head_id = self.pair()
        with Session() as db:
            first = compare(db, self.admin(), base_id, head_id)
        with Session() as db:
            run_obj = db.get(Run, head_id)
            run_obj.checksum = '0' * 64
            db.commit()
        with Session() as db, self.assertRaises(HTTPException) as ctx:
            compare(db, self.admin(), base_id, head_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn('快照校验失效', ctx.exception.detail)
        with Session() as db:
            self.assertEqual(db.query(RunComparison).count(), 1)
            self.assertEqual(db.get(RunComparison, first.id).status, 'reconciled')

    def test_unapproved_report_cannot_be_compared(self):
        base_id, _ = self.pair()
        head_id = self.make_run('未复核', [src('2026-11-02', '试制机A')], approved=False)
        with Session() as db, self.assertRaises(HTTPException) as ctx:
            compare(db, self.admin(), base_id, head_id)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn('尚未复核', ctx.exception.detail)

    def test_same_report_twice_is_rejected(self):
        base_id, _ = self.pair()
        with Session() as db, self.assertRaises(HTTPException) as ctx:
            compare(db, self.admin(), base_id, base_id)
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == '__main__':
    unittest.main()
