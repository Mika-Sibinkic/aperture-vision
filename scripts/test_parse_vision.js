// Runs the committed "Parse vision + tare + bias" node, the code that computes every
// logged weight, against synthetic NIM replies (shaped like choices[0].message.content).
// Usage: node scripts/test_parse_vision.js
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'n8n', 'aperture-workflow-ipad-nim.json'), 'utf8'));
const code = wf.nodes.find((n) => n.name === 'Parse vision + tare + bias').parameters.jsCode;

function parse(content) {
  const upstream = {
    'Webhook: donation button': { body: { donation_id: 'abcdef12-0000-4000-8000-000000000000', description: '' } },
    'Load prompt + config': { prompt_version: 'v0.8-scene', model: 'nvidia/nemotron-nano-12b-v2-vl' },
    'Build vision request': {},
  };
  const $ = (name) => ({ first: () => ({ json: upstream[name] }) });
  const $json = { choices: [{ message: { content } }] };
  return new Function('$', '$json', code)($, $json)[0].json;
}

const reading = (fields) => JSON.stringify({ item_type: 'kale', inside_zone: true, confidence: 0.8, ...fields });

// Empty dock: the reply the prompt asks for when the zone is empty.
const empty = parse(JSON.stringify({ item_type: 'empty', inside_zone: true, weight_lbs: 0, confidence: 0.9 }));
assert.strictEqual(empty.weight_lbs, 0);
assert.strictEqual(empty.implausible_weight, false);
assert.strictEqual(empty.prompt_version, 'v0.8-scene');

// A model that wraps its JSON in a fence still parses.
const fenced = parse('```json\n' + reading({ weight_lbs: 12.5 }) + '\n```');
assert.strictEqual(fenced.weight_lbs, 12.5);
assert.strictEqual(fenced.item_type, 'kale');

// Over 2000 lb is flagged and its confidence capped.
const huge = parse(reading({ weight_lbs: 2500 }));
assert.strictEqual(huge.implausible_weight, true);
assert.ok(huge.confidence <= 0.3, `confidence ${huge.confidence}`);
assert.ok(huge.known_failure_flags.includes('implausible_weight_review'));

// A negative weight is logged as 0.
assert.strictEqual(parse(reading({ weight_lbs: -5 })).weight_lbs, 0);

// Prose instead of JSON fails loudly rather than logging a weight.
assert.throws(() => parse('The zone looks empty.'), /non-JSON/);

console.log('all parse-vision cases pass');
