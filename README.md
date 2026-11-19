# 榫川设备有效产出核对册

试制设备班次与重叠停机记录→可用率/性能/质量口径→班组复盘站内交付；不把简单平均当加权总OEE

## 业务场景与工作流
模拟客户：榫川研究协作组，12位业务与分析人员。每月研究明细先从`oee-shifts-202611.csv`录入底稿，经口径冻结、Python核算、负责人复核后向业务阅读者交付站内CSV。原有流程依靠人工表格抄算，痛点为口径版本难追溯、重复计算易错、复核与交付脱节。

模块：业务总览、业务底稿、新建口径版本、异步核算与复核、差值归因、定时交付、站内收件箱、审计。底稿可新增/修改/删除；口径仅新增版本；报告提交时冻结来源与版本并保存SHA256。定时交付引用已复核报告快照，worker到期写入数据库，业务阅读者下载。

## OEE 差值归因（排班变动）
选择两份**已复核**报告作基期/对比期，只读它们各自的冻结底稿快照，不读取当前底稿、不补造历史：

- 先校验两端快照：`checksum` 必须与快照重算一致，且报告内 `summary` 每项须与冻结底稿重算精确对账；任一失效即 `409` 拒绝发布。
- 设备贡献 = 计划时长占比 × 设备 OEE（可用率 × 性能 × 节拍加权质量率），全部设备贡献合计即报告汇总 OEE。
- 新增设备只列本期自身贡献、退出设备只列基期自身贡献（单列进出贡献）。
- 两期都在的设备，按 计划时长占比 / 可用率 / 性能 / 节拍加权质量率 四因子的**所有 4! 种替换顺序取平均边际影响**（Shapley）归因；每个设备的四项之和等于其贡献变化。
- 新增影响 + 退出影响 + 存量四因子影响 必须加回两份报告的汇总 OEE 差值，残差超过 `1e-9` 即拒绝发布。
- 同一对报告（不计先后）只保留一份结论：重复提交/反向提交/并发提交都回读既有记录，重跑不另立结论；唯一键兜底并发。
- 页面可选基期与对比期报告、浏览历史核对、查看每台设备的归因依据（基期/对比期因子、变化、归因影响、残差）。

接口：`GET /comparisons`、`POST /comparisons {base_run_id, head_run_id}`（admin/analyst）、`GET /comparisons/{id}`。前端页面「差值归因」。

## 算法口径
停机区间合并裁剪、OEE三因子与按班次透视。重叠区间去重、跨班裁剪手算；性能超1显示警示不静默截断。

停机去重 · 三因子核对 · 逐班回看。输入：业务底稿与口径JSON；输出：summary、透视rows、method、warnings。算法实现在`backend/src/services/calculation.py`，输入校验在`validation.py`。固定seed=42，240条合成数据；未对接真实业务系统。修改源数据和新建因子/口径不会改变已提交报告。

## 一天的验收剧本
1. 09:00 admin查看240条seed底稿与具名业务期间。
2. 09:10 analyst添加`oee-shifts-202611.csv`的一条具名业务记录。
3. 09:20 admin在口径版本页登记新版本；旧版本保留。
4. 09:30 analyst命名“十一月核算”并选择期间/版本排队。
5. 09:31 Redis worker真实执行Python计算，展示汇总/透视与口径边界。
6. 09:40 admin核对数值后填写至少4字复核说明。
7. 09:45 admin建立60秒周期计划，worker到期生成站内持久化交付。
8. 09:46 viewer在站内收件箱下载交付CSV；审计页查看操作者与时间。
9. 09:50 排班变化后另建一份已复核报告，在「差值归因」选择基期/对比期，查看新增/退出设备与存量设备四因子归因，确认分项加回汇总OEE差值；重复点击只返回同一份结论。

## 快速启动
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18251 ，后端 http://localhost:19251/docs ，数据库宿主端口17751。中文父目录可用。恰好5服务frontend/backend/worker/db/redis；均有真实healthcheck。停止并清空演示数据：`docker compose down -v --remove-orphans`。

|角色|邮箱|密码|权限|
|---|---|---|---|
|admin|admin@demo.local|Demo2026!|全部底稿、口径版本、核算、复核、调度|
|analyst|analyst@demo.local|Demo2026!|底稿增改删、核算、导出；无复核/调度/口径写权限|
|viewer|viewer@demo.local|Demo2026!|只读；仅可下载已复核报告与站内交付|

## 工程结构与开发
Python3.11/FastAPI/SQLAlchemy/Redis，MySQL8；前端原生HTML/CSS/JS ES modules，Nginx代理`/api/`剥前缀至后端。`frontend/src`按api/stores/pages/components/hooks/utils/router/constants/types拆分；`backend/src`按models/schemas/services/controllers/routes/middlewares/config/utils/constants拆分；`backend/scripts/seed_demo.py`自然键幂等且不覆盖用户修改。SQLAlchemy启动创建初始结构，迁移说明在backend/migrations。差值归因算法在`backend/src/services/attribution.py`，快照与对账校验在`comparison.py`，因子计算与核算共用`oee_math.py`。

后端测试（无需数据库/Redis，使用进程内SQLite）：
```sh
cd backend && python -m unittest discover -s tests -v
```

后端开发：在backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET，`uvicorn src.main:app --reload`；前端可用Nginx或带同等代理的静态开发服务器。前后端全部业务计算在Python。

环境变量：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、JWT_SECRET（部署替换）、DATABASE_URL、REDIS_URL、SEED_DEMO。`.env`不入Git。数据库/Redis/共享产物为命名卷。共享角色枚举admin/analyst/viewer与状态queued/running/completed/failed分别定义于backend/src/constants/enums.py和frontend/src/constants/enums.js。两个中间件：统一可恢复校验错误、每IP每分钟360请求限流。

## 已知边界
定时分发为站内收件箱；一名worker轮询执行，无外部邮件。调度发送已复核固定报告快照，不自动重算新数据。时间显示Asia/Shanghai。报告导出适合小型数据；底稿全量加载240行演示数据。Google Fonts不可用时回退serif。后端API以专属字段对象收发，页面通过业务输入控件编辑，不要求用户写JSON。新增来源期间自动可选；专属字段和算法严格校验。JWT演示有效期2小时。

MIT License。

## 实际实体映射
来源记录（Source，专属业务字段校验）、口径版本（Policy）、核算报告（Run）、交付计划（Schedule）、交付（Delivery）均经数据库→模型→请求schema→service→route/controller→frontend API→store→page。Period为已有来源期间字典，在任务期间选择器使用；不单独作为复杂度计数。底稿JSON为小型多字段单记录存储，不虚构未落库的子实体。
