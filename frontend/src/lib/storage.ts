/**
 * localStorage for small per-browser conveniences (the chosen account and website, the theme). Every access is
 * wrapped: private windows and blocked site data throw, and the app must work without it.
 */
const PREFIX = "itos:";

export function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(PREFIX + key);
    else window.localStorage.setItem(PREFIX + key, value);
  } catch {
    // not remembered this time; nothing else depends on it
  }
}

export function readStoredNumber(key: string): number | null {
  const value = readStored(key);
  if (value === null) return null;
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}
