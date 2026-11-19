"""OEE 因子计算：核算与差值归因共用同一套口径，避免两份算法漂移。"""


def downtime_minutes(start, end, intervals):
    """把停机区间裁剪到班次内，合并重叠后返回去重停机分钟数。"""
    pieces = sorted((max(start, a), min(end, b)) for a, b in intervals if min(end, b) > max(start, a))
    merged = []
    for a, b in pieces:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return sum(b - a for a, b in merged)


def row_metrics(source):
    """单条班次底稿的时长与理想产出分钟。"""
    planned = source['end'] - source['start']
    down = downtime_minutes(source['start'], source['end'], source['downtime'])
    operating = planned - down
    if operating <= 0 and source['total'] > 0:
        raise ValueError('全部停机班次不得有产量')
    return {
        'planned': planned,
        'down': down,
        'operating': operating,
        'ideal_total': source['total'] * source['ideal_seconds'] / 60,
        'ideal_good': source['good'] * source['ideal_seconds'] / 60,
    }


def summary_from_sources(sources):
    """按底稿逐班汇总，返回与核算报告 summary 相同结构的指标。"""
    planned = operating = ideal_total = ideal_good = 0
    for source in sources:
        metrics = row_metrics(source)
        planned += metrics['planned']
        operating += metrics['operating']
        ideal_total += metrics['ideal_total']
        ideal_good += metrics['ideal_good']
    return {
        '计划分钟': planned,
        '运行分钟': operating,
        '可用率': operating / planned if planned else 0,
        '性能': ideal_total / operating if operating else 0,
        '节拍加权质量率': ideal_good / ideal_total if ideal_total else 0,
        '汇总OEE': ideal_good / planned if planned else 0,
    }


def device_factors(sources):
    """按设备汇总底稿并返回设备因子表。

    OEE = 理想合格分钟 / 计划分钟 = 可用率 × 性能 × 节拍加权质量率；
    计划时长占比 = 设备计划分钟 / 当份报告全部设备计划分钟；
    贡献 = 计划时长占比 × 设备OEE，全部设备贡献合计即当份报告汇总OEE。
    """
    groups = {}
    for source in sources:
        metrics = row_metrics(source)
        device = groups.setdefault(source['department'], {
            'rows': 0, 'planned': 0.0, 'operating': 0.0,
            'ideal_total': 0.0, 'ideal_good': 0.0,
        })
        device['rows'] += 1
        for key in ('planned', 'operating', 'ideal_total', 'ideal_good'):
            device[key] += metrics[key]

    total_planned = sum(device['planned'] for device in groups.values())
    factors = {}
    for name, device in groups.items():
        planned = device['planned']
        operating = device['operating']
        ideal_total = device['ideal_total']
        ideal_good = device['ideal_good']
        share = planned / total_planned if total_planned else 0.0
        oee = ideal_good / planned if planned else 0.0
        factors[name] = {
            'rows': device['rows'],
            'planned_minutes': planned,
            'operating_minutes': operating,
            'ideal_total_minutes': ideal_total,
            'ideal_good_minutes': ideal_good,
            'planned_share': share,
            'availability': operating / planned if planned else 0.0,
            'performance': ideal_total / operating if operating else 0.0,
            'quality': ideal_good / ideal_total if ideal_total else 0.0,
            'oee': oee,
            'contribution': share * oee,
        }
    return factors, total_planned
