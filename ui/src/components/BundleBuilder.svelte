<script lang="ts">
  /**
   * BundleBuilder.svelte - Phase 30D3
   *
   * Sectioned, state-aware bundle workflow. Form fields are grouped by
   * intent: vault/scope, filters, sections, budget/options, profile
   * defaults. The Generate Preview action is in a sticky footer. The
   * right pane is state-aware: it explains readiness before a preview,
   * then shows notes, budget, validation, and security status after.
   *
   * Raw JSON is demoted behind a cve-details inspector and the /app/raw
   * developer link.
   */

  import { onMount } from 'svelte';
  import {
    fetchVaults,
    fetchContextProfiles,
    generateContextBundle,
    isOk,
    type ContextBundleResponse,
    type ContextProfilesData,
    type BundleNote,
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
    resolveActiveProfile,
    applyProfileToConfig,
    describeFilters,
  } from '../lib/bundleConfig.ts';

  const MODE_NAMES = ['tiny', 'small', 'medium', 'large', 'agent'] as const;
  const DEVICE_PROFILE_NAMES = [
    'phone-local-llm',
    'desktop-agent',
    'full-review',
  ] as const;

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';

  let profilesData: ContextProfilesData | null = null;
  let profilesLoading = true;

  let selectedVault = '';
  let cfg: BundleConfigState = defaultBundleConfig();
  let newSectionInput = '';
  let sectionInputError = '';

  type SubmitState = 'idle' | 'loading' | 'ok' | 'error';
  let submitState: SubmitState = 'idle';
  let bundleResult: ContextBundleResponse | null = null;
  let submitError = '';
  let submitErrorCode = '';

  let expandedNoteIds: Set<string> = new Set();

  $: activeProfileDef = resolveActiveProfile(
    cfg.selectedProfile,
    cfg.selectedMode,
    profilesData,
  );

  $: filtersSummary = describeFilters(buildBundleFilters(cfg));

  $: partialConflict = cfg.statusFilter === 'partial' && !cfg.allowPartial;

  $: canSubmit =
    selectedVault !== '' &&
    cfg.includeSections.length > 0 &&
    submitState !== 'loading';

  $: rawDeepLink = selectedVault
    ? `/app/raw?endpoint=bundle&vault=${encodeURIComponent(selectedVault)}&source=bundles`
    : '/app/raw?endpoint=bundle&source=bundles';

  $: stateLabel =
    submitState === 'loading'
      ? 'Generating'
      : submitState === 'ok'
        ? 'Bundle ready'
        : submitState === 'error'
          ? 'Error'
          : 'Not generated';

  onMount(async () => {
    vaultsLoading = true;
    vaultsError = '';
    const [vaultsResult, profResult] = await Promise.all([
      fetchVaults(),
      fetchContextProfiles(),
    ]);
    if (isOk(vaultsResult)) {
      vaultList = vaultsResult.data.vaults ?? [];
      if (vaultList.length > 0) {
        const stored = getStoredVault();
        selectedVault =
          stored && vaultList.includes(stored) ? stored : vaultList[0];
      }
    } else {
      vaultsError = vaultsResult.error?.message ?? 'Failed to load vaults';
    }
    if (isOk(profResult)) profilesData = profResult.data;
    vaultsLoading = false;
    profilesLoading = false;
  });

  function onProfileChange(): void {
    cfg.selectedMode = '';
    const def = resolveActiveProfile(cfg.selectedProfile, '', profilesData);
    if (def) cfg = applyProfileToConfig(cfg, def);
  }

  function onModeChange(): void {
    cfg.selectedProfile = '';
    const def = resolveActiveProfile('', cfg.selectedMode, profilesData);
    if (def) cfg = applyProfileToConfig(cfg, def);
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

  async function handleGenerate(): Promise<void> {
    if (!canSubmit) return;
    const v = validateSections(cfg.includeSections);
    if (!v.ok) {
      submitErrorCode = v.code;
      submitError = v.message;
      submitState = 'error';
      return;
    }
    submitState = 'loading';
    submitError = '';
    submitErrorCode = '';
    expandedNoteIds = new Set();
    const req = buildContextBundleRequest(selectedVault, cfg);
    const result = await generateContextBundle(req);
    if (isOk(result)) {
      bundleResult = result.data;
      submitState = 'ok';
    } else {
      submitErrorCode = result.error?.code ?? 'UNKNOWN';
      submitError = result.error?.message ?? 'An unexpected error occurred.';
      submitState = 'error';
    }
  }

  function setStatusFilter(s: BundleStatusFilter): void {
    cfg.statusFilter = s;
  }

  function toggleNote(path: string): void {
    if (expandedNoteIds.has(path)) expandedNoteIds.delete(path);
    else expandedNoteIds.add(path);
    expandedNoteIds = expandedNoteIds;
  }

  function noteTitle(note: BundleNote): string {
    return (
      note.fields?.title ||
      note.path.split('/').pop()?.replace(/\.md$/, '') ||
      note.path
    );
  }

  function pct(used: number, max: number): number {
    if (max <= 0) return 0;
    return Math.min(100, Math.round((used / max) * 100));
  }

  function errorTitle(code: string): string {
    if (code === 'INVALID_VAULT') return 'Vault not found';
    if (code === 'INVALID_FILTER') return 'Invalid filter';
    if (code === 'VALIDATION_ERROR') return 'Validation error';
    if (code === 'BUNDLE_FAILED') return 'Bundle generation failed';
    if (code === 'NETWORK_ERROR') return 'Backend unavailable';
    if (code === 'DUPLICATE_SECTIONS') return 'Duplicate sections';
    if (code === 'NO_SECTIONS') return 'No sections';
    return 'Error';
  }
</script>

<div class="cve-page">
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">Context bundle</h1>
      <div class="cve-toolbar__meta">
        <span
          class="cve-p30d3-toolbar-pill"
          class:cve-p30d3-toolbar-pill--ready={submitState === 'ok'}
          data-testid="bundle-state-pill">{stateLabel}</span
        >
        {#if selectedVault}
          <span>Vault: <code class="cve-p30d3-mono">{selectedVault}</code></span>
        {/if}
        <span>Filters: {filtersSummary}</span>
      </div>
      <div class="cve-toolbar__actions">
        <a class="cve-toolbar-link" href={rawDeepLink}>Open in Developer</a>
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
          Configure scope, filters, sections, and budget. Then generate a
          deterministic context bundle. Use the same form on Exports to
          package a bundle for an external agent.
        </div>
      </div>

      <div class="cve-p30d3-twocol">
        <!-- Left: configuration -->
        <div class="cve-p30d3-workflow">
          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Scope</h2>
              <p class="cve-p30d3-section__hint">Vault and overall budget</p>
            </header>

            <div class="cve-p30d3-field">
              <label for="bundle-vault">Vault</label>
              <select
                id="bundle-vault"
                bind:value={selectedVault}
                class="cve-input"
                data-testid="bundle-vault-select"
              >
                {#each vaultList as v}
                  <option value={v}>{v}</option>
                {/each}
              </select>
            </div>

            <div class="cve-p30d3-field">
              <label for="bundle-profile">Device profile (overrides mode)</label>
              <select
                id="bundle-profile"
                bind:value={cfg.selectedProfile}
                on:change={onProfileChange}
                class="cve-input"
                disabled={profilesLoading}
              >
                <option value="">(none)</option>
                {#each DEVICE_PROFILE_NAMES as p}
                  <option value={p}>{p}</option>
                {/each}
              </select>
            </div>

            <div class="cve-p30d3-field">
              <label for="bundle-mode">Bundle mode</label>
              <select
                id="bundle-mode"
                bind:value={cfg.selectedMode}
                on:change={onModeChange}
                class="cve-input"
                disabled={profilesLoading}
              >
                <option value="">(none)</option>
                {#each MODE_NAMES as m}
                  <option value={m}>{m}</option>
                {/each}
              </select>
            </div>

            {#if activeProfileDef}
              <p class="cve-p30d3-field__help">
                Active: <strong>{activeProfileDef.label}</strong> -
                max_notes={activeProfileDef.max_notes},
                max_chars={activeProfileDef.max_chars},
                include_body={String(activeProfileDef.include_body)}.
              </p>
            {/if}
          </div>

          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Filters</h2>
              <p class="cve-p30d3-section__hint">Limit which notes are eligible</p>
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
                <label for="bundle-domain">Domain</label>
                <input
                  id="bundle-domain"
                  type="text"
                  bind:value={cfg.filterDomain}
                  class="cve-input"
                  placeholder="any"
                />
              </div>
              <div class="cve-p30d3-field">
                <label for="bundle-type">Note type</label>
                <input
                  id="bundle-type"
                  type="text"
                  bind:value={cfg.filterType}
                  class="cve-input"
                  placeholder="any"
                />
              </div>
            </div>
            <div class="cve-p30d3-field">
              <label for="bundle-difficulty">Difficulty</label>
              <input
                id="bundle-difficulty"
                type="text"
                bind:value={cfg.filterDifficulty}
                class="cve-input"
                placeholder="any"
              />
            </div>
          </div>

          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Sections</h2>
              <p class="cve-p30d3-section__hint">Section names extracted from each note</p>
            </header>

            <div class="cve-p30d3-chip-list" data-testid="bundle-section-chips">
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
            {#if cfg.includeSections.length === 0}
              <div class="cve-banner cve-banner--warning">
                <div class="cve-banner__body">
                  At least one section is required before generating a bundle.
                </div>
              </div>
            {/if}
          </div>

          <div class="cve-p30d3-section">
            <header class="cve-p30d3-section__head">
              <h2 class="cve-p30d3-section__title">Budget and content</h2>
              <p class="cve-p30d3-section__hint">Controls bundle size and body inclusion</p>
            </header>

            <div class="cve-p30d3-field-row">
              <div class="cve-p30d3-field">
                <label for="bundle-max-notes">Max notes ({BUNDLE_MAX_NOTES_MIN}-{BUNDLE_MAX_NOTES_LIMIT})</label>
                <input
                  id="bundle-max-notes"
                  type="number"
                  min={BUNDLE_MAX_NOTES_MIN}
                  max={BUNDLE_MAX_NOTES_LIMIT}
                  bind:value={cfg.maxNotes}
                  on:change={() => (cfg.maxNotes = clampMaxNotes(cfg.maxNotes))}
                  class="cve-input"
                />
              </div>
              <div class="cve-p30d3-field">
                <label for="bundle-max-chars">Max chars ({BUNDLE_MAX_CHARS_MIN}-{BUNDLE_MAX_CHARS_LIMIT})</label>
                <input
                  id="bundle-max-chars"
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
                  Status filter is set to partial; partial notes will be
                  included regardless of the checkbox above.
                </div>
              </div>
            {/if}
          </div>

          <div class="cve-p30d3-sticky-action">
            <button
              type="button"
              on:click={handleGenerate}
              disabled={!canSubmit}
              class="cve-btn cve-btn-primary"
              data-testid="bundle-generate-btn"
            >
              {submitState === 'loading' ? 'Generating...' : 'Generate preview'}
            </button>
            <span class="cve-p30d3-field__help">
              Preview is deterministic. Run multiple times to compare changes.
            </span>
          </div>
        </div>

        <!-- Right: state-aware output -->
        <div class="cve-p30d3-workflow">
          {#if submitState === 'idle' || (submitState === 'loading' && !bundleResult)}
            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">Readiness</h2>
                <p class="cve-p30d3-section__hint">
                  {submitState === 'loading' ? 'Generating...' : 'Pending generate'}
                </p>
              </header>
              <div class="cve-p30d3-readiness">
                <p class="cve-p30d3-readiness__title">Workflow stages</p>
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
                  <li class="cve-p30d3-stage--pending">Generate preview</li>
                  <li class="cve-p30d3-stage--pending">Review notes and budget</li>
                </ol>
                <p class="cve-p30d3-field__help">
                  Filters: {filtersSummary}. Sections: {cfg.includeSections.length}.
                  Budget: max_notes={clampMaxNotes(cfg.maxNotes)}, max_chars={clampMaxChars(cfg.maxChars)}.
                </p>
              </div>
            </div>
          {:else if submitState === 'error'}
            <div class="cve-banner cve-banner--danger">
              <div>
                <div class="cve-banner__title">{errorTitle(submitErrorCode)}</div>
                <div class="cve-banner__body">{submitError}</div>
              </div>
            </div>
          {:else if (submitState === 'ok' || submitState === 'loading') && bundleResult}
            {#if submitState === 'loading'}
              <div class="cve-banner cve-banner--info">
                <div class="cve-banner__body">Regenerating bundle preview...</div>
              </div>
            {/if}
            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">Bundle summary</h2>
                <p class="cve-p30d3-section__hint">Bundle id:
                  <code class="cve-p30d3-mono">{bundleResult.bundle_id}</code></p>
              </header>
              <div class="cve-status-strip">
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Notes selected</span>
                  <span class="cve-status-tile__value">{bundleResult.budget.note_count}</span>
                </div>
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Chars used</span>
                  <span class="cve-status-tile__value"
                    >{bundleResult.budget.used_chars} / {bundleResult.budget.max_chars}</span
                  >
                  <span class="cve-status-tile__hint"
                    >{pct(bundleResult.budget.used_chars, bundleResult.budget.max_chars)}% of budget</span
                  >
                </div>
                <div class="cve-status-tile" data-zero={!bundleResult.budget.truncated}>
                  <span class="cve-status-tile__label">Truncated</span>
                  <span class="cve-status-tile__value"
                    >{bundleResult.budget.truncated ? 'yes' : 'no'}</span
                  >
                </div>
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Validation</span>
                  <span class="cve-status-tile__value">{bundleResult.validation_status}</span>
                </div>
                <div class="cve-status-tile" data-zero={bundleResult.warnings.length === 0}>
                  <span class="cve-status-tile__label">Warnings</span>
                  <span class="cve-status-tile__value">{bundleResult.warnings.length}</span>
                </div>
              </div>

              <div class="cve-p30d3-progress" aria-hidden="true">
                <div
                  class="cve-p30d3-progress__fill"
                  class:cve-p30d3-progress__fill--warn={bundleResult.budget.truncated}
                  style="width:{pct(bundleResult.budget.used_chars, bundleResult.budget.max_chars)}%;"
                ></div>
              </div>

              {#if bundleResult.warnings.length > 0}
                <div class="cve-banner cve-banner--warning">
                  <div>
                    <div class="cve-banner__title">Warnings</div>
                    <ul class="cve-banner__body">
                      {#each bundleResult.warnings as w}
                        <li>{w}</li>
                      {/each}
                    </ul>
                  </div>
                </div>
              {/if}
            </div>

            <div class="cve-p30d3-section">
              <header class="cve-p30d3-section__head">
                <h2 class="cve-p30d3-section__title">
                  Notes ({bundleResult.notes.length})
                </h2>
                <p class="cve-p30d3-section__hint">Click a row to expand</p>
              </header>
              {#if bundleResult.notes.length === 0}
                <p class="cve-p30d3-empty">
                  No notes matched the filters. Try widening the filters or
                  including partial notes.
                </p>
              {:else}
                <ul class="cve-p30d3-item-list">
                  {#each bundleResult.notes as note}
                    <li class="cve-p30d3-item">
                      <button
                        type="button"
                        class="cve-btn cve-btn-ghost"
                        on:click={() => toggleNote(note.path)}
                        aria-expanded={expandedNoteIds.has(note.path)}
                      >
                        <div class="cve-p30d3-item__head">
                          <span class="cve-p30d3-tag cve-p30d3-tag--info">{note.fields?.status ?? 'unknown'}</span>
                          {#if note.fields?.domain}
                            <span class="cve-p30d3-tag">{note.fields.domain}</span>
                          {/if}
                          <strong>{noteTitle(note)}</strong>
                        </div>
                        <div class="cve-p30d3-item__path">{note.path}</div>
                      </button>
                      {#if expandedNoteIds.has(note.path)}
                        <hr class="cve-p30d3-divider" />
                        {#each Object.entries(note.sections) as [name, content]}
                          {#if content && content.trim().length > 0}
                            <div>
                              <p class="cve-p30d3-section__hint">{name}</p>
                              <pre
                                class="cve-p30d3-mono"
                                style="white-space:pre-wrap;">{content}</pre>
                            </div>
                          {/if}
                        {/each}
                        {#if note.body}
                          <div>
                            <p class="cve-p30d3-section__hint">Body</p>
                            <pre
                              class="cve-p30d3-mono"
                              style="white-space:pre-wrap;">{note.body}</pre>
                          </div>
                        {/if}
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>

            <details class="cve-details cve-details--inspector">
              <summary>Raw bundle JSON</summary>
              <div class="cve-details__body">
                <pre class="cve-raw">{JSON.stringify(
                    bundleResult,
                    null,
                    2,
                  )}</pre>
              </div>
            </details>

            <div class="cve-p30d3-followup">
              <a href="/app/exports">Package this configuration as an export</a>
              <a href="/app/security">Run security scan</a>
              <a href="/app/validation">Validation</a>
            </div>
          {/if}
        </div>
      </div>
    </section>
  {/if}
</div>
