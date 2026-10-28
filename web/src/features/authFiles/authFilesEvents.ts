import { authFilesListCache } from './authFilesListCache';

export const AUTH_FILES_CHANGED_EVENT = 'auth-files-changed';

export const notifyAuthFilesChanged = () => {
  authFilesListCache.invalidate();
  window.dispatchEvent(new Event(AUTH_FILES_CHANGED_EVENT));
};
