import {mkdir,open,readFile,rename,unlink} from 'node:fs/promises';
import path from 'node:path';

export const LIMITS=Object.freeze({monthlyRequests:100,dailyRequests:10,reservationUsd:0.02,monthlyReservationUsd:2});
export async function reserveRequest(file,now=new Date()) {
  await mkdir(path.dirname(file),{recursive:true});
  const lock=await open(file+'.lock','wx').catch(()=>{throw new Error('Usage ledger is busy. Try again shortly.');});
  try {
    let ledger={month:now.toISOString().slice(0,7),requests:0,days:{}};
    try {const saved=JSON.parse(await readFile(file,'utf8'));if(!saved||typeof saved.month!=='string'||!Number.isSafeInteger(saved.requests)||saved.requests<0||!saved.days||typeof saved.days!=='object'||Array.isArray(saved.days)||Object.values(saved.days).some(n=>!Number.isSafeInteger(n)||n<0))throw new Error('Invalid usage ledger.');if(saved.month===ledger.month)ledger=saved;}
    catch(error){if(error.code!=='ENOENT')throw error;}
    const day=now.toISOString().slice(0,10),used=ledger.days[day]??0;
    if(ledger.requests>=LIMITS.monthlyRequests||used>=LIMITS.dailyRequests)throw new Error('The analytics agent request allowance has been reached.');
    ledger.requests++;ledger.days[day]=used+1;
    const temp=file+'.tmp';await import('node:fs/promises').then(fs=>fs.writeFile(temp,JSON.stringify(ledger)+'\n',{mode:0o600}));await rename(temp,file);
    return {monthlyUsed:ledger.requests,dailyUsed:used+1,...LIMITS};
  } finally {await lock.close();await unlink(file+'.lock');}
}
