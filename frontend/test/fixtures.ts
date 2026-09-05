import type { AuthBootstrapResponse } from '../services/authService';
import type { HeygenXFile } from '../services/storageService';
import type { Project } from '../store/projectStore';

export const projectFixture: Project = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Launch film',
  sourceLanguage: 'en',
  targetLanguage: 'es',
  status: 'draft',
  createdAt: '2026-01-01T00:00:00.000Z',
  updatedAt: '2026-01-02T00:00:00.000Z',
  transcriptId: 'transcript-1',
  mediaId: 'media-1',
  mediaFilename: 'launch.mp4',
  mediaDurationSeconds: 42,
};

export const draftFixture: HeygenXFile = {
  version: '1.2.0',
  projectMetadata: {
    id: projectFixture.id,
    name: projectFixture.name,
    sourceLanguage: 'en',
    targetLanguage: 'es',
    createdAt: projectFixture.createdAt,
    updatedAt: projectFixture.updatedAt,
  },
  mediaReferences: {
    videoFilename: 'launch.mp4',
    durationSeconds: 42,
    transcriptId: 'transcript-1',
    mediaId: 'media-1',
    originalTranscriptSegments: [],
  },
  translations: [],
  timelineState: { markers: [], zoomLevel: 100 },
};

export const authContextFixture: AuthBootstrapResponse = {
  user: {
    id: 'user-1',
    email: 'editor@example.com',
    display_name: 'Editor',
    auth_provider: 'google',
    auth_subject: 'subject-1',
    is_active: true,
    last_login_at: null,
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  },
  workspace: {
    id: 'workspace-1',
    name: 'Studio',
    slug: 'studio',
    owner_user_id: 'user-1',
    is_personal: false,
    archived_at: null,
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  },
  membership: {
    workspace_id: 'workspace-1',
    user_id: 'user-1',
    role: 'owner',
    invited_by_user_id: null,
    joined_at: '2026-01-01T00:00:00.000Z',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  },
  bootstrap_completed: true,
};
