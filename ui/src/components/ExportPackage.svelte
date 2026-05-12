<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchVaults,
    exportContextPackage,
    isOk,
    type ContextExportRequest,
    type ContextExportResponse,
    type ExportFileInfo,
  } from '../lib/api.ts';
  import { getStoredVault } from '../lib/vaultState.ts';

  // ---------------------------------------------------------------------------
  // Vault state
  // ---------------------------------------------------------------------------

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';

  // ---------------------------------------------------------------------------
  // Form state
  // ---------------------------------------------------------------------------

  let selectedVault = '';

  // Filters
  type StatusFilter = 'complete' | 'partial' | 'all';
  let statusFilter: StatusFilter = 'complete';
  let filterDomain = '';
  let filterType = '';
  let filterDifficulty = '';

  // Sections
  const DEFAULT_SECTIONS = ['Key Principles', 'How It Works', 'Trade-offs'];
  let includeSections: string[] = [...DEFAULT_SECTIONS];
  let newSectionInput = '';
  let sectionInputError = '';

  // Flags
  let includeBody = true;
  let includeRelated = false;
  let allowPartial = false;

  // Budget
  let maxNotes = 10;
  let maxChars = 20000;

  // Export options
  let overwrite = false;
  let requireSecurityPass = false;

  // ---------------------------------------------------------------------------
  // Submit state
  // ---------------------------------------------------------------------------

  type SubmitState = 'idle' | 'loading' | 'ok' | 'conflict' | 'security_fail' | 'error';
  let submitState: SubmitState = 'idle';
  let exportResult: ContextExportResponse | null = null;
  let submitError = '';
  let submitErrorCode = '';
  let submitErrorDetails = '';

  // UI state
  let showRawJson = false;

  // ---------------------------------------------------------------------------
  // Derived / reactive
  // ---------------------------------------------------------------------------

  $: partialConflict = statusFilter === 'partial' && !allowPartial;

  $: canSubmit =
    selectedVault !== '' &&
    includeSections.length > 0 &&
    submitState !== 'loading';

  // Preview request (reactive for preview panel)
  $: previewFilters = (() => {
    const f: Record<string, string> = {};
    if (statusFilter === 'complete') f.status = 'complete';
    if (statusFilter === 'partial') f.status = 'partial';
    const d = filterDomain.trim();
    if (d) f.domain = d;
    const t = filterType.trim();
    if (t) f.type = t;
    const diff = filterDifficulty.trim();
    if (diff) f.difficulty = diff;
    return f;
  })();

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onMount(async () => {
    vaultsLoading = true;
    vaultsError = '';
    const result = await fetchVaults();
    if (isOk(result)) {
      vaultList = result.data.vaults ?? [];
      if (vaultList.length > 0) {
        const stored = getStoredVault();
        selectedVault = (stored && vaultList.includes(stored)) ? stored : vaultList[0];
      }
    } else {
      vaultsError = result.error?.message ?? 'Failed to load vaults';
    }
    vaultsLoading = false;
  });

  // ---------------------------------------------------------------------------
  // Section management
  // ---------------------------------------------------------------------------

  function addSection() {
    const val = newSectionInput.trim();
    sectionInputError = '';
    if (!val) {
      sectionInputError = 'Section name cannot be empty';
      return;
    }
    if (includeSections.map(s => s.trim().toLowerCase()).includes(val.toLowerCase())) {
      sectionInputError = 'Duplicate section name';
      return;
    }
    includeSections = [...includeSections, val];
    newSectionInput = '';
  }

  function removeSection(index: number) {
    includeSections = includeSections.filter((_, i) => i !== index);
  }

  function onSectionKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); addSection(); }
  }

  // ---------------------------------------------------------------------------
  // Request construction
  // ---------------------------------------------------------------------------

  function buildRequest(): ContextExportRequest {
    const filters: Record<string, string> = {};

    if (statusFilter === 'complete') filters.status = 'complete';
    if (statusFilter === 'partial') filters.status = 'partial';

    const domain = filterDomain.trim();
    if (domain) filters.domain = domain;

    const type = filterType.trim();
    if (type) filters.type = type;

    const difficulty = filterDifficulty.trim();
    if (difficulty) filters.difficulty = difficulty;

    return {
      vault: selectedVault,
      filters: Object.keys(filters).length > 0 ? filters : {},
      include_sections: includeSections.map(s => s.trim()).filter(Boolean),
      include_body: includeBody,
      include_related: includeRelated,
      allow_partial: statusFilter === 'partial' ? true : allowPartial,
      max_notes: Math.max(1, Math.min(100, maxNotes)),
      max_chars: Math.max(100, Math.min(500000, maxChars)),
      overwrite,
      require_security_pass: requireSecurityPass,
    };
  }

  // ---------------------------------------------------------------------------
  // Submit
  // ---------------------------------------------------------------------------

  async function handleExport() {
    if (!canSubmit) return;

    // Validate sections
    const trimmed = includeSections.map(s => s.trim()).filter(Boolean);
    const lower = trimmed.map(s => s.toLowerCase());
    if (new Set(lower).size !== lower.length) {
      submitError = 'Duplicate section names detected. Remove duplicates before exporting.';
      submitErrorCode = 'DUPLICATE_SECTIONS';
      submitErrorDetails = '';
      submitState = 'error';
      return;
    }
    if (trimmed.length === 0) {
      submitError = 'At least one section name is required.';
      submitErrorCode = 'NO_SECTIONS';
      submitErrorDetails = '';
      submitState = 'error';
      return;
    }

    submitState = 'loading';
    exportResult = null;
    submitError = '';
    submitErrorCode = '';
    submitErrorDetails = '';
    showRawJson = false;

    const req = buildRequest();
    const result = await exportContextPackage(req);

    if (isOk(result)) {
      exportResult = result.data;
      submitState = 'ok';
    } else {
      const code = result.error?.code ?? 'UNKNOWN';
      const msg = result.error?.message ?? 'An unexpected error occurred.';
      submitErrorCode = code;
      submitError = msg;
      submitErrorDetails = '';

      if (code === 'PACKAGE_EXISTS') {
        submitState = 'conflict';
      } else if (code === 'SECURITY_SCAN_FAIL') {
        submitState = 'security_fail';
      } else {
        submitState = 'error';
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function errorTitle(code: string): string {
    if (code === 'INVALID_VAULT') return 'Vault Not Found';
    if (code === 'INVALID_FILTER') return 'Invalid Filter';
    if (code === 'VALIDATION_ERROR') return 'Validation Error';
    if (code === 'BUNDLE_FAILED') return 'Bundle Generation Failed';
    if (code === 'EXPORT_FAILED') return 'Export Failed';
    if (code === 'NETWORK_ERROR') return 'Backend Unavailable';
    if (code === 'DUPLICATE_SECTIONS') return 'Duplicate Sections';
    if (code === 'NO_SECTIONS') return 'No Sections';
    return 'Error';
  }

  function formatBytes(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)} MB`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)} kB`;
    return `${n} B`;
  }

  function totalBytes(files: Record<string, ExportFileInfo>): number {
    return Object.values(files).reduce((sum, f) => sum + f.bytes, 0);
  }

  function fileEntries(files: Record<string, ExportFileInfo>): [string, ExportFileInfo][] {
    return Object.entries(files);
  }

  function filterDescription(filters: Record<string, string>): string {
    const parts = Object.entries(filters).map(([k, v]) => `${k}=${v}`);
    return parts.length > 0 ? parts.join(', ') : 'none';
  }

  // Hash display: show first 16 + last 8 chars of sha256 for compact display
  function shortHash(hash: string): string {
    if (hash.length <= 28) return hash;
    return `${hash.slice(0, 16)}…${hash.slice(-8)}`;
  }
</script>

<!-- =========================================================
     Page header
     ========================================================= -->
<div class="cve-page">
<div class="cve-page-header mb-5">
  <h1 class="cve-page-title text-xl font-semibold text-zinc-100">Export Package</h1>
  <p class="text-sm text-zinc-500 mt-0.5">
    Configure and export a context bundle as a portable package with SHA-256 manifest.
  </p>
</div>

<!-- =========================================================
     Vault loading states
     ========================================================= -->
{#if vaultsLoading}
  <div class="text-sm text-zinc-500 py-6">Loading vaults...</div>
{:else if vaultsError}
  <div class="bg-red-950 border border-red-800 rounded-lg p-4 text-sm text-red-300 mb-4">
    <span class="font-medium">Could not load vaults:</span> {vaultsError}
  </div>
{:else if vaultList.length === 0}
  <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-lg">
    <p class="text-sm text-zinc-400">No vaults registered. Use Vault Setup to create one.</p>
  </div>
{:else}
  <!-- =======================================================
       Two-column layout: config left, result right
       ======================================================= -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">

    <!-- ── Left: Configuration form ─────────────────────────── -->
    <div class="space-y-4">

      <!-- Vault selector -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Vault</h2>
        <select
          bind:value={selectedVault}
          class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-sky-600"
        >
          {#each vaultList as v}
            <option value={v}>{v}</option>
          {/each}
        </select>
      </div>

      <!-- Filters -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Filters</h2>

        <div class="space-y-3">
          <!-- Status -->
          <div>
            <label class="block text-xs font-medium text-zinc-400 mb-1.5">Status</label>
            <div class="flex gap-2">
              {#each ['complete', 'partial', 'all'] as opt}
                <button
                  type="button"
                  on:click={() => { statusFilter = opt as StatusFilter; }}
                  class:bg-sky-700={statusFilter === opt}
                  class:text-sky-100={statusFilter === opt}
                  class:border-sky-600={statusFilter === opt}
                  class:bg-zinc-800={statusFilter !== opt}
                  class:text-zinc-400={statusFilter !== opt}
                  class:border-zinc-700={statusFilter !== opt}
                  class="px-3 py-1.5 rounded-md text-xs font-medium border transition-colors"
                >{opt}</button>
              {/each}
            </div>
            {#if partialConflict}
              <p class="text-xs text-amber-400 mt-1.5">
                Status is "partial" but allow_partial is off. Enable allow_partial below or partial notes may be excluded.
              </p>
            {/if}
          </div>

          <!-- Domain -->
          <div>
            <label class="block text-xs font-medium text-zinc-400 mb-1">Domain <span class="text-zinc-600">(optional)</span></label>
            <input
              bind:value={filterDomain}
              type="text"
              placeholder="e.g. fundamentals"
              class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-sky-600"
            />
          </div>

          <!-- Type -->
          <div>
            <label class="block text-xs font-medium text-zinc-400 mb-1">Type <span class="text-zinc-600">(optional)</span></label>
            <input
              bind:value={filterType}
              type="text"
              placeholder="e.g. core-concept"
              class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-sky-600"
            />
          </div>

          <!-- Difficulty -->
          <div>
            <label class="block text-xs font-medium text-zinc-400 mb-1">Difficulty <span class="text-zinc-600">(optional)</span></label>
            <input
              bind:value={filterDifficulty}
              type="text"
              placeholder="e.g. intermediate"
              class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-sky-600"
            />
          </div>
        </div>
      </div>

      <!-- Sections -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Sections to Extract</h2>

        <div class="flex flex-wrap gap-1.5 mb-3">
          {#each includeSections as sec, i}
            <span class="inline-flex items-center gap-1 bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1 text-xs text-zinc-200">
              {sec}
              <button
                type="button"
                on:click={() => removeSection(i)}
                class="text-zinc-500 hover:text-red-400 ml-0.5 transition-colors"
                aria-label="Remove section"
              >
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          {/each}
        </div>

        <div class="flex gap-2">
          <input
            bind:value={newSectionInput}
            on:keydown={onSectionKeydown}
            type="text"
            placeholder="Add section name..."
            class="flex-1 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-sky-600"
            class:border-red-700={!!sectionInputError}
          />
          <button
            type="button"
            on:click={addSection}
            class="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 border border-zinc-600 text-zinc-200 text-sm rounded-md transition-colors"
          >Add</button>
        </div>
        {#if sectionInputError}
          <p class="text-xs text-red-400 mt-1">{sectionInputError}</p>
        {/if}
      </div>

      <!-- Content flags -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Content Options</h2>

        <div class="space-y-3">
          <label class="flex items-start gap-2.5 cursor-pointer select-none">
            <input type="checkbox" bind:checked={includeBody} class="mt-0.5 accent-sky-500" />
            <div>
              <span class="text-sm text-zinc-200">Include body</span>
              <p class="text-xs text-zinc-500 mt-0.5">Include full note text after frontmatter.</p>
            </div>
          </label>

          <label class="flex items-start gap-2.5 cursor-pointer select-none">
            <input type="checkbox" bind:checked={includeRelated} class="mt-0.5 accent-sky-500" />
            <div>
              <span class="text-sm text-zinc-200">Include related notes</span>
              <p class="text-xs text-zinc-500 mt-0.5">Attach graph relationship IDs for each note.</p>
            </div>
          </label>

          <label class="flex items-start gap-2.5 cursor-pointer select-none">
            <input type="checkbox" bind:checked={allowPartial} class="mt-0.5 accent-sky-500" />
            <div>
              <span class="text-sm text-zinc-200">Allow partial notes</span>
              <p class="text-xs text-zinc-500 mt-0.5">
                Include notes with <span class="font-mono text-xs text-zinc-400">status=partial</span>.
                {#if statusFilter === 'partial'}<span class="text-amber-400"> (auto-enabled when status filter is partial)</span>{/if}
              </p>
            </div>
          </label>
        </div>
      </div>

      <!-- Budget -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Budget</h2>

        <div class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-zinc-400 mb-1">
              Max notes
              <span class="text-zinc-600 font-normal">(1–100)</span>
            </label>
            <input
              bind:value={maxNotes}
              type="number"
              min="1"
              max="100"
              class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-sky-600"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-zinc-400 mb-1">
              Max chars
              <span class="text-zinc-600 font-normal">(100–500,000)</span>
            </label>
            <input
              bind:value={maxChars}
              type="number"
              min="100"
              max="500000"
              class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-sky-600"
            />
          </div>
        </div>
      </div>

      <!-- Export options -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Export Options</h2>

        <div class="space-y-3">
          <label class="flex items-start gap-2.5 cursor-pointer select-none">
            <input type="checkbox" bind:checked={overwrite} class="mt-0.5 accent-sky-500" />
            <div>
              <span class="text-sm text-zinc-200">Overwrite existing package</span>
              <p class="text-xs text-zinc-500 mt-0.5">
                Replace an existing package with the same deterministic bundle ID.
                If off and the package already exists, the export will return a conflict error.
              </p>
            </div>
          </label>

          <label class="flex items-start gap-2.5 cursor-pointer select-none">
            <input type="checkbox" bind:checked={requireSecurityPass} class="mt-0.5 accent-sky-500" />
            <div>
              <span class="text-sm text-zinc-200">Require security pass</span>
              <p class="text-xs text-zinc-500 mt-0.5">
                Abort export if the security scan detects a blocking finding.
                Nothing is written to disk if the scan fails.
              </p>
            </div>
          </label>
        </div>
      </div>

      <!-- Request preview -->
      <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-zinc-300 mb-3">Request Preview</h2>

        <dl class="space-y-2 text-xs">
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Vault</dt>
            <dd class="text-zinc-200 font-mono">{selectedVault}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Status filter</dt>
            <dd class="text-zinc-200">{statusFilter}</dd>
          </div>
          {#if Object.keys(previewFilters).length > 1 || (Object.keys(previewFilters).length === 1 && !previewFilters.status)}
            <div class="flex gap-2">
              <dt class="text-zinc-500 w-28 shrink-0">Other filters</dt>
              <dd class="text-zinc-200 font-mono">{filterDescription(Object.fromEntries(Object.entries(previewFilters).filter(([k]) => k !== 'status')))}</dd>
            </div>
          {/if}
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Sections</dt>
            <dd class="text-zinc-200">{#if includeSections.length > 0}{includeSections.join(', ')}{:else}<span class="text-red-400">none</span>{/if}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Include body</dt>
            <dd class="text-zinc-200">{includeBody ? 'yes' : 'no'}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Include related</dt>
            <dd class="text-zinc-200">{includeRelated ? 'yes' : 'no'}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Allow partial</dt>
            <dd class="text-zinc-200">{statusFilter === 'partial' ? 'yes (auto)' : allowPartial ? 'yes' : 'no'}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Max notes</dt>
            <dd class="text-zinc-200">{Math.max(1, Math.min(100, maxNotes))}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Max chars</dt>
            <dd class="text-zinc-200">{Math.max(100, Math.min(500000, maxChars)).toLocaleString()}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Overwrite</dt>
            <dd class="{overwrite ? 'text-amber-300' : 'text-zinc-200'}">{overwrite ? 'yes' : 'no'}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Security gate</dt>
            <dd class="{requireSecurityPass ? 'text-sky-300' : 'text-zinc-200'}">{requireSecurityPass ? 'enabled' : 'disabled'}</dd>
          </div>
          <div class="flex gap-2">
            <dt class="text-zinc-500 w-28 shrink-0">Output dir</dt>
            <dd class="text-zinc-500 font-mono">dist/context-bundles/&lt;bundle-id&gt;</dd>
          </div>
        </dl>
      </div>

      <!-- Export button -->
      <button
        type="button"
        on:click={handleExport}
        disabled={!canSubmit}
        class="w-full py-2.5 px-4 rounded-lg text-sm font-semibold transition-colors
          {submitState === 'loading'
            ? 'bg-zinc-700 text-zinc-400 cursor-wait'
            : canSubmit
              ? 'bg-emerald-700 hover:bg-emerald-600 text-white'
              : 'bg-zinc-800 text-zinc-600 cursor-not-allowed'
          }"
      >
        {#if submitState === 'loading'}
          Exporting...
        {:else}
          Export Package
        {/if}
      </button>

    </div>

    <!-- ── Right: Result panel ──────────────────────────────── -->
    <div class="space-y-4">

      <!-- Idle state -->
      {#if submitState === 'idle'}
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-8 flex flex-col items-center text-center">
          <div class="w-10 h-10 bg-zinc-800 border border-zinc-700 rounded-lg flex items-center justify-center mb-3">
            <svg class="w-5 h-5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
            </svg>
          </div>
          <p class="text-sm text-zinc-400">Configure the export on the left, then click <span class="font-medium text-zinc-300">Export Package</span>.</p>
          <p class="text-xs text-zinc-600 mt-1.5">The package will be written to <span class="font-mono">dist/context-bundles/</span> on the server.</p>
        </div>
      {/if}

      <!-- Loading state -->
      {#if submitState === 'loading'}
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-8 flex flex-col items-center text-center">
          <div class="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin mb-3"></div>
          <p class="text-sm text-zinc-400">Exporting package...</p>
        </div>
      {/if}

      <!-- Conflict state (PACKAGE_EXISTS) -->
      {#if submitState === 'conflict'}
        <div class="bg-amber-950 border border-amber-700 rounded-lg p-5">
          <div class="flex items-start gap-3">
            <div class="w-8 h-8 bg-amber-900 border border-amber-700 rounded-md flex items-center justify-center shrink-0 mt-0.5">
              <svg class="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M12 3a9 9 0 110 18A9 9 0 0112 3z" />
              </svg>
            </div>
            <div>
              <h3 class="text-sm font-semibold text-amber-300 mb-1">Package Already Exists</h3>
              <p class="text-sm text-amber-400 mb-2">{submitError}</p>
              <p class="text-xs text-amber-500">
                A package with this deterministic bundle ID already exists on disk.
                To replace it, enable <span class="font-semibold text-amber-300">Overwrite existing package</span> in the Export Options panel, then export again.
              </p>
            </div>
          </div>
          <button
            type="button"
            on:click={() => { submitState = 'idle'; }}
            class="mt-3 text-xs text-amber-500 hover:text-amber-300 underline"
          >Dismiss</button>
        </div>
      {/if}

      <!-- Security gate failure (SECURITY_SCAN_FAIL) -->
      {#if submitState === 'security_fail'}
        <div class="bg-red-950 border border-red-700 rounded-lg p-5">
          <div class="flex items-start gap-3">
            <div class="w-8 h-8 bg-red-900 border border-red-700 rounded-md flex items-center justify-center shrink-0 mt-0.5">
              <svg class="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h3 class="text-sm font-semibold text-red-300 mb-1">Security Gate — Export Blocked</h3>
              <p class="text-sm text-red-400 mb-2">{submitError}</p>
              <p class="text-xs text-red-500">
                The <span class="font-semibold text-red-300">Require security pass</span> option blocked this export because the bundle contains notes that failed the security scan.
                Nothing was written to disk.
                Review the security findings in the Dashboard before changing this setting.
              </p>
            </div>
          </div>
          <button
            type="button"
            on:click={() => { submitState = 'idle'; }}
            class="mt-3 text-xs text-red-500 hover:text-red-300 underline"
          >Dismiss</button>
        </div>
      {/if}

      <!-- Generic error state -->
      {#if submitState === 'error'}
        <div class="bg-red-950 border border-red-800 rounded-lg p-4">
          <h3 class="text-sm font-semibold text-red-300 mb-1">{errorTitle(submitErrorCode)}</h3>
          <p class="text-sm text-red-400">{submitError}</p>
          {#if submitErrorDetails}
            <p class="text-xs text-red-500 mt-1 font-mono">{submitErrorDetails}</p>
          {/if}
          <button
            type="button"
            on:click={() => { submitState = 'idle'; }}
            class="mt-3 text-xs text-red-400 hover:text-red-200 underline"
          >Dismiss</button>
        </div>
      {/if}

      <!-- Success: export result panels -->
      {#if submitState === 'ok' && exportResult}
        {@const result = exportResult}
        {@const files = result.files ?? {}}
        {@const entries = fileEntries(files)}
        {@const total = totalBytes(files)}

        <!-- ── Export Overview ──────────────────────────────── -->
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div class="flex items-center gap-2 mb-3">
            <h2 class="text-sm font-semibold text-zinc-300">Export Overview</h2>
            <span class="inline-block bg-emerald-900 text-emerald-300 border border-emerald-700 rounded px-1.5 py-0.5 text-xs font-medium">exported</span>
            {#if overwrite}
              <span class="inline-block bg-amber-900 text-amber-300 border border-amber-700 rounded px-1.5 py-0.5 text-xs font-medium">overwrite used</span>
            {/if}
            {#if requireSecurityPass}
              <span class="inline-block bg-sky-900 text-sky-300 border border-sky-700 rounded px-1.5 py-0.5 text-xs font-medium">security gate enabled</span>
            {/if}
          </div>

          <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <div class="col-span-2">
              <dt class="text-xs text-zinc-500">Bundle ID</dt>
              <dd class="font-mono text-zinc-200 text-xs mt-0.5 break-all">{result.bundle_id}</dd>
            </div>
            <div class="col-span-2">
              <dt class="text-xs text-zinc-500">Package directory</dt>
              <dd class="font-mono text-zinc-300 text-xs mt-0.5">{result.package_dir}</dd>
            </div>
            <div>
              <dt class="text-xs text-zinc-500">Files written</dt>
              <dd class="text-zinc-200 text-xs mt-0.5">{entries.length}</dd>
            </div>
            <div>
              <dt class="text-xs text-zinc-500">Total size</dt>
              <dd class="text-zinc-200 text-xs mt-0.5">{formatBytes(total)}</dd>
            </div>
            <div>
              <dt class="text-xs text-zinc-500">Warnings</dt>
              <dd class="mt-0.5">
                {#if result.warnings?.length > 0}
                  <span class="inline-block bg-amber-900 text-amber-300 border border-amber-700 rounded px-1.5 py-0.5 text-xs font-medium">{result.warnings.length}</span>
                {:else}
                  <span class="text-zinc-500 text-xs">none</span>
                {/if}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-zinc-500">Overwrite</dt>
              <dd class="text-xs mt-0.5">
                {#if overwrite}
                  <span class="inline-block bg-amber-900 text-amber-300 border border-amber-700 rounded px-1.5 py-0.5 text-xs font-medium">yes</span>
                {:else}
                  <span class="text-zinc-500">no</span>
                {/if}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-zinc-500">Security gate</dt>
              <dd class="text-xs mt-0.5">
                {#if requireSecurityPass}
                  <span class="inline-block bg-sky-900 text-sky-300 border border-sky-700 rounded px-1.5 py-0.5 text-xs font-medium">enabled</span>
                {:else}
                  <span class="text-zinc-500">disabled</span>
                {/if}
              </dd>
            </div>
          </dl>
        </div>

        <!-- ── Files / Manifest panel ───────────────────────── -->
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-semibold text-zinc-300">
              Files
              <span class="font-normal text-zinc-500 text-xs ml-1">({entries.length})</span>
            </h2>
            <span class="text-xs text-zinc-500">{formatBytes(total)} total</span>
          </div>

          {#if entries.length === 0}
            <p class="text-xs text-zinc-500">No files reported.</p>
          {:else}
            <div class="overflow-x-auto -mx-1">
              <table class="cve-table w-full text-xs">
                <thead>
                  <tr class="border-b border-zinc-800">
                    <th class="text-left text-zinc-500 font-medium pb-2 pr-3 pl-1">File</th>
                    <th class="text-right text-zinc-500 font-medium pb-2 pr-3">Size</th>
                    <th class="text-left text-zinc-500 font-medium pb-2 pl-1">SHA-256</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-zinc-800/60">
                  {#each entries as [filename, info]}
                    <tr class="group">
                      <td class="py-2 pr-3 pl-1">
                        <span class="font-mono text-zinc-200">{filename}</span>
                      </td>
                      <td class="py-2 pr-3 text-right text-zinc-400 tabular-nums">
                        {formatBytes(info.bytes)}
                      </td>
                      <td class="py-2 pl-1">
                        <details class="group/hash">
                          <summary class="list-none cursor-pointer">
                            <span class="font-mono text-zinc-500 group-hover:text-zinc-300 transition-colors" title={info.sha256}>
                              {shortHash(info.sha256)}
                            </span>
                          </summary>
                          <div class="mt-1.5 bg-zinc-950 rounded p-1.5 border border-zinc-800">
                            <code class="font-mono text-zinc-400 text-xs break-all select-all">{info.sha256}</code>
                          </div>
                        </details>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>

        <!-- ── Warnings panel ───────────────────────────────── -->
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <h2 class="text-sm font-semibold text-zinc-300 mb-3">Warnings</h2>

          {#if !result.warnings || result.warnings.length === 0}
            <p class="text-xs text-zinc-500">No warnings.</p>
          {:else}
            <div class="space-y-1.5">
              {#each result.warnings as w}
                <div class="bg-amber-950/60 border border-amber-800/60 rounded-md px-2.5 py-1.5 text-xs text-amber-400">{w}</div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- ── Raw JSON ─────────────────────────────────────── -->
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-zinc-300">Raw Export JSON</h2>
            <button
              type="button"
              on:click={() => { showRawJson = !showRawJson; }}
              class="text-xs text-zinc-500 hover:text-zinc-300 underline transition-colors"
            >
              {showRawJson ? 'Hide' : 'Show'}
            </button>
          </div>
          {#if showRawJson}
            <pre class="mt-3 text-xs text-zinc-500 bg-zinc-950/60 rounded p-3 overflow-x-auto max-h-96 whitespace-pre-wrap break-words">{JSON.stringify(result, null, 2)}</pre>
          {/if}
        </div>

      {/if}

    </div>
  </div>
{/if}
</div>
