import {env} from 'cloudflare:workers';
import fallback from '../../../dashboard/dist/snapshot.json';
import {loadSnapshot} from '../../../dashboard/dist/feed.mjs';
import {runChat,validateRequest} from '../../../agent/chat.mjs';
import {reserveCloudRequest} from '../../../agent/cloud-budget.mjs';
export const dynamic='force-dynamic';
const json=(body:unknown,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
export async function POST(request:Request){
  if(!request.headers.get('oai-authenticated-user-id'))return json({error:'Sign in with ChatGPT to use AI analytics.'},401);
  const origin=request.headers.get('origin');if(origin&&origin!==new URL(request.url).origin)return json({error:'Use the dashboard to send chat requests.'},403);
  if(!request.headers.get('content-type')?.startsWith('application/json'))return json({error:'Use JSON.'},415);
  if(!env.OPENAI_API_KEY)return json({error:'AI analytics is not configured. Guided metrics remain available.'},503);
  let input;
  try {const body=await request.text();if(new TextEncoder().encode(body).length>16000)return json({error:'The request is too large.'},413);input=validateRequest(JSON.parse(body));}
  catch{return json({error:'Check the message, conversation length, and month/state selection.'},400);}
  try{
    const loaded=await loadSnapshot(async(url:string,options:RequestInit)=>url==='./snapshot.json'?{ok:true,json:async()=>fallback}:fetch(url,options));
    const usage=await reserveCloudRequest(env.DB);
    const result=await runChat(loaded.snapshot,input,{apiKey:env.OPENAI_API_KEY});
    return json({...result,usage,dataMode:loaded.mode});
  }catch(error:any){
    const quota=['credit_balance_exhausted','insufficient_quota'].includes(error.code);
    const limit=/allowance|ledger/.test(error.message??'');
    return json({error:quota?'OpenAI API credits are unavailable.':error.status===401?'The API key is invalid or expired. Renew it securely.':limit?error.message:'The AI request could not finish. Try a shorter question later, or use guided metrics.'},limit?429:503);
  }
}
