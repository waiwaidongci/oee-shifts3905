"""两份冻结底稿的 OEE 差值归因（纯计算，无框架/数据库依赖）。

口径：
- 设备 OEE = 可用率 × 性能 × 节拍加权质量率 = 理想合格分钟 / 计划分钟；
- 设备贡献 = 计划时长占比 × 设备 OEE，全部设备贡献合计等于报告汇总 OEE；
- 存量设备的贡献变化按 计划时长占比/可用率/性能/质量率 四个因子，
  对所有 4! 种替换顺序取平均边际影响（Shapley 分解），四项之和精确等于贡献变化；
- 新增/退出设备只列本期/基期自身贡献，不虚构另一期历史；
- 全部影响之和必须加回两份报告的汇总 OEE 差值。
"""

from itertools import permutations

from src.services.oee_math import device_factors

FACTORS = ('share', 'availability', 'performance', 'quality')
FACTOR_LABELS = {
    'share': '计划时长占比',
    'availability': '可用率',
    'performance': '性能',
    'quality': '节拍加权质量率',
}
TOLERANCE = 1e-9


def _product(values):
    result = 1.0
    for factor in FACTORS:
        result *= values[factor]
    return result


def shapley(base, head):
    """四因子乘法模型在所有替换顺序下的平均边际影响。"""
    totals = {factor: 0.0 for factor in FACTORS}
    orders = list(permutations(FACTORS))
    for order in orders:
        current = dict(base)
        previous = _product(current)
        for factor in order:
            current[factor] = head[factor]
            value = _product(current)
            totals[factor] += value - previous
            previous = value
    return {factor: totals[factor] / len(orders) for factor in FACTORS}


def _vector(factors):
    return {
        'share': factors['planned_share'],
        'availability': factors['availability'],
        'performance': factors['performance'],
        'quality': factors['quality'],
    }


def _device_row(name, factors, direction):
    return {
        'device': name,
        'direction': direction,
        'rows': factors['rows'],
        'planned_minutes': factors['planned_minutes'],
        'operating_minutes': factors['operating_minutes'],
        'planned_share': factors['planned_share'],
        'availability': factors['availability'],
        'performance': factors['performance'],
        'quality': factors['quality'],
        'oee': factors['oee'],
        'contribution': factors['contribution'],
        'effect': factors['contribution'] if direction == 'enter' else -factors['contribution'],
        'note': '本期新增设备，不补造基期历史' if direction == 'enter' else '本期退出设备，不补造本期历史',
    }


def _common_row(name, base, head):
    base_vector = _vector(base)
    head_vector = _vector(head)
    attribution = shapley(base_vector, head_vector)
    delta = head['contribution'] - base['contribution']
    residual = sum(attribution.values()) - delta
    return {
        'device': name,
        'direction': 'common',
        'base': {
            'rows': base['rows'],
            'planned_minutes': base['planned_minutes'],
            'planned_share': base['planned_share'],
            'availability': base['availability'],
            'performance': base['performance'],
            'quality': base['quality'],
            'oee': base['oee'],
            'contribution': base['contribution'],
        },
        'head': {
            'rows': head['rows'],
            'planned_minutes': head['planned_minutes'],
            'planned_share': head['planned_share'],
            'availability': head['availability'],
            'performance': head['performance'],
            'quality': head['quality'],
            'oee': head['oee'],
            'contribution': head['contribution'],
        },
        'deltas': {
            'planned_share': head['planned_share'] - base['planned_share'],
            'availability': head['availability'] - base['availability'],
            'performance': head['performance'] - base['performance'],
            'quality': head['quality'] - base['quality'],
            'oee': head['oee'] - base['oee'],
            'contribution': delta,
        },
        'attribution': attribution,
        'residual': residual,
        'reconciled': abs(residual) <= TOLERANCE,
        'effect': delta,
    }


def _report_check(factors, summary):
    total = sum(item['contribution'] for item in factors.values())
    summary_oee = summary.get('汇总OEE', 0.0)
    residual = total - summary_oee
    return {
        'device_contributions': total,
        'summary_oee': summary_oee,
        'residual': residual,
        'reconciled': abs(residual) <= TOLERANCE,
    }


def build_explanation(base_sources, head_sources, base_summary, head_summary, base_meta, head_meta):
    """生成差值归因结果；调用方负责快照校验，本函数保证分项可加回汇总差值。"""
    base_factors, _ = device_factors(base_sources)
    head_factors, _ = device_factors(head_sources)

    common_names = sorted(set(base_factors) & set(head_factors))
    entered_names = sorted(set(head_factors) - set(base_factors))
    exited_names = sorted(set(base_factors) - set(head_factors))

    common = [_common_row(name, base_factors[name], head_factors[name]) for name in common_names]
    entered = [_device_row(name, head_factors[name], 'enter') for name in entered_names]
    exited = [_device_row(name, base_factors[name], 'exit') for name in exited_names]

    factor_effects = {
        factor: sum(item['attribution'][factor] for item in common) for factor in FACTORS
    }
    entered_effect = sum(item['effect'] for item in entered)
    exited_effect = sum(item['effect'] for item in exited)
    common_effect = sum(item['effect'] for item in common)
    sum_effect = entered_effect + exited_effect + common_effect
    oee_delta = head_summary['汇总OEE'] - base_summary['汇总OEE']
    residual = sum_effect - oee_delta

    base_check = _report_check(base_factors, base_summary)
    head_check = _report_check(head_factors, head_summary)
    reconciled = (
        abs(residual) <= TOLERANCE
        and base_check['reconciled']
        and head_check['reconciled']
        and all(item['reconciled'] for item in common)
    )

    summary_delta = {
        key: head_summary.get(key, 0.0) - base_summary.get(key, 0.0) for key in base_summary
    }
    for key in head_summary:
        summary_delta.setdefault(key, head_summary[key] - base_summary.get(key, 0.0))

    return {
        'base': base_meta,
        'head': head_meta,
        'summary_delta': summary_delta,
        'devices': {'entered': entered, 'exited': exited, 'common': common},
        'factor_effects': factor_effects,
        'reconciliation': {
            'entered_effect': entered_effect,
            'exited_effect': exited_effect,
            'common_effect': common_effect,
            'factor_effects': factor_effects,
            'sum_effect': sum_effect,
            'oee_delta': oee_delta,
            'residual': residual,
            'base_report': base_check,
            'head_report': head_check,
            'reconciled': reconciled,
        },
        'method': (
            '取两份已复核报告的冻结快照重新汇总。设备贡献=计划时长占比×设备OEE，'
            '其合计即报告汇总OEE。存量设备的贡献变化按计划时长占比、可用率、性能、'
            '节拍加权质量率四个因子，对所有替换顺序取平均边际影响（Shapley）；'
            '新增/退出设备单列自身贡献，不补造另一期历史。各分项之和须加回汇总OEE差值。'
        ),
    }
