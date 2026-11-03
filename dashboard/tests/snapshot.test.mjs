import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {sum,fields} from '../dist/metrics.mjs';
const snapshot=JSON.parse(readFileSync(new URL('../dist/snapshot.json',import.meta.url),'utf8'));
test('published snapshot matches registered warehouse baseline and row totals',()=>{
  const baseline=JSON.parse(readFileSync(new URL('../../infrastructure/postgres_baseline.json',import.meta.url),'utf8'));
  assert.deepEqual(sum(snapshot.rows),snapshot.totals);
  assert.equal(snapshot.totals.orders,baseline.order_count);
  assert.equal(snapshot.totals.delivered,baseline.delivered_order_count);
  assert.equal(snapshot.totals.labeled,baseline.labeled_deliveries);
  assert.equal(snapshot.totals.late,baseline.late_deliveries);
  assert.equal(snapshot.totals.gmv_cents,Math.round(Number(baseline.delivered_items_gmv_brl)*100));
});
test('published rows contain only declared aggregates with valid denominators',()=>{
  assert.equal(new Set(snapshot.rows.map(r=>`${r.month}/${r.state}`)).size,snapshot.rows.length);
  for(const row of snapshot.rows){assert.deepEqual(Object.keys(row).sort(),['month','state',...fields].sort());for(const field of fields)assert.ok(Number.isSafeInteger(row[field])&&row[field]>=0);assert.ok(row.late<=row.labeled&&row.labeled<=row.delivered&&row.delivered<=row.orders);}
});
