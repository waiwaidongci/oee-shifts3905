from src.services.validation import validate_source,validate_policy
from src.services.oee_math import row_metrics,summary_from_sources
def calculate(sources,policy):
 validate_policy(policy);rows=[];warnings=[]
 for s in sources:
  validate_source(s);p=s['end']-s['start'];m=row_metrics(s);down,op,it,ig=m['down'],m['operating'],m['ideal_total'],m['ideal_good']
  perf=it/op if op else 0;q=s['good']/s['total'] if s['total'] else 0
  if perf>1:warnings.append(s['department']+' '+s['period']+'性能大于1，请复核理想节拍；保留原值')
  rows.append({'日期':s['period'],'设备':s['department'],'计划分钟':p,'去重停机分钟':down,'运行分钟':op,'可用率':op/p,'性能':perf,'质量率':q,'OEE':ig/p})
 return {'summary':summary_from_sources(sources),'rows':rows,'method':'班次停机区间先裁剪到班次再合并。A=运行/计划；P=理想产出分钟/运行；单班Q=合格/总量。跨节拍汇总Q采用理想产出分钟加权，汇总OEE=合格产出理想分钟/计划分钟，绝不简单平均各班OEE。','warnings':warnings}
