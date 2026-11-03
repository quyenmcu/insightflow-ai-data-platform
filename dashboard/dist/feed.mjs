import {fields,sum} from './metrics.mjs';

export const SNAPSHOT_FEED_URL='https://raw.githubusercontent.com/quyenmcu/insightflow-ai-data-platform/refs/heads/codex/dashboard-data/snapshot.json';
export const SOURCE_FINGERPRINT='09b5148b3a846d400c6c303505b23439cc111b07321abcf203c84894db512afa';
export async function validateFeed(snapshot) {
  if(snapshot.schema_version!==1||snapshot.source_fingerprint!==SOURCE_FINGERPRINT||snapshot.currency!=='BRL'||!Array.isArray(snapshot.rows)||!snapshot.rows.length)throw new Error('Unexpected snapshot contract.');
  const keys=['month','state',...fields].sort().join(',');const seen=new Set();
  for(const row of snapshot.rows){
    if(Object.keys(row).sort().join(',')!==keys||!/^\d{4}-(0[1-9]|1[0-2])$/.test(row.month)||!/^([A-Z]{2}|Unknown)$/.test(row.state))throw new Error('Invalid aggregate group.');
    if(fields.some(k=>!Number.isSafeInteger(row[k])||row[k]<0)||!(row.late<=row.labeled&&row.labeled<=row.delivered&&row.delivered<=row.orders))throw new Error('Invalid aggregate values.');
    const key=`${row.month}/${row.state}`;if(seen.has(key))throw new Error('Duplicate aggregate group.');seen.add(key);
  }
  const totals=sum(snapshot.rows);if(fields.some(k=>!Number.isSafeInteger(totals[k])||totals[k]!==snapshot.totals[k]))throw new Error('Snapshot totals differ.');
  const months=snapshot.rows.map(r=>r.month).sort();
  if(snapshot.source_period.from!==months[0]||snapshot.source_period.to!==months.at(-1)||!Number.isFinite(Date.parse(snapshot.exported_at))||!snapshot.warehouse_build_id)throw new Error('Snapshot provenance is incomplete.');
  const canonical=JSON.stringify(snapshot.rows.map(row=>Object.fromEntries(Object.keys(row).sort().map(k=>[k,row[k]]))));
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical));
  const actual=Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
  if(actual!==snapshot.aggregate_sha256)throw new Error('Snapshot aggregate checksum differs.');
  return snapshot;
}
export async function loadSnapshot(fetcher=fetch) {
  async function read(url){const response=await fetcher(url,{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('Snapshot request failed.');return validateFeed(await response.json());}
  try {return {snapshot:await read(SNAPSHOT_FEED_URL),mode:'scheduled'};}
  catch {return {snapshot:await read('./snapshot.json'),mode:'bundled'};}
}
export function refreshNotice(snapshot,mode,now=Date.now()) {
  if(mode==='bundled')return 'Scheduled refresh is unavailable. Showing the bundled historical snapshot; see its export time below.';
  if(now-Date.parse(snapshot.exported_at)>9*24*60*60*1000)return 'The latest verified warehouse snapshot is more than 9 days old. The weekly pipeline may need attention.';
  return 'Loaded the latest published warehouse snapshot. Refreshes follow the Monday 08:00 Taiwan pipeline; publication and CDN caching can add a short delay.';
}
