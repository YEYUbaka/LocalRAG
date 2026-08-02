import { afterEach, describe, expect, it, vi } from 'vitest';
import { importBatchUrls } from './api';
import type { BatchImportResult } from '../types';

describe('importBatchUrls', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns backend results including skipped entries', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      imported: 1,
      results: [
        { url: 'https://example.com/a', status: 'pending', id: 7 },
        { url: 'https://example.com/b', status: 'skipped', detail: '已导入' },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const result = await importBatchUrls(
      ['https://example.com/a', 'https://example.com/b'], 3,
    );

    const pending = result.results[0] as Extract<BatchImportResult, { status: 'pending' }>;
    const skipped = result.results[1] as Extract<BatchImportResult, { status: 'skipped' }>;
    expect(pending.id).toBe(7);
    expect(skipped.detail).toBe('已导入');
  });
});
