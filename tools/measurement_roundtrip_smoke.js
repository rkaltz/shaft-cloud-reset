const fs = require('fs');

const source = fs.readFileSync('main.py', 'utf8');

function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`Missing function: ${name}`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;

  for (let index = bodyStart; index < source.length; index += 1) {
    const char = source[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char;
      continue;
    }
    if (char === '{') depth += 1;
    if (char === '}' && --depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`Unclosed function: ${name}`);
}

const MEASUREMENT_ENVELOPE_SCHEMA = 'shaftcad.measurement-envelope.v1';
eval(extractFunction('measuredCpmValue'));
eval(extractFunction('validateMeasurementEnvelope'));

if (measuredCpmValue('255') !== 255) throw new Error('Whole-number CPM was not preserved.');
if (measuredCpmValue('255.5') !== null) throw new Error('Fractional measured CPM was accepted.');
if (measuredCpmValue('1000') !== null) throw new Error('Out-of-range measured CPM was accepted.');

const envelope = {
  schema: MEASUREMENT_ENVELOPE_SCHEMA,
  schema_version: 1,
  specimen: {specimen_id: 'S-1', revision: 'A'},
  test_conditions: {
    apparatus: null,
    station_datum: null,
    orientation: null,
    applied_force_lb: null,
    test_mass_g: null,
  },
  observations: [{
    id: 'cpm-butt-frequency',
    measurement_type: 'cpm',
    original_value: 255,
    value: 255,
    units: 'CPM',
    evidence_class: 'measured',
    provenance: {source: null, calibration_status: 'unknown'},
  }],
};

const restored = JSON.parse(JSON.stringify(envelope));
const errors = validateMeasurementEnvelope(restored);
if (errors.length) throw new Error(errors.join(' | '));
if (JSON.stringify(envelope) !== JSON.stringify(restored)) throw new Error('Measurement envelope changed during JSON round-trip.');

console.log('Measurement CPM and JSON round-trip checks passed');
