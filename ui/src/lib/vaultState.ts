/**
 * vaultState.ts — Shared vault selection helpers.
 *
 * Vault selection precedence (highest to lowest):
 *   1. URL query parameter  ?vault=<name>
 *   2. localStorage stored vault
 *   3. Backend default (first vault from /vaults)
 *
 * These helpers are pure, side-effect-free except for the explicit
 * set/clear operations.  No global state library is used.
 */

export const SELECTED_VAULT_KEY = 'context-vault-engine:selected-vault';

/** Return the vault name stored in localStorage, or null. */
export function getStoredVault(): string | null {
  try {
    return localStorage.getItem(SELECTED_VAULT_KEY);
  } catch {
    return null;
  }
}

/** Persist the selected vault name to localStorage. */
export function setStoredVault(vault: string): void {
  try {
    localStorage.setItem(SELECTED_VAULT_KEY, vault);
  } catch {
    // Ignore — quota errors or private-browsing mode.
  }
}

/** Remove the stored vault from localStorage. */
export function clearStoredVault(): void {
  try {
    localStorage.removeItem(SELECTED_VAULT_KEY);
  } catch {
    // Ignore.
  }
}

/** Return the `?vault=` query parameter from the current URL, or null. */
export function getVaultFromUrl(): string | null {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get('vault');
  } catch {
    return null;
  }
}

/**
 * Choose an initial vault from the available list.
 *
 * Precedence:
 *   urlVault (if in vaults list) → storedVault (if in vaults list) → vaults[0]
 *
 * Returns '' when vaults is empty.
 */
export function chooseInitialVault(
  vaults: string[],
  urlVault?: string | null,
  storedVault?: string | null,
): string {
  if (urlVault && vaults.includes(urlVault)) return urlVault;
  if (storedVault && vaults.includes(storedVault)) return storedVault;
  return vaults[0] ?? '';
}
