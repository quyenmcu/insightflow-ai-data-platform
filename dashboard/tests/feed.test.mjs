import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateFeed,loadSnapshot,refreshNotice,SNAPSHOT_FEED_URL} from '../dist/feed.mjs';
const fixture=()=>JSON.parse(readFileSync(new URL('../dist/snapshot.json',import.meta.url),'utf8'));
test('reference snapshot validates using browser SHA-256 canonicalization',async()=>{assert.equal((await validateFeed(fixture())).rows.length,565);});
test('corrupt hashes, duplicate groups, missing provenance, and row details fail',async()=>{
  for(const change of [s=>s.aggregate_sha256='0'.repeat(64),s=>s.rows.push(s.rows[0]),s=>s.exported_at='bad',s=>s.rows[0].customer_id='private']){const s=fixture();change(s);await assert.rejects(validateFeed(s));}
});
test('a valid remote feed wins without loading bundled data',async()=>{const calls=[];const loaded=await loadSnapshot(async url=>{calls.push(url);return {ok:true,json:async()=>fixture()};});assert.equal(loaded.mode,'scheduled');assert.deepEqual(calls,[SNAPSHOT_FEED_URL]);});
test('remote failure and invalid remote content fall back visibly',async()=>{
  for(const bad of ['http','content']){const calls=[];const loaded=await loadSnapshot(async url=>{calls.push(url);if(url===SNAPSHOT_FEED_URL)return {ok:bad!=='http',json:async()=>({})};return {ok:true,json:async()=>fixture()};});assert.equal(loaded.mode,'bundled');assert.equal(calls.length,2);assert.match(refreshNotice(loaded.snapshot,loaded.mode),/unavailable.*bundled/);}
});
test('both data sources failing rejects rather than showing invented metrics',async()=>{await assert.rejects(loadSnapshot(async()=>({ok:false})));});
test('old successful refresh warns while a recent one identifies the schedule',()=>{const s=fixture(),at=Date.parse(s.exported_at);assert.match(refreshNotice(s,'scheduled',at+10*86400000),/more than 9 days/);assert.match(refreshNotice(s,'scheduled',at),/Monday 08:00 Taiwan/);});
