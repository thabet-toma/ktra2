import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  SUPPORT_SESSION_KEY,
  clearSupportSession,
  parseSupportSession,
  readSupportSession,
  splitMinutes,
  supportMinutesLeft,
  supportSessionExpired,
  writeSupportSession,
  type SupportSession,
} from './supportSession.ts';

const memory = () => {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    removeItem: (key: string) => { data.delete(key); },
  };
};

const session: SupportSession = {
  grantId: 7, tenantId: 12, tenantName: 'شركة', scope: 'read_only',
  isEmergency: false, expiresAt: '2026-09-27T14:30:00Z', returnTenantId: 3,
};

test('round-trips through storage and clears', () => {
  const storage = memory();
  writeSupportSession(session, storage);
  assert.deepEqual(readSupportSession(storage), session);
  clearSupportSession(storage);
  assert.equal(readSupportSession(storage), null);
});

test('rejects malformed or tampered values instead of opening a company', () => {
  assert.equal(parseSupportSession(null), null);
  assert.equal(parseSupportSession('not json'), null);
  assert.equal(parseSupportSession(JSON.stringify({ ...session, scope: 'owner' })), null);
  assert.equal(parseSupportSession(JSON.stringify({ ...session, tenantId: '12' })), null);
  assert.equal(parseSupportSession(JSON.stringify({ ...session, expiresAt: 'soon' })), null);
});

test('missing optional fields fall back safely', () => {
  const storage = memory();
  storage.setItem(SUPPORT_SESSION_KEY, JSON.stringify({
    grantId: 1, tenantId: 2, scope: 'full', expiresAt: session.expiresAt,
  }));
  const parsed = readSupportSession(storage);
  assert.equal(parsed?.returnTenantId, null);
  assert.equal(parsed?.isEmergency, false);
  assert.equal(parsed?.tenantName, '');
});

test('minutes left never go negative and expiry is inclusive', () => {
  const end = Date.parse(session.expiresAt);
  assert.equal(supportMinutesLeft(session, end - 135 * 60000), 135);
  assert.equal(supportMinutesLeft(session, end + 60000), 0);
  assert.equal(supportSessionExpired(session, end), true);
  assert.equal(supportSessionExpired(session, end - 1), false);
  assert.deepEqual(splitMinutes(135), { hours: 2, minutes: 15 });
});
