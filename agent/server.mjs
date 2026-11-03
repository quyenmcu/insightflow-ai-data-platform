import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {loadSnapshot} from '../dashboard/dist/feed.mjs';
import {runChat,validateRequest,MODEL} from './chat.mjs';
import {reserveRequest,LIMITS} from './budget.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const staticRoot=path.join(root,'dashboard/dist');
const port=Number(process.env.PORT??8787);
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Choose a local port from 1024 through 65535.');
const origins=new Set([`http://localhost:${port}`,`http://127.0.0.1:${port}`]);
const ledger=path.join(root,'data/processed/agent/usage.json');
const mime={'.html':'text/html; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8'};
let active=false;
const fetchSnapshot=()=>loadSnapshot(async(url,options)=>url==='./snapshot.json'?{ok:true,json:async()=>JSON.parse(await readFile(path.join(staticRoot,'snapshot.json'),'utf8'))}:fetch(url,options));
const send=(res,status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(value));};
export const server=createServer(async(req,res)=>{
  try {
    if(!origins.has(`http://${req.headers.host}`)||(req.headers.origin&&!origins.has(req.headers.origin)))return send(res,403,{error:'This local agent accepts same-origin requests only.'});
    const url=new URL(req.url,`http://localhost:${port}`);
    if(url.pathname==='/health'||url.pathname==='/api/chat/health')return send(res,200,{configured:!!process.env.OPENAI_API_KEY,model:MODEL,mode:'local-agent',limits:LIMITS});
    if(url.pathname==='/api/chat'){
      if(req.method!=='POST')return send(res,405,{error:'Use POST.'});
      if(!process.env.OPENAI_API_KEY)return send(res,503,{error:'The agent API key is not configured.'});
      if(active)return send(res,429,{error:'An analytics request is already running. Try again after it finishes.'});
      if(!req.headers['content-type']?.startsWith('application/json'))return send(res,415,{error:'Use JSON.'});
      let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>16000)return send(res,413,{error:'The request is too large.'});}
      let input;try{input=validateRequest(JSON.parse(body));}catch{return send(res,400,{error:'Check the message, history, and month/state selection.'});}
      if(active)return send(res,429,{error:'An analytics request is already running.'});
      active=true;
      try {
        const loaded=await fetchSnapshot();
        const usage=await reserveRequest(ledger);
        const result=await runChat(loaded.snapshot,input,{apiKey:process.env.OPENAI_API_KEY});
        return send(res,200,{...result,usage,dataMode:loaded.mode});
      } catch(error){
        const quota=error.code==='insufficient_quota'||error.code==='credit_balance_exhausted';
        const denied=error.status===401;
        const limited=/allowance|ledger/.test(error.message??'');
        return send(res,limited?429:503,{error:quota?'OpenAI API credits are unavailable.':denied?'The API key is invalid or expired. Renew it securely.':limited?error.message:'The AI request could not finish. Try a shorter question later. Guided metric questions remain available.'});
      } finally {active=false;}
    }
    if(!['GET','HEAD'].includes(req.method))return send(res,405,{error:'Method not allowed.'});
    const name=url.pathname==='/'?'index.html':decodeURIComponent(url.pathname.slice(1));
    if(!/^[a-zA-Z0-9_.-]+$/.test(name)||!Object.hasOwn(mime,path.extname(name)))return send(res,404,{error:'Not found.'});
    const content=await readFile(path.join(staticRoot,name));res.writeHead(200,{'Content-Type':mime[path.extname(name)],'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff'});res.end(req.method==='HEAD'?undefined:content);
  } catch {send(res,404,{error:'Not found.'});}
});
server.requestTimeout=20000;
server.headersTimeout=10000;
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))server.listen(port,'127.0.0.1',()=>console.log(`InsightFlow local agent: http://localhost:${port}`));
