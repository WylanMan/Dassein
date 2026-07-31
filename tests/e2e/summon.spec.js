const { test, expect } = require('@playwright/test');

const BASE = 'http://localhost:3000';

async function summon(page, body) {
  return page.request.post(`${BASE}/api/summon`, { data: body });
}

async function stubCalls(page) {
  const r = await page.request.get('http://localhost:3001/__calls');
  return (await r.json()).count;
}

test.describe('Summon API (tier 2, LLM tier — grammar v2)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
  });

  test('S17: /api/summon returns a valid grammar-v2 spec', async ({ page }) => {
    const r = await summon(page, { concept: 'hourglass' });
    expect(r.status()).toBe(200);
    const data = await r.json();
    expect(data.id).toBe('hourglass');
    expect(data.cached).toBe(false);
    expect(typeof data.seed).toBe('number');
    const spec = data.spec;
    expect(spec).toBeTruthy();
    expect(typeof spec.id).toBe('string');
    expect(spec.schema).toBe(2);
    expect(['small', 'medium', 'large']).toContain(spec.size || 'medium');
    expect(spec.root).toBeTruthy();
    expect(typeof spec.root.op).toBe('string');
  });

  test('S19: invalid spec -> fix-retry -> 422 abstractify', async ({ page }) => {
    const before = await stubCalls(page);
    const bad = await summon(page, { concept: 'bad_spec' });
    expect(bad.status()).toBe(422);
    const badBody = await bad.json();
    expect(badBody.abstractify).toBe(true);

    const after = await stubCalls(page);
    // One initial call + one fix-prompt retry, then the 422.
    expect(after - before).toBe(2);

    // A spec that only fixes on the retry succeeds.
    const fix = await summon(page, { concept: 'retry_spec' });
    expect(fix.status()).toBe(200);
    const fixBody = await fix.json();
    expect(fixBody.spec.id).toBe('retry_fixed');
    expect(fixBody.spec.schema).toBe(2);
  });

  test('S21: cache hit returns the canonical spec with no LLM call', async ({ page }) => {
    const before = await stubCalls(page);
    const first = await summon(page, { concept: 'chair' });
    expect((await first.json()).cached).toBe(false);

    const mid = await stubCalls(page);
    expect(mid - before).toBe(1);

    const second = await summon(page, { concept: 'a chair' }); // phrasing collapse
    const data = await second.json();
    expect(data.cached).toBe(true);
    expect(data.id).toBe('chair');

    const after = await stubCalls(page);
    expect(after - mid).toBe(0); // no additional LLM call
  });

  test('S17b: missing concept is a 400', async ({ page }) => {
    const r = await summon(page, {});
    expect(r.status()).toBe(400);
  });
});
