declare global {
  interface Window {
    whaat?: { apiBase?: string; token?: string };
  }
}

/** The API's address and the token to call it with, from one place: the server's own page carries the token in a meta
    tag; an app that packages the UI sets `window.whaat` before it loads. */
export function apiBase(): string {
  return window.whaat?.apiBase ?? "";
}

export function authToken(): string {
  return window.whaat?.token ?? document.querySelector<HTMLMetaElement>('meta[name="whaat-token"]')?.content ?? "";
}
