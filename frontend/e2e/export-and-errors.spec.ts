import { expect, test } from '@playwright/test';

import { MockBackend, PROJECT_ID } from './mockBackend';

test('dub build exposes progress, readiness, partial history failure, and download state', async ({ page }) => {
  const backend = new MockBackend();
  backend.formatHistoryStatus = 500;
  await backend.install(page);

  await page.goto(`/editor/${PROJECT_ID}`);
  await expect(page.getByLabel(/Translation in ES for Speaker 1/)).toBeVisible();

  await page.getByRole('button', { name: 'Dub only' }).click();
  await expect(page.getByRole('progressbar', { name: 'Build progress' })).toHaveAttribute('aria-valuenow', '48');
  await expect(page.getByText('Dub complete. Preview is ready — download the dubbed video below.')).toBeVisible();
  expect(backend.renderRequests).toEqual([
    expect.objectContaining({ enable_lipsync: false, project_id: PROJECT_ID }),
  ]);
  await expect(page.getByRole('region', { name: 'Dub build status' }).getByText('Completed')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download video' })).toBeVisible();

  await page.getByRole('button', { name: 'Exports' }).click();
  const outputs = page.getByRole('dialog', { name: 'Project outputs' });
  await expect(outputs.getByText('Dub only')).toBeVisible();
  await expect(outputs.getByText('Dub + Lip-Sync')).toBeVisible();
  await expect(outputs.getByText('Needs attention')).toBeVisible();
  await expect(outputs.getByText('Format export history unavailable')).toBeVisible();
  await expect(outputs.getByRole('link', { name: 'Download dub-only output' })).toHaveAttribute(
    'href',
    'https://media.globesync.test/output.mp4?download=1',
  );
});

test('render service errors preserve editor state and show actionable UX', async ({ page }) => {
  const backend = new MockBackend();
  backend.buildStatus = 500;
  await backend.install(page);

  await page.goto(`/editor/${PROJECT_ID}`);
  const translation = page.getByLabel(/Translation in ES for Speaker 1/);
  await expect(translation).toHaveValue('Bienvenido a GlobeSync');

  await page.getByRole('button', { name: 'Dub + Lip-Sync' }).click();
  await expect(page.getByText('GlobeSync could not complete that request right now. Please try again in a moment.')).toBeVisible();
  expect(backend.renderRequests).toEqual([
    expect.objectContaining({ enable_lipsync: true, project_id: PROJECT_ID }),
  ]);
  await expect(translation).toHaveValue('Bienvenido a GlobeSync');
  await expect(page.getByRole('button', { name: 'Dub + Lip-Sync' })).toBeEnabled();
});
