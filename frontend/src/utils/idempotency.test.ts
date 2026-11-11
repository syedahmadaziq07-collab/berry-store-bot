import test from 'node:test';
import assert from 'node:assert/strict';
import {MutationKeys} from './idempotency';
test('Ambiguous or failed transaction retains its retry key, while new payloads get new keys', () => {
  const keys = new MutationKeys();
  assert.equal(keys.acquire('same-payload', () => 'key-1'), 'key-1');
  keys.settle('same-payload', 503);
  assert.equal(keys.acquire('same-payload', () => 'key-2'), 'key-1');
  assert.equal(keys.acquire('other-payload', () => 'key-3'), 'key-3');
});
test('Verified success or rejection releases the key for a later deliberate action', () => {
  for (const status of [200,201,400,401,403,423]) {
    const keys = new MutationKeys();
    keys.acquire('payload', () => 'key-1');
    keys.settle('payload', status);
    assert.equal(keys.acquire('payload', () => 'key-2'), 'key-2');
  }
});
