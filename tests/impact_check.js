'use strict';
const assert=require('node:assert/strict');
const {calculateImpact,impactExample}=require('../mutabi/static/impact.js');
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);
let r=calculateImpact(impactExample);
close(r.hoursFreed,50); close(r.assistedHours,250/3); close(r.capacityValue,2500);
assert.equal(r.cashBenefit,0); assert.equal(r.netMonthlyCash,-500);
assert.equal(r.firstYearNetCash,-8000); assert.equal(r.firstYearROI,-100); assert.equal(r.paybackMonths,null);
r=calculateImpact({...impactExample,realization:40});
assert.equal(r.cashBenefit,1000); assert.equal(r.netMonthlyCash,500);
assert.equal(r.firstYearNetCash,4000); assert.equal(r.firstYearROI,50); assert.equal(r.paybackMonths,4);
for(const overrides of [{tasks:0},{adoption:0},{assisted:8}]){
  r=calculateImpact({...impactExample,...overrides});close(r.hoursFreed,0);assert.equal(r.netMonthlyCash,-500);
}
r=calculateImpact({...impactExample,assisted:10,realization:0});
close(r.hoursFreed,-20);close(r.cashBenefit,-1000);close(r.netMonthlyCash,-1500);
r=calculateImpact({...impactExample,monthlyCost:0,setup:0,realization:100});
assert.equal(r.firstYearROI,null);assert.equal(r.paybackMonths,0);
for(const bad of [{tasks:''},{tasks:1.5},{hourly:NaN},{assisted:Infinity},{adoption:101},{realization:-1},{setup:-100},{manual:1441}]){
  assert.throws(()=>calculateImpact({...impactExample,...bad}),RangeError);
}
// More adoption scales both saved hours and cash benefits, without charging
// implementation costs twice or multiplying by a second team-size input.
const half=calculateImpact({...impactExample,adoption:50,realization:100});
const full=calculateImpact({...impactExample,adoption:100,realization:100});
close(full.hoursFreed,2*half.hoursFreed);close(full.cashBenefit,2*half.cashBenefit);
console.log('Impact scenarios: expected values, zero adoption, slower workflows, invalid inputs, ROI and payback passed.');
