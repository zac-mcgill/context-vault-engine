<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchVaults,
    fetchFeedback,
    createFeedback,
    updateFeedback,
    deleteFeedback,
    normaliseFeedback,
    fetchTasks,
    isOk,
    type FeedbackEntry,
    type FeedbackSource,
    type FeedbackSignal,
    type FeedbackSeverity,
    type Task,
  } from '../lib/api.ts';
  import { getStoredVault } from '../lib/vaultState.ts';
  import {
    buildRawDeepLink,
    severityWeight,
    isResolvedSignal,
  } from '../lib/phase30e1.ts';

  type LoadState = 'idle' | 'loading' | 'ok' | 'error';

  // ---------------------------------------------------------------------------
  // Vault state
  // ---------------------------------------------------------------------------

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';
  let selectedVault = '';

  // ---------------------------------------------------------------------------
  // Feedback + tasks state
  // ---------------------------------------------------------------------------

  let feedbackState: LoadState = 'idle';
  let entries: FeedbackEntry[] = [];
  let feedbackError = '';
  let feedbackWarnings: string[] = [];

  let tasksState: LoadState = 'idle';
  let tasks: Task[] = [];
  let tasksError = '';

  // ---------------------------------------------------------------------------
  // Filters
  // ---------------------------------------------------------------------------

  let filterSeverity: '' | FeedbackSeverity = '';
  let filterSignal: '' | string = '';
  let filterSource: '' | FeedbackSource = '';
  let filterText = '';
  let filterResolved: 'all' | 'open' | 'resolved' = 'open';

  // ---------------------------------------------------------------------------
  // Add slide-over
  // ---------------------------------------------------------------------------

  let addOpen = false;
  let addPath = '';
  let addSource: FeedbackSource = 'human';
  let addSignal: FeedbackSignal = 'unclear';
  let addSeverity: FeedbackSeverity = 'medium';
  let addComment = '';
  let addState: LoadState = 'idle';
  let addError = '';

  // ---------------------------------------------------------------------------
  // Edit / delete inline state
  // ---------------------------------------------------------------------------

  let editingId: string | null = null;
  let editPath = '';
  let editSource: FeedbackSource = 'human';
  let editSignal: FeedbackSignal = 'unclear';
  let editSeverity: FeedbackSeverity = 'medium';
  let editComment = '';
  let editState: LoadState = 'idle';
  let editError = '';

  let normaliseState: LoadState = 'idle';
  let normaliseError = '';

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
    if (selectedVault) await loadAll();
  });

  async function loadAll() {
    if (!selectedVault) return;
    feedbackState = 'loading';
    tasksState = 'loading';
    entries = [];
    tasks = [];
    feedbackError = '';
    tasksError = '';
    feedbackWarnings = [];

    const [fr, tr] = await Promise.all([
      fetchFeedback(selectedVault),
      fetchTasks(selectedVault, { include_feedback: true }),
    ]);

    if (isOk(fr)) {
      entries = fr.data.entries;
      feedbackWarnings = fr.data.warnings;
      feedbackState = 'ok';
    } else {
      feedbackError = fr.error?.message ?? 'Failed to load feedback';
      feedbackState = 'error';
    }

    if (isOk(tr)) {
      tasks = tr.data.tasks;
      tasksState = 'ok';
    } else {
      tasksError = tr.error?.message ?? 'Failed to load tasks';
      tasksState = 'error';
    }
  }

  function handleVaultChange() {
    if (selectedVault) loadAll();
  }

  async function submitAdd() {
    if (!selectedVault || !addPath.trim() || !addComment.trim()) return;
    addState = 'loading';
    addError = '';
    const resp = await createFeedback({
      vault: selectedVault,
      path: addPath.trim(),
      source: addSource,
      signal: addSignal,
      severity: addSeverity,
      comment: addComment.trim(),
    });
    if (!isOk(resp)) {
      addState = 'error';
      addError = resp.error?.message ?? 'Failed to add feedback';
      return;
    }
    addState = 'ok';
    addPath = '';
    addComment = '';
    addOpen = false;
    entries = resp.data.feedback.entries;
  }

  function startEdit(entry: FeedbackEntry) {
    editingId = entry.id ?? null;
    editPath = entry.path;
    editSource = (entry.source as FeedbackSource) ?? 'human';
    editSignal = (entry.signal as FeedbackSignal) ?? 'unclear';
    editSeverity = (entry.severity as FeedbackSeverity) ?? 'medium';
    editComment = entry.comment;
    editState = 'idle';
    editError = '';
  }

  function cancelEdit() {
    editingId = null;
    editError = '';
  }

  async function submitEdit() {
    if (!editingId) return;
    editState = 'loading';
    editError = '';
    const resp = await updateFeedback(editingId, {
      vault: selectedVault,
      path: editPath,
      source: editSource,
      signal: editSignal,
      severity: editSeverity,
      comment: editComment,
    });
    if (!isOk(resp)) {
      editState = 'error';
      editError = resp.error?.message ?? 'Failed to update feedback';
      return;
    }
    editState = 'ok';
    editingId = null;
    entries = resp.data.feedback.entries;
  }

  async function submitDelete(entry: FeedbackEntry) {
    if (!entry.id) return;
    const ok = window.confirm(`Delete feedback for "${entry.path}"?`);
    if (!ok) return;
    const resp = await deleteFeedback(entry.id, selectedVault);
    if (!isOk(resp)) {
      feedbackError = resp.error?.message ?? 'Failed to delete feedback';
      feedbackState = 'error';
      return;
    }
    entries = resp.data.feedback.entries;
  }

  async function runNormalise() {
    normaliseState = 'loading';
    normaliseError = '';
    const resp = await normaliseFeedback(selectedVault);
    if (!isOk(resp)) {
      normaliseState = 'error';
      normaliseError = resp.error?.message ?? 'Failed to normalise feedback';
      return;
    }
    normaliseState = 'ok';
    entries = resp.data.feedback.entries;
  }

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  $: rawDeepLink = buildRawDeepLink('feedback', selectedVault, 'feedback');

  $: counts = (() => {
    const c = {
      total: entries.length,
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
      resolved: 0,
      open: 0,
      tasks: tasks.length,
      feedback_adjusted: 0,
    };
    for (const e of entries) {
      if (e.severity === 'critical') c.critical += 1;
      else if (e.severity === 'high') c.high += 1;
      else if (e.severity === 'medium') c.medium += 1;
      else if (e.severity === 'low') c.low += 1;
      if (isResolvedSignal(String(e.signal))) c.resolved += 1;
      else c.open += 1;
    }
    for (const t of tasks) {
      if (t.feedback_weight) c.feedback_adjusted += 1;
    }
    return c;
  })();

  $: filteredEntries = (() => {
    let rows = entries.slice();
    if (filterSeverity) rows = rows.filter((e) => e.severity === filterSeverity);
    if (filterSignal) rows = rows.filter((e) => e.signal === filterSignal);
    if (filterSource) rows = rows.filter((e) => e.source === filterSource);
    if (filterResolved === 'open') rows = rows.filter((e) => !isResolvedSignal(String(e.signal)));
    if (filterResolved === 'resolved') rows = rows.filter((e) => isResolvedSignal(String(e.signal)));
    const q = filterText.trim().toLowerCase();
    if (q) rows = rows.filter((e) => e.path.toLowerCase().includes(q) || e.comment.toLowerCase().includes(q));

    // Deterministic sort: severity first (severityWeight), then open before resolved, then path.
    rows.sort((a, b) => {
      const wa = severityWeight(String(a.severity));
      const wb = severityWeight(String(b.severity));
      if (wa !== wb) return wa - wb;
      const ra = isResolvedSignal(String(a.signal)) ? 1 : 0;
      const rb = isResolvedSignal(String(b.signal)) ? 1 : 0;
      if (ra !== rb) return ra - rb;
      if (a.path < b.path) return -1;
      if (a.path > b.path) return 1;
      return 0;
    });
    return rows;
  })();

  $: banner = (() => {
    if (feedbackState === 'error') {
      return { severity: 'danger' as const, title: 'Could not load feedback', body: feedbackError };
    }
    if (counts.critical > 0) {
      return {
        severity: 'danger' as const,
        title: `${counts.critical} critical feedback entries`,
        body: 'Critical entries should be triaged before relying on this vault.',
      };
    }
    if (counts.high > 0) {
      return {
        severity: 'warning' as const,
        title: `${counts.high} high-severity feedback entries`,
        body: 'High-severity entries indicate notes that may be unreliable.',
      };
    }
    if (feedbackState === 'ok' && entries.length === 0) {
      return {
        severity: 'info' as const,
        title: 'No feedback entries',
        body: 'No human, agent, or system feedback has been logged for this vault.',
      };
    }
    return null;
  })();

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function severityTag(s: string): string {
    if (s === 'critical') return 'cve-p30e1-tag cve-p30e1-tag--critical';
    if (s === 'high') return 'cve-p30e1-tag cve-p30e1-tag--high';
    if (s === 'medium') return 'cve-p30e1-tag cve-p30e1-tag--medium';
    if (s === 'low') return 'cve-p30e1-tag cve-p30e1-tag--low';
    return 'cve-p30e1-tag';
  }

  function signalTag(sig: string): string {
    if (isResolvedSignal(sig)) return 'cve-p30e1-tag cve-p30e1-tag--resolved';
    return 'cve-p30e1-tag cve-p30e1-tag--pending';
  }

  function notesLink(path: string): string {
    const params = new URLSearchParams();
    if (selectedVault) params.set('vault', selectedVault);
    params.set('path', path);
    return `/app/notes?${params.toString()}`;
  }

  function tasksLink(): string {
    const params = new URLSearchParams();
    if (selectedVault) params.set('vault', selectedVault);
    return `/app/tasks?${params.toString()}`;
  }

  function validationLink(): string {
    const params = new URLSearchParams();
    if (selectedVault) params.set('vault', selectedVault);
    return `/app/validation?${params.toString()}`;
  }

  function fmtDate(iso: string | undefined): string {
    if (!iso) return '-';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }
</script>

<div class="cve-page cve-p30e1-page cve-page--fill">

  <!-- Toolbar -->
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">Feedback Triage</h1>
      <div class="cve-toolbar__meta">
        <span
          class="cve-p30e1-pill"
          class:cve-p30e1-pill--pending={counts.open > 0}
          data-testid="feedback-state-pill"
        >{counts.open} open</span>
        {#if selectedVault}
          <span>Vault: <code class="cve-p30e1-mono">{selectedVault}</code></span>
        {/if}
        <span>Tasks: {counts.tasks}</span>
      </div>
      <div class="cve-toolbar__actions">
        {#if vaultList.length > 1}
          <label class="cve-label cve-p30e1-inline-label" for="feedback-vault-select">Vault</label>
          <select
            id="feedback-vault-select"
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
          class="cve-btn cve-btn-primary"
          data-testid="feedback-add-action"
          on:click={() => { addOpen = true; addState = 'idle'; addError = ''; }}
          disabled={!selectedVault}
        >Add Feedback</button>
        <button
          type="button"
          class="cve-btn cve-btn-secondary"
          on:click={loadAll}
          disabled={!selectedVault || feedbackState === 'loading'}
          aria-label="Refresh feedback"
        >
          {feedbackState === 'loading' ? 'Refreshing' : 'Refresh'}
        </button>
        <button
          type="button"
          class="cve-btn cve-btn-ghost"
          on:click={runNormalise}
          disabled={!selectedVault || normaliseState === 'loading'}
        >
          {normaliseState === 'loading' ? 'Normalising' : 'Normalise IDs'}
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

    {#if banner}
      <section
        class="cve-banner cve-banner--{banner.severity}"
        role="status"
        aria-live="polite"
      >
        <div>
          <div class="cve-banner__title">{banner.title}</div>
          <div class="cve-banner__body">{banner.body}</div>
        </div>
      </section>
    {/if}

    {#if feedbackWarnings.length > 0}
      <section class="cve-banner cve-banner--warning" role="status">
        <div>
          <div class="cve-banner__title">Feedback warnings</div>
          <ul class="cve-banner__body">
            {#each feedbackWarnings as w}<li>{w}</li>{/each}
          </ul>
        </div>
      </section>
    {/if}

    {#if normaliseState === 'error'}
      <div class="cve-banner cve-banner--danger"><div><div class="cve-banner__body">{normaliseError}</div></div></div>
    {/if}

    <!-- Status strip -->
    <div class="cve-status-strip" aria-label="Feedback summary">
      <div class="cve-status-tile" data-zero={counts.total === 0}>
        <span class="cve-status-tile__label">Total</span>
        <span class="cve-status-tile__value">{counts.total}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.critical === 0}>
        <span class="cve-status-tile__label">Critical</span>
        <span class="cve-status-tile__value">{counts.critical}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.high === 0}>
        <span class="cve-status-tile__label">High</span>
        <span class="cve-status-tile__value">{counts.high}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.open === 0}>
        <span class="cve-status-tile__label">Open</span>
        <span class="cve-status-tile__value">{counts.open}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.resolved === 0}>
        <span class="cve-status-tile__label">Resolved</span>
        <span class="cve-status-tile__value">{counts.resolved}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.tasks === 0}>
        <span class="cve-status-tile__label">Tasks</span>
        <span class="cve-status-tile__value">{counts.tasks}</span>
      </div>
      <div class="cve-status-tile" data-zero={counts.feedback_adjusted === 0}>
        <span class="cve-status-tile__label">Feedback-adjusted</span>
        <span class="cve-status-tile__value">{counts.feedback_adjusted}</span>
      </div>
    </div>

    <!-- Workbench: triage table + tasks panel -->
    <div class="cve-workbench cve-workbench--bounded">

      <section class="cve-workbench__rail cve-p30e1-rail" aria-label="Feedback triage queue">

        <div class="cve-p30e1-rail__head">
          <div class="cve-p30e1-filter-row" role="group" aria-label="Feedback filters">
            <div class="cve-field">
              <label class="cve-label" for="feedback-filter-severity">Severity</label>
              <select id="feedback-filter-severity" class="cve-select" bind:value={filterSeverity}>
                <option value="">All</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
            <div class="cve-field">
              <label class="cve-label" for="feedback-filter-signal">Signal</label>
              <select id="feedback-filter-signal" class="cve-select" bind:value={filterSignal}>
                <option value="">All</option>
                <option value="unclear">unclear</option>
                <option value="incomplete">incomplete</option>
                <option value="outdated">outdated</option>
                <option value="incorrect">incorrect</option>
                <option value="agent_failed">agent_failed</option>
                <option value="needs_example">needs_example</option>
                <option value="needs_constraints">needs_constraints</option>
                <option value="useful">useful</option>
                <option value="agent_succeeded">agent_succeeded</option>
              </select>
            </div>
            <div class="cve-field">
              <label class="cve-label" for="feedback-filter-source">Source</label>
              <select id="feedback-filter-source" class="cve-select" bind:value={filterSource}>
                <option value="">All</option>
                <option value="human">human</option>
                <option value="agent">agent</option>
                <option value="system">system</option>
              </select>
            </div>
            <div class="cve-field">
              <label class="cve-label" for="feedback-filter-resolved">State</label>
              <select id="feedback-filter-resolved" class="cve-select" bind:value={filterResolved}>
                <option value="open">Open</option>
                <option value="resolved">Resolved</option>
                <option value="all">All</option>
              </select>
            </div>
            <div class="cve-field">
              <label class="cve-label" for="feedback-filter-text">Search</label>
              <input
                id="feedback-filter-text"
                class="cve-input"
                type="search"
                bind:value={filterText}
                placeholder="path or comment"
              />
            </div>
          </div>
        </div>

        <div class="cve-p30e1-rail__body" data-testid="feedback-triage-scroll">
          {#if feedbackState === 'loading'}
            <div class="cve-loading">Loading feedback...</div>
          {:else if filteredEntries.length === 0}
            <div class="cve-empty">No feedback matches the current filters.</div>
          {:else}
            <div class="cve-table-wrap">
              <table class="cve-table" data-testid="feedback-triage-table">
                <thead>
                  <tr>
                    <th scope="col">Severity</th>
                    <th scope="col">Signal</th>
                    <th scope="col">Source</th>
                    <th scope="col">Path</th>
                    <th scope="col">Comment</th>
                    <th scope="col">Created</th>
                    <th scope="col">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {#each filteredEntries as entry (entry.id ?? entry.path + entry.created_at)}
                    {#if editingId && entry.id === editingId}
                      <tr>
                        <td colspan="7">
                          <div class="cve-p30e1-edit-form" role="form" aria-label="Edit feedback entry">
                            <div class="cve-p30e1-filter-row">
                              <div class="cve-field">
                                <label class="cve-label" for="edit-path">Path</label>
                                <input id="edit-path" class="cve-input" bind:value={editPath} />
                              </div>
                              <div class="cve-field">
                                <label class="cve-label" for="edit-source">Source</label>
                                <select id="edit-source" class="cve-select" bind:value={editSource}>
                                  <option value="human">human</option>
                                  <option value="agent">agent</option>
                                  <option value="system">system</option>
                                </select>
                              </div>
                              <div class="cve-field">
                                <label class="cve-label" for="edit-signal">Signal</label>
                                <select id="edit-signal" class="cve-select" bind:value={editSignal}>
                                  <option value="unclear">unclear</option>
                                  <option value="incomplete">incomplete</option>
                                  <option value="outdated">outdated</option>
                                  <option value="incorrect">incorrect</option>
                                  <option value="agent_failed">agent_failed</option>
                                  <option value="needs_example">needs_example</option>
                                  <option value="needs_constraints">needs_constraints</option>
                                  <option value="useful">useful</option>
                                  <option value="agent_succeeded">agent_succeeded</option>
                                </select>
                              </div>
                              <div class="cve-field">
                                <label class="cve-label" for="edit-severity">Severity</label>
                                <select id="edit-severity" class="cve-select" bind:value={editSeverity}>
                                  <option value="critical">critical</option>
                                  <option value="high">high</option>
                                  <option value="medium">medium</option>
                                  <option value="low">low</option>
                                </select>
                              </div>
                            </div>
                            <div class="cve-field">
                              <label class="cve-label" for="edit-comment">Comment</label>
                              <textarea id="edit-comment" class="cve-textarea" bind:value={editComment} rows="3"></textarea>
                            </div>
                            {#if editState === 'error'}
                              <div class="cve-error">{editError}</div>
                            {/if}
                            <div class="cve-p30e1-action-row">
                              <button type="button" class="cve-btn cve-btn-primary" on:click={submitEdit} disabled={editState === 'loading'}>
                                {editState === 'loading' ? 'Saving' : 'Save'}
                              </button>
                              <button type="button" class="cve-btn cve-btn-ghost" on:click={cancelEdit}>Cancel</button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    {:else}
                      <tr>
                        <td><span class={severityTag(String(entry.severity))}>{entry.severity}</span></td>
                        <td><span class={signalTag(String(entry.signal))}>{entry.signal}</span></td>
                        <td>{entry.source}</td>
                        <td><a class="cve-link" href={notesLink(entry.path)}><code class="cve-p30e1-mono">{entry.path}</code></a></td>
                        <td>{entry.comment}</td>
                        <td>{fmtDate(entry.created_at)}</td>
                        <td>
                          <button type="button" class="cve-btn cve-btn-ghost cve-p30e1-row-btn" on:click={() => startEdit(entry)} disabled={!entry.id}>Edit</button>
                          <button type="button" class="cve-btn cve-btn-ghost cve-p30e1-row-btn" on:click={() => submitDelete(entry)} disabled={!entry.id}>Delete</button>
                          <a class="cve-link cve-p30e1-row-link" href={tasksLink()}>Tasks</a>
                          <a class="cve-link cve-p30e1-row-link" href={validationLink()}>Validation</a>
                        </td>
                      </tr>
                    {/if}
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      </section>

      <!-- Tasks side panel (never empty) -->
      <aside class="cve-workbench__inspector cve-p30e1-side-panel" aria-label="Related tasks" data-testid="feedback-tasks-panel">
        <header class="cve-p30e1-inspector__head">
          <h2 class="cve-p30e1-section__title">Related tasks</h2>
          <p class="cve-helper">
            Highest-priority improvement tasks for this vault. Feedback-adjusted
            tasks include a score delta from related feedback entries.
          </p>
        </header>
        <div class="cve-p30e1-rail__body">
          {#if tasksState === 'loading'}
            <div class="cve-loading">Loading tasks...</div>
          {:else if tasksState === 'error'}
            <div class="cve-error">{tasksError}</div>
          {:else if tasks.length === 0}
            <p class="cve-empty">
              No improvement tasks are pending for this vault. Run
              <a class="cve-link" href={tasksLink()}>Tasks</a> to refresh, or
              add Feedback to surface new tasks.
            </p>
          {:else}
            <ul class="cve-p30e1-task-list" role="list">
              {#each tasks.slice(0, 10) as t (t.path + t.target)}
                <li class="cve-p30e1-task">
                  <div class="cve-p30e1-task__head">
                    <span class="cve-p30e1-tag">priority {t.priority}</span>
                    <span class="cve-p30e1-tag cve-p30e1-tag--pending">{t.type}</span>
                    {#if t.feedback_weight}
                      <span class="cve-p30e1-tag cve-p30e1-tag--high">feedback delta {t.feedback_weight.score_delta}</span>
                    {/if}
                  </div>
                  <a class="cve-link" href={notesLink(t.path)}><code class="cve-p30e1-mono">{t.path}</code></a>
                  <p class="cve-helper">{t.instruction}</p>
                </li>
              {/each}
            </ul>
            <p class="cve-helper">
              See <a class="cve-link" href={tasksLink()}>Tasks</a> for the full
              list.
            </p>
          {/if}
        </div>

        <!-- Raw deep-link -->
        <details class="cve-details cve-details--inspector">
          <summary>Raw feedback response</summary>
          <div class="cve-details__body">
            <p class="cve-helper">
              The raw feedback JSON is intentionally not shown inline here.
              Use the Developer link in the toolbar to open the full payload at /app/raw.
            </p>
          </div>
        </details>
      </aside>
    </div>

  {/if}

  <!-- Add Feedback slide-over -->
  <div
    class="cve-slide-over"
    data-open={addOpen}
    data-testid="feedback-add-slide-over"
    aria-hidden={!addOpen}
  >
    <div class="cve-slide-over__backdrop" on:click={() => (addOpen = false)} role="presentation"></div>
    <aside class="cve-slide-over__panel" role="dialog" aria-modal="true" aria-labelledby="feedback-add-title">
      <header class="cve-slide-over__header">
        <h2 id="feedback-add-title">Add Feedback</h2>
        <button type="button" class="cve-btn cve-btn-ghost" on:click={() => (addOpen = false)} aria-label="Close add feedback">Close</button>
      </header>
      <div class="cve-slide-over__body">
        <div class="cve-field">
          <label class="cve-label" for="add-path">Note path</label>
          <input id="add-path" class="cve-input" bind:value={addPath} placeholder="Fundamentals/Algorithms.md" />
        </div>
        <div class="cve-field">
          <label class="cve-label" for="add-source">Source</label>
          <select id="add-source" class="cve-select" bind:value={addSource}>
            <option value="human">human</option>
            <option value="agent">agent</option>
            <option value="system">system</option>
          </select>
        </div>
        <div class="cve-field">
          <label class="cve-label" for="add-signal">Signal</label>
          <select id="add-signal" class="cve-select" bind:value={addSignal}>
            <option value="unclear">unclear</option>
            <option value="incomplete">incomplete</option>
            <option value="outdated">outdated</option>
            <option value="incorrect">incorrect</option>
            <option value="agent_failed">agent_failed</option>
            <option value="needs_example">needs_example</option>
            <option value="needs_constraints">needs_constraints</option>
            <option value="useful">useful</option>
            <option value="agent_succeeded">agent_succeeded</option>
          </select>
        </div>
        <div class="cve-field">
          <label class="cve-label" for="add-severity">Severity</label>
          <select id="add-severity" class="cve-select" bind:value={addSeverity}>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </div>
        <div class="cve-field">
          <label class="cve-label" for="add-comment">Comment</label>
          <textarea id="add-comment" class="cve-textarea" bind:value={addComment} rows="4"></textarea>
        </div>
        {#if addState === 'error'}
          <div class="cve-banner cve-banner--danger"><div><div class="cve-banner__body">{addError}</div></div></div>
        {/if}
      </div>
      <footer class="cve-slide-over__footer">
        <button type="button" class="cve-btn cve-btn-ghost" on:click={() => (addOpen = false)}>Cancel</button>
        <button
          type="button"
          class="cve-btn cve-btn-primary"
          on:click={submitAdd}
          disabled={addState === 'loading' || !addPath.trim() || !addComment.trim()}
        >
          {addState === 'loading' ? 'Adding' : 'Add Feedback'}
        </button>
      </footer>
    </aside>
  </div>

</div>
