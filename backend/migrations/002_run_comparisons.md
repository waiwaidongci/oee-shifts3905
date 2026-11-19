# 结构迁移说明

## 初始结构（001）

SQLAlchemy 启动创建以下业务表：shifts, downtimeevents, productioncounts, oeeruns, delivery_schedules, deliveries、users、audits。Source 专属 JSON 字段由对应 validation 严格校验；Policy 为不可覆盖的版本记录；Run 保存 source/policy 冻结快照；Period 仅用于已有期间选择器，不计入核心复杂度。

已有数据库升级需先备份，后续字段演进应以独立迁移执行。

## 差值归因（002）

新增 `run_comparisons` 表，保存两份已复核报告的差值归因结论：

| 列 | 说明 |
|---|---|
| base_run_id / head_run_id | 基期与对比期报告外键（业务级，不级联删除） |
| pair_key | 一对报告的唯一键（排序后取 SHA256），重跑与并发共用同一结论 |
| status | `reconciled`（已对账发布）；`rejected` 为保留状态字面量，拒绝发布时不落库 |
| checksum | 归因结果的 SHA256，便于复核 |
| result / error | 归因明细 JSON 与拒绝原因 |
| actor / created | 发起人与时间 |

唯一约束 `uq_comparison_pair(base_run_id, head_run_id)` 与唯一索引 `pair_key` 共同保证同一对报告只留一份结论；并发插入触发唯一键冲突时回读已有记录，不另立结论。

快照校验失效或两端无法对账时**不写入本表**（只在 `audits` 留痕），因此修正报告后可重新核对；不会把一次拒绝固化成结论。

现有 MySQL 库执行：

```sql
CREATE TABLE run_comparisons (
  id INT AUTO_INCREMENT PRIMARY KEY,
  base_run_id INT NOT NULL,
  head_run_id INT NOT NULL,
  pair_key VARCHAR(64) NOT NULL,
  status VARCHAR(20) NOT NULL,
  checksum VARCHAR(64),
  result JSON,
  error TEXT,
  actor VARCHAR(120),
  created DOUBLE,
  CONSTRAINT uq_comparison_pair UNIQUE (base_run_id, head_run_id),
  CONSTRAINT uq_comparison_key UNIQUE (pair_key)
);
```

新库由 `Base.metadata.create_all` 自动创建，无需手工执行。
