<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchVaults,
    fetchTrustSummary,
    fetchStaleSummary,
    buildEvidence,
    isOk,
    type TrustSummaryData,
    type StaleSummaryData,
    type EvidenceData,
    type TrustNoteSummary,
  } from '../lib/api.ts';
  import { getStoredVault } from '../lib/vaultState.ts';
  import { buildRawDeepLink } from '../lib/phase30e1.ts';

  type LoadState = 'idle' | 'loading' | 'ok' | 'error';

  // ---------------------------------------------------------------------------
  // Vault state
  // ---------------------------------------------------------------------------

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';
  let selectedVault = '';

  // ---------------------------------------------------------------------------
  // Trust + stale state
  // ---------------------------------------------------------------------------

  let trustState: LoadState = 'idle';
  let trustData: TrustSummaryData | null = null;
  let trustError = '';

  let staleState: LoadState = 'idle';
  let staleData: StaleSummaryData | null = null;
  let staleError = '';

  // ---------------------------------------------------------------------------
  // Evidence Builder (demoted)
  // ---------------------------------------------------------------------------

  let evidenceQuery = '';
  let evidencePreferVerified = true;
  let evidenceIncludeDeprecated = false;
  let evidenceIncludeStale = true;
  let evidenceMaxNotes = 20;

  let evidenceState: LoadState = 'idle';
  let evidenceData: EvidenceData | null = null;
  let evidenceError = '';

  // ---------------------------------------------------------------------------
  // Filtering for governance queue
  // ---------------------------------------------------------------------------

  type GovernanceCategory = 'deprecated' | 'stale' | 'freshness_unknown' | 'low_trust';

  interface GovernanceRow {
    category: GovernanceCategory;
    severity: number;
    path: string;
    trust_level: string | null;
    confidence: string;
    review_after: string | null;
    last_reviewed: string | null;
    trust_score: number;
  }

  let filterCategory: '' | GovernanceCategory = '';
  let filterText = '';

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onMount(async () => {
    const stored = getStoredVault();
    const resp = await fetchVaults();
    vaultsLoading = false;
    if (!isOk(resp)) {
      vaultsError = resp.error?.message ?? 'Failed to load vaults';
      return;
    }
    vaultList = resp.data.vaults;
    selectedVault = stored && vaultList.includes(stored) ? stored : (vaultList[0] ?? '');
    if (selectedVault) await loadTrustData();
  });

  async function loadTrustData() {
    if (!selectedVault) return;
    trustState = 'loading';
    staleState = 'loading';
    trustData = null;
    staleData = null;
    trustError = '';
    staleError = '';

    const [tr, sr] = await Promise.all([
      fetchTrustSummary(selectedVault),
      fetchStaleSummary(selectedVault),
    ]);

    if (isOk(tr)) {
      trustData = tr.data;
      trustState = 'ok';
    } else {
      trustError = tr.error?.message ?? 'Failed to load trust summary';
      trustState = 'error';
    }
    if (isOk(sr)) {
      staleData = sr.data;
      staleState = 'ok';
    } else {
      staleError = sr.error?.message ?? 'Failed to load stale notes';
      staleState = 'error';
    }
  }

  async function runBuildEvidence() {
    if (!selectedVault) return;
    evidenceState = 'loading';
    evidenceData = null;
    evidenceError = '';

    const resp = await buildEvidence({
      vault: selectedVault,
      q: evidenceQuery.trim() || undefined,
      prefer_verified: evidencePreferVerified,
      include_deprecated: evidenceIncludeDeprecated,
      include_stale: evidenceIncludeStale,
      max_notes: evidenceMaxNotes,
    });

    if (isOk(resp)) {
      evidenceData = resp.data;
      evidenceState = 'ok';
    } else {
      evidenceError = resp.error?.message ?? 'Failed to build evidence';
      evidenceState = 'error';
    }
  }

  function handleVaultChange() {
    trustData = null;
    staleData = null;
    evidenceData = null;
    trustState = 'idle';
    staleState = 'idle';
    evidenceState = 'idle';
    if (selectedVault) loadTrustData();
  }

  // ---------------------------------------------------------------------------
  // Derived governance queue
  // ---------------------------------------------------------------------------

  $: rawDeepLink = buildRawDeepLink('trust', selectedVault, 'trust');

  $: governanceRows = (() => {
    if (!trustData || !staleData) return [] as GovernanceRow[];

    const rows: GovernanceRow[] = [];
    const seen = new Set<string>();

    const push = (note: TrustNoteSummary, category: GovernanceCategory, severity: number) => {
      const key = `${category}::${note.path}`;
      if (seen.has(key)) return;
      seen.add(key);
      rows.push({
        category,
        severity,
        path: note.path,
        trust_level: note.trust_level,
        confidence: note.confidence,
        review_after: note.review_after,
        last_reviewed: note.last_reviewed,
        trust_score: note.trust_score,
      });
    };

    for (const n of staleData.deprecated) push(n, 'deprecated', 0);
    for (const n of staleData.stale) push(n, 'stale', 1);
    for (const n of staleData.freshness_unknown) push(n, 'freshness_unknown', 2);
    for (const n of trustData.notes) {
      if (n.confidence === 'low' || n.trust_level === 'draft') {
        push(n, 'low_trust', 3);
      }
    }

    // Deterministic sort: severity ascending (0 first), then path.
    rows.sort((a, b) => {
      if (a.severity !== b.severity) return a.severity - b.severity;
      if (a.path < b.path) return -1;
      if (a.path > b.path) return 1;
      return 0;
    });
    return rows;
  })();

  $: filteredRows = (() => {
    let rows = governanceRows;
    if (filterCategory) rows = rows.filter((r) => r.category === filterCategory);
    const q = filterText.trim().toLowerCase();
    if (q) rows = rows.filter((r) => r.path.toLowerCase().includes(q));
    return rows;
  })();

  $: counts = (() => {
    const c = {
      total: trustData?.total_notes ?? 0,
      stale: trustData?.stale_count ?? staleData?.stale.length ?? 0,
      deprecated: trustData?.deprecated_count ?? staleData?.deprecated.length ?? 0,
      missing: trustData?.missing_trust_metadata ?? 0,
      low_trust: 0,
      draft: 0,
    };
    if (trustData) {
      for (const n of trustData.notes) {
        if (n.confidence === 'low') c.low_trust += 1;
        if (n.trust_level === 'draft') c.draft += 1;
      }
    }
    return c;
  })();

  $: governanceBanner = (() => {
    if (trustState === 'error') {
      return { severity: 'danger' as const, title: 'Could not load trust summary', body: trustError };
    }
    if (staleState === 'error') {
      return { severity: 'danger' as const, title: 'Could not load stale summary', body: staleError };
    }
    if (counts.deprecated > 0 || counts.stale > 0 || counts.low_trust > 0) {
      const parts: string[] = [];
      if (counts.deprecated > 0) parts.push(`${counts.deprecated} deprecated`);
      if (counts.stale > 0) parts.push(`${counts.stale} stale`);
      if (counts.low_trust > 0) parts.push(`${counts.low_trust} low-trust`);
      return {
        severity: 'warning' as const,
        title: 'Governance attention needed',
        body: parts.join(', ') + '. Review and update before relying on this vault.',
      };
    }
    if (counts.missing > 0) {
      return {
        severity: 'info' as const,
        title: 'Trust metadata gaps',
        body: `${counts.missing} note(s) have no trust metadata. Confidence falls back to 'unknown'.`,
      };
    }
    if (trustState === 'ok' && staleState === 'ok') {
      return {
        severity: 'success' as const,
        title: 'Governance clean',
        body: 'No deprecated, stale, or low-trust notes detected.',
      };
    }
    return null;
  })();

  // ---------------------------------------------------------------------------
  // Per-row links
  // ---------------------------------------------------------------------------

  function notesLink(path: string): string {
    const params = new URLSearchParams();
    if (selectedVault) params.set('vault', selectedVault);
    params.set('path', path);
    return `/app/notes?${params.toString()}`;
  }

  function feedbackLink(): string {
    const params = new URLSearchParams();
    if (selectedVault) params.set('vault', selectedVault);
    return `/app/feedback?${params.toString()}`;
  }

  function pendingLink(): string {
    const params = new URLSearchParams();
    if (selectedVault) params.set('vault', selectedVault);
    return `/app/pending?${params.toString()}`;
  }

  function categoryLabel(c: GovernanceCategory): string {
    if (c === 'deprecated') return 'Deprecated';
    if (c === 'stale') return 'Stale';
    if (c === 'freshness_unknown') return 'Freshness unknown';
    if (c === 'low_trust') return 'Low trust';
    return c;
  }

  function categoryTag(c: GovernanceCategory): string {
    if (c === 'deprecated') return 'cve-p30e1-tag cve-p30e1-tag--invalid';
    if (c === 'stale') return 'cve-p30e1-tag cve-p30e1-tag--rejected';
    if (c === 'freshness_unknown') return 'cve-p30e1-tag cve-p30e1-tag--pending';
    return 'cve-p30e1-tag';
  }
</script>

<div class="cve-page cve-p30e1-page">

  <!-- Toolbar -->
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">Trust and Governance</h1>
      <div class="cve-toolbar__meta">
        <span
          class="cve-p30e1-pill"
          class:cve-p30e1-pill--pending={counts.deprecated > 0 || counts.stale > 0 || counts.low_trust > 0}
          data-testid="trust-state-pill"
        >{counts.stale + counts.deprecated + counts.low_trust} flagged</span>
        {#if selectedVault}
          <span>Vault: <code class="cve-p30e1-mono">{selectedVault}</code></span>
        {/if}
        <span>Total notes: {counts.total}</span>
      </div>
      <div class="cve-toolbar__actions">
        {#if vaultList.length > 1}
          <label class="cve-label cve-p30e1-inline-label" for="trust-vault-select">Vault</label>
          <select
            id="trust-vault-select"
            class="cve-select cve-p30e1-inline-select"
            bind:value={selectedVault}
            on:change={handleVaultChange}
            aria-label="Active vault"
          >
            {#each vaultList as v}
              <option value={v}>{v}</option>
            {/each}
          </select>
        {/if}
        <button
          type="button"
          class="cve-btn cve-btn-secondary"
          on:click={loadTrustData}
          disabled={!selectedVault || trustState === 'loading'}
          aria-label="Refresh trust summary"
        >
          {trustState === 'loading' ? 'Refreshing' : 'Refresh'}
        </button>
        <a class="cve-details__developer-link" href={rawDeepLink}>Open in Developer</a>
      </div>
    </div>
  </header>

  <!-- Vault load states -->
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
          Use <a class="cve-link" href="/app/vault-setup">Vault Setup</a> to create one.
        </div>
      </div>
    </div>
  {:else}

    <!-- Trust disclaimer (kept prominent above all queues) -->
    <div class="cve-trust-warning" data-testid="trust-disclaimer">
      <strong>Trust metadata is informational.</strong> It reflects review
      and maintenance state. It does not prove factual correctness of any
      note content.
    </div>

    {#if governanceBanner}
      <section
        class="cve-banner cve-banner--{governanceBanner.severity}"
        role="status"
        aria-live="polite"
      >
        <div>
          <div class="cve-banner__title">{governanceBanner.title}</div>
          <div class="cve-banner__body">{governanceBanner.body}</div>
        </div>
      </section>
    {/if}

    <!-- Status strip -->
    <div class="cve-status-strip" aria-label="Trust summary">
      <div class="cve-status-tile" data-zero={counts.total === 0}>
        <span class="cve-status-tile__label">Total notes</span>
        <span class="cve-status-tile__value">{counts.total}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.stale === 0}>
        <span class="cve-status-tile__label">Stale</span>
        <span class="cve-status-tile__value">{counts.stale}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.low_trust === 0}>
        <span class="cve-status-tile__label">Low trust</span>
        <span class="cve-status-tile__value">{counts.low_trust}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.draft === 0}>
        <span class="cve-status-tile__label">Draft</span>
        <span class="cve-status-tile__value">{counts.draft}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.deprecated === 0}>
        <span class="cve-status-tile__label">Deprecated</span>
        <span class="cve-status-tile__value">{counts.deprecated}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.missing === 0}>
        <span class="cve-status-tile__label">Missing metadata</span>
        <span class="cve-status-tile__value">{counts.missing}</span>
      </div>
    </div>

    <!-- Two-column governance layout -->
    <div class="cve-p30e1-twocol">

      <!-- Main: governance queue (leads the page) -->
      <section class="cve-p30e1-main" aria-labelledby="trust-queue-head">
        <header class="cve-p30e1-section__head">
          <h2 id="trust-queue-head" class="cve-p30e1-section__title">Stale and low-trust queue</h2>
          <p class="cve-helper">
            Notes that need governance attention. Rows link to Notes for
            inspection, Pending for related write proposals, and Feedback
            for triage.
          </p>
        </header>

        <div class="cve-p30e1-filter-row" role="group" aria-label="Governance queue filters">
          <div class="cve-field">
            <label class="cve-label" for="trust-filter-category">Category</label>
            <select
              id="trust-filter-category"
              class="cve-select"
              bind:value={filterCategory}
            >
              <option value="">All categories</option>
              <option value="deprecated">Deprecated</option>
              <option value="stale">Stale</option>
              <option value="freshness_unknown">Freshness unknown</option>
              <option value="low_trust">Low trust</option>
            </select>
          </div>
          <div class="cve-field">
            <label class="cve-label" for="trust-filter-text">Search path</label>
            <input
              id="trust-filter-text"
              class="cve-input"
              type="search"
              bind:value={filterText}
              placeholder="e.g. Fundamentals/"
            />
          </div>
        </div>

        {#if trustState === 'loading' || staleState === 'loading'}
          <div class="cve-loading">Loading governance queue...</div>
        {:else if filteredRows.length === 0}
          <div class="cve-empty">
            No notes match the current governance filters.
          </div>
        {:else}
          <div class="cve-table-wrap cve-p30e1-queue-table-wrap">
            <table class="cve-table" data-testid="trust-governance-table">
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">Path</th>
                  <th scope="col">Trust</th>
                  <th scope="col">Confidence</th>
                  <th scope="col">Review after</th>
                  <th scope="col">Last reviewed</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {#each filteredRows as row (row.category + '::' + row.path)}
                  <tr>
                    <td><span class={categoryTag(row.category)}>{categoryLabel(row.category)}</span></td>
                    <td><code class="cve-p30e1-mono">{row.path}</code></td>
                    <td>{row.trust_level ?? '-'}</td>
                    <td>{row.confidence}</td>
                    <td>{row.review_after ?? '-'}</td>
                    <td>{row.last_reviewed ?? '-'}</td>
                    <td>
                      <a class="cve-link cve-p30e1-row-link" href={notesLink(row.path)} data-testid="trust-row-notes">Notes</a>
                      <a class="cve-link cve-p30e1-row-link" href={pendingLink()} data-testid="trust-row-pending">Pending</a>
                      <a class="cve-link cve-p30e1-row-link" href={feedbackLink()} data-testid="trust-row-feedback">Feedback</a>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </section>

      <!-- Secondary: trust breakdown + demoted evidence builder -->
      <aside class="cve-p30e1-aside" aria-labelledby="trust-breakdown-head">

        <section aria-labelledby="trust-breakdown-head">
          <h2 id="trust-breakdown-head" class="cve-p30e1-section__title">Trust breakdown</h2>
          {#if trustData}
            <ul class="cve-p30e1-kv-list">
              {#each Object.entries(trustData.by_trust_level) as [level, count]}
                <li><span>{level}</span><span class="cve-p30e1-mono">{count}</span></li>
              {/each}
            </ul>
            <h3 class="cve-p30e1-section__subtitle">By confidence</h3>
            <ul class="cve-p30e1-kv-list">
              {#each Object.entries(trustData.by_confidence) as [conf, count]}
                <li><span>{conf}</span><span class="cve-p30e1-mono">{count}</span></li>
              {/each}
            </ul>
          {:else}
            <p class="cve-helper">Trust breakdown loads with the governance queue.</p>
          {/if}
        </section>

        <!-- Demoted Evidence Builder -->
        <details class="cve-details cve-p30e1-evidence-disclosure" data-testid="trust-evidence-builder">
          <summary>Evidence Builder (secondary)</summary>
          <div class="cve-details__body">
            <p class="cve-helper">
              Build a trust-ranked evidence response from this vault. Notes
              are sorted by trust score when prefer_verified is on. This
              tool is secondary to the governance queue above.
            </p>

            <div class="cve-field">
              <label class="cve-label" for="ev-query">Query (optional)</label>
              <input
                id="ev-query"
                class="cve-input"
                type="search"
                bind:value={evidenceQuery}
                placeholder="e.g. sorting algorithms"
              />
            </div>
            <div class="cve-field">
              <label class="cve-label" for="ev-max-notes">Max notes</label>
              <input
                id="ev-max-notes"
                class="cve-input"
                type="number"
                min="1"
                max="100"
                bind:value={evidenceMaxNotes}
              />
            </div>
            <div class="cve-p30e1-checkbox-row">
              <label class="cve-p30e1-checkbox">
                <input type="checkbox" bind:checked={evidencePreferVerified} />
                <span>Prefer verified</span>
              </label>
              <label class="cve-p30e1-checkbox">
                <input type="checkbox" bind:checked={evidenceIncludeStale} />
                <span>Include stale</span>
              </label>
              <label class="cve-p30e1-checkbox">
                <input type="checkbox" bind:checked={evidenceIncludeDeprecated} />
                <span>Include deprecated</span>
              </label>
            </div>
            <button
              type="button"
              class="cve-btn cve-btn-secondary"
              on:click={runBuildEvidence}
              disabled={!selectedVault || evidenceState === 'loading'}
            >
              {evidenceState === 'loading' ? 'Building...' : 'Build evidence'}
            </button>

            {#if evidenceState === 'error'}
              <div class="cve-banner cve-banner--danger" role="alert">
                <div><div class="cve-banner__body">{evidenceError}</div></div>
              </div>
            {/if}
            {#if evidenceState === 'ok' && evidenceData}
              <p class="cve-helper">
                {evidenceData.summary.total_notes} note(s) returned.
                {evidenceData.confidence_disclaimer}
              </p>
              <ul class="cve-p30e1-kv-list">
                {#each evidenceData.evidence.slice(0, 5) as note}
                  <li>
                    <a class="cve-link" href={notesLink(note.path)}>{note.path}</a>
                    <span class="cve-p30e1-mono">{note.confidence}</span>
                  </li>
                {/each}
              </ul>
              {#if evidenceData.evidence.length > 5}
                <p class="cve-helper">
                  Showing 5 of {evidenceData.evidence.length}. Full payload via
                  <a class="cve-link" href={buildRawDeepLink('evidence', selectedVault, 'trust-evidence')}
                    >/app/raw</a>.
                </p>
              {/if}
            {/if}
          </div>
        </details>

        <!-- Developer raw deep-link -->
        <details class="cve-details cve-details--inspector">
          <summary>Raw trust response</summary>
          <div class="cve-details__body">
            <p class="cve-helper">
              The raw trust JSON is intentionally not shown inline here. Open
              the full payload in the Developer route:
            </p>
            <a class="cve-details__developer-link" href={rawDeepLink}
              >Open this vault in /app/raw</a>
          </div>
        </details>

      </aside>
    </div>

  {/if}

</div>
