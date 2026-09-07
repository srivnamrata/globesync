import { expect, test } from '@playwright/test';

import {
  MockBackend,
  PROJECT_ID,
  makeDraft,
  makeProject,
} from './mockBackend';

test('loads authenticated media, transcript, translation, and readiness state', async ({ page }) => {
  const backend = new MockBackend();
  await backend.install(page);

  await page.goto(`/editor/${PROJECT_ID}`);

  await expect(page.getByRole('heading', { name: 'Launch video' })).toBeVisible();
  await expect(page.getByLabel(/Source transcript for Speaker 1/)).toHaveValue('Welcome to GlobeSync');
  await expect(page.getByLabel(/Translation in ES for Speaker 1/)).toHaveValue('Bienvenido a GlobeSync');
  await expect(page.getByText('1 segments loaded')).toBeVisible();
  await expect(page.getByText('Downloading original media as `launch.mp4`.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Original' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Dub only' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Dub + Lip-Sync' })).toBeEnabled();

  await page.getByRole('button', { name: 'Readiness' }).click();
  await expect(page.getByText('Ready to build')).toBeVisible();
  await expect(page.getByText('All checks passed')).toBeVisible();
});

test('upload, transcription, and first translation save complete without a false conflict', async ({ page }) => {
  const project = makeProject({
    media_file_id: null,
    media_filename: null,
    media_duration_seconds: null,
    transcript_id: null,
  });
  const backend = new MockBackend(project);
  backend.draft = makeDraft(project);
  await backend.install(page);

  await page.goto(`/editor/${PROJECT_ID}`);
  await expect(page.getByText('0 segments loaded')).toBeVisible();

  await page.getByLabel('Upload audio or video and start transcription').setInputFiles({
    name: 'sample.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('deterministic-e2e-media'),
  });

  await expect(page.getByLabel(/Source transcript for Speaker 1/)).toHaveValue('Welcome to GlobeSync', { timeout: 10_000 });
  await expect(page.getByLabel(/Translation in ES for Speaker 1/)).toHaveValue('Bienvenido a GlobeSync');
  await expect(page.getByText('Translation complete — 1 segments loaded.')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole('button', { name: 'Keep editor edits' })).toHaveCount(0);
  expect(backend.draftWriteVersions).toEqual([1, 2]);
});

test('a genuine draft conflict supports keeping edits and loading the saved draft', async ({ page }) => {
  const backend = new MockBackend();
  await backend.install(page);
  await page.goto(`/editor/${PROJECT_ID}`);

  const translation = page.getByLabel(/Translation in ES for Speaker 1/);
  await expect(translation).toHaveValue('Bienvenido a GlobeSync');

  backend.rejectDraftWrites = true;
  await translation.fill('Edición local');
  await page.getByRole('button', { name: 'Save (1)' }).click();
  await expect(page.getByText(/A newer saved draft is available/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load saved draft' })).toBeVisible();

  await expect(page.getByRole('button', { name: 'Keep editor edits' })).toBeVisible();
  await page.getByRole('button', { name: 'Keep editor edits' }).click();
  await expect(page.getByRole('button', { name: 'Keep editor edits' })).toHaveCount(0);
  await expect(translation).toHaveValue('Edición local');

  await translation.fill('Otra edición local');
  await page.getByRole('button', { name: 'Save (1)' }).click();
  await expect(page.getByRole('button', { name: 'Load saved draft' })).toBeVisible();

  backend.draft = makeDraft(backend.project, 'Borrador guardado');
  backend.translationText = 'Borrador guardado';
  backend.rejectDraftWrites = false;
  await page.getByRole('button', { name: 'Load saved draft' }).click();
  await expect(translation).toHaveValue('Borrador guardado');
  await expect(page.getByRole('button', { name: 'Keep editor edits' })).toHaveCount(0);
});
