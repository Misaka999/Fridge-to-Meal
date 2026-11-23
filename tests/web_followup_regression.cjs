// Browser regression for accepted vs rejected clarification responses.
// Run with Node.js and Playwright installed; all API responses are mocked.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH} : {})});
  try {
    const page = await browser.newPage();
    const empty = {pantry:null, servings:null,
      preferences:{dietary_restrictions:[],likes:[]}, as_of_date:null};
    let state = structuredClone(empty), reject = false;
    await page.route('**/api/kitchen', route => route.fulfill({json:{
      state, example: empty, units:['g','ml','count'], restrictions:['vegetarian'],
      catalogue:{description:'Offline browser regression'}
    }}));
    await page.route('**/api/turn', async route => {
      const body = route.request().postDataJSON();
      if (!reject) {
        state = structuredClone(body.update);
        // Backend object key order must not affect comparison.
        state.pantry = state.pantry.map(item => ({unit:item.unit, name:item.name,
          expires_on:item.expires_on, quantity:item.quantity}));
      }
      await route.fulfill({json:{request:state,
        result:{status:'needs_clarification',recipe_ids:[],message:'Source serving count needs verification.'},
        metrics:{model_calls:0,elapsed_seconds:0},tool_trace:[]}});
    });
    await page.goto('http://127.0.0.1:8766');
    await page.locator('#fields').waitFor();
    await page.waitForFunction(() => !document.querySelector('#fields').disabled);
    const follow = page.locator('#message');
    assert.equal(await follow.isDisabled(),true);
    await page.locator('.name').fill('egg');
    await page.locator('.qty').fill('4');
    await page.locator('.unit').selectOption('count');
    await page.locator('#recommend').click();
    await page.waitForFunction(() => !document.querySelector('#fields').disabled);
    assert.equal(await follow.isEnabled(),true,'Accepted source clarification must allow a follow-up.');
    await follow.fill('Make it for one person.');
    assert.equal(await follow.inputValue(),'Make it for one person.');
    await page.locator('.qty').fill('6');
    assert.equal(await follow.isDisabled(),true,'Unsubmitted edits must remain distinct from server state.');
    reject = true;
    await page.locator('#recommend').click();
    await page.waitForFunction(() => !document.querySelector('#fields').disabled);
    assert.equal(await follow.isDisabled(),true,'Rejected edits must not unlock follow-up on stale state.');
    assert.equal(await page.locator('.qty').inputValue(),'6','Rejected input must be preserved.');
    reject = false;
    await page.locator('#recommend').click();
    await page.waitForFunction(() => !document.querySelector('#fields').disabled);
    assert.equal(await follow.isEnabled(),true);
    console.log('PASS: initial lock, accepted clarification, typing, dirty edits, rejected edits, accepted retry. No model calls.');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode=1;});
