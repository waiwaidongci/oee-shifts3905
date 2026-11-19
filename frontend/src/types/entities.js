// API实体字段约定：来源{id,natural_key,data}、口径{id,version,data}、报告{id,status,snapshot,checksum,result,approved}、核对{id,base_run_id,head_run_id,status,result}、计划{next_at,enabled}。
export const ENTITY_KEYS=['sources','policies','runs','comparisons','schedules','deliveries'];
