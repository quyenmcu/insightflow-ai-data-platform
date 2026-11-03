// Same-origin server calls only. No API credentials or provider calls in the browser.
const $=id=>document.getElementById(id);
let ready=false,busy=false,revision=0,history=[];
const controls=document.createElement('div');controls.className='agent-controls';
const label=document.createElement('label');label.textContent='Answer mode';
const mode=document.createElement('select');mode.id='chat-mode';mode.setAttribute('aria-label','Answer mode');
for(const [value,text] of [['guided','Guided metrics'],['ai','AI analytics']]){const option=document.createElement('option');option.value=value;option.textContent=text;option.disabled=value==='ai';mode.append(option);}label.append(mode);
const clear=document.createElement('button');clear.type='button';clear.className='text-button';clear.textContent='Clear conversation';controls.append(label,clear);
$('messages').before(controls);
const disclosure=document.querySelector('.assistant-disclosure');
const reset=()=>{revision++;history=[];$('messages').replaceChildren();};
function updateMode(){reset();disclosure.textContent=mode.value==='ai'?'AI analytics · verified calculations · up to 10 requests/day':'Guided metric answers · no model calls · selection applies';}
mode.addEventListener('change',updateMode);clear.addEventListener('click',reset);$('filters').addEventListener('change',reset);$('reset').addEventListener('click',reset);
const selectedScope=()=>({from:$('from').value,to:$('to').value,states:$('state').value==='all'?null:[$('state').value]});
async function askAI(question){
  if(!question.trim()||busy)return;
  const version=revision,scope=selectedScope();busy=true;
  const card=document.createElement('div');card.className='answer';const title=document.createElement('h3');title.textContent=question;
  const answer=document.createElement('p');answer.textContent='Checking the verified data…';answer.style.whiteSpace='pre-line';card.append(title,answer);$('messages').append(card);$('question').value='';
  const send=$('ask-form').querySelector('button');send.disabled=true;send.setAttribute('aria-busy','true');
  try{
    const response=await fetch('/api/chat',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:question,scope,history}),signal:AbortSignal.timeout(55000)});
    const result=await response.json();if(version!==revision)return;
    if(!response.ok)throw new Error(result.error||'AI analytics is unavailable. Guided metrics remain available.');
    answer.textContent=result.answer;
    const detail=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Verified calculations & source';detail.append(summary);
    for(const item of result.evidence??[]){const p=document.createElement('p');p.textContent=item.result.definition;const pre=document.createElement('pre');pre.textContent=JSON.stringify(item.result,null,2);detail.append(p,pre);}
    const source=document.createElement('small');source.textContent=`Historical snapshot · exported ${new Date(result.provenance.exported_at).toLocaleString('en-US',{timeZone:'UTC'})} UTC`;detail.append(source);card.append(detail);
    history=[...history,{role:'user',content:question.slice(0,1000)},{role:'assistant',content:result.answer.slice(0,800)}].slice(-4);
    disclosure.textContent=`AI analytics · ${result.usage.dailyUsed}/${result.usage.dailyRequests} requests used today · historical data`;
  }catch(error){if(version===revision)answer.textContent=error.name==='TimeoutError'?'The request timed out. Try a shorter question or use guided metrics.':error.message;}
  finally{busy=false;send.disabled=false;send.removeAttribute('aria-busy');}
}
$('ask-form').addEventListener('submit',event=>{if(mode.value!=='ai'||!ready)return;event.preventDefault();event.stopImmediatePropagation();askAI($('question').value);},true);
$('suggestions').addEventListener('click',event=>{const button=event.target.closest('button');if(!button||mode.value!=='ai'||!ready)return;event.preventDefault();event.stopImmediatePropagation();askAI(button.textContent);},true);
$('question').maxLength=1000;
try{const response=await fetch('/api/chat/health',{credentials:'same-origin',signal:AbortSignal.timeout(2500)});if(response.ok){const health=await response.json();if(health.configured){ready=true;mode.querySelector('[value="ai"]').disabled=false;mode.value='ai';updateMode();}else if(health.signInRequired){const signIn=document.createElement('a');signIn.href='/signin-with-chatgpt?return_to=%2Findex.html';signIn.target='_top';signIn.textContent='Sign in for AI analytics';signIn.className='text-button';controls.append(signIn);}}}catch{/* Guided questions remain available when no server is deployed. */}
