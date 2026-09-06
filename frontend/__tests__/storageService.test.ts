import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LocalStorageService } from '../services/storageService';
import { draftFixture } from '../test/fixtures';

function deleteDatabase(): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase('HeygenX_Studio_Store');
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => resolve();
  });
}

describe('LocalStorageService', () => {
  beforeEach(async () => {
    await deleteDatabase();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('persists, lists, recovers, and deletes editor drafts', async () => {
    const service = new LocalStorageService();
    const draft = structuredClone(draftFixture);

    await service.saveDraft(draft);

    expect(Date.parse(draft.projectMetadata.updatedAt)).not.toBeNaN();
    await expect(service.getDraft(draft.projectMetadata.id)).resolves.toEqual(draft);
    await expect(service.listDrafts()).resolves.toEqual([draft]);

    await service.deleteDraft(draft.projectMetadata.id);
    await expect(service.getDraft(draft.projectMetadata.id)).resolves.toBeNull();
  });

  it('reports unsupported IndexedDB explicitly', async () => {
    const original = window.indexedDB;
    Object.defineProperty(window, 'indexedDB', { configurable: true, value: undefined });
    const service = new LocalStorageService();

    await expect(service.listDrafts()).rejects.toThrow('IndexedDB is not supported');
    Object.defineProperty(window, 'indexedDB', { configurable: true, value: original });
  });

  it('reports storage quota pressure', async () => {
    Object.defineProperty(navigator, 'storage', {
      configurable: true,
      value: { estimate: vi.fn().mockResolvedValue({ usage: 85, quota: 100 }) },
    });

    await expect(new LocalStorageService().checkStorageQuota()).resolves.toEqual({
      usagePercent: 85,
      isWarning: true,
    });
  });

  it('falls back safely when quota estimation is unavailable or fails', async () => {
    Object.defineProperty(navigator, 'storage', {
      configurable: true,
      value: { estimate: vi.fn().mockRejectedValue(new Error('quota unavailable')) },
    });
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    await expect(new LocalStorageService().checkStorageQuota()).resolves.toEqual({
      usagePercent: 0,
      isWarning: false,
    });

    Object.defineProperty(navigator, 'storage', { configurable: true, value: undefined });
    await expect(new LocalStorageService().checkStorageQuota()).resolves.toEqual({
      usagePercent: 0,
      isWarning: false,
    });
  });
});
