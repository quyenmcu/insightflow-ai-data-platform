import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {executeAnalyticsTool as run} from '../analytics.mjs';
const snapshot=JSON.parse(readFileSync(new URL('../../dashboard/dist/snapshot.json',import.meta.url),'utf8'));
const scope={from:'2018-01',to:'2018-03',states:null};
test('summary computes weighted delivery rates with explicit evidence',()=>{
  const r=run('metric_summary',{metric:'late_rate',scope},snapshot);
  assert.equal(r.value,r.numerator/r.denominator);assert.equal(r.denominator,r.counts.labeled);
  assert.equal(r.provenance.aggregate_sha256,snapshot.aggregate_sha256);assert.equal(r.unit,'ratio');
});
test('AOV preserves numerator and denominator rather than averaging state means',()=>{
  const r=run('metric_summary',{metric:'aov',scope},snapshot);assert.equal(r.value,r.numerator/r.denominator);assert.equal(r.denominator,r.counts.delivered);
});
test('state comparisons match independent scope summaries',()=>{
  const left={...scope,states:['SP']},right={...scope,states:['RJ']};
  const r=run('compare_scopes',{metric:'gmv',left,right},snapshot);
  assert.equal(r.left.value,run('metric_summary',{metric:'gmv',scope:left},snapshot).value);
  assert.equal(r.absolute_change,r.right.value-r.left.value);assert.equal(r.unit,'BRL_cents');
});
test('out-of-history dates, invalid states and reversed ranges are rejected',()=>{
  for(const s of [{...scope,from:'2026-01',to:'2026-02'},{...scope,states:['ZZ']},{...scope,from:'2018-04'},{...scope,from:'2018-13'}])assert.throws(()=>run('metric_summary',{metric:'gmv',scope:s},snapshot));
});
test('unknown tools, unsupported profit and extra arguments cannot execute',()=>{
  assert.throws(()=>run('sql',{query:'DROP TABLE orders'},snapshot));
  assert.throws(()=>run('metric_summary',{metric:'profit',scope},snapshot));
  assert.throws(()=>run('metric_summary',{metric:'gmv',scope,sql:'SELECT * FROM raw.orders'},snapshot));
});
test('series totals reconcile with the summary',()=>{
  const r=run('metric_series',{metric:'gmv',scope,group_by:'month'},snapshot);
  assert.equal(r.groups.reduce((n,g)=>n+g.value,0),run('metric_summary',{metric:'gmv',scope},snapshot).value);
});
test('rankings enforce output limits and minimum late-rate support',()=>{
  const r=run('rank_groups',{metric:'late_rate',scope,group_by:'state',limit:3},snapshot);
  assert.ok(r.groups.length<=3);assert.ok(r.groups.every(g=>g.counts.labeled>=20));
  assert.throws(()=>run('rank_groups',{metric:'gmv',scope,group_by:'state',limit:1000},snapshot));
});
test('zero baselines have no invented relative growth or delivery rates',()=>{
  const empty={from:'2018-10',to:'2018-10',states:['SP']};
  const r=run('compare_scopes',{metric:'gmv',left:empty,right:scope},snapshot);assert.equal(r.relative_change,null);
  assert.equal(run('metric_summary',{metric:'late_rate',scope:empty},snapshot).value,null);
});
test('tool execution leaves the verified snapshot unchanged',()=>{
  const before=JSON.stringify(snapshot);run('rank_groups',{metric:'gmv',scope,group_by:'state',limit:5},snapshot);assert.equal(JSON.stringify(snapshot),before);
});
