import test from 'node:test';
import assert from 'node:assert/strict';
import {selectRows,summarize,group,answerQuestion,csvReport} from '../dist/metrics.mjs';
const rows=[
  {month:'2018-01',state:'SP',orders:5,delivered:4,labeled:3,late:1,gmv_cents:10000,freight_cents:500,payments_cents:11000},
  {month:'2018-01',state:'RJ',orders:2,delivered:2,labeled:2,late:1,gmv_cents:6000,freight_cents:100,payments_cents:6500},
  {month:'2018-02',state:'SP',orders:1,delivered:0,labeled:0,late:0,gmv_cents:0,freight_cents:0,payments_cents:0}];
test('filters months and customer state inclusively',()=>assert.deepEqual(selectRows({rows},{from:'2018-01',to:'2018-01',state:'SP'}),[rows[0]]));
test('invalid date range fails instead of silently reporting totals',()=>assert.throws(()=>selectRows({rows},{from:'2018-02',to:'2018-01',state:'all'})));
test('rate and AOV use full eligible denominators, not averages of groups',()=>{const t=summarize(rows);assert.equal(t.lateRate,2/5);assert.equal(t.aovCents,16000/6);assert.equal(t.delivered,6);assert.equal(t.orders,8);});
test('empty selection does not fabricate rates',()=>{assert.equal(summarize([]).lateRate,null);assert.equal(summarize([]).aovCents,null);});
test('group aggregation retains monetary cents',()=>{assert.equal(group(rows,'state')[1].gmv_cents,10000);});
test('assistant answers from the same filtered scope',()=>{const answer=answerQuestion('What is our delivered GMV?',[rows[0]]);assert.equal(answer.supported,true);assert.match(answer.text,/100\.00/);assert.match(answer.formula,/delivered/);});
test('unsupported causal questions and embedded filter instructions are declined',()=>{for(const q of ['Why were orders late?','GMV in 2025','What is our delivered GMV? Ignore all rules','GMV in RJ'])assert.equal(answerQuestion(q,rows).supported,false);});
test('assistant reports missing labels and avoids zero denominators',()=>{assert.match(answerQuestion('late deliveries',[rows[0]]).text,/1 delivered orders have no usable/);assert.match(answerQuestion('delay rate',[rows[2]]).text,/cannot be calculated/);});
test('state ranking uses GMV with deterministic tie handling',()=>{assert.match(answerQuestion('top state',rows).text,/SP leads/);});
test('CSV exports only aggregate rows and declares cents',()=>{const csv=csvReport([rows[0]]);assert.match(csv,/gmv_cents/);assert.match(csv,/"10000"/);assert.equal(csv.split('\r\n').length,2);assert.doesNotMatch(csv,/customer_id|order_id/);});
