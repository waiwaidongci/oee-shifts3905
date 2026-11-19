import {heading} from '../components/common/header.js';
import {esc,fmt,time} from '../utils/format.js';
import {table} from '../components/common/table.js';

const pct=v=>typeof v==='number'?(v*100).toFixed(3)+'%':'';
const pp=v=>typeof v==='number'?(v>=0?'+':'')+(v*100).toFixed(4)+'pp':'';
const raw=v=>typeof v==='number'?v.toFixed(9):'';

const FACTORS=[['share','计划时长占比'],['availability','可用率'],['performance','性能'],['quality','节拍加权质量率']];

function reportCard(label,meta){
 return `<article class="compare-report"><small>${esc(label)}</small><h3>${esc(meta.name)}</h3><p>期间 ${esc(meta.period)} · 口径 ${esc(meta.policy_version)} · 来源 ${meta.source_rows} 行</p><p class="checksum">SHA256 ${esc(meta.checksum)}</p><p>${esc(meta.review)}</p></article>`;
}

function summaryTable(base,head){
 const keys=Object.keys(head);
 return table(keys.map(k=>({指标:k,基期:fmt(base[k]),对比期:fmt(head[k]),差值:fmt(head[k]-base[k])})));
}

function entryTable(rows,rowsLabel){
 if(!rows.length)return `<p class="empty">本期无${esc(rowsLabel)}设备。</p>`;
 return table(rows.map(d=>({设备:d.device,班次:d.rows,计划分钟:fmt(d.planned_minutes),计划时长占比:pct(d.planned_share),可用率:pct(d.availability),性能:pct(d.performance),节拍加权质量率:pct(d.quality),设备OEE:pct(d.oee),贡献:pp(d.effect),依据:d.note})));
}

function commonDetail(rows){
 if(!rows.length)return '<p class="empty">两期没有共同设备。</p>';
 return rows.map(d=>`<details class="device-basis"><summary>${esc(d.device)} · 贡献变化 ${pp(d.effect)} · 四因子加回残差 ${raw(d.residual)} ${d.reconciled?'（已对账）':'（未对账）'}</summary>
  <div class="table-wrap"><table><thead><tr><th>依据</th><th>基期</th><th>对比期</th><th>变化</th><th>归因影响</th></tr></thead><tbody>
   <tr><td>班次数</td><td>${d.base.rows}</td><td>${d.head.rows}</td><td>${d.head.rows-d.base.rows}</td><td>—</td></tr>
   <tr><td>计划分钟</td><td>${fmt(d.base.planned_minutes)}</td><td>${fmt(d.head.planned_minutes)}</td><td>${fmt(d.head.planned_minutes-d.base.planned_minutes)}</td><td>—</td></tr>
   ${FACTORS.map(([key,label])=>`<tr><td>${label}</td><td>${pct(d.base[key])}</td><td>${pct(d.head[key])}</td><td>${pp(d.deltas[key])}</td><td>${pp(d.attribution[key])}</td></tr>`).join('')}
   <tr><td>设备OEE</td><td>${pct(d.base.oee)}</td><td>${pct(d.head.oee)}</td><td>${pp(d.deltas.oee)}</td><td>—</td></tr>
   <tr><td>贡献（计划时长占比×OEE）</td><td>${pp(d.base.contribution)}</td><td>${pp(d.head.contribution)}</td><td>${pp(d.effect)}</td><td>${pp(d.effect)}</td></tr>
  </tbody></table></div>
  <p class="method">按所有 4! 种替换顺序取平均边际影响，四项合计 ${pp(FACTORS.reduce((sum,[key])=>sum+d.attribution[key],0))}，与贡献变化相差 ${raw(d.residual)}。</p>
 </details>`).join('');
}

const INSTRUCTIONS='仅使用两份已复核报告的冻结底稿；新增/退出设备单列进出贡献，不补造历史；存量设备按计划时长占比、可用率、性能、节拍加权质量率四因子全排列平均归因。';

export function comparisons(c,d,selected,store){
 const approved=d.runs.filter(r=>r.approved&&r.status==='completed');
 const current=d.comparisons.find(x=>x.id===store.comparison)||d.comparisons[0]||null;
 const options=approved.map(r=>`<option value="${r.id}">#${r.id} ${esc(r.name)} · ${esc(r.snapshot.period)} · ${esc(r.snapshot.policy.version)}</option>`).join('');
 const headOptions=approved.map((r,i)=>`<option value="${r.id}" ${i===1?'selected':''}>#${r.id} ${esc(r.name)} · ${esc(r.snapshot.period)} · ${esc(r.snapshot.policy.version)}</option>`).join('');
 const form=approved.length>=2
  ?`<form id="compare-form" class="inline-form"><label>基期报告<select name="base_run_id">${options}</select></label><label>对比期报告<select name="head_run_id">${headOptions}</select></label><button>生成差值归因</button></form>`
  :'<p class="empty">至少需要两份已复核报告才能比较；同一对报告只会保留一份结论。</p>';
 const list=d.comparisons.length?`<aside class="run-list">${d.comparisons.map(x=>`<button class="select-comparison" data-id="${x.id}">#${x.id} ${esc(x.result?.base?.name||'')} → ${esc(x.result?.head?.name||'')}<span class="status ${x.status==='reconciled'?'completed':'failed'}">${x.status==='reconciled'?'已对账':'未发布'}</span></button>`).join('')}</aside>`:'<p class="empty">尚无核对。选择两份已复核报告生成差值归因。</p>';
 const head=heading('VARIANCE EXPLAIN / 05','排班变动后的 OEE 差值归因',INSTRUCTIONS);
 if(!current)return head+form+list;
 if(current.status!=='reconciled'){
  const rec=current.result?.reconciliation||{};
  return head+form+`<div class="run-layout">${list}<div><section class="report"><div class="report-top"><h2>核对 #${current.id}</h2><span class="status failed">拒绝发布</span></div><p class="error">${esc(current.error||'两端无法对账')}</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px">${esc(JSON.stringify(rec,null,2))}</pre></section></div></div>`;
 }
 const r=current.result, rec=r.reconciliation;
 return head+`<div class="run-layout">${list}<div>
  ${form}
  <section class="report"><div class="report-top"><h2>核对 #${current.id}</h2><span class="status completed">已对账</span></div>
  <div class="compare-reports">${reportCard('基期报告',r.base)}${reportCard('对比期报告',r.head)}</div>
  <div class="metrics"><div><small>汇总 OEE 差值</small><strong>${pp(rec.oee_delta)}</strong></div><div><small>分项归因合计</small><strong>${pp(rec.sum_effect)}</strong></div><div><small>加回残差</small><strong>${raw(rec.residual)}</strong></div></div>
  <p class="method">${esc(r.method)}</p>
  <h2>汇总指标</h2>${summaryTable(r.base.summary,r.head.summary)}
  <h2>加回汇总差值</h2>
  ${table([
    {项目:'新增设备贡献',影响:pp(rec.entered_effect)},
    {项目:'退出设备贡献',影响:pp(rec.exited_effect)},
    ...FACTORS.map(([key,label])=>({项目:'存量设备 · '+label,影响:pp(rec.factor_effects[key])})),
    {项目:'存量设备贡献变化合计',影响:pp(rec.common_effect)},
    {项目:'分项归因合计',影响:pp(rec.sum_effect)},
    {项目:'两份报告汇总OEE差值',影响:pp(rec.oee_delta)},
    {项目:'加回残差',影响:raw(rec.residual)},
  ])}
  <p class="method">基期设备贡献合计 ${pp(rec.base_report.device_contributions)}，报告汇总 OEE ${pp(rec.base_report.summary_oee)}，残差 ${raw(rec.base_report.residual)}；对比期设备贡献合计 ${pp(rec.head_report.device_contributions)}，报告汇总 OEE ${pp(rec.head_report.summary_oee)}，残差 ${raw(rec.head_report.residual)}。两端均已对账，分项合计加回 ${pp(rec.oee_delta)}。</p>
  <details><summary>冻结快照校验</summary><p class="checksum">基期 ${esc(r.base.checksum)}</p><p class="checksum">对比期 ${esc(r.head.checksum)}</p><p>${time(current.created)} · 核对人 ${esc(current.actor)}</p></details>
  </section>
  <h2>新增设备（本期进入）</h2>${entryTable(r.devices.entered,'新增')}
  <h2>退出设备（本期离开）</h2>${entryTable(r.devices.exited,'退出')}
  <h2>共同设备 · 四因子平均归因</h2><p>展开任一设备查看基期/对比期的计划时长占比、可用率、性能、节拍加权质量率与贡献依据。</p>${commonDetail(r.devices.common)}
 </div></div>`;
}
