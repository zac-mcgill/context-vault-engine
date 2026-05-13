<script lang="ts">
  /**
   * ImportReview.svelte - Phase 30D3
   *
   * State-aware Import workflow. Preview-first contract preserved from
   * Phase 26: vault, source path, destination, optional overwrite, dry-run
   * preview, explicit confirmation, then write. Markdown folder and
   * Obsidian vault are the only supported source types in this phase; no
   * new sources are introduced.
   *
   * Visual primitives:
   *   - cve-toolbar         sticky workflow header with state pill
   *   - cve-banner          info/warning/danger framing
   *   - cve-status-strip    readiness and outcome metrics
   *   - cve-details inspector + developer deep-link for raw response
   *
   * Every data-testid required by Phase 26 tests is preserved.
   */

  import { onMount } from 'svelte';
  import {
    fetchVaults,
    fetchNotes,
    fetchValidation,
    fetchTasks,
    fetchTrustSummary,
    importMarkdownFolder,
    importObsidianVault,
    isOk,
    buildNotesLink,
    type ImportMarkdownFolderRequest,
    type ImportMarkdownFolderResponse,
    type ImportMarkdownItem,
    type ImportObsidianVaultRequest,
    type ImportObsidianVaultResponse,
    type ImportObsidianItem,
    type NoteListItem,
    type TasksData,
    type TrustSummaryData,
    type ValidationData,
  } from '../lib/api.ts';
  import { getStoredVault } from '../lib/vaultState.ts';
  import ImportedReviewSummary from './ImportedReviewSummary.svelte';

  type SourceType = 'markdown-folder' | 'obsidian-vault';
  type OpState =
    | 'idle'
    | 'previewing'
    | 'preview_ok'
    | 'writing'
    | 'write_ok'
    | 'error';
  type ImportResponse = ImportMarkdownFolderResponse &
    Partial<ImportObsidianVaultResponse>;

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';

  let sourceType: SourceType = 'markdown-folder';
  let destinationTouched = false;
  let selectedVault = '';
  let sourceDir = '';
  let destination = 'Imported';
  let overwrite = false;

  let previewedVault = '';
  let previewedSourceType: SourceType = 'markdown-folder';
  let previewedSourceDir = '';
  let previewedDestination = '';
  let previewedOverwrite = false;

  let opState: OpState = 'idle';
  let opErrorCode = '';
  let opErrorMsg = '';

  let preview: ImportResponse | null = null;
  let writeResult: ImportResponse | null = null;

  let postWriteNotes: NoteListItem[] | null = null;
  let postWriteValidation: ValidationData | null = null;
  let postWriteTasks: TasksData | null = null;
  let postWriteTrust: TrustSummaryData | null = null;
  let postWriteLoading = false;

  let confirmReviewed = false;
  let expandedItem: number | null = null;

  function defaultDestinationForType(t: SourceType): string {
    return t === 'obsidian-vault' ? 'Imported/Obsidian' : 'Imported';
  }

  $: previewStale =
    preview !== null &&
    (selectedVault !== previewedVault ||
      sourceType !== previewedSourceType ||
      sourceDir.trim() !== previewedSourceDir ||
      destination.trim() !== previewedDestination ||
      overwrite !== previewedOverwrite);

  $: if (!destinationTouched) {
    destination = defaultDestinationForType(sourceType);
  }

  $: previewHasBlockers =
    preview !== null &&
    (preview.summary.errors > 0 || preview.summary.planned === 0);

  $: canPreview =
    selectedVault !== '' &&
    sourceDir.trim() !== '' &&
    destination.trim() !== '' &&
    opState !== 'previewing' &&
    opState !== 'writing';

  $: canWrite =
    preview !== null &&
    !previewStale &&
    !previewHasBlockers &&
    confirmReviewed &&
    opState !== 'previewing' &&
    opState !== 'writing';

  $: stateLabel =
    opState === 'previewing'
      ? 'Previewing'
      : opState === 'writing'
        ? 'Writing'
        : opState === 'write_ok'
          ? 'Write complete'
          : preview !== null && previewStale
            ? 'Preview stale'
            : preview !== null
              ? 'Preview ready'
              : opState === 'error'
                ? 'Error'
                : 'Preview not run';

  $: rawDeepLink = selectedVault
    ? `/app/raw?endpoint=import&vault=${encodeURIComponent(selectedVault)}&source=import`
    : '/app/raw?endpoint=import&source=import';

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

  function buildRequest(
    dryRun: boolean,
  ): ImportMarkdownFolderRequest | ImportObsidianVaultRequest {
    return {
      vault: selectedVault,
      source_dir: sourceDir.trim(),
      destination: destination.trim() || defaultDestinationForType(sourceType),
      dry_run: dryRun,
      overwrite,
    };
  }

  async function callImport(
    req: ImportMarkdownFolderRequest | ImportObsidianVaultRequest,
  ) {
    if (sourceType === 'obsidian-vault') {
      return await importObsidianVault(req as ImportObsidianVaultRequest);
    }
    return await importMarkdownFolder(req as ImportMarkdownFolderRequest);
  }

  async function handlePreview(): Promise<void> {
    if (!canPreview) return;
    opState = 'previewing';
    opErrorCode = '';
    opErrorMsg = '';
    writeResult = null;
    confirmReviewed = false;

    const result = await callImport(buildRequest(true));
    if (isOk(result)) {
      preview = result.data as ImportResponse;
      previewedVault = selectedVault;
      previewedSourceType = sourceType;
      previewedSourceDir = sourceDir.trim();
      previewedDestination = destination.trim();
      previewedOverwrite = overwrite;
      opState = 'preview_ok';
    } else {
      preview = null;
      opErrorCode = result.error?.code ?? 'UNKNOWN';
      opErrorMsg = result.error?.message ?? 'Preview failed.';
      opState = 'error';
    }
  }

  async function handleWrite(): Promise<void> {
    if (!canWrite) return;
    opState = 'writing';
    opErrorCode = '';
    opErrorMsg = '';
    const result = await callImport(buildRequest(false));
    if (isOk(result)) {
      writeResult = result.data as ImportResponse;
      opState = 'write_ok';
      await loadPostWriteData();
    } else {
      opErrorCode = result.error?.code ?? 'UNKNOWN';
      opErrorMsg = result.error?.message ?? 'Import failed.';
      opState = 'error';
    }
  }

  async function loadPostWriteData(): Promise<void> {
    if (!writeResult) return;
    postWriteLoading = true;
    postWriteNotes = null;
    postWriteValidation = null;
    postWriteTasks = null;
    postWriteTrust = null;
    const vault = writeResult.vault;
    const [nRes, vRes, tRes, trRes] = await Promise.all([
      fetchNotes(vault),
      fetchValidation(vault),
      fetchTasks(vault, { limit: 500, include_feedback: false }),
      fetchTrustSummary(vault),
    ]);
    if (isOk(nRes)) postWriteNotes = nRes.data.notes;
    if (isOk(vRes)) postWriteValidation = vRes.data;
    if (isOk(tRes)) postWriteTasks = tRes.data;
    if (isOk(trRes)) postWriteTrust = trRes.data;
    postWriteLoading = false;
  }

  function resetAll(): void {
    preview = null;
    writeResult = null;
    confirmReviewed = false;
    expandedItem = null;
    opState = 'idle';
    opErrorCode = '';
    opErrorMsg = '';
    postWriteNotes = null;
    postWriteValidation = null;
    postWriteTasks = null;
    postWriteTrust = null;
    postWriteLoading = false;
    destinationTouched = false;
    destination = defaultDestinationForType(sourceType);
  }

  function errorTitle(code: string): string {
    if (code === 'INVALID_VAULT') return 'Unknown vault';
    if (code === 'INVALID_SOURCE') return 'Source folder is not valid';
    if (code === 'UNSAFE_SOURCE') return 'Unsafe source folder';
    if (code === 'UNSAFE_DESTINATION') return 'Unsafe destination folder';
    if (code === 'IMPORT_FAILED') return 'Import failed';
    if (code === 'READ_ONLY') return 'Remote read-only mode';
    if (code === 'NETWORK_ERROR') return 'Backend unavailable';
    return 'Error';
  }

  function errorHelp(code: string): string {
    if (code === 'INVALID_SOURCE')
      return 'Check that the path exists on the machine running the backend, points to a folder, and does not contain null bytes.';
    if (code === 'UNSAFE_DESTINATION')
      return 'Destination must be vault-relative. It cannot be absolute, cannot contain "..", and cannot be inside Vault Files/.';
    if (code === 'UNSAFE_SOURCE')
      return 'The source folder must not be inside the target vault.';
    if (code === 'READ_ONLY')
      return 'Imports are disabled in remote read-only mode.';
    if (code === 'NETWORK_ERROR')
      return 'Could not reach the backend. Is the server running on the expected port?';
    return '';
  }

  function itemErrorLabel(code: string): string {
    if (code === 'READ_FAILED') return 'Could not read source file';
    if (code === 'SOURCE_TOO_LARGE') return 'Source file exceeds the 5 MB size cap';
    if (code === 'NULL_BYTE') return 'Source file contains a null byte and was blocked';
    if (code === 'INVALID_FRONTMATTER') return 'YAML frontmatter is malformed';
    if (code === 'FRONTMATTER_NOT_OBJECT') return 'YAML frontmatter is not a mapping';
    if (code === 'DUPLICATE_YAML_KEY') return 'YAML frontmatter has a duplicate key';
    if (code === 'DESTINATION_EXISTS')
      return 'A note already exists at the destination; re-run with overwrite to replace it';
    if (code === 'UNSAFE_DESTINATION') return 'Destination path is unsafe';
    if (code === 'SECURITY_FAIL') return 'Security scan blocked the import';
    if (code === 'VALIDATION_FAILED') return 'Validation rejected the imported note';
    if (code === 'SERIALISE_FAILED') return 'Could not serialise the imported note';
    if (code === 'WRITE_FAILED') return 'Filesystem write failed';
    return code;
  }

  function toggleItem(idx: number): void {
    expandedItem = expandedItem === idx ? null : idx;
  }

  function activeItems(resp: ImportResponse | null): (ImportMarkdownItem | ImportObsidianItem)[] {
    return resp?.items ?? [];
  }

  function blockedCount(resp: ImportResponse | null): number {
    if (!resp) return 0;
    return resp.items.filter((i) => i.status === 'blocked').length;
  }

  function hasCollisionErrors(resp: ImportResponse | null): boolean {
    if (!resp) return false;
    return resp.items.some((i) =>
      (i.errors ?? []).some((e) => e.code === 'DESTINATION_EXISTS'),
    );
  }

  function hasFrontmatterErrors(resp: ImportResponse | null): boolean {
    if (!resp) return false;
    return resp.items.some((i) =>
      (i.errors ?? []).some(
        (e) =>
          e.code === 'INVALID_FRONTMATTER' ||
          e.code === 'FRONTMATTER_NOT_OBJECT' ||
          e.code === 'DUPLICATE_YAML_KEY',
      ),
    );
  }

  function statusTagClass(status: string): string {
    if (status === 'written') return 'cve-p30d3-tag cve-p30d3-tag--written';
    if (status === 'planned') return 'cve-p30d3-tag cve-p30d3-tag--planned';
    if (status === 'skipped') return 'cve-p30d3-tag cve-p30d3-tag--skipped';
    if (status === 'blocked') return 'cve-p30d3-tag cve-p30d3-tag--blocked';
    if (status === 'error') return 'cve-p30d3-tag cve-p30d3-tag--error';
    return 'cve-p30d3-tag cve-p30d3-tag--neutral';
  }

  function securityTagClass(status: string): string {
    return securityClass(status);
  }

  function securityClass(status: string): string {
    if (status === 'pass') return 'cve-p30d3-tag cve-p30d3-tag--pass';
    if (status === 'warning') return 'cve-p30d3-tag cve-p30d3-tag--warning';
    if (status === 'fail') return 'cve-p30d3-tag cve-p30d3-tag--fail';
    return 'cve-p30d3-tag cve-p30d3-tag--neutral';
  }

  function validationTagClass(status: string): string {
    return validationClass(status);
  }

  function validationClass(status: string): string {
    if (status === 'pass') return 'cve-p30d3-tag cve-p30d3-tag--pass';
    if (status === 'fail') return 'cve-p30d3-tag cve-p30d3-tag--fail';
    return 'cve-p30d3-tag cve-p30d3-tag--neutral';
  }
</script>

<div class="cve-page">
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">Import Markdown Folder</h1>
      <div class="cve-toolbar__meta">
        <span
          class="cve-p30d3-toolbar-pill"
          class:cve-p30d3-toolbar-pill--ready={opState === 'preview_ok' && !previewStale}
          class:cve-p30d3-toolbar-pill--stale={previewStale}
          data-testid="import-state-pill"
        >
          {stateLabel}
        </span>
        {#if selectedVault}
          <span>Vault: <code class="cve-p30d3-mono">{selectedVault}</code></span>
        {/if}
      </div>
      <div class="cve-toolbar__actions">
        <a class="cve-details__developer-link" href={rawDeepLink}
          >Open in Developer</a
        >
      </div>
    </div>
  </header>

  {#if vaultsLoading}
    <div class="cve-banner cve-banner--info">
      <div class="cve-banner__body">Loading vaults...</div>
    </div>
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
          Use <a href="/app/vault-setup">Vault Setup</a> to create one before importing.
        </div>
      </div>
    </div>
  {:else}
    <section class="cve-p30d3-workflow">
      <div class="cve-banner cve-banner--info">
        <div class="cve-banner__body">
          Markdown folder import only - Import is a preview-first, write-second
          workflow. Markdown folder and Obsidian vault are supported. No PDF,
          no GitHub repo, no browser article, no chat transcript, no semantic,
          and no LLM-extraction imports yet; those sources are deferred to
          later phases. Source paths resolve on the backend host.
        </div>
      </div>

      <div class="cve-p30d3-twocol">
        <div class="cve-p30d3-section">
          <header class="cve-p30d3-section__head">
            <h2 class="cve-p30d3-section__title">Source</h2>
            <p class="cve-p30d3-section__hint">Step 1 of 3</p>
          </header>

          <div class="cve-p30d3-field">
            <label for="import-source-type">Source type</label>
            <select
              id="import-source-type"
              data-testid="source-type-select"
              bind:value={sourceType}
              disabled={opState === 'previewing' || opState === 'writing'}
              class="cve-input"
            >
              <option value="markdown-folder">Markdown folder</option>
              <option value="obsidian-vault">Obsidian vault</option>
            </select>
            <p class="cve-p30d3-field__help" data-testid="source-type-help">
              {#if sourceType === 'obsidian-vault'}
                Source path must be the Obsidian vault folder on the backend
                host. The <code class="cve-p30d3-mono">.obsidian/</code> config
                folder is skipped. Markdown notes are imported; binary
                attachments are not imported. Wikilinks are preserved verbatim
                and reported as metadata.
              {:else}
                Plain Markdown folder import. Recursively discovers
                <code class="cve-p30d3-mono">.md</code> files; non-Markdown
                files are ignored. Obsidian wikilinks are preserved verbatim
                if any are present; binary attachments are not imported.
              {/if}
            </p>
          </div>

          <div class="cve-p30d3-field">
            <label for="import-vault">Vault</label>
            <select
              id="import-vault"
              bind:value={selectedVault}
              disabled={opState === 'previewing' || opState === 'writing'}
              class="cve-input"
            >
              {#each vaultList as v}
                <option value={v}>{v}</option>
              {/each}
            </select>
          </div>

          <div class="cve-p30d3-field">
            <label for="import-source">Source folder path (server-local)</label>
            <input
              id="import-source"
              type="text"
              bind:value={sourceDir}
              placeholder="C:\path\to\markdown-folder"
              disabled={opState === 'previewing' || opState === 'writing'}
              class="cve-input cve-p30d3-mono"
            />
            <p class="cve-p30d3-field__help">
              Resolved on the backend host. Browsers cannot pick server
              filesystem folders, so type or paste the path here.
            </p>
          </div>

          <div class="cve-p30d3-field">
            <label for="import-destination">Destination folder (vault-relative)</label>
            <input
              id="import-destination"
              type="text"
              bind:value={destination}
              on:input={() => (destinationTouched = true)}
              placeholder={defaultDestinationForType(sourceType)}
              disabled={opState === 'previewing' || opState === 'writing'}
              class="cve-input cve-p30d3-mono"
            />
            <p class="cve-p30d3-field__help">
              Defaults to
              <code class="cve-p30d3-mono">{defaultDestinationForType(sourceType)}</code>.
              Cannot be absolute, cannot contain
              <code class="cve-p30d3-mono">..</code>, and cannot live inside
              <code class="cve-p30d3-mono">Vault Files/</code>.
            </p>
          </div>

          <label class="cve-p30d3-checkbox">
            <input
              type="checkbox"
              bind:checked={overwrite}
              disabled={opState === 'previewing' || opState === 'writing'}
            />
            <span>
              Overwrite existing files at destination paths.
              <span class="cve-p30d3-field__help">
                By default, existing files are skipped. Imported notes are
                marked as imported/draft via trust metadata when the schema
                supports it.
              </span>
            </span>
          </label>

          <div class="cve-p30d3-sticky-action">
            <button
              type="button"
              on:click={handlePreview}
              disabled={!canPreview}
              class="cve-btn cve-btn-primary"
              data-testid="import-preview-btn"
            >
              {opState === 'previewing' ? 'Previewing...' : 'Preview import (dry-run)'}
            </button>
            <button
              type="button"
              on:click={resetAll}
              disabled={opState === 'previewing' || opState === 'writing'}
              class="cve-btn cve-btn-ghost"
            >
              Reset
            </button>
          </div>
        </div>

        <div class="cve-p30d3-section">
          <header class="cve-p30d3-section__head">
            <h2 class="cve-p30d3-section__title">Readiness</h2>
            <p class="cve-p30d3-section__hint">Step 2 of 3</p>
          </header>

          {#if preview === null && writeResult === null}
            <div class="cve-p30d3-readiness">
              <p class="cve-p30d3-readiness__title">Workflow stages</p>
              <ol class="cve-p30d3-stage-list">
                <li class="cve-p30d3-stage--pending">Choose source, vault, destination</li>
                <li class="cve-p30d3-stage--pending">Run a dry-run preview</li>
                <li class="cve-p30d3-stage--pending">Review items and confirm</li>
                <li class="cve-p30d3-stage--pending">Write</li>
              </ol>
              <p class="cve-p30d3-field__help">
                Write is only available after a successful preview with no
                blocking errors and explicit confirmation.
              </p>
            </div>
          {:else}
            {@const display = writeResult ?? preview}
            <div class="cve-status-strip">
              <div class="cve-status-tile">
                <span class="cve-status-tile__label">Discovered</span>
                <span class="cve-status-tile__value">{display?.summary.discovered ?? 0}</span>
              </div>
              <div class="cve-status-tile" data-zero={(display?.summary.planned ?? 0) === 0}>
                <span class="cve-status-tile__label">Planned</span>
                <span class="cve-status-tile__value">{display?.summary.planned ?? 0}</span>
              </div>
              <div class="cve-status-tile" data-zero={(display?.summary.written ?? 0) === 0}>
                <span class="cve-status-tile__label">Written</span>
                <span class="cve-status-tile__value">{display?.summary.written ?? 0}</span>
              </div>
              <div class="cve-status-tile" data-zero={(display?.summary.skipped ?? 0) === 0}>
                <span class="cve-status-tile__label">Skipped</span>
                <span class="cve-status-tile__value">{display?.summary.skipped ?? 0}</span>
              </div>
              <div class="cve-status-tile" data-zero={blockedCount(display) === 0}>
                <span class="cve-status-tile__label">Blocked</span>
                <span class="cve-status-tile__value">{blockedCount(display)}</span>
              </div>
              <div class="cve-status-tile" data-zero={(display?.summary.errors ?? 0) === 0}>
                <span class="cve-status-tile__label">Errors</span>
                <span class="cve-status-tile__value">{display?.summary.errors ?? 0}</span>
              </div>
              <div class="cve-status-tile" data-zero={(display?.summary.warnings ?? 0) === 0}>
                <span class="cve-status-tile__label">Warnings</span>
                <span class="cve-status-tile__value">{display?.summary.warnings ?? 0}</span>
              </div>
              {#if (display?.summary as any)?.wikilinks !== undefined}
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Wikilinks</span>
                  <span class="cve-status-tile__value" data-testid="summary-wikilinks"
                    >{(display?.summary as any).wikilinks}</span
                  >
                </div>
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Embeds</span>
                  <span class="cve-status-tile__value" data-testid="summary-embeds"
                    >{(display?.summary as any).embeds ?? 0}</span
                  >
                </div>
                <div class="cve-status-tile">
                  <span class="cve-status-tile__label">Attachment refs</span>
                  <span class="cve-status-tile__value" data-testid="summary-attachments"
                    >{(display?.summary as any).attachment_refs ?? 0}</span
                  >
                </div>
              {/if}
            </div>

            <dl class="cve-p30d3-summary-kv">
              <dt>Vault</dt>
              <dd class="cve-p30d3-mono">{display?.vault}</dd>
              <dt>Source folder</dt>
              <dd class="cve-p30d3-mono">{display?.source_dir}</dd>
              <dt>Destination folder</dt>
              <dd class="cve-p30d3-mono">{display?.destination}</dd>
              <dt>Mode</dt>
              <dd>{display?.dry_run ? 'dry-run' : 'write'}</dd>
            </dl>
          {/if}
        </div>
      </div>

      {#if preview !== null && writeResult === null}
        <div
          class="cve-p30d3-section"
          class:cve-p30d3-section--warning={previewStale || previewHasBlockers}
        >
          <header class="cve-p30d3-section__head">
            <h2 class="cve-p30d3-section__title">Confirm and write</h2>
            <p class="cve-p30d3-section__hint">Step 3 of 3</p>
          </header>

          <div class="cve-p30d3-confirm-block">
            <label class="cve-p30d3-checkbox">
              <input
                type="checkbox"
                bind:checked={confirmReviewed}
                disabled={previewStale || previewHasBlockers || opState === 'writing'}
                data-testid="import-confirm-checkbox"
              />
              <span>I have reviewed the import preview and want to write these files. Write requires a successful preview and explicit confirmation.</span>
            </label>

            {#if previewStale}
              <div class="cve-banner cve-banner--warning" data-testid="import-stale-banner">
                <div class="cve-banner__body">
                  Preview is stale because source folder, vault, destination,
                  or overwrite changed. Re-run preview before writing.
                </div>
              </div>
            {:else if previewHasBlockers}
              <div class="cve-banner cve-banner--danger" data-testid="import-blocked-banner">
                <div class="cve-banner__body">
                  Preview has blocking errors or zero planned writes. Resolve
                  them before writing.
                </div>
              </div>
            {/if}

            <div class="cve-p30d3-action-row">
              <button
                type="button"
                on:click={handleWrite}
                disabled={!canWrite}
                class="cve-btn cve-btn-primary cve-p30d3-btn-success"
                data-testid="import-write-btn"
              >
                {opState === 'writing' ? 'Writing...' : 'Write import'}
              </button>
              <span class="cve-p30d3-field__help">
                Write is disabled until preview is fresh and confirmation is
                checked.
              </span>
            </div>
          </div>
        </div>
      {/if}

      {#if opState === 'error'}
        <div class="cve-banner cve-banner--danger">
          <div>
            <div class="cve-banner__title">{errorTitle(opErrorCode)}</div>
            <div class="cve-banner__body">{opErrorMsg}</div>
            {#if errorHelp(opErrorCode)}
              <div class="cve-p30d3-field__help">{errorHelp(opErrorCode)}</div>
            {/if}
          </div>
        </div>
      {/if}

      {#if preview !== null || writeResult !== null}
        {@const display = writeResult ?? preview}
        <div class="cve-p30d3-section">
          <header class="cve-p30d3-section__head">
            <h2 class="cve-p30d3-section__title">
              Items ({activeItems(display).length})
            </h2>
            <p class="cve-p30d3-section__hint">
              {writeResult ? 'Write outcome per file' : 'Preview outcome per file'}
            </p>
          </header>

          {#if hasCollisionErrors(display)}
            <div class="cve-banner cve-banner--warning" data-testid="collision-banner">
              <div class="cve-banner__body">
                One or more items would overwrite existing notes (code
                <code class="cve-p30d3-mono">DESTINATION_EXISTS</code>). Re-run
                with overwrite enabled to replace them, or rename the source
                file to import alongside the existing note.
              </div>
            </div>
          {/if}
          {#if hasFrontmatterErrors(display)}
            <div class="cve-banner cve-banner--warning" data-testid="frontmatter-banner">
              <div class="cve-banner__body">
                One or more items had malformed YAML frontmatter and were
                blocked at the item level. The rest of the batch was processed
                normally.
              </div>
            </div>
          {/if}

          {#if activeItems(display).length === 0}
            <p class="cve-p30d3-empty" data-testid="empty-items-message">
              No Markdown files were discovered in the source folder. Confirm
              that the folder contains files with the
              <code class="cve-p30d3-mono">.md</code> extension and that the
              path is correct on the backend host. Non-Markdown files are
              intentionally ignored.
            </p>
          {:else}
            <ul class="cve-p30d3-item-list">
              {#each activeItems(display) as item, idx}
                <li class="cve-p30d3-item">
                  <button
                    type="button"
                    class="cve-btn cve-btn-ghost"
                    on:click={() => toggleItem(idx)}
                    aria-expanded={expandedItem === idx}
                  >
                    <div class="cve-p30d3-item__head">
                      <span class={statusTagClass(item.status)}>{item.status}</span>
                      <span class={securityTagClass(item.security?.status ?? '')}
                        >security: {item.security?.status ?? 'unknown'}</span
                      >
                      <span class={validationTagClass(item.validation?.status ?? '')}
                        >validation: {item.validation?.status ?? 'unknown'}</span
                      >
                      <span>action: {item.action}</span>
                      {#if item.warnings.length > 0}
                        <span class="cve-p30d3-tag cve-p30d3-tag--warning"
                          >{item.warnings.length} warning{item.warnings.length === 1
                            ? ''
                            : 's'}</span
                        >
                      {/if}
                      {#if item.errors.length > 0}
                        <span class="cve-p30d3-tag cve-p30d3-tag--error"
                          >{item.errors.length} error{item.errors.length === 1 ? '' : 's'}</span
                        >
                      {/if}
                    </div>
                    <div class="cve-p30d3-item__path">{item.source_path}</div>
                    <div class="cve-p30d3-item__dest">
                      to {item.destination_path || '(no destination)'}
                    </div>
                  </button>

                  {#if expandedItem === idx}
                    <hr class="cve-p30d3-divider" />
                    {#if item.warnings.length > 0}
                      <div>
                        <p class="cve-p30d3-section__hint">Warnings</p>
                        <ul>
                          {#each item.warnings as w}
                            <li>{w}</li>
                          {/each}
                        </ul>
                      </div>
                    {/if}
                    {#if item.errors.length > 0}
                      <div>
                        <p class="cve-p30d3-section__hint">Errors</p>
                        <ul data-testid="item-errors">
                          {#each item.errors as e}
                            <li>
                              <code class="cve-p30d3-mono">{e.code}</code>
                              {' - '}{itemErrorLabel(e.code)}
                              <span class="cve-p30d3-field__help">({e.message})</span>
                            </li>
                          {/each}
                        </ul>
                      </div>
                    {/if}
                    {#if item.security?.findings?.length}
                      <div>
                        <p class="cve-p30d3-section__hint">Security findings</p>
                        <ul>
                          {#each item.security.findings as f}
                            <li>
                              <code class="cve-p30d3-mono">{f.rule ?? 'rule'}</code>
                              ({f.severity ?? 'severity'}) {' - '}{f.detail ?? ''}
                            </li>
                          {/each}
                        </ul>
                      </div>
                    {/if}
                    {#if item.validation?.errors?.length}
                      <div>
                        <p class="cve-p30d3-section__hint">Validation errors</p>
                        <ul>
                          {#each item.validation.errors as ve}
                            <li>{ve}</li>
                          {/each}
                        </ul>
                      </div>
                    {/if}
                    {#if (item as ImportObsidianItem).obsidian_metadata}
                      {@const om = (item as ImportObsidianItem).obsidian_metadata}
                      <div data-testid="obsidian-metadata">
                        <p class="cve-p30d3-section__hint">Obsidian metadata</p>
                        <dl class="cve-p30d3-summary-kv">
                          <dt>Wikilinks</dt>
                          <dd>{om?.wikilinks ?? 0}</dd>
                          <dt>Embeds</dt>
                          <dd>{om?.embeds ?? 0}</dd>
                          <dt>Attachment refs</dt>
                          <dd>{om?.attachment_refs ?? 0}</dd>
                        </dl>
                      </div>
                    {/if}
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
        </div>

        <details class="cve-details cve-details--inspector">
          <summary>Raw response</summary>
          <div class="cve-details__body">
            <a class="cve-details__developer-link" href={rawDeepLink}
              >Open in Developer</a
            >
            <pre class="cve-p30d3-mono" style="white-space:pre-wrap;">{JSON.stringify(
                display,
                null,
                2,
              )}</pre>
          </div>
        </details>
      {/if}

      {#if writeResult !== null}
        <div class="cve-p30d3-section">
          <header class="cve-p30d3-section__head">
            <h2 class="cve-p30d3-section__title">Follow-up</h2>
            <p class="cve-p30d3-section__hint">Imported notes are marked
              <code class="cve-p30d3-mono">source_type: imported</code></p>
          </header>
          <nav class="cve-p30d3-followup">
            <a href={buildNotesLink({ vault: writeResult.vault, filter: 'imported' })}
              >Notes (imported only)</a
            >
            <a href={buildNotesLink({ vault: writeResult.vault, filter: 'draft' })}
              >Notes (draft trust)</a
            >
            <a href="/app/validation">Validation</a>
            <a href="/app/tasks">Tasks</a>
            <a href="/app/trust">Trust and evidence</a>
            <a href="/app/security">Security</a>
            <a href="/app/">Dashboard</a>
          </nav>

          <ImportedReviewSummary
            vault={writeResult.vault}
            notes={postWriteNotes}
            validation={postWriteValidation}
            tasks={postWriteTasks}
            trust={postWriteTrust}
          />
          {#if postWriteLoading}
            <p class="cve-p30d3-field__help">Loading post-import review data...</p>
          {/if}
        </div>
      {/if}
    </section>
  {/if}
</div>
