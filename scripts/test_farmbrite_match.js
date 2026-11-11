// Runs the committed "Build Farmbrite order" node against a table of donations.
// Usage: node scripts/test_farmbrite_match.js
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'n8n', 'aperture-workflow-ipad-nim.json'), 'utf8'));
const code = wf.nodes.find((n) => n.name === 'Build Farmbrite order').parameters.jsCode;

function build(parsed, isoDate) {
  const $ = () => ({ first: () => ({ json: parsed }) });
  class FixedDate extends Date {
    constructor(...a) { super(...(a.length ? a : [isoDate])); }
  }
  return new Function('$', 'Date', code)($, FixedDate)[0].json;
}

const NOV = '2026-11-11T12:00:00Z';
const AUG = '2026-08-12T12:00:00Z';
const cases = [
  // [description, item_type, date, expected product (null = skipped)]
  ['', 'kale', NOV, 'Kale'],
  ['2 crates of kale', 'leafy greens', NOV, 'Kale'],
  ['yukon gold potatoes', 'potatoes', NOV, 'Yukon Gold Potatoes'],
  // Generic words used to land on whichever variety had the longest name.
  ['', 'potatoes', NOV, null],
  ['', 'peppers', NOV, null],
  ['', 'squash', NOV, null],
  ['', 'onion', NOV, null],
  // 'produce' used to match Community Garden Produce.
  ['', 'produce', NOV, null],
  ['', 'mixed produce', AUG, 'Seasonal Produce - August'],
  ['', 'potatoes', AUG, 'Seasonal Produce - August'],
];

let failed = 0;
for (const [description, item_type, date, want] of cases) {
  const out = build({ description, item_type, weight_lbs: 12.5, donation_id: 'abcdef123456' }, date);
  const got = out.__skip ? null : out.product_name;
  const ok = got === want;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${JSON.stringify(description || item_type).padEnd(24)} ${date.slice(0, 7)} -> ${got ?? 'skip: ' + out.reason}`);
}

// A skip must say why, so the response can surface it.
const nov = build({ description: '', item_type: 'mixed produce', weight_lbs: 30 }, NOV);
assert.strictEqual(nov.__skip, true);
assert.match(nov.reason, /November/);

assert.strictEqual(failed, 0, `${failed} case(s) failed`);
console.log('all Farmbrite match cases pass');
