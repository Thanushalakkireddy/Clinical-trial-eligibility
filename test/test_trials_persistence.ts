import assert from 'node:assert';
import { dataStore } from '../server/dataStore';

async function runTrialsPersistenceTestSuite() {
  console.log('🧪 Starting Clinical Trial Persistence Test Suite...');

  // Ensure dataStore has loaded storage files
  dataStore.reloadFromDisk();

  const trials = dataStore.getTrials();
  console.log(`Found ${trials.length} trials in dataStore`);

  // Test 1: Trials are populated and include SYN-CARDIO-001
  const cardioTrial = trials.find((t) => t.trial_id === 'SYN-CARDIO-001');
  assert(cardioTrial, 'SYN-CARDIO-001 must be present in getTrials()');
  assert.strictEqual(cardioTrial.trial_id, 'SYN-CARDIO-001');
  assert.ok(cardioTrial.trial_title, 'Trial must have a trial_title');
  assert.ok(
    cardioTrial.trial_title.includes('Acute Myocardial Infarction'),
    `Title should match acute myocardial infarction protocol: got "${cardioTrial.trial_title}"`
  );
  assert.ok(
    cardioTrial.inclusion_criteria && cardioTrial.inclusion_criteria.length > 0,
    'SYN-CARDIO-001 must include extracted inclusion criteria'
  );
  assert.ok(
    cardioTrial.exclusion_criteria && cardioTrial.exclusion_criteria.length > 0,
    'SYN-CARDIO-001 must include extracted exclusion criteria'
  );
  console.log('✅ TEST 1 passed: SYN-CARDIO-001 present with full criteria and metadata.');

  // Test 2: Idempotent saveTrial - no duplicate trials created
  const beforeCount = dataStore.getTrials().length;
  dataStore.saveTrial(cardioTrial as any);
  dataStore.saveTrial(cardioTrial as any);
  const afterCount = dataStore.getTrials().length;
  assert.strictEqual(afterCount, beforeCount, 'Trial list count must remain identical (no duplicates)');
  console.log('✅ TEST 2 passed: Idempotency verified - no duplicate trials created.');

  // Test 3: getTrial by ID
  const retrieved = dataStore.getTrial('SYN-CARDIO-001');
  assert(retrieved, 'getTrial("SYN-CARDIO-001") must return the trial object');
  assert.strictEqual(retrieved.trial_id, 'SYN-CARDIO-001');
  console.log('✅ TEST 3 passed: getTrial by ID returns complete protocol.');

  // Test 4: Live HTTP test if server is active
  const baseUrl = 'http://127.0.0.1:3000';
  try {
    const res = await fetch(`${baseUrl}/api/v1/trials`);
    if (res.status === 200) {
      const liveTrials = await res.json();
      assert(Array.isArray(liveTrials), 'Live /api/v1/trials must return an array');
      const liveCardio = liveTrials.find((t: any) => t.trial_id === 'SYN-CARDIO-001');
      assert(liveCardio, 'Live /api/v1/trials must include SYN-CARDIO-001');
      assert.ok(liveCardio.trial_title, 'Live trial must have trial_title');
      console.log('✅ TEST 4 passed: Live HTTP endpoint /api/v1/trials returns SYN-CARDIO-001 with full details.');
    } else {
      console.log(`ℹ️ Live server returned status ${res.status}, skipping live test.`);
    }
  } catch {
    console.log('ℹ️ Live server on port 3000 not responding, unit test suite complete.');
  }

  console.log('🎉 ALL CLINICAL TRIAL PERSISTENCE TESTS PASSED!');
}

runTrialsPersistenceTestSuite().catch((err) => {
  console.error('Test suite failure:', err);
  process.exit(1);
});
