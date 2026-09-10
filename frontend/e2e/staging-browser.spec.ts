import { expect, test } from '@playwright/test';

const stagingBaseUrl = process.env.PLAYWRIGHT_BASE_URL?.trim();
const stagingAuthToken = process.env.STAGING_AUTH_BEARER_TOKEN?.trim();
const stagingWorkspaceId = process.env.STAGING_WORKSPACE_ID?.trim();
const stagingWorkspaceName = process.env.STAGING_WORKSPACE_NAME?.trim();

test.describe('deployed staging browser validation', () => {
  test.skip(!stagingBaseUrl, 'Set PLAYWRIGHT_BASE_URL to the deployed staging web URL.');

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });
  });

  test('signed-out landing renders the marketing shell on staging', async ({ page }) => {
    await page.goto('/');

    await expect(
      page.getByRole('heading', { name: /Translate one video\.?\s*Reach every audience\.?/i }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue with Google' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Start free' })).toBeVisible();
  });

  test('authenticated operator reaches the workspace home on staging', async ({ page }) => {
    test.skip(!stagingAuthToken, 'Set STAGING_AUTH_BEARER_TOKEN for authenticated staging browser validation.');

    await page.addInitScript(
      ({ token, workspaceId }) => {
        window.localStorage.setItem('globesync.auth_token', token);
        if (workspaceId) {
          window.localStorage.setItem('globesync.active_workspace_id', workspaceId);
        }
      },
      { token: stagingAuthToken ?? '', workspaceId: stagingWorkspaceId ?? '' },
    );

    await page.goto('/');

    await expect(page.getByRole('heading', { name: /Welcome,/i })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('Your workspace')).toBeVisible();
    await expect(page.getByText('Create, review, and deliver every localized video from one place.')).toBeVisible();
    await expect(page.getByText('Sign out').first()).toBeVisible();

    if (stagingWorkspaceName) {
      await expect(page.getByText(stagingWorkspaceName).first()).toBeVisible();
    }
  });
});
