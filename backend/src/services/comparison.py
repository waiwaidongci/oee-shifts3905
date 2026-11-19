import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.models.run import Run, RunComparison
from src.services.attribution import build_explanation
from src.services.audit import log
from src.services.oee_math import summary_from_sources
from src.services.snapshot import checksum as snapshot_checksum

SUMMARY_KEYS = ('计划分钟', '运行分钟', '可用率', '性能', '节拍加权质量率', '汇总OEE')
TOLERANCE = 1e-9


def pair_key(first_id, second_id):
    """一对报告（不计基期/对比期先后）的唯一键，重跑与并发都落到同一结论。"""
    low, high = sorted((int(first_id), int(second_id)))
    raw = json.dumps({'pair': [low, high]}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _reattest(run):
    """校验冻结快照完整、校验和有效且与复核结果可对账；任一不成立即拒绝发布。"""
    if not run:
        raise HTTPException(404, '报告不存在')
    if run.status != 'completed':
        raise HTTPException(409, f'报告 {run.id} 尚未完成，不能参与核对')
    if not run.approved:
        raise HTTPException(409, f'报告 {run.id} 尚未复核，不能参与核对')
    if not run.snapshot or not run.result:
        raise HTTPException(409, f'报告 {run.id} 缺少冻结底稿或结果快照')
    if snapshot_checksum(run.snapshot) != run.checksum:
        raise HTTPException(409, f'报告 {run.id} 快照校验失效（checksum 不符），拒绝发布')
    try:
        recomputed = summary_from_sources(run.snapshot['sources'])
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        raise HTTPException(409, f'报告 {run.id} 冻结底稿无法重算：{exc}')
    stored = run.result.get('summary') or {}
    for key in SUMMARY_KEYS:
        try:
            stored_value = float(stored[key])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(409, f'报告 {run.id} 缺少可对账的 {key}，拒绝发布')
        if abs(stored_value - float(recomputed[key])) > TOLERANCE:
            raise HTTPException(409, f'报告 {run.id} 的 {key} 与冻结底稿重算无法对账，拒绝发布')
    return {
        'id': run.id,
        'name': run.name,
        'checksum': run.checksum,
        'period': run.snapshot.get('period'),
        'policy_version': run.snapshot.get('policy', {}).get('version'),
        'review': run.review,
        'source_rows': len(run.snapshot['sources']),
        'summary': {key: stored[key] for key in SUMMARY_KEYS},
    }


def existing(db, first_id, second_id):
    return db.query(RunComparison).filter_by(pair_key=pair_key(first_id, second_id)).first()


def _note_reuse(db, user, first_id, second_id, prior):
    """重跑/并发/反向复用既有结论时只留痕，不新立结论。"""
    note = f'{first_id}->{second_id}:#{prior.id}'
    if (prior.base_run_id, prior.head_run_id) != (first_id, second_id):
        note += '（反向请求，沿用已有基期→对比期结论）'
    log(db, user.email, 'comparison.reuse', note)
    db.commit()
    return prior


def compare(db, user, base_id, head_id):
    """同一对报告只保留一份结论：已有记录直接复用，并发插入由唯一键兜底。

    复用前仍重验两端快照；任一端校验失效则拒绝发布，不返回可能已过期的结论。
    """
    if base_id == head_id:
        raise HTTPException(422, '基期与对比期必须是两份不同报告')
    base = db.get(Run, base_id)
    head = db.get(Run, head_id)
    base_meta = _reattest(base)
    head_meta = _reattest(head)
    prior = existing(db, base_id, head_id)
    if prior:
        return _note_reuse(db, user, base_id, head_id, prior)

    explanation = build_explanation(
        base.snapshot['sources'], head.snapshot['sources'],
        base.result['summary'], head.result['summary'],
        base_meta, head_meta,
    )
    reconciliation = explanation['reconciliation']
    if not reconciliation['reconciled']:
        log(db, user.email, 'comparison.reject', f'{base_id}->{head_id}:残差 {reconciliation["residual"]}')
        db.commit()
        raise HTTPException(409, {
            'message': '分项归因无法加回汇总 OEE 差值，拒绝发布',
            'reconciliation': reconciliation,
        })

    obj = RunComparison(
        base_run_id=base_id,
        head_run_id=head_id,
        pair_key=pair_key(base_id, head_id),
        status='reconciled',
        checksum=hashlib.sha256(json.dumps(explanation, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        result=explanation,
        error=None,
        actor=user.email,
        created=time.time(),
    )
    db.add(obj)
    try:
        log(db, user.email, 'comparison.create', f'{base_id}->{head_id}')
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = existing(db, base_id, head_id)
        if prior:
            return _note_reuse(db, user, base_id, head_id, prior)
        raise HTTPException(409, '同一对报告的核对正在并发处理，请稍后刷新')
    return obj


def list_comparisons(db):
    return db.query(RunComparison).order_by(RunComparison.id.desc()).all()


def get_comparison(db, id):
    obj = db.get(RunComparison, id)
    if not obj:
        raise HTTPException(404, '核对记录不存在')
    return obj
