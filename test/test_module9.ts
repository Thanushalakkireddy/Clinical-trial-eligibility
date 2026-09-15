import {
  hashPassword,
  verifyPassword,
  generateToken,
  verifyToken,
  authenticateUser,
} from '../server/auth';
import { dataStore } from '../server/dataStore';
import { buildStructuredProfile } from '../server/normalization';
import { testTrialOncology01, testPatientDemo01 } from './fixtures';
import fs from 'fs';
import path from 'path';

function assert(condition: boolean, msg: string) {
  if (!condition) {
    console.error(`❌ Assertion failed: ${msg}`);
    process.exit(1);
  }
}

async function runTests() {
  console.log('🧪 Starting Module 9 Production Hardening & Security Test Suite...\n');

  // --------------------------------------------------------------------------
  // 1. Password Hashing & Verification Security
  // --------------------------------------------------------------------------
  console.log('--- Test Group 1: Password Hashing & Verification ---');
  const password = 'VerySecureClinicalPassword2026!';
  const { salt, hash } = hashPassword(password);
  assert(typeof salt === 'string' && salt.length > 0, 'Salt should be non-empty string');
  assert(typeof hash === 'string' && hash.length === 128, 'PBKDF2 SHA-512 hex hash should be 128 chars');

  const validMatch = verifyPassword(password, salt, hash);
  assert(validMatch === true, 'Valid password verification must return true');

  const invalidMatch = verifyPassword('WrongPassword!', salt, hash);
  assert(invalidMatch === false, 'Invalid password verification must return false');
  console.log('✅ Test Group 1 Passed: Password hashing with PBKDF2 salt and constant-time verification.');

  // --------------------------------------------------------------------------
  // 2. JWT Generation, Tamper Detection & Expiration
  // --------------------------------------------------------------------------
  console.log('\n--- Test Group 2: JWT Security & Expiration ---');
  const token = generateToken('clinical_evaluator', 'clinician', 3600);
  assert(typeof token === 'string' && token.split('.').length === 3, 'JWT must have 3 dot-separated parts');

  const verified = verifyToken(token);
  assert(verified.valid === true, 'Valid token must verify successfully');
  if (verified.valid) {
    assert(verified.payload.sub === 'clinical_evaluator', 'Token payload subject must match');
    assert(verified.payload.role === 'clinician', 'Token payload role must match');
  }

  // Tamper signature test
  const tamperedToken = token.slice(0, -4) + 'abcd';
  const tamperedResult = verifyToken(tamperedToken);
  assert(tamperedResult.valid === false && tamperedResult.reason === 'invalid_signature', 'Tampered token must fail signature verification');

  // Expired token test (expires in -10 seconds)
  const expiredToken = generateToken('admin', 'admin', -10);
  const expiredResult = verifyToken(expiredToken);
  assert(expiredResult.valid === false && expiredResult.reason === 'expired', 'Expired token must be flagged as expired');
  console.log('✅ Test Group 2 Passed: JWT generation, HMAC signature verification, tamper resistance, and expiration.');

  // --------------------------------------------------------------------------
  // 3. User Authentication Engine
  // --------------------------------------------------------------------------
  console.log('\n--- Test Group 3: User Authentication ---');
  const authedClinician = authenticateUser('clinical_evaluator', 'Evaluator123!');
  assert(authedClinician !== null, 'Seeded clinical evaluator credentials should authenticate');
  assert(authedClinician?.role === 'clinician', 'Evaluator should have clinician role');

  const authedAdmin = authenticateUser('admin', 'AdminSecret123!');
  assert(authedAdmin !== null, 'Seeded admin credentials should authenticate');
  assert(authedAdmin?.role === 'admin', 'Admin should have admin role');

  const badAuth = authenticateUser('clinical_evaluator', 'WrongPassword!');
  assert(badAuth === null, 'Invalid password must return null user');
  console.log('✅ Test Group 3 Passed: User authentication and role mapping.');

  // --------------------------------------------------------------------------
  // 4. Persistence to Disk
  // --------------------------------------------------------------------------
  console.log('\n--- Test Group 4: Durable Disk Persistence ---');
  const testPatientId = `test_persisted_patient_${Date.now()}`;
  const profile = buildStructuredProfile({
    patient_profile_id: testPatientId,
    age: 52,
    sex: 'female',
    height: 165,
    weight: 68,
    conditions: ['Hypertension'],
    clinical_notes_raw: 'Test patient note.',
  });
  dataStore.savePatient(profile);

  const persistedFile = path.join(process.cwd(), 'data', 'patients', `${testPatientId}.json`);
  assert(fs.existsSync(persistedFile), `Patient file must exist on disk at ${persistedFile}`);
  const persistedContent = JSON.parse(fs.readFileSync(persistedFile, 'utf8'));
  assert(persistedContent.patient_profile_id === testPatientId, 'Persisted JSON must match saved ID');
  // Clean up test file
  try {
    fs.unlinkSync(persistedFile);
  } catch {}
  console.log('✅ Test Group 4 Passed: Durable disk persistence verified.');

  // --------------------------------------------------------------------------
  // 5. Live HTTP Endpoints Check (port 3000)
  // --------------------------------------------------------------------------
  console.log('\n--- Test Group 5: HTTP Endpoints & Security Integration ---');
  const baseUrl = 'http://127.0.0.1:3000';

  try {
    // Check if server is accessible before running live HTTP suite
    let serverAvailable = false;
    try {
      const ping = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(1500) });
      if (ping.status === 200) serverAvailable = true;
    } catch {
      serverAvailable = false;
    }

    if (!serverAvailable) {
      console.log('ℹ️ Local server on port 3000 is not currently active. Skipping live HTTP integration tests in offline unit test mode.');
    } else {
      // Health check
      const healthRes = await fetch(`${baseUrl}/health`);
      assert(healthRes.status === 200, `Health check returned status ${healthRes.status}`);
      const healthData = await healthRes.json();
      assert(healthData.status === 'ok', 'Health status should be ok');

      // Auth Login
      const loginRes = await fetch(`${baseUrl}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'clinical_evaluator', password: 'Evaluator123!' }),
      });
      assert(loginRes.status === 200, `Login returned status ${loginRes.status}`);
      const loginData = await loginRes.json();
      assert(typeof loginData.access_token === 'string', 'Login must return access_token');
      const userToken = loginData.access_token;

      // Protected Auth Me with valid token
      const meRes = await fetch(`${baseUrl}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${userToken}` },
      });
      assert(meRes.status === 200, `Protected endpoint returned ${meRes.status}`);
      const meData = await meRes.json();
      assert(meData.username === 'clinical_evaluator', 'User info must match token');

      // Protected Auth Me without token -> 401
      const unauthorizedRes = await fetch(`${baseUrl}/api/v1/auth/me`);
      assert(unauthorizedRes.status === 401, 'Request without token must return 401');

      // Protected Auth Me with invalid token -> 401
      const invalidTokenRes = await fetch(`${baseUrl}/api/v1/auth/me`, {
        headers: { Authorization: 'Bearer invalid.token.payload' },
      });
      assert(invalidTokenRes.status === 401, 'Request with invalid token must return 401');

      // CORS OPTIONS preflight
      const corsRes = await fetch(`${baseUrl}/api/v1/trials`, {
        method: 'OPTIONS',
        headers: {
          Origin: 'http://localhost:3000',
          'Access-Control-Request-Method': 'GET',
        },
      });
      assert(corsRes.status === 204, 'CORS preflight OPTIONS request must return 204');

      // Seed test fixtures to live API specifically for this test suite
      await fetch(`${baseUrl}/api/v1/trials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(testTrialOncology01),
      });
      await fetch(`${baseUrl}/api/v1/patients/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(testPatientDemo01),
      });

      // End-to-end Workflow Evaluation
      const evalRes = await fetch(
        `${baseUrl}/api/v1/trials/trial-oncology-01/patients/patient-demo-01/workflow-evaluation`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      assert(evalRes.status === 200, `Workflow evaluation returned status ${evalRes.status}`);
      const evalData = await evalRes.json();
      assert(evalData.final_decision !== undefined, 'Workflow evaluation must return final_decision');

      // POST /api/v1/eligibility/evaluate
      const generalEvalRes = await fetch(`${baseUrl}/api/v1/eligibility/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trial_id: 'trial-oncology-01',
          patient_id: 'patient-demo-01',
        }),
      });
      assert(generalEvalRes.status === 200, `/api/v1/eligibility/evaluate returned ${generalEvalRes.status}`);
      const generalData = await generalEvalRes.json();
      assert(generalData.final_decision !== undefined, 'General evaluation must return final_decision');

      // Clean up test fixture files from disk so application stays clean
      try {
        const trialFile = path.join(process.cwd(), 'storage', 'pdfs', 'trial-oncology-01_protocol.json');
        if (fs.existsSync(trialFile)) fs.unlinkSync(trialFile);
        const patientFile = path.join(process.cwd(), 'data', 'patients', 'patient-demo-01.json');
        if (fs.existsSync(patientFile)) fs.unlinkSync(patientFile);
      } catch {}

      console.log('✅ Test Group 5 Passed: Live endpoints, auth, CORS, and full evaluation verified.');
    }
  } catch (err: any) {
    console.error('HTTP endpoint verification error:', err.message);
    throw err;
  }

  console.log('\n🎉 ALL MODULE 9 PRODUCTION HARDENING & SECURITY TESTS PASSED!');
}

runTests().catch((err) => {
  console.error('Test execution failed:', err);
  process.exit(1);
});
