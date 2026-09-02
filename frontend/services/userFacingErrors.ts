import { ApiError } from './apiClient';

function normalizeErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message.trim();
  }

  return 'Unexpected error';
}

function containsAny(message: string, fragments: string[]): boolean {
  const normalized = message.toLowerCase();
  return fragments.some((fragment) => normalized.includes(fragment.toLowerCase()));
}

export function mapUserFacingError(error: unknown, fallbackMessage: string): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return 'Your session expired or access could not be verified. Sign in again to continue.';
    }

    if (error.status === 404) {
      return 'The requested GlobeSync resource could not be found. Refresh and try again.';
    }

    if (error.status === 409) {
      return 'GlobeSync found a newer version of this work. Reload the latest workspace state before continuing.';
    }

    if (error.status === 429 || error.status === 503) {
      return 'GlobeSync is busy right now. Please wait a moment and try again.';
    }

    if (error.status >= 500) {
      return 'GlobeSync could not complete that request right now. Please try again in a moment.';
    }
  }

  const message = normalizeErrorMessage(error);

  if (containsAny(message, ['missing bearer token', 'bearer token', 'not authenticated'])) {
    return 'Sign in to continue to your GlobeSync workspace.';
  }

  if (containsAny(message, ['authenticated bootstrap returned no user context', 'auth bootstrap', 'bootstrap is not configured'])) {
    return 'Sign-in is temporarily unavailable for this deployment. Check the GlobeSync authentication configuration and try again.';
  }

  if (containsAny(message, ['google identity services', 'google sign-in did not return an identity token', 'google sign-in is not configured'])) {
    return 'Google sign-in is not available right now. Refresh the page and try again in a moment.';
  }

  if (containsAny(message, ['project api scope is not configured'])) {
    return 'Your workspace is still being prepared. Sign in again to refresh your GlobeSync workspace context.';
  }

  if (containsAny(message, ['failed to fetch', 'networkerror', 'network error'])) {
    return 'GlobeSync could not reach the service. Check your connection and try again.';
  }

  return fallbackMessage;
}

export function mapAuthError(error: unknown): string {
  return mapUserFacingError(error, 'We could not open GlobeSync sign-in right now. Please try again.');
}

export function mapProjectLoadError(error: unknown): string {
  return mapUserFacingError(error, 'We could not load your GlobeSync workspace right now. Please refresh and try again.');
}

export function mapProjectCreateError(error: unknown): string {
  return mapUserFacingError(error, 'We could not create your project right now. Please try again.');
}

export function mapLanguageLoadError(error: unknown): string {
  return mapUserFacingError(error, 'We could not load the latest language list, so GlobeSync is using the default options for now.');
}
