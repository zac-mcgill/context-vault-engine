<script lang="ts">
  /**
   * ExportPackage.svelte - Phase 30D3
   *
   * Sectioned export workflow that reuses the shared bundleConfig helper
   * with the Bundles page. Adds two export-only controls:
   *
   *   - require_security_pass: defaults to TRUE in the UI so destructive
   *     exports are gated by a successful security scan unless the user
   *     explicitly opts out. (Backend default is unchanged.)
   *   - overwrite: treated as destructive. Requires typed confirmation
   *     equal to the literal text OVERWRITE before the Export button
   *     becomes enabled.
   *
   * The route remains separate from /app/bundles even though it shares
   * the configuration shape, because Exports writes files to disk and
   * has additional safety gates.
   */

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
  import {
    type BundleConfigState,
    type BundleStatusFilter,
    defaultBundleConfig,
    clampMaxNotes,
    clampMaxChars,
    BUNDLE_MAX_NOTES_LIMIT,
    BUNDLE_MAX_NOTES_MIN,
    BUNDLE_MAX_CHARS_LIMIT,
    BUNDLE_MAX_CHARS_MIN,
    buildContextBundleRequest,
    buildBundleFilters,
    validateSections,
    describeFilters,
  } from '../lib/bundleConfig.ts';

  const OVERWRITE_CONFIRM_TEXT = 'OVERWRITE';

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';

  let selectedVault = '';
  let cfg: BundleConfigState = defaultBundleConfig();
  let newSectionInput = '';
  let sectionInputError = '';

  // Export-only options. require_security_pass defaults to true in the UI.
  let overwrite = false;
  let requireSecurityPass = true;
  let overwriteConfirmText = '';

  type SubmitState =
    | 'idle'
    | 'loading'
    | 'ok'
    | 'conflict'
    | 'security_fail'
    | 'error';
  let submitState: SubmitState = 'idle';
  let exportResult: ContextExportResponse | null = null;
  let submitError = '';
  let submitErrorCode = '';

  $: filtersSummary = describeFilters(buildBundleFilters(cfg));

  $: partialConflict = cfg.statusFilter === 'partial' && !cfg.allowPartial;

  $: overwriteConfirmed = !overwrite || overwriteConfirmText === OVERWRITE_CONFIRM_TEXT;

  $: canSubmit =
    selectedVault !== '' &&
    cfg.includeSections.length > 0 &&
    overwriteConfirmed &&
    submitState !== 'loading';

  $: rawDeepLink = selectedVault
    ? `/app/raw?endpoint=export&vault=${encodeURIComponent(selectedVault)}&source=exports`
    : '/app/raw?endpoint=export&source=exports';

  $: stateLabel =
    submitState === 'loading'
      ? 'Exporting'
      : submitState === 'ok'
        ? 'Export complete'
        : submitState === 'conflict'
          ? 'Package exists'
          : submitState === 'security_fail'
            ? 'Security blocked'
            : submitState === 'error'
              ? 'Error'
              : 'Not exported';

  onMount(async () => {
    vaultsLoading = true;
    vaultsError = '';
    const result = await fetchVaults();
    if (isOk(result)) {
      vaultList = result.data.vaults ?? [];
      if (vaultList.length > 0) {
        const stored = getStoredVault();
        selectedVault =
          stored && vaultList.includes(stored) ? stored : vaultList[0];
      }
    } else {
      vaultsError = result.error?.message ?? 'Failed to load vaults';
    }
    vaultsLoading = false;
  });

  function setStatusFilter(s: BundleStatusFilter): void {
    cfg.statusFilter = s;
  }

  function addSection(): void {
    const val = newSectionInput.trim();
    sectionInputError = '';
    if (!val) {
      sectionInputError = 'Section name cannot be empty';
      return;
    }
    if (
      cfg.includeSections
        .map((s) => s.trim().toLowerCase())
        .includes(val.toLowerCase())
    ) {
      sectionInputError = 'Duplicate section name';
      return;
    }
    cfg.includeSections = [...cfg.includeSections, val];
    newSectionInput = '';
  }

  function removeSection(idx: number): void {
    cfg.includeSections = cfg.includeSections.filter((_, i) => i !== idx);
  }

  function onSectionKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      addSection();
    }
  }

  function buildRequest(): ContextExportRequest {
    const base = buildContextBundleRequest(selectedVault, cfg);
    return {
      ...base,
      overwrite,
      require_security_pass: requireSecurityPass,
    };
  }

  async function handleExport(): Promise<void> {
    if (!canSubmit) return;
    const v = validateSections(cfg.includeSections);
    if (!v.ok) {
      submitErrorCode = v.code;
      submitError = v.message;
      submitState = 'error';
      return;
    }
    submitState = 'loading';
    exportResult = null;
    submitError = '';
    submitErrorCode = '';

    const result = await exportContextPackage(buildRequest());
    if (isOk(result)) {
      exportResult = result.data;
      submitState = 'ok';
    } else {
      const code = result.error?.code ?? 'UNKNOWN';
      submitErrorCode = code;
      submitError = result.error?.message ?? 'An unexpected error occurred.';
      if (code === 'PACKAGE_EXISTS') submitState = 'conflict';
      else if (code === 'SECURITY_SCAN_FAIL') submitState = 'security_fail';
      else submitState = 'error';
    }
  }

  function errorTitle(code: string): string {
    if (code === 'INVALID_VAULT') return 'Vault not found';
    if (code === 'INVALID_FILTER') return 'Invalid filter';
    if (code === 'VALIDATION_ERROR') return 'Validation error';
    if (code === 'BUNDLE_FAILED') return 'Bundle generation failed';
    if (code === 'EXPORT_FAILED') return 'Export failed';
    if (code === 'NETWORK_ERROR') return 'Backend unavailable';
    if (code === 'DUPLICATE_SECTIONS') return 'Duplicate sections';
    if (code === 'NO_SECTIONS') return 'No sections';
    if (code === 'PACKAGE_EXISTS') return 'Package already exists';
    if (code === 'SECURITY_SCAN_FAIL') return 'Security scan blocked export';
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

  function fileEntries(
    files: Record<string, ExportFileInfo>,
  ): [string, ExportFileInfo][] {
    return Object.entries(files);
  }
</script>

<div class="cve-page">
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">Export bundle package</h1>
      <div class="cve-toolbar__meta">
        <span
          class="cve-p30d3-toolbar-pill"
          class:cve-p30d3-toolbar-pill--ready={submitState === 'ok'}
          class:cve-p30d3-toolbar-pill--stale={submitState === 'conflict' || submitState === 'security_fail'}
          data-testid="export-state-pill">{stateLabel}</span
        >
        {#if selectedVault}
          <span>Vault: <code class="cve-p30d3-mono">{selectedVault}</code></span>
        {/if}
        <span>Filters: {filtersSummary}</span>
      </div>
      <div class="cve-toolbar__actions">
        <a class="cve-details__developer-link" href={rawDeepLink}>Open in Developer</a>
      </div>
    </div>
  </header>

  <div class="cve-status-strip">
    <div class="cve-status-tile">
      <span class="cve-status-tile__label">State</span>
      <span class="cve-status-tile__value">{stateLabel}</span>
      <span class="cve-status-tile__hint">Export workflow status</span>
    </div>
    <div class="cve-status-tile">
      <span class="cve-status-tile__label">Security gate</span>
      <span class="cve-status-tile__value">{requireSecurityPass ? 'Required' : 'Skipped'}</span>
      <span class="cve-status-tile__hint">Block on security findings</span>
    </div>
    <div class="cve-status-tile">
      <span class="cve-status-tile__label">Overwrite</span>
      <span class="cve-status-tile__value">{overwrite ? (overwriteConfirmed ? 'Confirmed' : 'Pending') : 'Off'}</span>
      <span class="cve-status-tile__hint">Typed OVERWRITE gate</span>
    </div>
  </div>

  {#if vaultsLoading}
    <div class="cve-banner cve-banner--info"><div class="cve-banner__body">Loading vaults...</div></div>
  {:else if vaultsError}
    <div class="cve-banner cve-banner--danger">
      <div>
        <div class="cve-banner__title">Could not load vaults</div>
        <div class="cve-banner__body">{vaultsError}</div>
      </div>
    </div>
  {:else if vaultList.length === 0}
    <div class="cve-banner cve-banner--info">
      <div>
        <div class="cve-banner__title">No vaults registered</div>
        <div class="cve-banner__body">
          Use <a href="/app/vault-setup">Vault Setup</a> to create one.
        </div>
      </div>
    </div>
  {:else}
    <section class="cve-p30d3-workflow">
      <div class="cve-banner cve-banner--info">
        <div class="cve-banner__body">
          Exports writes a deterministic bundle package to disk. The
          configuration form mirrors the Bundles page. Two extra safety
          gates apply here: require security pass, and overwrite. The
          /app/bundles preview workflow is the recommended way to validate
          the configuration before exporting.
        </div>
      </div>

      <div class="cve-p30d3-twocol">
        <div class="cve-p30d3-workflow">
          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Scope</h2>
              <p class="cve-p30d3-section__hint">Shared with Bundles</p>
            </header>
            <div class="cve-p30d3-field">
              <label for="export-vault">Vault</label>
              <select
                id="export-vault"
                bind:value={selectedVault}
                class="cve-input"
                data-testid="export-vault-select"
              >
                {#each vaultList as v}
                  <option value={v}>{v}</option>
                {/each}
              </select>
            </div>
          </div>

          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Filters</h2>
              <p class="cve-p30d3-section__hint">Limit eligible notes</p>
            </header>
            <div class="cve-p30d3-field">
              <span class="cve-p30d3-field__label">Status</span>
              <div class="cve-p30d3-segmented" role="group" aria-label="Status filter">
                <button
                  type="button"
                  aria-pressed={cfg.statusFilter === 'complete'}
                  on:click={() => setStatusFilter('complete')}>Complete only</button
                >
                <button
                  type="button"
                  aria-pressed={cfg.statusFilter === 'partial'}
                  on:click={() => setStatusFilter('partial')}>Partial only</button
                >
                <button
                  type="button"
                  aria-pressed={cfg.statusFilter === 'all'}
                  on:click={() => setStatusFilter('all')}>All</button
                >
              </div>
            </div>
            <div class="cve-p30d3-field-row">
              <div class="cve-p30d3-field">
                <label for="export-domain">Domain</label>
                <input id="export-domain" type="text" bind:value={cfg.filterDomain} class="cve-input" />
              </div>
              <div class="cve-p30d3-field">
                <label for="export-type">Note type</label>
                <input id="export-type" type="text" bind:value={cfg.filterType} class="cve-input" />
              </div>
            </div>
            <div class="cve-p30d3-field">
              <label for="export-difficulty">Difficulty</label>
              <input
                id="export-difficulty"
                type="text"
                bind:value={cfg.filterDifficulty}
                class="cve-input"
              />
            </div>
          </div>

          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Sections and budget</h2>
              <p class="cve-p30d3-section__hint">Determines bundle size</p>
            </header>
            <div class="cve-p30d3-chip-list">
              {#each cfg.includeSections as s, idx}
                <span class="cve-p30d3-chip">
                  {s}
                  <button
                    type="button"
                    class="cve-p30d3-chip__remove"
                    aria-label={`Remove section ${s}`}
                    on:click={() => removeSection(idx)}>x</button
                  >
                </span>
              {/each}
            </div>
            <div class="cve-p30d3-action-row">
              <input
                type="text"
                bind:value={newSectionInput}
                on:keydown={onSectionKeydown}
                class="cve-input"
                placeholder="Section name"
                aria-label="New section name"
              />
              <button type="button" class="cve-btn cve-btn-secondary" on:click={addSection}
                >Add section</button
              >
            </div>
            {#if sectionInputError}
              <p class="cve-p30d3-field__help" style="color:var(--cve-danger);">
                {sectionInputError}
              </p>
            {/if}
            <div class="cve-p30d3-field-row">
              <div class="cve-p30d3-field">
                <label for="export-max-notes">Max notes</label>
                <input
                  id="export-max-notes"
                  type="number"
                  min={BUNDLE_MAX_NOTES_MIN}
                  max={BUNDLE_MAX_NOTES_LIMIT}
                  bind:value={cfg.maxNotes}
                  on:change={() => (cfg.maxNotes = clampMaxNotes(cfg.maxNotes))}
                  class="cve-input"
                />
              </div>
              <div class="cve-p30d3-field">
                <label for="export-max-chars">Max chars</label>
                <input
                  id="export-max-chars"
                  type="number"
                  min={BUNDLE_MAX_CHARS_MIN}
                  max={BUNDLE_MAX_CHARS_LIMIT}
                  bind:value={cfg.maxChars}
                  on:change={() => (cfg.maxChars = clampMaxChars(cfg.maxChars))}
                  class="cve-input"
                />
              </div>
            </div>
            <label class="cve-p30d3-checkbox">
              <input type="checkbox" bind:checked={cfg.includeBody} />
              <span>Include body text</span>
            </label>
            <label class="cve-p30d3-checkbox">
              <input type="checkbox" bind:checked={cfg.includeRelated} />
              <span>Include related notes graph</span>
            </label>
            <label class="cve-p30d3-checkbox">
              <input type="checkbox" bind:checked={cfg.allowPartial} />
              <span>Allow partial notes</span>
            </label>
            {#if partialConflict}
              <div class="cve-banner cve-banner--info">
                <div class="cve-banner__body">
                  Status filter is partial; partial notes will be included.
                </div>
              </div>
            {/if}
          </div>

          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Safety gates</h2>
              <p class="cve-p30d3-section__hint">Apply before writing files to disk</p>
            </header>
            <label class="cve-p30d3-checkbox">
              <input
                type="checkbox"
                bind:checked={requireSecurityPass}
                data-testid="export-require-security-checkbox"
              />
              <span>
                Require security scan to pass before exporting
                <span class="cve-p30d3-field__help">
                  Recommended. When enabled, the export is rejected if the
                  bundle fails the deterministic security scan.
                </span>
              </span>
            </label>
          </div>

          <div
            class="cve-p30d3-section"
            class:cve-p30d3-section--danger={overwrite}
          >
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Destructive: overwrite</h2>
              <p class="cve-p30d3-section__hint">Replaces an existing package</p>
            </header>
            <label class="cve-p30d3-checkbox">
              <input
                type="checkbox"
                bind:checked={overwrite}
                data-testid="export-overwrite-checkbox"
              />
              <span>
                Overwrite existing package directory if it exists.
                <span class="cve-p30d3-field__help">
                  By default, if a package with the same deterministic bundle
                  id already exists, the export returns a conflict error.
                </span>
              </span>
            </label>
            {#if overwrite}
              <div class="cve-p30d3-confirm-block" data-testid="export-overwrite-confirm-block">
                <div class="cve-banner cve-banner--danger">
                  <div class="cve-banner__body">
                    This will overwrite any existing package on disk. Type
                    <code class="cve-p30d3-mono">{OVERWRITE_CONFIRM_TEXT}</code>
                    to confirm.
                  </div>
                </div>
                <div class="cve-p30d3-field">
                  <label for="export-overwrite-confirm">Confirmation</label>
                  <input
                    id="export-overwrite-confirm"
                    type="text"
                    bind:value={overwriteConfirmText}
                    placeholder={OVERWRITE_CONFIRM_TEXT}
                    class="cve-input cve-p30d3-mono"
                    data-testid="export-overwrite-confirm-input"
                  />
                  <p class="cve-p30d3-field__help">
                    Export stays disabled until this matches exactly.
                  </p>
                </div>
              </div>
            {/if}
          </div>

          <div class="cve-p30d3-sticky-action">
            <button
              type="button"
              on:click={handleExport}
              disabled={!canSubmit}
              class="cve-btn cve-btn-primary cve-p30d3-btn-danger"
              data-testid="export-submit-btn"
            >
              {submitState === 'loading' ? 'Exporting...' : 'Export package'}
            </button>
            {#if overwrite && !overwriteConfirmed}
              <span class="cve-p30d3-field__help" style="color:var(--cve-warning);">
                Type {OVERWRITE_CONFIRM_TEXT} above to enable Export.
              </span>
            {/if}
          </div>
        </div>

        <!-- Right: state-aware output -->
        <div class="cve-p30d3-workflow">
          {#if submitState === 'idle' || submitState === 'loading'}
            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">Readiness</h2>
                <p class="cve-p30d3-section__hint">
                  {submitState === 'loading' ? 'Exporting...' : 'Pending export'}
                </p>
              </header>
              <div class="cve-p30d3-readiness">
                <p class="cve-p30d3-readiness__title">Stages</p>
                <ol class="cve-p30d3-stage-list">
                  <li class={selectedVault ? 'cve-p30d3-stage--done' : 'cve-p30d3-stage--pending'}>
                    Choose vault
                  </li>
                  <li
                    class={cfg.includeSections.length > 0
                      ? 'cve-p30d3-stage--done'
                      : 'cve-p30d3-stage--pending'}
                  >
                    Define sections
                  </li>
                  <li class={requireSecurityPass ? 'cve-p30d3-stage--done' : 'cve-p30d3-stage--pending'}>
                    Security gate engaged
                  </li>
                  <li class={overwriteConfirmed ? 'cve-p30d3-stage--done' : 'cve-p30d3-stage--pending'}>
                    Overwrite confirmation (if used)
                  </li>
                  <li class="cve-p30d3-stage--pending">Write package to disk</li>
                </ol>
              </div>
            </div>
          {:else if submitState === 'conflict'}
            <div class="cve-banner cve-banner--warning">
              <div>
                <div class="cve-banner__title">{errorTitle(submitErrorCode)}</div>
                <div class="cve-banner__body">
                  {submitError} To replace it, enable overwrite, type
                  {OVERWRITE_CONFIRM_TEXT} to confirm, then export again.
                </div>
              </div>
            </div>
          {:else if submitState === 'security_fail'}
            <div class="cve-banner cve-banner--danger">
              <div>
                <div class="cve-banner__title">{errorTitle(submitErrorCode)}</div>
                <div class="cve-banner__body">
                  {submitError} The security scan rejected the bundle. Review
                  <a href="/app/security">Security</a> findings before
                  retrying.
                </div>
              </div>
            </div>
          {:else if submitState === 'error'}
            <div class="cve-banner cve-banner--danger">
              <div>
                <div class="cve-banner__title">{errorTitle(submitErrorCode)}</div>
                <div class="cve-banner__body">{submitError}</div>
              </div>
            </div>
          {:else if submitState === 'ok' && exportResult}
            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">Export complete</h2>
                <p class="cve-p30d3-section__hint">Bundle id:
                  <code class="cve-p30d3-mono">{exportResult.bundle_id}</code></p>
              </header>
              <dl class="cve-p30d3-summary-kv">
                <dt>Package directory</dt>
                <dd class="cve-p30d3-mono">{exportResult.package_dir}</dd>
                <dt>Files</dt>
                <dd>{Object.keys(exportResult.files).length}</dd>
                <dt>Total size</dt>
                <dd>{formatBytes(totalBytes(exportResult.files))}</dd>
                <dt>Overwrite used</dt>
                <dd>{overwrite ? 'yes' : 'no'}</dd>
                <dt>Security gate</dt>
                <dd>{requireSecurityPass ? 'required' : 'not required'}</dd>
              </dl>

              {#if exportResult.warnings.length > 0}
                <div class="cve-banner cve-banner--warning">
                  <div>
                    <div class="cve-banner__title">Warnings</div>
                    <ul class="cve-banner__body">
                      {#each exportResult.warnings as w}
                        <li>{w}</li>
                      {/each}
                    </ul>
                  </div>
                </div>
              {/if}

              <div class="cve-p30d3-table-wrap">
                <table class="cve-table">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Bytes</th>
                      <th>sha256</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each fileEntries(exportResult.files) as [name, info]}
                      <tr>
                        <td class="cve-p30d3-mono">{name}</td>
                        <td>{info.bytes}</td>
                        <td class="cve-p30d3-mono">{info.sha256}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>

            <details class="cve-details cve-details--inspector">
              <summary>Raw export response</summary>
              <div class="cve-details__body">
                <pre class="cve-p30d3-mono" style="white-space:pre-wrap;">{JSON.stringify(
                    exportResult,
                    null,
                    2,
                  )}</pre>
              </div>
            </details>

            <div class="cve-p30d3-followup">
              <a href="/app/bundles">Bundles</a>
              <a href="/app/security">Security</a>
              <a href="/app/validation">Validation</a>
            </div>
          {/if}
        </div>
      </div>
    </section>
  {/if}
</div>
