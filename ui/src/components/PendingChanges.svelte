<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchVaults,
    listPendingChanges,
    getPendingChange,
    acceptPendingChange,
    rejectPendingChange,
    isOk,
    type PendingChange,
    type PendingChangesData,
    type PendingChangeData,
  } from '../lib/api.ts';
  import { getStoredVault } from '../lib/vaultState.ts';

  // ---------------------------------------------------------------------------
  // Vault state
  // ---------------------------------------------------------------------------

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';
  let selectedVault = '';

  // ---------------------------------------------------------------------------
  // Pending changes list state
  // ---------------------------------------------------------------------------

  type LoadState = 'idle' | 'loading' | 'ok' | 'error';

  let listState: LoadState = 'idle';
  let changes: PendingChange[] = [];
  let listError = '';
  let filterStatus = 'pending';
  let filterLimit = 50;

  // ---------------------------------------------------------------------------
  // Detail state
  // ---------------------------------------------------------------------------

  let selectedChange: PendingChange | null = null;
  let detailState: LoadState = 'idle';
  let detailError = '';
  let showRawJson = false;

  // ---------------------------------------------------------------------------
  // Accept / Reject form state
  // ---------------------------------------------------------------------------

  type ActionState = 'idle' | 'loading' | 'ok' | 'error';
  let actionState: ActionState = 'idle';
  let actionError = '';
  let actionErrorCode = '';
  let reviewerInput = '';
  let auditNoteInput = '';
  let showAcceptConfirm = false;
  let showRejectConfirm = false;

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
    if (selectedVault) await loadChanges();
  });

  // ---------------------------------------------------------------------------
  // Load list
  // ---------------------------------------------------------------------------

  async function loadChanges() {
    if (!selectedVault) return;
    listState = 'loading';
    listError = '';
    changes = [];
    selectedChange = null;
    const statusArg = filterStatus === 'all' ? undefined : filterStatus;
    const resp = await listPendingChanges(selectedVault, statusArg, filterLimit);
    if (!isOk(resp)) {
      listState = 'error';
      listError = resp.error?.message ?? 'Failed to load pending changes';
      return;
    }
    changes = resp.data.changes;
    listState = 'ok';
  }

  async function selectChange(change: PendingChange) {
    selectedChange = change;
    showRawJson = false;
    actionState = 'idle';
    actionError = '';
    actionErrorCode = '';
    showAcceptConfirm = false;
    showRejectConfirm = false;
    reviewerInput = '';
    auditNoteInput = '';

    // Reload full detail from server for freshest data
    detailState = 'loading';
    const resp = await getPendingChange(selectedVault, change.id);
    if (!isOk(resp)) {
      detailState = 'error';
      detailError = resp.error?.message ?? 'Failed to load change detail';
      return;
    }
    selectedChange = resp.data.change;
    detailState = 'ok';
  }

  // ---------------------------------------------------------------------------
  // Accept
  // ---------------------------------------------------------------------------

  async function submitAccept() {
    if (!selectedChange) return;
    actionState = 'loading';
    actionError = '';
    actionErrorCode = '';
    const resp = await acceptPendingChange(
      selectedVault,
      selectedChange.id,
      reviewerInput || undefined,
      auditNoteInput || undefined,
    );
    if (!isOk(resp)) {
      actionState = 'error';
      actionError = resp.error?.message ?? 'Failed to accept change';
      actionErrorCode = resp.error?.code ?? '';
      showAcceptConfirm = false;
      return;
    }
    actionState = 'ok';
    selectedChange = resp.data.change;
    showAcceptConfirm = false;
    await loadChanges();
  }

  // ---------------------------------------------------------------------------
  // Reject
  // ---------------------------------------------------------------------------

  async function submitReject() {
    if (!selectedChange) return;
    actionState = 'loading';
    actionError = '';
    actionErrorCode = '';
    const resp = await rejectPendingChange(
      selectedVault,
      selectedChange.id,
      reviewerInput || undefined,
      auditNoteInput || undefined,
    );
    if (!isOk(resp)) {
      actionState = 'error';
      actionError = resp.error?.message ?? 'Failed to reject change';
      actionErrorCode = resp.error?.code ?? '';
      showRejectConfirm = false;
      return;
    }
    actionState = 'ok';
    selectedChange = resp.data.change;
    showRejectConfirm = false;
    await loadChanges();
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function statusBadgeClass(status: string): string {
    switch (status) {
      case 'pending': return 'bg-amber-900/40 text-amber-300 border border-amber-700/50';
      case 'accepted': return 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/50';
      case 'rejected': return 'bg-zinc-700/40 text-zinc-400 border border-zinc-600/50';
      case 'invalid': return 'bg-red-900/40 text-red-300 border border-red-700/50';
      default: return 'bg-zinc-800 text-zinc-400';
    }
  }

  function validationBadgeClass(vs: string): string {
    switch (vs) {
      case 'pass': return 'text-emerald-400';
      case 'fail': return 'text-red-400';
      case 'not_checked': return 'text-zinc-500';
      default: return 'text-zinc-500';
    }
  }

  function typeBadge(type: string): string {
    switch (type) {
      case 'create_note_draft': return 'CREATE';
      case 'suggest_note_update': return 'UPDATE';
      case 'update_note_section_draft': return 'SECTION';
      default: return type.toUpperCase();
    }
  }

  function diffLineClass(line: string): string {
    if (line.startsWith('+') && !line.startsWith('+++')) return 'bg-emerald-950/50 text-emerald-300';
    if (line.startsWith('-') && !line.startsWith('---')) return 'bg-red-950/50 text-red-300';
    if (line.startsWith('@@')) return 'text-sky-400 bg-sky-950/30';
    return 'text-zinc-400';
  }

  function formatDate(iso: string | null): string {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }
</script>

<!-- ── Page ─────────────────────────────────────────────────────────────── -->
<div class="cve-page space-y-6">

  <!-- Header -->
  <div class="cve-page-header flex items-center justify-between">
    <div>
      <h1 class="cve-page-title text-xl font-semibold text-zinc-100">Pending Changes</h1>
      <p class="mt-1 text-sm text-zinc-400">
        Review LLM-proposed note changes before they are written to the vault.
        Nothing is applied without explicit acceptance.
      </p>
    </div>
  </div>

  <!-- Vault selector + filter bar -->
  {#if vaultsLoading}
    <p class="text-sm text-zinc-500">Loading vaults…</p>
  {:else if vaultsError}
    <p class="text-sm text-red-400">{vaultsError}</p>
  {:else}
    <div class="flex flex-wrap gap-3 items-end">
      <div class="flex flex-col gap-1">
        <label for="vault-select" class="text-xs text-zinc-400">Vault</label>
        <select
          id="vault-select"
          bind:value={selectedVault}
          on:change={loadChanges}
          class="bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          {#each vaultList as v}
            <option value={v}>{v}</option>
          {/each}
        </select>
      </div>

      <div class="flex flex-col gap-1">
        <label for="status-filter" class="text-xs text-zinc-400">Status</label>
        <select
          id="status-filter"
          bind:value={filterStatus}
          on:change={loadChanges}
          class="bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
        >
          <option value="pending">Pending</option>
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      <button
        on:click={loadChanges}
        class="px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-700 rounded text-zinc-200 hover:bg-zinc-700 transition-colors"
      >
        Refresh
      </button>
    </div>
  {/if}

  <!-- Main layout: list + detail -->
  <div class="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">

    <!-- Change list -->
    <div class="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div class="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <span class="text-sm font-medium text-zinc-300">Changes</span>
        {#if listState === 'ok'}
          <span class="text-xs text-zinc-500">{changes.length} result{changes.length !== 1 ? 's' : ''}</span>
        {/if}
      </div>

      {#if listState === 'loading'}
        <div class="cve-loading p-4 text-sm text-zinc-500">Loading…</div>
      {:else if listState === 'error'}
        <div class="cve-error p-4 text-sm text-red-400">{listError}</div>
      {:else if listState === 'ok' && changes.length === 0}
        <div class="cve-empty p-4 text-sm text-zinc-500">No changes found.</div>
      {:else if listState === 'ok'}
        <ul class="cve-list divide-y divide-zinc-800 max-h-[600px] overflow-y-auto">
          {#each changes as ch}
            <li>
              <button
                on:click={() => selectChange(ch)}
                class:list={[
                  'w-full text-left px-4 py-3 transition-colors',
                  selectedChange?.id === ch.id
                    ? 'bg-zinc-800'
                    : 'hover:bg-zinc-800/50',
                ]}
              >
                <!-- Type + status -->
                <div class="flex items-center gap-2 mb-1">
                  <span class="cve-badge cve-badge-info text-xs font-mono font-semibold text-sky-400">{typeBadge(ch.type)}</span>
                  <span class="cve-badge text-xs px-1.5 py-0.5 rounded-full font-medium {statusBadgeClass(ch.status)}">{ch.status}</span>
                  {#if ch.validation_status === 'fail'}
                    <span class="text-xs text-red-400">⚠ invalid</span>
                  {/if}
                </div>
                <!-- Path -->
                <div class="text-xs text-zinc-300 font-mono truncate" title={ch.path}>{ch.path}</div>
                {#if ch.section}
                  <div class="text-xs text-zinc-500 truncate">§ {ch.section}</div>
                {/if}
                <!-- Meta -->
                <div class="text-xs text-zinc-600 mt-1">{formatDate(ch.created_at)}</div>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <div class="p-4 text-sm text-zinc-500">Select a vault to load changes.</div>
      {/if}
    </div>

    <!-- Detail panel -->
    <div class="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      {#if !selectedChange && detailState !== 'loading'}
        <div class="p-8 text-sm text-zinc-500 text-center">
          Select a change from the list to review it.
        </div>
      {:else if detailState === 'loading'}
        <div class="p-8 text-sm text-zinc-500 text-center">Loading…</div>
      {:else if detailState === 'error'}
        <div class="p-4 text-sm text-red-400">{detailError}</div>
      {:else if selectedChange}
        {@const ch = selectedChange}
        <div class="flex flex-col h-full">

          <!-- Detail header -->
          <div class="px-5 py-4 border-b border-zinc-800 flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap mb-1">
                <span class="text-xs font-mono font-semibold text-sky-400">{typeBadge(ch.type)}</span>
                <span class="text-xs px-1.5 py-0.5 rounded-full font-medium {statusBadgeClass(ch.status)}">{ch.status}</span>
                <span class="text-xs {validationBadgeClass(ch.validation_status)}">
                  validation: {ch.validation_status}
                </span>
              </div>
              <div class="text-sm font-mono text-zinc-200 break-all">{ch.path}</div>
              {#if ch.section}
                <div class="text-xs text-zinc-400 mt-0.5">Section: {ch.section}</div>
              {/if}
            </div>
            <div class="text-xs text-zinc-600 shrink-0">{ch.id}</div>
          </div>

          <!-- Scrollable body -->
          <div class="flex-1 overflow-y-auto divide-y divide-zinc-800">

            <!-- Metadata -->
            <div class="px-5 py-4 grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
              <div><span class="text-zinc-500">Source:</span> <span class="text-zinc-300">{ch.source}</span></div>
              <div><span class="text-zinc-500">Created:</span> <span class="text-zinc-300">{formatDate(ch.created_at)}</span></div>
              {#if ch.session_id}
                <div><span class="text-zinc-500">Session:</span> <span class="text-zinc-400 font-mono">{ch.session_id}</span></div>
              {/if}
              {#if ch.project}
                <div><span class="text-zinc-500">Project:</span> <span class="text-zinc-300">{ch.project}</span></div>
              {/if}
              {#if ch.reviewer}
                <div><span class="text-zinc-500">Reviewer:</span> <span class="text-zinc-300">{ch.reviewer}</span></div>
              {/if}
              {#if ch.applied_at}
                <div><span class="text-zinc-500">Applied:</span> <span class="text-emerald-400">{formatDate(ch.applied_at)}</span></div>
              {/if}
              {#if ch.rejected_at}
                <div><span class="text-zinc-500">Rejected:</span> <span class="text-zinc-400">{formatDate(ch.rejected_at)}</span></div>
              {/if}
            </div>

            <!-- Reason -->
            {#if ch.reason}
              <div class="px-5 py-4">
                <div class="text-xs font-semibold text-zinc-400 mb-1 uppercase tracking-wider">Reason</div>
                <p class="text-sm text-zinc-300">{ch.reason}</p>
              </div>
            {/if}

            <!-- Audit note -->
            {#if ch.audit_note}
              <div class="px-5 py-4">
                <div class="text-xs font-semibold text-zinc-400 mb-1 uppercase tracking-wider">Audit Note</div>
                <p class="text-sm text-zinc-300">{ch.audit_note}</p>
              </div>
            {/if}

            <!-- Validation errors -->
            {#if ch.validation_errors.length > 0}
              <div class="px-5 py-4">
                <div class="text-xs font-semibold text-red-400 mb-2 uppercase tracking-wider">Validation Errors</div>
                <ul class="space-y-1">
                  {#each ch.validation_errors as err}
                    <li class="text-xs text-red-300 bg-red-950/30 border border-red-800/50 rounded px-3 py-1.5 font-mono">{err}</li>
                  {/each}
                </ul>
              </div>
            {/if}

            <!-- Diff -->
            <div class="px-5 py-4">
              <div class="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wider">
                Diff
                {#if ch.diff.length === 0}
                  <span class="text-zinc-600 font-normal ml-1">(no diff — new file)</span>
                {/if}
              </div>
              {#if ch.diff.length > 0}
                <pre class="text-xs rounded-lg bg-zinc-950 border border-zinc-800 overflow-x-auto p-3 leading-relaxed"><code>{#each ch.diff as line}<span class={diffLineClass(line)}>{line}
</span>{/each}</code></pre>
              {:else}
                <div class="text-xs text-zinc-600">This is a new note — no diff to show.</div>
              {/if}
            </div>

            <!-- Raw JSON toggle -->
            <div class="px-5 py-4">
              <button
                on:click={() => { showRawJson = !showRawJson; }}
                class="text-xs text-zinc-500 hover:text-zinc-300 underline underline-offset-2 transition-colors"
              >
                {showRawJson ? 'Hide' : 'Show'} raw JSON
              </button>
              {#if showRawJson}
                <pre class="mt-2 text-xs bg-zinc-950 border border-zinc-800 rounded p-3 overflow-x-auto text-zinc-400">{JSON.stringify(ch, null, 2)}</pre>
              {/if}
            </div>

            <!-- Action result -->
            {#if actionState === 'ok'}
              <div class="px-5 py-3 bg-emerald-950/30 border-t border-emerald-800/40">
                <p class="text-sm text-emerald-300">Action applied. Change status: <strong>{ch.status}</strong></p>
              </div>
            {/if}

            {#if actionState === 'error'}
              <div class="px-5 py-3 bg-red-950/30 border-t border-red-800/40">
                <p class="text-xs text-red-400">
                  {#if actionErrorCode}<span class="font-mono mr-1">[{actionErrorCode}]</span>{/if}{actionError}
                </p>
              </div>
            {/if}

            <!-- Accept / Reject buttons (only for pending) -->
            {#if ch.status === 'pending'}
              <div class="px-5 py-4 space-y-4">

                <!-- Reviewer fields -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div class="flex flex-col gap-1">
                    <label for="reviewer-input" class="text-xs text-zinc-400">Reviewer (optional)</label>
                    <input
                      id="reviewer-input"
                      type="text"
                      bind:value={reviewerInput}
                      placeholder="Your name"
                      class="bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    />
                  </div>
                  <div class="flex flex-col gap-1">
                    <label for="audit-note-input" class="text-xs text-zinc-400">Audit note (optional)</label>
                    <input
                      id="audit-note-input"
                      type="text"
                      bind:value={auditNoteInput}
                      placeholder="Reason for decision"
                      class="bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-500"
                    />
                  </div>
                </div>

                <!-- Validation warning -->
                {#if ch.validation_status === 'fail'}
                  <div class="bg-red-950/30 border border-red-700/50 rounded p-3 text-xs text-red-300">
                    <strong>Cannot accept:</strong> this change has validation errors. Fix the proposal and re-submit.
                  </div>
                {/if}

                <!-- Action buttons -->
                <div class="flex gap-3">

                  <!-- Accept -->
                  {#if !showAcceptConfirm}
                    <button
                      on:click={() => { showAcceptConfirm = true; showRejectConfirm = false; }}
                      disabled={ch.validation_status === 'fail' || actionState === 'loading'}
                      class="px-4 py-2 text-sm font-medium rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
                    >
                      Accept &amp; Apply
                    </button>
                  {:else}
                    <div class="bg-emerald-950/30 border border-emerald-700/50 rounded p-3 flex flex-col gap-2">
                      <p class="text-xs text-emerald-300 font-medium">
                        Confirm: apply this change to <span class="font-mono">{ch.path}</span>? This cannot be undone.
                      </p>
                      <div class="flex gap-2">
                        <button
                          on:click={submitAccept}
                          disabled={actionState === 'loading'}
                          class="px-3 py-1.5 text-xs font-semibold rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white transition-colors"
                        >
                          {actionState === 'loading' ? 'Applying…' : 'Yes, apply'}
                        </button>
                        <button
                          on:click={() => { showAcceptConfirm = false; }}
                          class="px-3 py-1.5 text-xs rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-200 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  {/if}

                  <!-- Reject -->
                  {#if !showRejectConfirm}
                    <button
                      on:click={() => { showRejectConfirm = true; showAcceptConfirm = false; }}
                      disabled={actionState === 'loading'}
                      class="px-4 py-2 text-sm font-medium rounded bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-zinc-200 transition-colors"
                    >
                      Reject
                    </button>
                  {:else}
                    <div class="bg-zinc-800 border border-zinc-700 rounded p-3 flex flex-col gap-2">
                      <p class="text-xs text-zinc-300 font-medium">Confirm rejection and archive?</p>
                      <div class="flex gap-2">
                        <button
                          on:click={submitReject}
                          disabled={actionState === 'loading'}
                          class="px-3 py-1.5 text-xs font-semibold rounded bg-zinc-600 hover:bg-zinc-500 disabled:opacity-40 text-zinc-100 transition-colors"
                        >
                          {actionState === 'loading' ? 'Rejecting…' : 'Yes, reject'}
                        </button>
                        <button
                          on:click={() => { showRejectConfirm = false; }}
                          class="px-3 py-1.5 text-xs rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-200 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  {/if}
                </div>

              </div>
            {/if}

          </div><!-- /.flex-1 -->
        </div>
      {/if}
    </div>

  </div><!-- /.grid -->
</div>
