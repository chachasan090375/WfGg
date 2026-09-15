import { describe, expect, it } from 'vitest';
import app from '../src/index.js';

describe('wfgg-api module contract', () => {
  it('exports a Worker fetch handler', () => {
    expect(app).toBeTruthy();
    expect(typeof app.fetch).toBe('function');
  });
});
