// Provider-independent, read-only calculations. Call only with a verified snapshot.
import {summarize,group} from '../dashboard/dist/metrics.mjs';

export const metrics=Object.freeze({
  gmv:{unit:'BRL_cents',definition:'Delivered item GMV; excludes freight, not profit or net revenue.',read:t=>t.gmv_cents},
  orders:{unit:'orders',definition:'Orders across all final statuses.',read:t=>t.orders},
  delivered_orders:{unit:'orders',definition:'Orders with final status delivered.',read:t=>t.delivered},
  aov:{unit:'BRL_cents',definition:'Delivered item GMV divided by delivered orders; excludes freight.',read:t=>t.aovCents},
  late_rate:{unit:'ratio',definition:'Late delivered orders divided by labeled delivered orders; calendar-day comparison.',read:t=>t.lateRate},
  payments:{unit:'BRL_cents',definition:'Payment totals for delivered orders; distinct from item GMV.',read:t=>t.payments_cents},
  freight:{unit:'BRL_cents',definition:'Freight totals for delivered orders.',read:t=>t.freight_cents}
});

function object(value,allowed,required=allowed) {
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!allowed.includes(k))||required.some(k=>!Object.hasOwn(value,k)))throw new Error('Invalid tool arguments.');
}
function metric(name) {
  if(!Object.hasOwn(metrics,name))throw new Error('Unsupported metric. Available metrics: '+Object.keys(metrics).join(', '));
  return metrics[name];
}
function scoped(snapshot,scope) {
  object(scope,['from','to','states']);
  for(const date of [scope.from,scope.to])if(typeof date!=='string'||!/^\d{4}-(0[1-9]|1[0-2])$/.test(date))throw new Error('Use calendar months in YYYY-MM format.');
  if(scope.from>scope.to)throw new Error('The start month must precede or equal the end month.');
  if(scope.from<snapshot.source_period.from||scope.to>snapshot.source_period.to)throw new Error(`Requested period is outside the available history (${snapshot.source_period.from} through ${snapshot.source_period.to}).`);
  if(scope.states!==null){
    const known=new Set(snapshot.rows.map(r=>r.state));
    if(!Array.isArray(scope.states)||scope.states.length<1||scope.states.length>5||new Set(scope.states).size!==scope.states.length||scope.states.some(s=>typeof s!=='string'||!known.has(s)))throw new Error('Choose up to five known customer states, or null for all states.');
  }
  return snapshot.rows.filter(r=>r.month>=scope.from&&r.month<=scope.to&&(scope.states===null||scope.states.includes(r.state)));
}
function result(rows,name) {
  const total=summarize(rows),definition=metric(name);
  return {value:rows.length?definition.read(total):null,unit:definition.unit,matching_groups:rows.length,
    counts:{orders:total.orders,delivered:total.delivered,labeled:total.labeled,late:total.late},
    numerator:name==='late_rate'?total.late:name==='aov'?total.gmv_cents:null,
    denominator:name==='late_rate'?total.labeled:name==='aov'?total.delivered:null};
}
function provenance(snapshot) {
  return {source:snapshot.warehouse,source_fingerprint:snapshot.source_fingerprint,
    aggregate_sha256:snapshot.aggregate_sha256,warehouse_build_id:snapshot.warehouse_build_id,
    exported_at:snapshot.exported_at,purchase_date_basis:true,historical_data:true};
}
export function executeAnalyticsTool(name,args,snapshot) {
  const evidence=provenance(snapshot);
  if(name==='metric_definition'){
    object(args,['metric']);const definition=metric(args.metric);
    return {metric:args.metric,definition:definition.definition,unit:definition.unit,provenance:evidence};
  }
  if(name==='compare_scopes'){
    object(args,['metric','left','right']);const definition=metric(args.metric);
    const left=result(scoped(snapshot,args.left),args.metric),right=result(scoped(snapshot,args.right),args.metric);
    const available=left.value!==null&&right.value!==null;
    return {metric:args.metric,definition:definition.definition,left:{scope:args.left,...left},right:{scope:args.right,...right},
      absolute_change:available?right.value-left.value:null,
      relative_change:available&&left.value!==0?(right.value-left.value)/left.value:null,
      change_direction:'right minus left',unit:definition.unit,provenance:evidence};
  }
  if(name==='metric_summary'){
    object(args,['metric','scope']);const definition=metric(args.metric);
    return {metric:args.metric,definition:definition.definition,scope:args.scope,...result(scoped(snapshot,args.scope),args.metric),provenance:evidence};
  }
  if(name==='metric_series'||name==='rank_groups'){
    const allowed=name==='rank_groups'?['metric','scope','group_by','limit']:['metric','scope','group_by'];
    object(args,allowed);const definition=metric(args.metric);
    if(!['state','month'].includes(args.group_by))throw new Error('Grouping must be state or purchase month.');
    if(name==='rank_groups'&&(!Number.isInteger(args.limit)||args.limit<1||args.limit>10))throw new Error('Ranking limit must be between 1 and 10.');
    const rows=scoped(snapshot,args.scope);
    let groups=group(rows,args.group_by).map(g=>({group:g.key,...result(rows.filter(r=>r[args.group_by]===g.key),args.metric)}));
    const allGroups=groups.length;
    if(name==='rank_groups'){
      groups=groups.filter(g=>g.value!==null&&(args.metric!=='late_rate'||g.counts.labeled>=20));
      groups.sort((a,b)=>b.value-a.value||a.group.localeCompare(b.group));groups=groups.slice(0,args.limit);
    }
    return {metric:args.metric,definition:definition.definition,scope:args.scope,group_by:args.group_by,unit:definition.unit,
      groups,matching_groups:allGroups,minimum_labeled_deliveries:name==='rank_groups'&&args.metric==='late_rate'?20:null,
      missing_months:'Absent groups are omitted, not interpolated.',provenance:evidence};
  }
  throw new Error('Unsupported analytics tool.');
}
