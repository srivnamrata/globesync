export interface HeygenXFile {
  version: string;
  projectMetadata: {
    id: string;
    name: string;
    sourceLanguage: string;
    targetLanguage: string;
    createdAt: string;
    updatedAt: string;
  };
  mediaReferences: {
    videoFilename: string;
    durationSeconds: number;
    originalTranscriptSegments: any[];
    transcriptId?: string;
    mediaId?: string;
  };
  translations: any[];
  timelineState?: {
    markers?: any[];
    zoomLevel?: number;
  };
}

export class LocalStorageService {
  private dbName = 'HeygenX_Studio_Store';
  private dbVersion = 1;
  private storeName = 'project_drafts';

  private openDB(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (typeof window === 'undefined' || !window.indexedDB) {
        reject(new Error('IndexedDB is not supported on this platform.'));
        return;
      }

      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);

      request.onupgradeneeded = (event) => {
        const db = request.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          db.createObjectStore(this.storeName, { keyPath: 'projectMetadata.id' });
        }
      };
    });
  }

  async saveDraft(draft: HeygenXFile): Promise<void> {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(this.storeName, 'readwrite');
      const store = transaction.objectStore(this.storeName);
      
      draft.projectMetadata.updatedAt = new Date().toISOString();
      const request = store.put(draft);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getDraft(projectId: string): Promise<HeygenXFile | null> {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(this.storeName, 'readonly');
      const store = transaction.objectStore(this.storeName);
      const request = store.get(projectId);

      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }

  async deleteDraft(projectId: string): Promise<void> {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(this.storeName, 'readwrite');
      const store = transaction.objectStore(this.storeName);
      const request = store.delete(projectId);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async listDrafts(): Promise<HeygenXFile[]> {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(this.storeName, 'readonly');
      const store = transaction.objectStore(this.storeName);
      const request = store.getAll();

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  async checkStorageQuota(): Promise<{ usagePercent: number; isWarning: boolean }> {
    if (typeof navigator !== 'undefined' && navigator.storage && navigator.storage.estimate) {
      try {
        const estimate = await navigator.storage.estimate();
        const usage = estimate.usage || 0;
        const quota = estimate.quota || 1;
        const usagePercent = (usage / quota) * 100;
        return {
          usagePercent,
          isWarning: usagePercent >= 80.0,
        };
      } catch (err) {
        console.warn('Storage quota query failed:', err);
      }
    }
    return { usagePercent: 0, isWarning: false };
  }
}

export const storageService = new LocalStorageService();
