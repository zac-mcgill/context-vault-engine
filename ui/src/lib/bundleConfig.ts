/**
 * bundleConfig.ts - Phase 30D3
 *
 * Small shared frontend helper for the Bundle and Export workflows.
 *
 * Bundles (POST /context/bundle) and Exports (POST /context/export) accept
 * the same upstream configuration shape: filters, sections, content flags,
 * and a notes/chars budget. This helper centralises the form-state shape
 * and the request builder so the two workflows can not drift on field
 * naming, range clamping, or filter assembly.
 *
 * The Export workflow extends this shape with overwrite and
 * require_security_pass options handled in ExportPackage.svelte directly.
 *
 * Hard scope:
 *   - No backend route changes.
 *   - No new dependencies.
 *   - No state library; consumers own their own reactive bindings.
 *   - No mutation semantics changes; pure request-building helpers.
 */

import type {
  ContextBundleRequest,
  ContextProfileDefinition,
  ContextProfilesData,
} from './api';

export type BundleStatusFilter = 'complete' | 'partial' | 'all';

export const DEFAULT_BUNDLE_SECTIONS: string[] = [
  'Key Principles',
  'How It Works',
  'Trade-offs',
];

export const BUNDLE_MAX_NOTES_DEFAULT = 10;
export const BUNDLE_MAX_CHARS_DEFAULT = 20000;

export const BUNDLE_MAX_NOTES_LIMIT = 100;
export const BUNDLE_MAX_NOTES_MIN = 1;
export const BUNDLE_MAX_CHARS_LIMIT = 500000;
export const BUNDLE_MAX_CHARS_MIN = 100;

/** Common bundle/export configuration form state. */
export interface BundleConfigState {
  statusFilter: BundleStatusFilter;
  filterDomain: string;
  filterType: string;
  filterDifficulty: string;
  includeSections: string[];
  includeBody: boolean;
  includeRelated: boolean;
  allowPartial: boolean;
  maxNotes: number;
  maxChars: number;
  /** Optional named profile (device profile). Overrides mode when set. */
  selectedProfile?: string;
  /** Optional named mode (bundle size). */
  selectedMode?: string;
}

/** Return a fresh default config snapshot. */
export function defaultBundleConfig(): BundleConfigState {
  return {
    statusFilter: 'complete',
    filterDomain: '',
    filterType: '',
    filterDifficulty: '',
    includeSections: [...DEFAULT_BUNDLE_SECTIONS],
    includeBody: true,
    includeRelated: false,
    allowPartial: false,
    maxNotes: BUNDLE_MAX_NOTES_DEFAULT,
    maxChars: BUNDLE_MAX_CHARS_DEFAULT,
    selectedProfile: '',
    selectedMode: '',
  };
}

/** Clamp the notes budget into the legal range. */
export function clampMaxNotes(n: number): number {
  if (!Number.isFinite(n)) return BUNDLE_MAX_NOTES_DEFAULT;
  return Math.max(BUNDLE_MAX_NOTES_MIN, Math.min(BUNDLE_MAX_NOTES_LIMIT, Math.floor(n)));
}

/** Clamp the chars budget into the legal range. */
export function clampMaxChars(n: number): number {
  if (!Number.isFinite(n)) return BUNDLE_MAX_CHARS_DEFAULT;
  return Math.max(BUNDLE_MAX_CHARS_MIN, Math.min(BUNDLE_MAX_CHARS_LIMIT, Math.floor(n)));
}

/** Assemble the deterministic filters record from the config state. */
export function buildBundleFilters(cfg: BundleConfigState): Record<string, string> {
  const filters: Record<string, string> = {};
  if (cfg.statusFilter === 'complete') filters.status = 'complete';
  if (cfg.statusFilter === 'partial') filters.status = 'partial';
  const d = cfg.filterDomain.trim();
  if (d) filters.domain = d;
  const t = cfg.filterType.trim();
  if (t) filters.type = t;
  const diff = cfg.filterDifficulty.trim();
  if (diff) filters.difficulty = diff;
  return filters;
}

/** Build the shared portion of a POST /context/bundle request. */
export function buildContextBundleRequest(
  vault: string,
  cfg: BundleConfigState,
): ContextBundleRequest {
  const req: ContextBundleRequest = {
    vault,
    filters: buildBundleFilters(cfg),
    include_sections: cfg.includeSections.map((s) => s.trim()).filter(Boolean),
    include_body: cfg.includeBody,
    include_related: cfg.includeRelated,
    allow_partial: cfg.statusFilter === 'partial' ? true : cfg.allowPartial,
    max_notes: clampMaxNotes(cfg.maxNotes),
    max_chars: clampMaxChars(cfg.maxChars),
  };
  if (cfg.selectedProfile) req.profile = cfg.selectedProfile;
  else if (cfg.selectedMode) req.mode = cfg.selectedMode;
  return req;
}

/** Validate sections list. Returns null on success or an error code. */
export function validateSections(
  sections: string[],
): { ok: true } | { ok: false; code: 'NO_SECTIONS' | 'DUPLICATE_SECTIONS'; message: string } {
  const trimmed = sections.map((s) => s.trim()).filter(Boolean);
  if (trimmed.length === 0) {
    return { ok: false, code: 'NO_SECTIONS', message: 'At least one section name is required.' };
  }
  const lower = trimmed.map((s) => s.toLowerCase());
  if (new Set(lower).size !== lower.length) {
    return {
      ok: false,
      code: 'DUPLICATE_SECTIONS',
      message: 'Duplicate section names detected. Remove duplicates before continuing.',
    };
  }
  return { ok: true };
}

/** Resolve a named profile or mode from the loaded profiles catalogue. */
export function resolveActiveProfile(
  profile: string | undefined,
  mode: string | undefined,
  data: ContextProfilesData | null,
): ContextProfileDefinition | null {
  if (!data) return null;
  if (profile && data.profiles[profile]) return data.profiles[profile];
  if (mode && data.modes[mode]) return data.modes[mode];
  return null;
}

/** Apply a profile/mode definition onto the config state in place. */
export function applyProfileToConfig(
  cfg: BundleConfigState,
  def: ContextProfileDefinition,
): BundleConfigState {
  return {
    ...cfg,
    includeBody: def.include_body,
    includeRelated: def.include_related,
    allowPartial: def.allow_partial,
    maxNotes: def.max_notes,
    maxChars: def.max_chars,
    includeSections:
      def.include_sections && def.include_sections.length > 0
        ? [...def.include_sections]
        : cfg.includeSections,
  };
}

/** Compact filter summary string ("status=complete, domain=foo" or "none"). */
export function describeFilters(filters: Record<string, string>): string {
  const parts = Object.entries(filters).map(([k, v]) => `${k}=${v}`);
  return parts.length > 0 ? parts.join(', ') : 'none';
}
