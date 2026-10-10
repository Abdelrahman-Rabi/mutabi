'use strict';
// Render the actual backend contract in both languages without browser packages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({
  payload, console, Intl, Date, performance: { now: () => 0 },
  localStorage: { getItem: () => null },
  document: { addEventListener() {} }, window: { addEventListener() {} },
  fetch: () => new Promise(() => {}),
});
const staticPath = path.join(__dirname, '..', 'mutabi', 'static');
for (const file of ['i18n.js', 'impact.js', 'app.js']) {
  vm.runInContext(fs.readFileSync(path.join(staticPath, file), 'utf8'), context, { filename: file });
}
vm.runInContext('state = JSON.parse(JSON.stringify(payload))', context);
const views = ['overviewView', 'collectionsView', 'promisesView', 'tasksView',
  'approvalsView', 'analyticsView', 'impactView', 'feedbackView', 'settingsView', 'studioView'];
for (const locale of ['ar', 'en']) {
  vm.runInContext(`language = '${locale}'`, context);
  for (const view of views) {
    const html = vm.runInContext(`${view}()`, context);
    assert.match(html, /<h1>/, `${locale} ${view} must render its heading`);
  }
  for (const steps of [{}, { steps: ['English step'] }, { steps_ar: ['خطوة عربية'] },
    { steps: null, steps_ar: null }, { steps: 'unexpected string', steps_ar: {} }]) {
    context.storyFixture = { id: 'example', title: 'Example', description: 'Example', ...steps };
    vm.runInContext('state.stories = [storyFixture]', context);
    assert.match(vm.runInContext('studioView()', context), /story-card/);
  }
  context.storyFixture = { steps: ['English fallback'], steps_ar: ['خطوة عربية'] };
  const selectedSteps = vm.runInContext('storySteps(storyFixture)', context);
  assert.equal(selectedSteps[0], locale === 'ar' ? 'خطوة عربية' : 'English fallback');
  context.storyFixture = { steps: ['English fallback'] };
  assert.equal(vm.runInContext('storySteps(storyFixture)[0]', context), 'English fallback');
  vm.runInContext('state = JSON.parse(JSON.stringify(payload))', context);
}
console.log('All ten views render in English and Arabic; optional story steps are safe.');
