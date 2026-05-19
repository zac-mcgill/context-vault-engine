<script lang="ts">
  /**
   * SecurityScan.svelte - Phase 30D3
   *
   * Full-vault security scan workflow.
   *
   * Behaviour change in Phase 30D3:
   *   - Default scope is the full vault (no filters, large note budget,
   *     allow_partial=true). Users see this as "Scan whole vault" without
   *     having to think about bundle sampling.
   *   - Sampling, filters, sections, and per-note budgets are demoted to
   *     an "Advanced scope" disclosure for power users.
   *   - Pre-run note count is surfaced via fetchNotes(vault) so users
   *     understand how many notes the deterministic scan will cover.
   *
   * Findings render in a bounded cve-table with internal scroll. Raw
   * response is demoted to a cve-details inspector with a developer
   * deep-link to /app/raw.
   */

  import { onMount } from 'svelte';
  import {
    fetchVaults,
    fetchNotes,
    scanContextSecurity,
    isOk,
    type ContextSecurityRequest,
    type ContextSecurityResponse,
    type SecurityFinding,
  } from '../lib/api.ts';
  import { getStoredVault } from '../lib/vaultState.ts';

  // Full-vault defaults. These intentionally bypass the bundle sampling
  // ergonomics of /app/bundles and /app/exports.
  const FULL_VAULT_MAX_NOTES = 100;
  const FULL_VAULT_MAX_CHARS = 500_000;

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';

  let selectedVault = '';
  let preRunNoteCount: number | null = null;
  let preRunNotesLoading = false;
  let preRunNotesError = '';

  // Advanced scope (defaults to OFF; full-vault is the standard path)
  let useAdvancedScope = false;
  type StatusFilter = 'complete' | 'partial' | 'all';
  let statusFilter: StatusFilter = 'all';
  let filterDomain = '';
  let filterType = '';
  let filterDifficulty = '';
  const DEFAULT_SECTIONS = ['Key Principles', 'How It Works', 'Trade-offs'];
  let includeSections: string[] = [...DEFAULT_SECTIONS];
  let newSectionInput = '';
  let sectionInputError = '';
  let allowPartial = true;
  let maxNotes = FULL_VAULT_MAX_NOTES;
  let maxChars = FULL_VAULT_MAX_CHARS;

  type SubmitState = 'idle' | 'loading' | 'ok' | 'error';
  let submitState: SubmitState = 'idle';
  let scanResult: ContextSecurityResponse | null = null;
  let submitError = '';
  let submitErrorCode = '';

  type SeverityFilter = 'all' | 'fail' | 'warning' | 'info';
  let severityFilter: SeverityFilter = 'all';
  let findingTextFilter = '';

  $: canSubmit = selectedVault !== '' && submitState !== 'loading';

  $: rawDeepLink = selectedVault
    ? `/app/raw?endpoint=security&vault=${encodeURIComponent(selectedVault)}&source=security`
    : '/app/raw?endpoint=security&source=security';

  $: stateLabel =
    submitState === 'loading'
      ? 'Scanning'
      : submitState === 'ok' && scanResult
        ? `Scan ${scanResult.status}`
        : submitState === 'error'
          ? 'Error'
          : 'Not run';

  $: filteredFindings = (() => {
    if (!scanResult) return [];
    let findings = scanResult.findings ?? [];
    if (severityFilter !== 'all') {
      findings = findings.filter((f) => f.severity === severityFilter);
    }
    const q = findingTextFilter.trim().toLowerCase();
    if (q) {
      findings = findings.filter(
        (f) =>
          f.path.toLowerCase().includes(q) ||
          f.rule.toLowerCase().includes(q) ||
          f.detail.toLowerCase().includes(q) ||
          (f.field ?? '').toLowerCase().includes(q),
      );
    }
    return findings;
  })();

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
        await refreshPreRunCount();
      }
    } else {
      vaultsError = result.error?.message ?? 'Failed to load vaults';
    }
    vaultsLoading = false;
  });

  $: void selectedVault, refreshPreRunCount();

  async function refreshPreRunCount(): Promise<void> {
    if (!selectedVault) {
      preRunNoteCount = null;
      return;
    }
    preRunNotesLoading = true;
    preRunNotesError = '';
    const res = await fetchNotes(selectedVault);
    if (isOk(res)) {
      preRunNoteCount = res.data.notes.length;
    } else {
      preRunNoteCount = null;
      preRunNotesError = res.error?.message ?? 'Failed to count notes';
    }
    preRunNotesLoading = false;
  }

  function addSection(): void {
    const val = newSectionInput.trim();
    sectionInputError = '';
    if (!val) {
      sectionInputError = 'Section name cannot be empty';
      return;
    }
    if (
      includeSections
        .map((s) => s.trim().toLowerCase())
        .includes(val.toLowerCase())
    ) {
      sectionInputError = 'Duplicate section name';
      return;
    }
    includeSections = [...includeSections, val];
    newSectionInput = '';
  }

  function removeSection(idx: number): void {
    includeSections = includeSections.filter((_, i) => i !== idx);
  }

  function onSectionKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter') {
      e.preventDefault();
      addSection();
    }
  }

  function buildRequest(): ContextSecurityRequest {
    if (!useAdvancedScope) {
      return {
        vault: selectedVault,
        filters: {},
        include_sections: [...DEFAULT_SECTIONS],
        include_body: true,
        allow_partial: true,
        max_notes: FULL_VAULT_MAX_NOTES,
        max_chars: FULL_VAULT_MAX_CHARS,
      };
    }
    const filters: Record<string, string> = {};
    if (statusFilter === 'complete') filters.status = 'complete';
    if (statusFilter === 'partial') filters.status = 'partial';
    const d = filterDomain.trim();
    if (d) filters.domain = d;
    const t = filterType.trim();
    if (t) filters.type = t;
    const diff = filterDifficulty.trim();
    if (diff) filters.difficulty = diff;
    return {
      vault: selectedVault,
      filters,
      include_sections: includeSections.map((s) => s.trim()).filter(Boolean),
      include_body: true,
      allow_partial: statusFilter === 'partial' ? true : allowPartial,
      max_notes: Math.max(1, Math.min(FULL_VAULT_MAX_NOTES, maxNotes)),
      max_chars: Math.max(100, Math.min(FULL_VAULT_MAX_CHARS, maxChars)),
    };
  }

  async function handleScan(): Promise<void> {
    if (!canSubmit) return;
    if (useAdvancedScope) {
      const trimmed = includeSections.map((s) => s.trim()).filter(Boolean);
      const lower = trimmed.map((s) => s.toLowerCase());
      if (new Set(lower).size !== lower.length) {
        submitError = 'Duplicate section names detected.';
        submitErrorCode = 'DUPLICATE_SECTIONS';
        submitState = 'error';
        return;
      }
      if (trimmed.length === 0) {
        submitError = 'At least one section name is required.';
        submitErrorCode = 'NO_SECTIONS';
        submitState = 'error';
        return;
      }
    }
    submitState = 'loading';
    scanResult = null;
    submitError = '';
    submitErrorCode = '';
    const res = await scanContextSecurity(buildRequest());
    if (isOk(res)) {
      scanResult = res.data;
      submitState = 'ok';
    } else {
      submitErrorCode = res.error?.code ?? 'UNKNOWN';
      submitError = res.error?.message ?? 'Scan failed.';
      submitState = 'error';
    }
  }

  function errorTitle(code: string): string {
    if (code === 'INVALID_VAULT') return 'Vault not found';
    if (code === 'INVALID_FILTER') return 'Invalid filter';
    if (code === 'BUNDLE_FAILED') return 'Bundle generation failed';
    if (code === 'SECURITY_FAILED') return 'Security scan failed';
    if (code === 'NETWORK_ERROR') return 'Backend unavailable';
    if (code === 'DUPLICATE_SECTIONS') return 'Duplicate sections';
    if (code === 'NO_SECTIONS') return 'No sections';
    return 'Error';
  }

  function severityTagClass(sev: string): string {
    if (sev === 'fail') return 'cve-p30d3-tag cve-p30d3-tag--fail';
    if (sev === 'warning') return 'cve-p30d3-tag cve-p30d3-tag--warning';
    if (sev === 'info') return 'cve-p30d3-tag cve-p30d3-tag--info';
    return 'cve-p30d3-tag cve-p30d3-tag--neutral';
  }

  function overallTagClass(status: string): string {
    if (status === 'pass') return 'cve-p30d3-tag cve-p30d3-tag--pass';
    if (status === 'warning') return 'cve-p30d3-tag cve-p30d3-tag--warning';
    if (status === 'fail') return 'cve-p30d3-tag cve-p30d3-tag--fail';
    return 'cve-p30d3-tag cve-p30d3-tag--neutral';
  }
</script>

<div class="cve-page">
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">Security scan</h1>
      <div class="cve-toolbar__meta">
        <span
          class="cve-p30d3-toolbar-pill"
          class:cve-p30d3-toolbar-pill--ready={submitState === 'ok' && scanResult?.status === 'pass'}
          class:cve-p30d3-toolbar-pill--stale={submitState === 'ok' &&
            (scanResult?.status === 'warning' || scanResult?.status === 'fail')}
          data-testid="security-state-pill">{stateLabel}</span
        >
        {#if selectedVault}
          <span>Vault: <code class="cve-p30d3-mono">{selectedVault}</code></span>
        {/if}
        <span>Scope: {useAdvancedScope ? 'advanced' : 'full vault'}</span>
      </div>
      <div class="cve-toolbar__actions">
        <a class="cve-details__developer-link" href={rawDeepLink}>Open in Developer</a>
      </div>
    </div>
  </header>

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
          Security scans the deterministic bundle for a vault and reports
          findings by severity. The default scope is the full vault. Use
          Advanced scope only when you need to scan a sampled subset.
        </div>
      </div>

      <div class="cve-p30d3-twocol">
        <div class="cve-p30d3-workflow">
          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Vault</h2>
              <p class="cve-p30d3-section__hint">Pre-run note count is informational</p>
            </header>
            <div class="cve-p30d3-field">
              <label for="security-vault">Vault</label>
              <select
                id="security-vault"
                bind:value={selectedVault}
                class="cve-input"
                data-testid="security-vault-select"
              >
                {#each vaultList as v}
                  <option value={v}>{v}</option>
                {/each}
              </select>
            </div>

            <div class="cve-status-strip">
              <div class="cve-status-tile" data-testid="security-prerun-tile">
                <span class="cve-status-tile__label">Notes in vault</span>
                <span class="cve-status-tile__value">
                  {#if preRunNotesLoading}
                    ...
                  {:else if preRunNoteCount === null}
                    unknown
                  {:else}
                    {preRunNoteCount}
                  {/if}
                </span>
                <span class="cve-status-tile__hint">
                  {#if preRunNotesError}
                    {preRunNotesError}
                  {:else}
                    pre-run, deterministic count
                  {/if}
                </span>
              </div>
              <div class="cve-status-tile">
                <span class="cve-status-tile__label">Scope</span>
                <span class="cve-status-tile__value">
                  {useAdvancedScope ? 'Advanced' : 'Full vault'}
                </span>
                <span class="cve-status-tile__hint">
                  max_notes={useAdvancedScope ? maxNotes : FULL_VAULT_MAX_NOTES}
                </span>
              </div>
            </div>
          </div>

          <details class="cve-p30d3-disclosure" bind:open={useAdvancedScope}>
            <summary data-testid="security-advanced-summary">
              Advanced scope (sampling, filters, custom budget)
            </summary>
            <div class="cve-p30d3-disclosure__body">
              <div class="cve-banner cve-banner--warning">
                <div class="cve-banner__body">
                  Advanced scope samples the vault using bundle filters and a
                  reduced budget. Results are NOT a full-vault scan; use
                  Advanced scope only when you have a specific reason.
                </div>
              </div>

              <div class="cve-p30d3-field">
                <span class="cve-p30d3-field__label">Status filter</span>
                <div class="cve-p30d3-segmented" role="group">
                  <button
                    type="button"
                    aria-pressed={statusFilter === 'complete'}
                    on:click={() => (statusFilter = 'complete')}>Complete</button
                  >
                  <button
                    type="button"
                    aria-pressed={statusFilter === 'partial'}
                    on:click={() => (statusFilter = 'partial')}>Partial</button
                  >
                  <button
                    type="button"
                    aria-pressed={statusFilter === 'all'}
                    on:click={() => (statusFilter = 'all')}>All</button
                  >
                </div>
              </div>

              <div class="cve-p30d3-field-row">
                <div class="cve-p30d3-field">
                  <label for="sec-domain">Domain</label>
                  <input id="sec-domain" type="text" bind:value={filterDomain} class="cve-input" />
                </div>
                <div class="cve-p30d3-field">
                  <label for="sec-type">Type</label>
                  <input id="sec-type" type="text" bind:value={filterType} class="cve-input" />
                </div>
              </div>
              <div class="cve-p30d3-field">
                <label for="sec-difficulty">Difficulty</label>
                <input
                  id="sec-difficulty"
                  type="text"
                  bind:value={filterDifficulty}
                  class="cve-input"
                />
              </div>

              <div class="cve-p30d3-field">
                <span class="cve-p30d3-field__label">Sections</span>
                <div class="cve-p30d3-chip-list">
                  {#each includeSections as s, idx}
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
              </div>

              <div class="cve-p30d3-field-row">
                <div class="cve-p30d3-field">
                  <label for="sec-max-notes">Max notes</label>
                  <input
                    id="sec-max-notes"
                    type="number"
                    min="1"
                    max={FULL_VAULT_MAX_NOTES}
                    bind:value={maxNotes}
                    class="cve-input"
                  />
                </div>
                <div class="cve-p30d3-field">
                  <label for="sec-max-chars">Max chars</label>
                  <input
                    id="sec-max-chars"
                    type="number"
                    min="100"
                    max={FULL_VAULT_MAX_CHARS}
                    bind:value={maxChars}
                    class="cve-input"
                  />
                </div>
              </div>
              <label class="cve-p30d3-checkbox">
                <input type="checkbox" bind:checked={allowPartial} />
                <span>Allow partial notes</span>
              </label>
            </div>
          </details>

          <div class="cve-p30d3-sticky-action">
            <button
              type="button"
              on:click={handleScan}
              disabled={!canSubmit}
              class="cve-btn cve-btn-primary"
              data-testid="security-scan-btn"
            >
              {submitState === 'loading' ? 'Scanning...' : 'Run security scan'}
            </button>
            <span class="cve-p30d3-field__help">
              {useAdvancedScope ? 'Advanced scope' : 'Full-vault scope'}
            </span>
          </div>
        </div>

        <div class="cve-p30d3-workflow">
          {#if submitState === 'idle' || submitState === 'loading'}
            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">Readiness</h2>
                <p class="cve-p30d3-section__hint">
                  {submitState === 'loading' ? 'Scanning...' : 'Pending scan'}
                </p>
              </header>
              <div class="cve-p30d3-readiness">
                <p class="cve-p30d3-readiness__title">Stages</p>
                <ol class="cve-p30d3-stage-list">
                  <li class={selectedVault ? 'cve-p30d3-stage--done' : 'cve-p30d3-stage--pending'}>
                    Choose vault
                  </li>
                  <li class="cve-p30d3-stage--done">
                    Default scope is full vault
                  </li>
                  <li class="cve-p30d3-stage--pending">Run scan</li>
                  <li class="cve-p30d3-stage--pending">Review findings</li>
                </ol>
              </div>
            </div>
          {:else if submitState === 'error'}
            <div class="cve-banner cve-banner--danger">
              <div>
                <div class="cve-banner__title">{errorTitle(submitErrorCode)}</div>
                <div class="cve-banner__body">{submitError}</div>
              </div>
            </div>
          {:else if submitState === 'ok' && scanResult}
            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">Scan summary</h2>
                <span class={overallTagClass(scanResult.status)}
                  data-testid="security-overall-status">{scanResult.status}</span
                >
              </header>
              <div class="cve-status-strip">
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Findings</span>
                  <span class="cve-status-tile__value">{scanResult.findings.length}</span>
                </div>
                <div class="cve-status-tile" data-zero={scanResult.summary.fail === 0}>
                  <span class="cve-status-tile__label">Fail</span>
                  <span class="cve-status-tile__value">{scanResult.summary.fail}</span>
                </div>
                <div class="cve-status-tile" data-zero={scanResult.summary.warning === 0}>
                  <span class="cve-status-tile__label">Warning</span>
                  <span class="cve-status-tile__value">{scanResult.summary.warning}</span>
                </div>
                <div class="cve-status-tile" data-zero={scanResult.summary.info === 0}>
                  <span class="cve-status-tile__label">Info</span>
                  <span class="cve-status-tile__value">{scanResult.summary.info}</span>
                </div>
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Scanned notes</span>
                  <span class="cve-status-tile__value">{scanResult.scanned.note_count}</span>
                  {#if scanResult.scanned.total_notes !== undefined}
                    <span class="cve-status-tile__hint"
                      >of {scanResult.scanned.total_notes} (coverage {Math.round(
                        (scanResult.scanned.coverage ?? 0) * 100,
                      )}%)</span
                    >
                  {/if}
                </div>
              </div>

              {#if scanResult.scanned.source_paths.length > 0}
                <details class="cve-p30d3-disclosure">
                  <summary>Source paths covered ({scanResult.scanned.source_paths.length})</summary>
                  <div class="cve-p30d3-disclosure__body">
                    <ul class="cve-p30d3-item-list">
                      {#each scanResult.scanned.source_paths as p}
                        <li class="cve-p30d3-mono">{p}</li>
                      {/each}
                    </ul>
                  </div>
                </details>
              {/if}
            </div>

            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">
                  Findings ({filteredFindings.length} / {scanResult.findings.length})
                </h2>
                <p class="cve-p30d3-section__hint">Filter by severity or text</p>
              </header>
              <div class="cve-p30d3-action-row">
                <div class="cve-p30d3-segmented" role="group" aria-label="Severity filter">
                  <button
                    type="button"
                    aria-pressed={severityFilter === 'all'}
                    on:click={() => (severityFilter = 'all')}>All</button
                  >
                  <button
                    type="button"
                    aria-pressed={severityFilter === 'fail'}
                    on:click={() => (severityFilter = 'fail')}>Fail</button
                  >
                  <button
                    type="button"
                    aria-pressed={severityFilter === 'warning'}
                    on:click={() => (severityFilter = 'warning')}>Warning</button
                  >
                  <button
                    type="button"
                    aria-pressed={severityFilter === 'info'}
                    on:click={() => (severityFilter = 'info')}>Info</button
                  >
                </div>
                <input
                  type="text"
                  bind:value={findingTextFilter}
                  class="cve-input"
                  placeholder="Filter findings (path, rule, detail, field)"
                  data-testid="security-finding-filter"
                  aria-label="Filter findings"
                />
              </div>

              {#if filteredFindings.length === 0}
                <p class="cve-p30d3-empty">
                  No findings match the current filters.
                </p>
              {:else}
                <div class="cve-p30d3-table-wrap cve-p30d3-findings-table">
                  <table class="cve-table">
                    <thead>
                      <tr>
                        <th>Severity</th>
                        <th>Rule</th>
                        <th>Path</th>
                        <th>Field</th>
                        <th>Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each filteredFindings as f}
                        <tr>
                          <td><span class={severityTagClass(f.severity)}>{f.severity}</span></td>
                          <td class="cve-p30d3-mono">{f.rule}</td>
                          <td class="cve-p30d3-mono">{f.path}</td>
                          <td class="cve-p30d3-mono">{f.field}</td>
                          <td>{f.detail}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </div>

            <details class="cve-details cve-details--inspector">
              <summary>Raw scan response</summary>
              <div class="cve-details__body">
                <pre class="cve-p30d3-mono" style="white-space:pre-wrap;">{JSON.stringify(
                    scanResult,
                    null,
                    2,
                  )}</pre>
              </div>
            </details>

            <div class="cve-p30d3-followup">
              <a href="/app/validation">Validation</a>
              <a href="/app/bundles">Bundles</a>
              <a href="/app/exports">Exports</a>
            </div>
          {/if}
        </div>
      </div>
    </section>
  {/if}
</div>
