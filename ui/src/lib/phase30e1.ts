// ---------------------------------------------------------------------------
// Phase 30E1 - shared helpers for Pending, Trust, and Feedback polish
// ---------------------------------------------------------------------------
// Tiny deterministic helpers used by the Pending, Trust, and Feedback
// review/governance surfaces. No new runtime deps; no backend contract
// changes; pure functions only.

/**
 * Build a /app/raw deep link for the Developer route. Matches the
 * existing Phase 30D Developer deep-link contract used by Import,
 * Bundles, Exports, and Security pages.
 */
export function buildRawDeepLink(
  endpoint: string,
  vault: string,
  source: string,
): string {
  const params = new URLSearchParams();
  params.set('endpoint', endpoint);
  if (vault) params.set('vault', vault);
  params.set('source', source);
  return `/app/raw?${params.toString()}`;
}

/**
 * Deterministic severity ordering for Feedback triage.
 * Highest severity first; ties broken by status, then path.
 */
export const SEVERITY_RANK: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export function severityWeight(severity: string): number {
  const w = SEVERITY_RANK[severity];
  return typeof w === 'number' ? w : 999;
}

/**
 * Resolution status for a feedback signal. Signals like `useful` and
 * `agent_succeeded` count as resolved/positive; the rest are open
 * issues that should sort first.
 */
const RESOLVED_SIGNALS = new Set(['useful', 'agent_succeeded']);

export function isResolvedSignal(signal: string): boolean {
  return RESOLVED_SIGNALS.has(signal);
}

/**
 * Confirmation phrase contract for typed-confirmation gates in
 * Pending. The confirmation must match exactly (case-sensitive).
 */
export const PENDING_ACCEPT_PHRASE = 'ACCEPT';
export const PENDING_REJECT_PHRASE = 'REJECT';

export function isConfirmed(input: string, phrase: string): boolean {
  return input.trim() === phrase;
}
