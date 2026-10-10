'use strict';

// Scenario inputs are held only in this page's memory; no business data is sent.
const impactExample = {currency:'SAR', tasks:1000, manual:8, assisted:3, adoption:60,
  hourly:50, realization:0, monthlyCost:500, setup:2000};
let impactInputs = {...impactExample};
let impactEdited = false;
const impactLimits = {tasks:[0,10000000],manual:[0,1440],assisted:[0,1440],
  adoption:[0,100],hourly:[0,1000000],realization:[0,100],monthlyCost:[0,1000000000],setup:[0,1000000000]};

function calculateImpact(input) {
  for (const [key,[min,max]] of Object.entries(impactLimits)) {
    if (input[key] === '' || input[key] == null || !Number.isFinite(Number(input[key])) || Number(input[key]) < min || Number(input[key]) > max)
      throw new RangeError('Invalid assumption: '+key);
  }
  const v = Object.fromEntries(Object.keys(impactLimits).map(key=>[key,Number(input[key])]));
  const adoptedTasks = v.tasks*v.adoption/100;
  const baselineHours = v.tasks*v.manual/60;
  if(!Number.isInteger(v.tasks))throw new RangeError('Task count must be a whole number');
  const hoursFreed = adoptedTasks*(v.manual-v.assisted)/60;
  const assistedHours = baselineHours-hoursFreed;
  const capacityValue = hoursFreed*v.hourly;
  // A slower assisted workflow adds full labor cost, rather than discounting it
  // by the share of saved capacity a business can turn into cash.
  const cashBenefit = capacityValue > 0 ? capacityValue*v.realization/100 : capacityValue;
  const netMonthlyCash = cashBenefit-v.monthlyCost;
  const firstYearCosts = v.setup+12*v.monthlyCost;
  return {adoptedTasks,baselineHours,assistedHours,hoursFreed,capacityValue,cashBenefit,
    netMonthlyCash,firstYearCosts,firstYearNetCash:12*netMonthlyCash-v.setup,
    firstYearROI:firstYearCosts>0?(12*cashBenefit-firstYearCosts)/firstYearCosts*100:null,
    paybackMonths:netMonthlyCash>0?v.setup/netMonthlyCash:null};
}

function impactNumber(value) {
  return new Intl.NumberFormat(language==='ar'?'ar-SA':'en',{maximumFractionDigits:1}).format(value);
}
function impactMoney(value) {return esc(impactInputs.currency)+' '+impactNumber(value);}
function impactField(key,label,help) {
  const [min,max]=impactLimits[key];
  return `<label class="field"><span>${tx(label)}</span><input name="${key}" type="number" value="${esc(impactInputs[key])}" min="${min}" max="${max}" step="${key==='tasks'?'1':'any'}" required aria-describedby="impact-help-${key}"><small id="impact-help-${key}">${tx(help)}</small></label>`;
}
function impactResults() {
  let r;
  try {r=calculateImpact(impactInputs);} catch {
    return `<p class="impact-error" role="alert">${tx('Enter a valid number in every field. Percentages must be between 0 and 100; costs and times cannot be negative.')}</p>`;
  }
  const metric=(label,value,help)=>stat(label,value,help);
  const scenarios=[25,50,75,100].map(adoption=>{
    const s=calculateImpact({...impactInputs,adoption});
    return `<tr><th scope="row">${impactNumber(adoption)}%</th><td>${impactNumber(s.hoursFreed)}</td><td>${impactMoney(s.capacityValue)}</td><td>${impactMoney(s.netMonthlyCash)}</td></tr>`;
  }).join('');
  return `<div class="stats impact-stats">${metric('Hours freed / month',impactNumber(r.hoursFreed),'Includes review and corrections')}${metric('Capacity value / month',impactMoney(r.capacityValue),'Value of time; not extra cash')}${metric('Net cash effect / month',impactMoney(r.netMonthlyCash),'Cash benefit minus recurring cost')}${metric('First-year net cash effect',impactMoney(r.firstYearNetCash),'Twelve months, less setup cost')}</div>
    ${r.hoursFreed<0?`<p class="impact-error">${tx('These assumptions increase staff workload. Added labor cost is included in the cash effect.')}</p>`:''}
    <dl class="impact-breakdown"><div><dt>${tx('Manual workload / month')}</dt><dd>${impactNumber(r.baselineHours)} ${tx('hours')}</dd></div><div><dt>${tx('Assisted workload / month')}</dt><dd>${impactNumber(r.assistedHours)} ${tx('hours')}</dd></div><div><dt>${tx('Cash benefit / month')}</dt><dd>${impactMoney(r.cashBenefit)}</dd></div><div><dt>${tx('First-year cash ROI')}</dt><dd>${r.firstYearROI===null?tx('Not applicable: no costs'):impactNumber(r.firstYearROI)+'%'}</dd></div><div><dt>${tx('Setup payback')}</dt><dd>${r.paybackMonths===null?tx('No payback under these assumptions'):r.paybackMonths===0?tx('No setup cost'):impactNumber(r.paybackMonths)+' '+tx('months')}</dd></div></dl>
    <h3>${tx('What if adoption changes?')}</h3><p class="hint">${tx('All other assumptions stay the same. These scenarios are not forecasts or confidence intervals.')}</p>
    <div class="impact-table-wrap"><table class="impact-table"><caption>${tx('Monthly impact by share of tasks using the agent')}</caption><thead><tr><th scope="col">${tx('Adoption')}</th><th scope="col">${tx('Hours freed')}</th><th scope="col">${tx('Capacity value')}</th><th scope="col">${tx('Net cash effect')}</th></tr></thead><tbody>${scenarios}</tbody></table></div>`;
}
function impactView() {
  return heading('Impact calculator','Explore an assumed business case using your own workload and costs.')+
    `<div class="impact-notice"><strong>${tx('Scenario projection — not measured impact')}</strong><p>${tx('The starting numbers are illustrative. Replace them with your estimates. Results do not demonstrate Mutabi performance or guarantee savings.')}</p></div>
    <div class="impact-layout">${panel('Your assumptions','Any repeatable workflow; use the same task definition before and after.',
      `<form id="impactForm" class="form-stack"><label class="field"><span>${tx('Currency label')}</span><select name="currency">${['SAR','EGP','JOD','USD','EUR','GBP','AED'].map(c=>`<option ${impactInputs.currency===c?'selected':''}>${c}</option>`).join('')}</select><small>${tx('All money inputs use this currency. No exchange-rate conversion.')}</small></label>
      ${impactField('tasks','Tasks per month','Count tasks across the whole team, once each.')}
      <div class="form-two">${impactField('manual','Manual minutes / task','Average current end-to-end staff effort.')}${impactField('assisted','Assisted minutes / task','Include human review, exceptions and corrections.')}</div>
      ${impactField('adoption','Tasks using the agent (%)','Remaining tasks keep the manual workflow.')}
      ${impactField('hourly','Staff cost / hour','Fully loaded hourly cost in the selected currency.')}
      ${impactField('realization','Saved capacity converted to cash (%)','Use 0 unless payroll, overtime or contractor spending falls.')}
      <div class="form-two">${impactField('monthlyCost','Recurring cost / month','Include models, hosting, support and subscription.')}${impactField('setup','One-time setup cost','Include integration, onboarding and training.')}</div>
      <p class="hint">${tx('Inputs stay in this page until you reload. They are not sent to the server.')}</p><button type="button" class="secondary" data-impact-action="example">${tx('Restore illustrative example')}</button></form>`)}
      ${panel('Projected impact','Constant workload and adoption; a full twelve months of use.',`<div id="impactResults" aria-live="polite" aria-atomic="true">${impactResults()}</div><div class="card-actions"><button type="button" class="primary" data-impact-action="export">${tx('Download scenario')}</button><button type="button" class="secondary" data-impact-action="print">${tx('Print scenario')}</button></div>`)}
    </div>${panel('How the calculation works','',`<ol class="definition-list"><li>${tx('Hours freed = tasks × adoption × (manual minutes − assisted minutes) ÷ 60.')}</li><li>${tx('Capacity value = hours freed × hourly staff cost.')}</li><li>${tx('Cash benefit = positive capacity value × cash realization; added labor is charged in full.')}</li><li>${tx('Net monthly cash = cash benefit − recurring cost. First-year net cash = 12 × net monthly cash − setup cost.')}</li><li>${tx('Cash ROI = (12 × cash benefit − first-year costs) ÷ first-year costs. Payback = setup cost ÷ positive net monthly cash.')}</li></ol><p class="hint">${tx('Capacity value and cash benefit overlap; do not add them. Collections, revenue uplift, financing benefits and tax effects are excluded. Test the time and adoption assumptions in a pilot.')}</p><p id="impactScenarioBasis" class="hint">${tx(impactEdited?'Scenario uses your entered assumptions.':'Illustrative example assumptions.')}</p>`)}`;
}

if (typeof document !== 'undefined') {
  document.addEventListener('submit',event=>{if(event.target.id==='impactForm')event.preventDefault();});
  document.addEventListener('input',event=>{
    if(!event.target.closest('#impactForm'))return;
    impactInputs[event.target.name]=event.target.value;
    impactEdited=true;
    document.getElementById('impactResults').innerHTML=impactResults();
    document.getElementById('impactScenarioBasis').textContent=t('Scenario uses your entered assumptions.');
  });
  document.addEventListener('click',event=>{
    const action=event.target.closest('[data-impact-action]')?.dataset.impactAction;
    if(!action)return;
    if(action==='example'){impactInputs={...impactExample};impactEdited=false;render();return;}
    let results;
    try {results=calculateImpact(impactInputs);} catch {document.getElementById('impactForm').reportValidity();return;}
    if(action==='print'){window.print();return;}
    const report={type:'Assumption-based scenario; not measured business impact',
      basis:impactEdited?'User-entered assumptions':'Illustrative example',
      assumptions:{...impactInputs},results,
      adoptionScenarios:[25,50,75,100].map(adoption=>({adoption,results:calculateImpact({...impactInputs,adoption})})),
      scope:'Monthly constant workload, full 12-month use. Assisted effort includes human review. Capacity value overlaps with cash benefit. No revenue or collections uplift modeled.',
      formulas:{hoursFreed:'tasks * adoption / 100 * (manual - assisted) / 60',capacityValue:'hoursFreed * hourly',cashBenefit:'capacityValue > 0 ? capacityValue * realization / 100 : capacityValue',netMonthlyCash:'cashBenefit - monthlyCost',firstYearNetCash:'12 * netMonthlyCash - setup',firstYearROI:'(12 * cashBenefit - setup - 12 * monthlyCost) / (setup + 12 * monthlyCost) * 100',paybackMonths:'setup / positive netMonthlyCash'}};
    const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='mutabi-impact-scenario.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
}
if(typeof module!=='undefined')module.exports={calculateImpact,impactExample};
