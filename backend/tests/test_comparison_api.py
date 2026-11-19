import os
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp(prefix='oee-api-test-')
os.environ.setdefault('PROJECT_FILE', str(BACKEND / 'project.json'))
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + _TMP + '/api.db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6399/0')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('SEED_DEMO', 'false')

sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402
from src.config.database import Session  # noqa: E402
from src.models.identity import User  # noqa: E402
from src.models.run import Run, RunComparison  # noqa: E402
from src.services.calculation import calculate  # noqa: E402
from src.services.snapshot import checksum as snapshot_checksum  # noqa: E402
from src.utils.security import password_hash, token  # noqa: E402

POLICY = {'version': 'OEE-v1', 'definition': '测试口径'}


def src(period, device, total=900, good=872, end=1020, downtime=None):
    return {
        'period': period, 'department': device, 'start': 480, 'end': end,
        'ideal_seconds': 25, 'total': total, 'good': good,
        'downtime': downtime if downtime is not None else [[540, 570], [560, 590]],
    }


class ComparisonApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        with Session() as db:
            db.query(RunComparison).delete()
            db.query(Run).delete()
            db.query(User).filter(User.email.in_(['admin@demo.local', 'viewer@demo.local'])).delete(synchronize_session=False)
            for email, role in (('admin@demo.local', 'admin'), ('viewer@demo.local', 'viewer')):
                db.add(User(email=email, role=role, password=password_hash('Demo2026!')))
            db.commit()
        self.admin_headers = self._login('admin@demo.local')
        self.viewer_headers = self._login('viewer@demo.local')

    def _login(self, email):
        response = self.client.post('/auth/login', json={'email': email, 'password': 'Demo2026!'})
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['token']}

    def _run(self, name, sources, approved=True):
        snapshot = {'policy': POLICY, 'sources': sources, 'period': '全部'}
        with Session() as db:
            obj = Run(name=name, status='completed', snapshot=snapshot, checksum=snapshot_checksum(snapshot),
                      result=calculate(sources, POLICY), created=1.0, approved=approved, review='已核对口径与业务结论')
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj.id

    def _pair(self):
        return (
            self._run('基期', [src('2026-11-01', '试制机A'), src('2026-11-01', '试制机B', total=700, good=650)]),
            self._run('对比期', [src('2026-11-02', '试制机A', end=1140, total=1000, good=900), src('2026-11-02', '试制机C')]),
        )

    def test_viewer_sees_explanations_and_cannot_create(self):
        base_id, head_id = self._pair()
        created = self.client.post('/comparisons', json={'base_run_id': base_id, 'head_run_id': head_id}, headers=self.admin_headers)
        self.assertEqual(created.status_code, 200, created.text)
        listing = self.client.get('/comparisons', headers=self.viewer_headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)
        detail = self.client.get(f"/comparisons/{listing.json()[0]['id']}", headers=self.viewer_headers)
        self.assertEqual(detail.status_code, 200)
        self.assertLess(abs(detail.json()['result']['reconciliation']['residual']), 1e-12)
        forbidden = self.client.post('/comparisons', json={'base_run_id': base_id, 'head_run_id': head_id}, headers=self.viewer_headers)
        self.assertEqual(forbidden.status_code, 403)

    def test_repeat_calls_keep_one_record(self):
        base_id, head_id = self._pair()
        first = self.client.post('/comparisons', json={'base_run_id': base_id, 'head_run_id': head_id}, headers=self.admin_headers)
        second = self.client.post('/comparisons', json={'base_run_id': head_id, 'head_run_id': base_id}, headers=self.admin_headers)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(len(self.client.get('/comparisons', headers=self.admin_headers).json()), 1)

    def test_tampered_report_returns_409(self):
        base_id, head_id = self._pair()
        with Session() as db:
            run_obj = db.get(Run, base_id)
            run_obj.checksum = '0' * 64
            db.commit()
        response = self.client.post('/comparisons', json={'base_run_id': base_id, 'head_run_id': head_id}, headers=self.admin_headers)
        self.assertEqual(response.status_code, 409)
        self.assertIn('快照校验失效', response.json()['detail'])
        self.assertEqual(self.client.get('/comparisons', headers=self.admin_headers).json(), [])


if __name__ == '__main__':
    unittest.main()
