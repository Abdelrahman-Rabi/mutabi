'use strict';
let state, token, selected = 'INV-001', scenario = '', busy = false, noticeSource = '';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = value => translateCopy(String(value ?? '').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()));
const amount = value => new Intl.NumberFormat(language==='ar'?'ar-SA':'en-SA',{minimumFractionDigits:2,maximumFractionDigits:2}).format(value/100);
const date = value => value ? new Date(value.slice(0,10)+'T12:00:00').toLocaleDateString(language==='ar'?'ar-SA-u-ca-gregory':'en-GB',{day:'numeric',month:'short',year:'numeric'}) : '—';
const invoiceRows = (name,id=selected) => state[name].filter(r=>r.invoice_id===id);
const scenarioLabels = {'TC-03':'Payment claim — no payment confirmed','TC-04':'Full payment confirmed','TC-05':'Partial payment received','TC-06':'Missed promise — balance unchanged','TC-11':'Accounting source unavailable','TC-14':'Payment confirmed before sending','TC-15':'Promise date passed — no payment'};
function caseStatus(invoice){
  if(invoice.status==='settled') return ['Settled','teal'];
  if(invoiceRows('disputes',invoice.invoice_id).some(r=>r.status==='pending_review')) return ['Disputed','amber'];
  const tasks=invoiceRows('tasks',invoice.invoice_id);
  if(tasks.some(r=>r.status==='pending'&&r.task_type==='payment_verification')) return ['Verify payment','amber'];
  const promises=invoiceRows('promises',invoice.invoice_id);
  if(promises.some(r=>r.status==='missed')) return ['Missed promise','red'];
  if(promises.some(r=>r.status==='partially_fulfilled')) return ['Part paid','amber'];
  if(promises.some(r=>r.status==='active')) return ['Promise recorded','teal'];
  const completed=invoiceRows('audit_events',invoice.invoice_id).filter(r=>r.action==='message_completed').at(-1);
  if(completed){const result=JSON.parse(completed.details_json);if(result.status==='awaiting_clarification')return ['Needs details','amber'];if(result.status==='needs_human_review')return ['Needs review','amber'];}
  return ['Overdue',''];
}
function badge(text,tone=''){return `<span class="badge ${escape(tone)}">${escape(text)}</span>`;}
function notice(text,error=false){noticeSource=text;$('notice').hidden=false;$('notice').className=error?'error':'';$('notice').textContent=translateCopy(text);}
async function refresh(){const reply=$('newReply')?.value,opened=document.querySelector('.reply-form')?.open;const response=await fetch('/api/state');if(!response.ok)throw new Error('Could not load workspace');state=await response.json();render();if($('newReply'))$('newReply').value=reply??'';if(document.querySelector('.reply-form'))document.querySelector('.reply-form').open=opened??false;}
function render(){
  applyLanguage();renderProvider();
  $('modelStatus').textContent=state.model_ready?'AI provider ready':'Connect the selected provider';
  $('modelStatus').title=state.model_ready?`Configured model: ${state.model}. Calls require API availability.`:state.provider==='chatgpt_plan'?'Connect ChatGPT and enable plan usage.':'Set GEMINI_API_KEY locally and restart the server.';
  $('demoDate').value=state.now.slice(0,10);$('demoDate').min=state.now.slice(0,10);$('clockLabel').textContent='Riyadh · '+date(state.now);
  const balance=state.invoices.reduce((sum,r)=>sum+r.outstanding_minor,0);
  const pending=state.tasks.filter(r=>r.status==='pending');
  const metrics=[['Outstanding balance','SAR '+amount(balance),'Across '+state.invoices.length+' synthetic invoices'],['Open promises',state.promises.filter(r=>r.status==='active').length,'Commitments awaiting payment'],['Tasks due',pending.filter(r=>r.due_date<=state.now.slice(0,10)).length,'Pending tasks as of the demo date'],['Awaiting approval',state.drafts.filter(r=>r.status==='awaiting_approval').length,'Employee review before sending']];
  $('metrics').innerHTML=metrics.map(([title,value,help])=>`<div class="metric"><span class="label">${escape(title)}</span><strong>${escape(value)}</strong><small>${escape(help)}</small></div>`).join('');
  renderCases();renderDetail();['metrics','modelStatus','clockLabel'].forEach(id=>localizeDOM($(id)));$('modelStatus').title=translateCopy($('modelStatus').title);setBusy(busy);
}
function renderCases(){
  const query=$('search').value.toLowerCase();
  const invoices=state.invoices.filter(r=>(r.customer_name+' '+customerName(r.customer_name)+' '+r.invoice_id).toLowerCase().includes(query));
  $('caseCount').textContent=state.invoices.length;
  $('caseList').innerHTML=invoices.map(r=>{const [text,tone]=caseStatus(r);return `<button class="case-button ${selected===r.invoice_id?'selected':''}" data-case="${escape(r.invoice_id)}" aria-pressed="${selected===r.invoice_id}"><div class="case-top"><strong>${escape(customerName(r.customer_name))}</strong>${badge(text,tone)}</div><div class="case-meta"><span>${escape(r.invoice_id)}</span><span>SAR ${amount(r.outstanding_minor)}</span></div></button>`;}).join('')+
    `<button class="case-button ${selected==='unlinked'?'selected':''}" data-case="unlinked" aria-pressed="${selected==='unlinked'}"><div class="case-top"><strong>Unassigned replies</strong>${badge('Needs reference','amber')}</div><div class="case-meta"><span>Customer inbox</span><span>${state.messages.filter(m=>!m.invoice_id).length} reply</span></div></button>`;
  localizeDOM($('caseList'));
  document.querySelectorAll('[data-case]').forEach(button=>button.onclick=()=>{selected=button.dataset.case;scenario='';$('notice').hidden=true;render();});
}
function messageCard(message){
  return `<div class="message"><div class="message-meta"><span>${escape(message.message_id)}</span><span>${date(message.received_at)}</span></div><p dir="auto">${escape(message.text)}</p><div class="message-actions"><button data-process="${escape(message.message_id)}" ${!state.model_ready&&message.processing_status==='pending'?'disabled':''}>${message.processing_status==='pending'?'Analyze reply':'View saved result'}</button>${badge(message.processing_status,message.processing_status==='processed'?'teal':'')}</div></div>`;
}
function renderDetail(){
  if(selected==='unlinked'){
    $('detail').innerHTML=`<div class="detail-header"><div><div class="eyebrow">CUSTOMER INBOX</div><h2>Identify the invoice first.</h2><p class="hint">An amount match alone is not enough to assign a payment promise.</p></div></div>${state.messages.filter(m=>!m.invoice_id).map(messageCard).join('')}`;
    localizeDOM($('detail'));bindProcesses();return;
  }
  const invoice=state.invoices.find(r=>r.invoice_id===selected);if(!invoice)return;
  const [status,tone]=caseStatus(invoice);
  const simulations=state.accounting_scenarios.filter(r=>r.invoice_id===selected);
  const messages=invoiceRows('messages').filter(r=>r.message_id!=='MSG-013');
  const promises=invoiceRows('promises');const tasks=invoiceRows('tasks');const drafts=invoiceRows('drafts');
  const audits=invoiceRows('audit_events');
  $('detail').innerHTML=`
    <div class="detail-header"><div><div class="eyebrow">${escape(invoice.invoice_id)} · CUSTOMER ACCOUNT</div><h2>${escape(customerName(invoice.customer_name))}</h2>${badge(status,tone)}</div><div class="balance"><strong>SAR ${amount(invoice.outstanding_minor)}</strong><span>Outstanding balance</span></div></div>
    <div class="facts"><div><span>Invoice due</span><strong>${date(invoice.due_date)}</strong></div><div><span>Last balance snapshot</span><strong>${date(invoice.balance_updated_at)}</strong></div><div><span>Contact channel</span><strong>Simulated inbox</strong></div></div>
    <div class="simulation"><label for="scenario">Accounting simulation</label><select id="scenario"><option value="">Current snapshot only</option>${simulations.map(r=>`<option value="${escape(r.scenario_id)}" ${scenario===r.scenario_id?'selected':''}>${escape(scenarioLabels[r.scenario_id]||r.scenario_id)}</option>`).join('')}</select><button class="secondary" id="verifyBalance">Verify balance</button><button class="secondary" id="checkFollowups">Run due follow-ups</button><div class="hint" id="simulationHint">Choose an accounting event to test settlement or a missed payment.</div></div>
    <section class="panel"><div class="panel-head"><h3>Customer replies</h3><span class="subtle">AI interprets · rules validate</span></div><div class="panel-body">${messages.length?messages.map(messageCard).join(''):'<p class="empty">No incoming reply yet. Add a synthetic reply below.</p>'}<details class="reply-form"><summary>Add a synthetic customer reply</summary><label for="newReply" class="sr-only">New customer reply</label><textarea id="newReply" placeholder="I will pay SAR 3,000 on October 5, 2026."></textarea><button class="secondary" id="saveReply">Save reply</button><p class="hint">Saved replies are processed separately so you can review them first.</p></details></div></section>
    <div class="grid-two"><section class="panel"><div class="panel-head"><h3>Payment promises</h3></div><div class="panel-body">${promises.length?promises.map(p=>`<div class="record"><strong>SAR ${amount(p.amount_minor)}</strong> ${badge(label(p.status),p.status==='active'||p.status==='fulfilled'?'teal':'amber')}<p>Promised for ${date(p.promised_date)}</p></div>`).join(''):'<p class="empty">No confirmed promise recorded.</p>'}</div></section><section class="panel"><div class="panel-head"><h3>Next actions</h3></div><div class="panel-body">${tasks.length?tasks.map(t=>`<div class="record"><strong>${escape(label(t.task_type))}</strong> ${badge(label(t.status),t.status==='closed'?'teal':'')}<p>${date(t.due_date)}</p></div>`).join(''):'<p class="empty">No follow-up task yet.</p>'}</div></section></div>
    <section class="panel"><div class="panel-head"><h3>Drafts & approval</h3><button class="text-button" id="prepareReminder">Prepare reminder</button></div>${drafts.length?drafts.map(d=>`<div class="draft"><p class="draft-text" dir="auto">${escape(d.text)}</p><div class="draft-actions">${badge(label(d.status),d.status==='sent'?'teal':'')} ${d.status==='awaiting_approval'?`<button data-approve="${escape(d.draft_id)}">Approve draft</button>`:''}${d.status==='approved'?`<button data-send="${escape(d.draft_id)}">Send to simulated inbox</button>`:''}</div>${state.deliveries.some(r=>r.draft_id===d.draft_id)?'<div class="delivery">Delivered once to the simulated inbox. No customer was contacted.</div>':''}</div>`).join(''):'<div class="panel-body"><p class="empty">Process a reply or prepare a reminder to create a draft.</p></div>'}</section>
    <details class="audit"><summary>Activity history · ${audits.length} events</summary>${audits.slice().reverse().map(a=>`<div class="audit-row"><time>${escape(a.occurred_at.slice(11,16))}</time><span>${escape(label(a.action))}<br><span class="subtle">${escape(auditDescription(a))}</span></span></div>`).join('')||'<p class="empty">Your actions will appear here.</p>'}</details>`;
  localizeDOM($('detail'));
  $('scenario').onchange=()=>{scenario=$('scenario').value;simulationHint();};simulationHint();
  $('verifyBalance').onclick=()=>act('verify');$('checkFollowups').onclick=()=>act('followups');$('prepareReminder').onclick=()=>act('prepare');
  $('saveReply').onclick=()=>act('add_reply',{text:$('newReply').value});
  bindProcesses();
  document.querySelectorAll('[data-approve]').forEach(button=>button.onclick=()=>act('approve',{draft_id:button.dataset.approve}));
  document.querySelectorAll('[data-send]').forEach(button=>button.onclick=()=>act('send',{draft_id:button.dataset.send}));
}
function auditDescription(event){const data=JSON.parse(event.details_json);return data.reason||data.source_reference||(data.promised_date?`Promise date ${data.promised_date}`:data.status?label(data.status):data.message_id||'Saved in the workspace');}
function simulationHint(){const event=state.accounting_scenarios.find(r=>r.scenario_id===scenario&&r.invoice_id===selected);$('simulationHint').textContent=event?`Synthetic event available from ${date(event.available_at)} at ${event.available_at.slice(11,16)} Riyadh time.`:'Uses the existing snapshot. Future events are not applied automatically.';localizeDOM($('simulationHint'));}
function bindProcesses(){document.querySelectorAll('[data-process]').forEach(button=>button.onclick=()=>act('process',{message_id:button.dataset.process}));}
function setBusy(value){busy=value;document.querySelectorAll('button,input,select,textarea').forEach(element=>{if(value){if(element.dataset.wasDisabled===undefined)element.dataset.wasDisabled=element.disabled?'1':'0';element.disabled=true;}else if(element.dataset.wasDisabled!==undefined){element.disabled=element.dataset.wasDisabled==='1';delete element.dataset.wasDisabled;}});}
function resultMessage(action,result){
  if(action==='process'){
    if(result.status==='promise_recorded')return 'Promise recorded. A balance check has been scheduled for the day after the promised date.';
    if(result.status==='awaiting_clarification')return result.clarification_text||'More detail is needed. Review the clarification draft before approving.';
    if(result.status==='awaiting_payment_verification')return 'Payment claim recorded. Finance verification is needed; the balance remains authoritative.';
    if(result.status==='dispute_pending_review')return 'Dispute recorded and routed to finance review. The balance has not been reduced.';
    return label(result.status)+'. Review the case history for details.';
  }
  if(action==='send')return result.sent?'Message delivered to the simulated inbox. No real customer was contacted.':'Sending blocked: '+label(result.reason)+'.';
  if(action==='verify')return result.verified?'Balance verified: SAR '+amount(result.outstanding_minor)+'.':'Verification unavailable: '+label(result.error)+'. No payment confirmation was assumed.';
  if(action==='followups')return result.results.length?result.results.map(r=>label(r.status)).join(' · ')+'. Review the updated tasks and drafts.':'No balance-check tasks are due for this case on the selected date.';
  if(action==='approve')return 'Draft approved by the demo employee. Sending remains a separate action.';
  if(action==='add_reply')return 'Synthetic reply saved. Select “Analyze reply” to interpret it.';
  if(action==='clock')return 'Demo date updated. Run follow-ups to check commitments due by this date.';
  if(action==='reset')return 'Demo workspace reset to the original synthetic examples.';
  if(action==='prepare')return result.status==='draft_ready'?'Reminder draft created for employee review.':label(result.status)+'. Review the case before contacting the customer.';
  if(action==='provider')return 'AI provider updated.';
  if(action.startsWith('chatgpt_'))return 'ChatGPT settings updated.';
  return 'Action completed.';
}
async function act(action,extra={}){
  if(busy)return;
  setBusy(true);notice(action==='process'?'AI is interpreting the reply. The workflow will validate the result before saving changes…':'Updating the workspace…');
  try{
    const response=await fetch('/api/action/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Demo-Token':token},body:JSON.stringify({invoice_id:selected==='unlinked'?null:selected,scenario,...extra})});
    const body=await response.json();if(!response.ok)throw new Error(body.error+(body.retry_after?` Retry after about ${Math.ceil(body.retry_after)} seconds.`:''));
    if(action==='reset'){selected='INV-001';scenario='';}
    if((action==='add_reply'||action==='reset')&&$('newReply'))$('newReply').value='';
    await refresh();notice(resultMessage(action,body.result),action==='send'&&!body.result.sent);
  }catch(error){notice(error.message,true);}finally{setBusy(false);}
}
let authPoll = null;
function renderProvider(){
  const auth=state.chatgpt;
  $('providerSettings').innerHTML=`<div class="provider-row"><label for="providerChoice">AI provider</label><select id="providerChoice"><option value="chatgpt_plan" ${state.provider==='chatgpt_plan'?'selected':''}>ChatGPT plan</option><option value="gemini" ${state.provider==='gemini'?'selected':''}>Gemini API</option></select>${state.provider==='chatgpt_plan'?`<button class="secondary" id="connectChatGPT">${auth.pending?'Sign-in in progress…':'Continue with ChatGPT'}</button>${auth.connected?'<button class="text-button" id="disconnectChatGPT">Disconnect</button>':''}<a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Manage usage</a>`:'<span class="hint">Gemini uses the locally configured API key.</span>'}</div>${state.provider==='chatgpt_plan'?`<p class="hint">Eligible requests use your ChatGPT plan allowance. Initial sign-in and permission are required.</p><div class="provider-row">${auth.accounts.length?`<label for="chatgptAccount">ChatGPT account</label><select id="chatgptAccount">${auth.accounts.map(a=>`<option value="${escape(a.id)}" ${auth.active_account===a.id?'selected':''}>${escape(a.label)}</option>`).join('')}</select><button class="text-button" id="addChatGPT">Add account</button>`:''}${auth.connected?`<span>${auth.plan_enabled?'Using ChatGPT plan':'Plan permission is disabled'}</span><button class="secondary" id="refreshModels">Refresh models</button>`:''}${auth.models.length?`<label for="chatgptModel">Model</label><select id="chatgptModel">${auth.models.map(m=>`<option value="${escape(m.slug)}" ${auth.model===m.slug?'selected':''}>${escape(m.display_name)}</option>`).join('')}</select>`:auth.model?`<span>${escape(auth.model)}</span>`:''}</div>${auth.error?`<p class="connection-error" role="status">${escape(translateCopy(auth.error))}</p>`:''}${auth.show_welcome?'<div class="welcome"><span>You’re using your ChatGPT plan. Manage usage in ChatGPT settings.</span><button class="secondary" id="dismissWelcome">Got it</button></div>':''}`:''}`;
  localizeDOM($('providerSettings'));
  $('providerChoice').onchange=()=>act('provider',{provider:$('providerChoice').value});
  if($('connectChatGPT')){$('connectChatGPT').onclick=()=>connectChatGPT(false);$('connectChatGPT').disabled=auth.pending;}
  if($('addChatGPT'))$('addChatGPT').onclick=()=>connectChatGPT(true);
  if($('disconnectChatGPT'))$('disconnectChatGPT').onclick=()=>act('chatgpt_disconnect');
  if($('refreshModels'))$('refreshModels').onclick=()=>act('chatgpt_models');
  if($('chatgptModel'))$('chatgptModel').onchange=()=>act('chatgpt_model',{model:$('chatgptModel').value});
  if($('chatgptAccount'))$('chatgptAccount').onchange=()=>act('chatgpt_account',{account:$('chatgptAccount').value});
  if($('dismissWelcome'))$('dismissWelcome').onclick=()=>act('chatgpt_welcome');
  if(auth.pending)pollChatGPT();
}
function pollChatGPT(){
  if(authPoll)return;
    authPoll=setInterval(async()=>{
      try{
        const response=await fetch('/api/chatgpt');if(!response.ok)return;
        const auth=await response.json();state.chatgpt=auth;renderProvider();
        if(!auth.pending){clearInterval(authPoll);authPoll=null;
          state.model_ready=state.provider==='chatgpt_plan'?auth.ready:state.model_ready;
          state.model=state.provider==='chatgpt_plan'?(auth.model||'ChatGPT plan'):state.model;
          const reply=$('newReply')?.value,opened=document.querySelector('.reply-form')?.open;
          render();if($('newReply'))$('newReply').value=reply??'';
          if(document.querySelector('.reply-form'))document.querySelector('.reply-form').open=opened??false;
          notice(auth.error|| (auth.ready?'ChatGPT connected. You can analyze a synthetic reply.':'Review the ChatGPT connection and model settings.'),!!auth.error);
        }
      }catch(error){/* Poll does not mutate collection data; next tick can retry. */}
    },2000);
}
async function connectChatGPT(newAccount){
  if(busy)return;
  // Open synchronously from the user's click so browser popup blockers do not lose the flow.
  const popup=window.open('about:blank','mutabi-chatgpt-signin');
  if(!popup){notice('Allow the sign-in popup, then try again.',true);return;}
  setBusy(true);
  try{
    const response=await fetch('/api/action/chatgpt_connect',{method:'POST',headers:{'Content-Type':'application/json','X-Demo-Token':token},body:JSON.stringify({new_account:newAccount})});
    const body=await response.json();if(!response.ok)throw new Error(body.error);
    popup.opener=null;popup.location.href=body.result.authorization_url;
    state.chatgpt.pending=true;renderProvider();
    notice('Complete sign-in and permission in the browser window, then return here.');
    pollChatGPT();
  }catch(error){popup.close();notice(error.message,true);}finally{setBusy(false);}
}

function customerName(name){return language==='ar'?name.replace(/^Demo Grocery /,'بقالة تجريبية '):name;}
function applyLanguage(){
  document.documentElement.lang=language;document.documentElement.dir=language==='ar'?'rtl':'ltr';
  document.title=language==='ar'?'متابع — مساحة عمل التحصيل':'Mutabi — Collections workspace';
  document.querySelectorAll('.rail,header,.controls,.queue>.section-head,.queue>.sr-only,main>footer,#resetDialog').forEach(root=>localizeDOM(root,true));
  const search=$('search');if(!search.dataset.originalPlaceholder)search.dataset.originalPlaceholder=search.placeholder;
  search.placeholder=translateCopy(search.dataset.originalPlaceholder);
  $('metrics').setAttribute('aria-label',translateCopy('Workspace summary'));
  $('languageSwitch').textContent=language==='ar'?'English':'العربية';
  $('languageSwitch').setAttribute('aria-label',language==='ar'?'Switch to English':'Switch to Arabic');
  if(noticeSource)$('notice').textContent=translateCopy(noticeSource);
}
$('languageSwitch').onclick=()=>{
  const reply=$('newReply')?.value, replyOpen=document.querySelector('.reply-form')?.open;
  const auditOpen=document.querySelector('.audit')?.open, draftDate=$('demoDate').value;
  language=language==='ar'?'en':'ar';localStorage.setItem('mutabi-language',language);render();
  if($('newReply'))$('newReply').value=reply??'';
  if(document.querySelector('.reply-form'))document.querySelector('.reply-form').open=replyOpen??false;
  if(document.querySelector('.audit'))document.querySelector('.audit').open=auditOpen??false;
  $('demoDate').value=draftDate;
};
applyLanguage();
$('search').oninput=()=>renderCases();
$('advanceClock').onclick=()=>act('clock',{now:$('demoDate').value+'T10:05:00+03:00'});
$('resetDemo').onclick=()=>$('resetDialog').showModal();$('cancelReset').onclick=()=>$('resetDialog').close();
$('confirmReset').onclick=()=>{$('resetDialog').close();act('reset',{scenario:null});};
(async()=>{try{const response=await fetch('/api/session');token=(await response.json()).token;await refresh();}catch(error){notice(error.message,true);}})();
