import { expect, test } from '@playwright/test';

import { MockBackend, PROJECT_ID } from './mockBackend';

test('signed-out landing presents Google sign-in and session-expiry guidance', async ({ page }) => {
  const backend = new MockBackend();
  backend.authStatus = 401;
  await backend.install(page);

  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Translate one video. Reach every audience.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible();
  await expect(page.getByText('Your session expired or access could not be verified. Sign in again to continue.')).toBeVisible();
});

test('authenticated operator can create and open a workspace project', async ({ page }) => {
  const backend = new MockBackend();
  backend.projects = [];
  await backend.install(page);

  await page.goto('/');

  await expect(page.getByText('Production Test Workspace').first()).toBeVisible();
  await page.getByLabel('Project name').fill('Launch campaign');
  await page.getByRole('button', { name: 'Start Upload' }).click();

  await expect(page.getByText('Launch campaign').first()).toBeVisible();
  await page.getByRole('link', { name: /Open project/i }).click();
  await expect(page).toHaveURL(new RegExp(`/editor/${PROJECT_ID}$`));
  await expect(page.getByRole('heading', { name: 'Launch campaign' })).toBeVisible();
});
