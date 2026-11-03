import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFile,readdir} from 'node:fs/promises';
import {reserveCloudRequest} from '../cloud-budget.mjs';
async function database(){const sqlite=new DatabaseSync(':memory:');for(const name of(await readdir(new URL('../../drizzle/',import.meta.url))).filter(n=>n.endsWith('.sql')).sort())sqlite.exec(await readFile(new URL('../../drizzle/'+name,import.meta.url),'utf8'));return {sqlite,prepare(sql){return {bind(...values){return {async first(){return sqlite.prepare(sql).get(...values)??null;}};}};}};}
test('hosted reservations enforce day/month limits using the deployed migration and SQL',async()=>{
  const db=await database();try{for(let i=0;i<10;i++)await reserveCloudRequest(db,new Date('2026-11-03T00:00:00Z'));await assert.rejects(reserveCloudRequest(db,new Date('2026-11-03T00:00:00Z')),/allowance/);
  assert.equal((await reserveCloudRequest(db,new Date('2026-11-04T00:00:00Z'))).monthlyUsed,11);
  for(let day=5;day<=12;day++)for(let n=0;n<10;n++)await reserveCloudRequest(db,new Date(`2026-11-${String(day).padStart(2,'0')}T00:00:00Z`));
  for(let n=0;n<9;n++)await reserveCloudRequest(db,new Date('2026-11-13T00:00:00Z'));
  await assert.rejects(reserveCloudRequest(db,new Date('2026-11-14T00:00:00Z')),/allowance/);
  assert.equal((await reserveCloudRequest(db,new Date('2026-12-01T00:00:00Z'))).monthlyUsed,1);
  }finally{db.sqlite.close();}
});
test('missing hosted ledger fails closed before model use',async()=>{await assert.rejects(reserveCloudRequest(null),/unavailable/);});
