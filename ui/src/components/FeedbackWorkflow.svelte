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
    type FeedbackData,
    type FeedbackResponse,
    type FeedbackDeleteResponse,
    type FeedbackNormaliseResponse,
    type FeedbackCreateRequest,
    type FeedbackUpdateRequest,
    type FeedbackSource,
    type FeedbackSignal,
    type FeedbackSeverity,
    type TasksData,
    type Task,
  } from '../lib/api.ts';

  // ---------------------------------------------------------------------------
  // Vault state
  // ---------------------------------------------------------------------------

  let vaultList: string[] = [];
  let vaultsLoading = true;
  let vaultsError = '';
  let selectedVault = '';

  // ---------------------------------------------------------------------------
  // Feedback state
  // ---------------------------------------------------------------------------

  type LoadState = 'idle' | 'loading' | 'ok' | 'error';

  let feedbackState: LoadState = 'idle';
  let feedbackData: FeedbackData | null = null;
  let feedbackLoadError = '';

  // ---------------------------------------------------------------------------
  // Task state
  // ---------------------------------------------------------------------------

  let tasksState: LoadState = 'idle';
  let tasksData: TasksData | null = null;
  let tasksError = '';

  // ---------------------------------------------------------------------------
  // Filter state
  // ---------------------------------------------------------------------------

  let filterPath = '';
  let filterSignal = '';
  let filterSeverity = '';
  let filterSource = '';

  // ---------------------------------------------------------------------------
  // Add form state
  // ---------------------------------------------------------------------------

  let addPath = '';
  let addSource: FeedbackSource = 'human';
  let addSignal: FeedbackSignal = 'unclear';
  let addSeverity: FeedbackSeverity = 'medium';
  let addComment = '';

  type WriteState = 'idle' | 'loading' | 'ok' | 'error';
  let addState: WriteState = 'idle';
  let addError = '';
  let addErrorCode = '';
  let addResult: FeedbackResponse | null = null;

  // Validation errors
  let addPathError = '';
  let addCommentError = '';

  // ---------------------------------------------------------------------------
  // Edit state
  // ---------------------------------------------------------------------------

  let editingId: string | null = null;
  let editPath = '';
  let editSource: FeedbackSource = 'human';
  let editSignal: FeedbackSignal = 'unclear';
  let editSeverity: FeedbackSeverity = 'medium';
  let editComment = '';
  let editState: WriteState = 'idle';
  let editError = '';
  let editErrorCode = '';

  let editPathError = '';
  let editCommentError = '';

  // ---------------------------------------------------------------------------
  // Delete state
  // ---------------------------------------------------------------------------

  let deletingId: string | null = null;
  let deleteState: WriteState = 'idle';
  let deleteError = '';
  let deleteErrorCode = '';

  // ---------------------------------------------------------------------------
  // Normalise state
  // ---------------------------------------------------------------------------

  let normaliseState: WriteState = 'idle';
  let normaliseError = '';
  let normaliseResult: FeedbackNormaliseResponse | null = null;

  // ---------------------------------------------------------------------------
  // Raw JSON toggles
  // ---------------------------------------------------------------------------

  let showRawFeedback = false;
  let showRawTasks = false;
  let showRawWriteResult = false;
  let writeResultForRaw: unknown = null;

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  const SOURCES: FeedbackSource[] = ['human', 'agent', 'system'];
  const SIGNALS: FeedbackSignal[] = [
    'unclear',
    'incomplete',
    'outdated',
    'incorrect',
    'agent_failed',
    'needs_example',
    'needs_constraints',
    'useful',
    'agent_succeeded',
  ];
  const SEVERITIES: FeedbackSeverity[] = ['low', 'medium', 'high', 'critical'];

  // ---------------------------------------------------------------------------
  // Derived / reactive
  // ---------------------------------------------------------------------------

  $: filteredEntries = (() => {
    if (!feedbackData) return [];
    let entries = [...feedbackData.entries];
    const pathQ = filterPath.trim().toLowerCase();
    if (pathQ) entries = entries.filter(e => e.path.toLowerCase().includes(pathQ));
    if (filterSignal) entries = entries.filter(e => e.signal === filterSignal);
    if (filterSeverity) entries = entries.filter(e => e.severity === filterSeverity);
    if (filterSource) entries = entries.filter(e => e.source === filterSource);
    // newest first
    entries.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return entries;
  })();

  $: feedbackCount = feedbackData?.entries.length ?? 0;
  $: warningCount = feedbackData?.warnings.length ?? 0;
  $: errorCount = Array.isArray(feedbackData?.errors) ? (feedbackData!.errors as unknown[]).length : 0;
  $: taskCount = tasksData?.total ?? 0;
  $: feedbackAdjustedCount = (() => {
    if (!tasksData) return 0;
    return (tasksData.tasks ?? []).filter(t => t.feedback_weight !== undefined).length;
  })();
  $: highestPriorityTask = (() => {
    if (!tasksData || !tasksData.tasks || tasksData.tasks.length === 0) return null;
    return tasksData.tasks.reduce((a, b) => (b.priority > a.priority ? b : a));
  })();

  $: hasFilters = !!(filterPath || filterSignal || filterSeverity || filterSource);

  // Add form validation
  $: {
    const p = addPath.trim();
    if (!p) {
      addPathError = 'Path is required.';
    } else if (p.includes('..')) {
      addPathError = 'Path must not contain ".." traversal.';
    } else {
      addPathError = '';
    }
  }
  $: {
    const c = addComment.trim();
    if (!c) {
      addCommentError = 'Comment is required.';
    } else if (c.length > 2000) {
      addCommentError = `Comment too long (${c.length}/2000).`;
    } else {
      addCommentError = '';
    }
  }
  $: canAdd =
    !addPathError &&
    !addCommentError &&
    addPath.trim() !== '' &&
    addComment.trim() !== '' &&
    addState !== 'loading';

  // Edit form validation
  $: {
    const p = editPath.trim();
    if (editingId !== null) {
      if (!p) {
        editPathError = 'Path is required.';
      } else if (p.includes('..')) {
        editPathError = 'Path must not contain ".." traversal.';
      } else {
        editPathError = '';
      }
    } else {
      editPathError = '';
    }
  }
  $: {
    const c = editComment.trim();
    if (editingId !== null) {
      if (!c) {
        editCommentError = 'Comment is required.';
      } else if (c.length > 2000) {
        editCommentError = `Comment too long (${c.length}/2000).`;
      } else {
        editCommentError = '';
      }
    } else {
      editCommentError = '';
    }
  }
  $: canEdit =
    editingId !== null &&
    !editPathError &&
    !editCommentError &&
    editPath.trim() !== '' &&
    editComment.trim() !== '' &&
    editState !== 'loading';

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onMount(async () => {
    const result = await fetchVaults();
    vaultsLoading = false;
    if (isOk(result)) {
      vaultList = result.data.vaults;
      if (vaultList.length > 0) {
        selectedVault = vaultList[0];
        await loadAll();
      }
    } else {
      vaultsError = result.error?.message ?? 'Failed to load vaults';
    }
  });

  async function loadAll() {
    await Promise.all([loadFeedback(), loadTasks()]);
  }

  async function loadFeedback() {
    if (!selectedVault) return;
    feedbackState = 'loading';
    feedbackLoadError = '';
    const result = await fetchFeedback(selectedVault);
    if (isOk(result)) {
      feedbackData = result.data;
      feedbackState = 'ok';
    } else {
      feedbackLoadError = result.error?.message ?? 'Failed to load feedback';
      feedbackState = 'error';
    }
  }

  async function loadTasks() {
    if (!selectedVault) return;
    tasksState = 'loading';
    tasksError = '';
    const result = await fetchTasks(selectedVault, { include_feedback: true, limit: 10 });
    if (isOk(result)) {
      tasksData = result.data;
      tasksState = 'ok';
    } else {
      tasksError = result.error?.message ?? 'Failed to load tasks';
      tasksState = 'error';
    }
  }

  async function onVaultChange() {
    editingId = null;
    deletingId = null;
    addState = 'idle';
    normaliseState = 'idle';
    await loadAll();
  }

  // ---------------------------------------------------------------------------
  // Add feedback
  // ---------------------------------------------------------------------------

  async function handleAdd() {
    if (!canAdd) return;
    addState = 'loading';
    addError = '';
    addErrorCode = '';
    addResult = null;

    const req: FeedbackCreateRequest = {
      vault: selectedVault,
      path: addPath.trim(),
      source: addSource,
      signal: addSignal,
      severity: addSeverity,
      comment: addComment.trim(),
    };
    const result = await createFeedback(req);
    if (isOk(result)) {
      addState = 'ok';
      addResult = result.data;
      writeResultForRaw = result.data;
      // Reset form
      addPath = '';
      addSource = 'human';
      addSignal = 'unclear';
      addSeverity = 'medium';
      addComment = '';
      // Update local state from server response
      if (result.data.feedback) {
        feedbackData = result.data.feedback;
        feedbackState = 'ok';
      } else {
        await loadFeedback();
      }
      await loadTasks();
    } else {
      addState = 'error';
      addError = result.error?.message ?? 'Failed to add feedback';
      addErrorCode = result.error?.code ?? '';
    }
  }

  // ---------------------------------------------------------------------------
  // Edit feedback
  // ---------------------------------------------------------------------------

  function startEdit(entry: FeedbackEntry) {
    editingId = entry.id ?? null;
    if (!editingId) return; // cannot edit without id
    editPath = entry.path;
    editSource = (entry.source as FeedbackSource) || 'human';
    editSignal = (entry.signal as FeedbackSignal) || 'unclear';
    editSeverity = (entry.severity as FeedbackSeverity) || 'medium';
    editComment = entry.comment;
    editState = 'idle';
    editError = '';
    editErrorCode = '';
    deletingId = null;
  }

  function cancelEdit() {
    editingId = null;
    editState = 'idle';
    editError = '';
  }

  async function handleUpdate() {
    if (!canEdit || !editingId) return;
    editState = 'loading';
    editError = '';
    editErrorCode = '';

    const req: FeedbackUpdateRequest = {
      vault: selectedVault,
      path: editPath.trim(),
      source: editSource,
      signal: editSignal,
      severity: editSeverity,
      comment: editComment.trim(),
    };
    const result = await updateFeedback(editingId, req);
    if (isOk(result)) {
      editState = 'ok';
      writeResultForRaw = result.data;
      if (result.data.feedback) {
        feedbackData = result.data.feedback;
        feedbackState = 'ok';
      } else {
        await loadFeedback();
      }
      await loadTasks();
      editingId = null;
    } else {
      editState = 'error';
      editError = result.error?.message ?? 'Failed to update feedback';
      editErrorCode = result.error?.code ?? '';
    }
  }

  // ---------------------------------------------------------------------------
  // Delete feedback
  // ---------------------------------------------------------------------------

  function confirmDelete(entry: FeedbackEntry) {
    deletingId = entry.id ?? null;
    if (!deletingId) return;
    deleteState = 'idle';
    deleteError = '';
    editingId = null;
  }

  function cancelDelete() {
    deletingId = null;
    deleteState = 'idle';
    deleteError = '';
  }

  async function handleDelete() {
    if (!deletingId) return;
    deleteState = 'loading';
    deleteError = '';
    deleteErrorCode = '';

    const result = await deleteFeedback(deletingId, selectedVault);
    if (isOk(result)) {
      writeResultForRaw = result.data;
      if (result.data.feedback) {
        feedbackData = result.data.feedback;
        feedbackState = 'ok';
      } else {
        await loadFeedback();
      }
      await loadTasks();
      deletingId = null;
      deleteState = 'idle';
    } else {
      deleteState = 'error';
      deleteError = result.error?.message ?? 'Failed to delete feedback';
      deleteErrorCode = result.error?.code ?? '';
    }
  }

  // ---------------------------------------------------------------------------
  // Normalise
  // ---------------------------------------------------------------------------

  async function handleNormalise() {
    normaliseState = 'loading';
    normaliseError = '';
    normaliseResult = null;
    const result = await normaliseFeedback(selectedVault);
    if (isOk(result)) {
      normaliseState = 'ok';
      normaliseResult = result.data;
      writeResultForRaw = result.data;
      if (result.data.feedback) {
        feedbackData = result.data.feedback;
        feedbackState = 'ok';
      } else {
        await loadFeedback();
      }
    } else {
      normaliseState = 'error';
      normaliseError = result.error?.message ?? 'Normalise failed';
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function clearFilters() {
    filterPath = '';
    filterSignal = '';
    filterSeverity = '';
    filterSource = '';
  }

  function severityClass(s: string): string {
    if (s === 'critical') return 'bg-red-900 text-red-300 border border-red-700';
    if (s === 'high') return 'bg-orange-900 text-orange-300 border border-orange-700';
    if (s === 'medium') return 'bg-yellow-900 text-yellow-300 border border-yellow-700';
    return 'bg-zinc-800 text-zinc-400 border border-zinc-600';
  }

  function signalClass(s: string): string {
    if (s === 'useful' || s === 'agent_succeeded') return 'bg-emerald-900 text-emerald-300 border border-emerald-700';
    if (s === 'incorrect' || s === 'agent_failed') return 'bg-red-900 text-red-300 border border-red-700';
    return 'bg-sky-900 text-sky-300 border border-sky-700';
  }

  function fmtDate(dt: string | undefined): string {
    if (!dt) return '—';
    try {
      return new Date(dt).toLocaleString();
    } catch {
      return dt;
    }
  }
</script>

<!-- ═══════════════════════════════════════════════════════════════════════════
     TEMPLATE
     ═══════════════════════════════════════════════════════════════════════════ -->

<!-- Loading / error state -->
{#if vaultsLoading}
  <div class="text-zinc-400 text-sm py-8 text-center">Loading vaults...</div>
{:else if vaultsError}
  <div class="rounded-md bg-red-950 border border-red-700 px-4 py-3 text-sm text-red-300">{vaultsError}</div>
{:else if vaultList.length === 0}
  <div class="rounded-md bg-zinc-900 border border-zinc-700 px-4 py-6 text-center text-zinc-400 text-sm">
    No vaults registered. Use Vault Setup to create one.
  </div>
{:else}

<!-- ── Vault selector ─────────────────────────────────────────────────────── -->
<div class="mb-6 flex flex-wrap items-center gap-3">
  <label class="text-sm text-zinc-400 shrink-0" for="vault-select">Vault</label>
  <select
    id="vault-select"
    class="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-sky-600"
    bind:value={selectedVault}
    on:change={onVaultChange}
  >
    {#each vaultList as v}
      <option value={v}>{v}</option>
    {/each}
  </select>
  <button
    class="ml-auto px-3 py-1.5 rounded-md bg-zinc-800 text-zinc-300 text-sm hover:bg-zinc-700 transition-colors"
    on:click={loadAll}
    disabled={feedbackState === 'loading' || tasksState === 'loading'}
  >
    Refresh
  </button>
</div>

<!-- ── Summary cards ─────────────────────────────────────────────────────── -->
<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
  <div class="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-3">
    <div class="text-xs text-zinc-500 mb-1">Feedback entries</div>
    <div class="text-xl font-semibold text-zinc-100">{feedbackCount}</div>
  </div>
  <div class="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-3">
    <div class="text-xs text-zinc-500 mb-1">Warnings</div>
    <div class="text-xl font-semibold {warningCount > 0 ? 'text-yellow-400' : 'text-zinc-100'}">{warningCount}</div>
  </div>
  <div class="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-3">
    <div class="text-xs text-zinc-500 mb-1">Errors</div>
    <div class="text-xl font-semibold {errorCount > 0 ? 'text-red-400' : 'text-zinc-100'}">{errorCount}</div>
  </div>
  <div class="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-3">
    <div class="text-xs text-zinc-500 mb-1">Tasks</div>
    <div class="text-xl font-semibold text-zinc-100">{taskCount}</div>
  </div>
  <div class="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-3">
    <div class="text-xs text-zinc-500 mb-1">Feedback-adjusted</div>
    <div class="text-xl font-semibold text-sky-400">{feedbackAdjustedCount}</div>
  </div>
  <div class="rounded-md bg-zinc-900 border border-zinc-800 px-3 py-3">
    <div class="text-xs text-zinc-500 mb-1">Top priority</div>
    <div class="text-sm font-semibold text-zinc-100 truncate" title={highestPriorityTask?.path ?? '—'}>
      {#if highestPriorityTask}
        <span class="text-orange-400">{highestPriorityTask.priority}</span>
        <span class="text-zinc-500 ml-1 text-xs font-normal">{highestPriorityTask.path.split('/').pop()}</span>
      {:else}
        —
      {/if}
    </div>
  </div>
</div>

<!-- ── Main two-column layout ─────────────────────────────────────────────── -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

  <!-- ── LEFT COLUMN ───────────────────────────────────────────────────────── -->
  <div class="flex flex-col gap-6">

    <!-- Feedback list panel -->
    <div class="rounded-lg bg-zinc-900 border border-zinc-800">
      <div class="px-4 py-3 border-b border-zinc-800 flex items-center justify-between gap-2 flex-wrap">
        <h2 class="text-sm font-semibold text-zinc-200">Feedback Entries</h2>
        {#if feedbackState === 'loading'}
          <span class="text-xs text-zinc-500">Loading...</span>
        {/if}
      </div>

      <!-- Filters -->
      <div class="px-4 py-3 border-b border-zinc-800 grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          type="text"
          class="bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-600"
          placeholder="Filter by path…"
          bind:value={filterPath}
        />
        <select
          class="bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
          bind:value={filterSignal}
        >
          <option value="">All signals</option>
          {#each SIGNALS as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
        <select
          class="bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
          bind:value={filterSeverity}
        >
          <option value="">All severities</option>
          {#each SEVERITIES as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
        <select
          class="bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
          bind:value={filterSource}
        >
          <option value="">All sources</option>
          {#each SOURCES as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
        {#if hasFilters}
          <button
            class="sm:col-span-2 text-xs text-sky-400 hover:text-sky-300 text-left"
            on:click={clearFilters}
          >
            Clear filters
          </button>
        {/if}
      </div>

      <!-- Backend warnings/errors -->
      {#if feedbackData?.warnings && feedbackData.warnings.length > 0}
        <div class="mx-4 mt-3 rounded bg-yellow-950 border border-yellow-800 px-3 py-2 text-xs text-yellow-300">
          <strong>Warnings:</strong>
          <ul class="mt-1 space-y-0.5 list-disc list-inside">
            {#each feedbackData.warnings as w}
              <li>{w}</li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if feedbackData?.errors && (feedbackData.errors as unknown[]).length > 0}
        <div class="mx-4 mt-2 rounded bg-red-950 border border-red-800 px-3 py-2 text-xs text-red-300">
          <strong>Errors:</strong>
          <ul class="mt-1 space-y-0.5 list-disc list-inside">
            {#each feedbackData.errors as e}
              <li>{typeof e === 'string' ? e : JSON.stringify(e)}</li>
            {/each}
          </ul>
        </div>
      {/if}

      <!-- Error state -->
      {#if feedbackState === 'error'}
        <div class="mx-4 my-3 rounded bg-red-950 border border-red-700 px-3 py-2 text-sm text-red-300">{feedbackLoadError}</div>
      {/if}

      <!-- Entry list -->
      <div class="divide-y divide-zinc-800">
        {#if feedbackState !== 'loading' && filteredEntries.length === 0}
          <div class="px-4 py-8 text-center text-sm text-zinc-500">
            {feedbackData && feedbackData.entries.length > 0 ? 'No entries match current filters.' : 'No feedback entries found.'}
          </div>
        {/if}
        {#each filteredEntries as entry (entry.id ?? entry.created_at + entry.path)}
          <div class="px-4 py-3 text-sm {editingId === entry.id ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'} transition-colors">
            <!-- Entry header row -->
            <div class="flex items-start gap-2 flex-wrap">
              <div class="flex-1 min-w-0">
                <div class="font-mono text-xs text-zinc-500 mb-0.5">
                  {#if entry.id}
                    <span class="text-zinc-600">id:</span> {entry.id}
                  {:else}
                    <span class="text-yellow-600 italic">no id</span>
                  {/if}
                </div>
                <div class="text-zinc-200 font-medium truncate" title={entry.path}>{entry.path}</div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0 flex-wrap">
                <span class="text-xs px-1.5 py-0.5 rounded font-mono {severityClass(entry.severity)}">{entry.severity}</span>
                <span class="text-xs px-1.5 py-0.5 rounded font-mono {signalClass(entry.signal)}">{entry.signal}</span>
                <span class="text-xs px-1.5 py-0.5 rounded font-mono bg-zinc-800 text-zinc-400 border border-zinc-700">{entry.source}</span>
              </div>
            </div>
            <!-- Comment -->
            <p class="mt-1.5 text-zinc-400 text-xs leading-relaxed">{entry.comment}</p>
            <!-- Dates -->
            <div class="mt-1 flex gap-3 text-xs text-zinc-600">
              <span>Created: {fmtDate(entry.created_at)}</span>
              {#if entry.updated_at}
                <span>Updated: {fmtDate(entry.updated_at)}</span>
              {/if}
            </div>
            <!-- Actions -->
            <div class="mt-2 flex gap-2">
              {#if entry.id}
                <button
                  class="text-xs px-2 py-1 rounded bg-zinc-800 text-sky-400 hover:bg-sky-900 hover:text-sky-200 transition-colors border border-zinc-700"
                  on:click={() => startEdit(entry)}
                  disabled={editingId === entry.id || deleteState === 'loading'}
                >
                  Edit
                </button>
                <button
                  class="text-xs px-2 py-1 rounded bg-zinc-800 text-red-400 hover:bg-red-900 hover:text-red-200 transition-colors border border-zinc-700"
                  on:click={() => confirmDelete(entry)}
                  disabled={deletingId === entry.id || deleteState === 'loading'}
                >
                  Delete
                </button>
              {:else}
                <span class="text-xs text-yellow-600 italic">Normalise IDs to enable edit/delete</span>
              {/if}
            </div>

            <!-- Delete confirmation -->
            {#if deletingId === entry.id}
              <div class="mt-3 rounded-md bg-red-950 border border-red-700 px-3 py-3">
                <p class="text-sm text-red-300 mb-3">
                  Delete this feedback entry permanently?
                  <br /><span class="font-mono text-xs text-red-400">{entry.id}</span>
                </p>
                {#if deleteState === 'error'}
                  <div class="mb-2 text-xs text-red-400">
                    {deleteError}
                    {#if deleteErrorCode}<span class="ml-1 font-mono text-red-600">[{deleteErrorCode}]</span>{/if}
                  </div>
                {/if}
                <div class="flex gap-2">
                  <button
                    class="px-3 py-1.5 rounded bg-red-700 text-white text-xs hover:bg-red-600 transition-colors"
                    on:click={handleDelete}
                    disabled={deleteState === 'loading'}
                  >
                    {deleteState === 'loading' ? 'Deleting…' : 'Confirm Delete'}
                  </button>
                  <button
                    class="px-3 py-1.5 rounded bg-zinc-800 text-zinc-300 text-xs hover:bg-zinc-700 transition-colors"
                    on:click={cancelDelete}
                    disabled={deleteState === 'loading'}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            {/if}

            <!-- Inline edit form -->
            {#if editingId === entry.id}
              <div class="mt-3 rounded-md bg-zinc-800 border border-zinc-700 px-3 py-3">
                <h3 class="text-xs font-semibold text-zinc-300 mb-3">Edit feedback</h3>
                <!-- Path -->
                <div class="mb-2">
                  <label class="block text-xs text-zinc-400 mb-1">Path <span class="text-red-500">*</span></label>
                  <input
                    type="text"
                    class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600 {editPathError ? 'border-red-600' : ''}"
                    bind:value={editPath}
                  />
                  {#if editPathError}<p class="text-xs text-red-400 mt-1">{editPathError}</p>{/if}
                </div>
                <!-- Source / Signal / Severity row -->
                <div class="grid grid-cols-3 gap-2 mb-2">
                  <div>
                    <label class="block text-xs text-zinc-400 mb-1">Source</label>
                    <select class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600" bind:value={editSource}>
                      {#each SOURCES as s}<option value={s}>{s}</option>{/each}
                    </select>
                  </div>
                  <div>
                    <label class="block text-xs text-zinc-400 mb-1">Signal</label>
                    <select class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600" bind:value={editSignal}>
                      {#each SIGNALS as s}<option value={s}>{s}</option>{/each}
                    </select>
                  </div>
                  <div>
                    <label class="block text-xs text-zinc-400 mb-1">Severity</label>
                    <select class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600" bind:value={editSeverity}>
                      {#each SEVERITIES as s}<option value={s}>{s}</option>{/each}
                    </select>
                  </div>
                </div>
                <!-- Comment -->
                <div class="mb-2">
                  <label class="block text-xs text-zinc-400 mb-1">Comment <span class="text-red-500">*</span></label>
                  <textarea
                    rows="3"
                    class="w-full bg-zinc-900 border border-zinc-600 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600 resize-y {editCommentError ? 'border-red-600' : ''}"
                    bind:value={editComment}
                  ></textarea>
                  {#if editCommentError}
                    <p class="text-xs text-red-400 mt-1">{editCommentError}</p>
                  {:else}
                    <p class="text-xs text-zinc-600 mt-1">{editComment.trim().length}/2000</p>
                  {/if}
                </div>
                {#if editState === 'error'}
                  <div class="mb-2 text-xs text-red-400">
                    {editError}
                    {#if editErrorCode}<span class="ml-1 font-mono text-red-600">[{editErrorCode}]</span>{/if}
                  </div>
                {/if}
                <div class="flex gap-2">
                  <button
                    class="px-3 py-1.5 rounded bg-sky-700 text-white text-xs hover:bg-sky-600 transition-colors disabled:opacity-50"
                    on:click={handleUpdate}
                    disabled={!canEdit}
                  >
                    {editState === 'loading' ? 'Saving…' : 'Save changes'}
                  </button>
                  <button
                    class="px-3 py-1.5 rounded bg-zinc-700 text-zinc-300 text-xs hover:bg-zinc-600 transition-colors"
                    on:click={cancelEdit}
                    disabled={editState === 'loading'}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <!-- Raw feedback JSON -->
      <div class="px-4 py-3 border-t border-zinc-800">
        <details>
          <summary class="text-xs text-zinc-500 cursor-pointer hover:text-zinc-400">Raw feedback response</summary>
          <pre class="mt-2 text-xs text-zinc-400 bg-zinc-950 rounded p-3 overflow-auto max-h-64">{JSON.stringify(feedbackData, null, 2)}</pre>
        </details>
      </div>
    </div>

    <!-- Add feedback panel -->
    <div class="rounded-lg bg-zinc-900 border border-zinc-800">
      <div class="px-4 py-3 border-b border-zinc-800">
        <h2 class="text-sm font-semibold text-zinc-200">Add Feedback</h2>
      </div>
      <div class="px-4 py-4">
        <!-- Path -->
        <div class="mb-3">
          <label class="block text-xs text-zinc-400 mb-1" for="add-path">Path <span class="text-red-500">*</span></label>
          <input
            id="add-path"
            type="text"
            class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-600 {addPathError && addPath !== '' ? 'border-red-600' : ''}"
            placeholder="Fundamentals/Algorithms.md"
            bind:value={addPath}
          />
          {#if addPathError && addPath !== ''}<p class="text-xs text-red-400 mt-1">{addPathError}</p>{/if}
        </div>
        <!-- Source / Signal / Severity -->
        <div class="grid grid-cols-3 gap-2 mb-3">
          <div>
            <label class="block text-xs text-zinc-400 mb-1" for="add-source">Source</label>
            <select
              id="add-source"
              class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
              bind:value={addSource}
            >
              {#each SOURCES as s}<option value={s}>{s}</option>{/each}
            </select>
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1" for="add-signal">Signal</label>
            <select
              id="add-signal"
              class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
              bind:value={addSignal}
            >
              {#each SIGNALS as s}<option value={s}>{s}</option>{/each}
            </select>
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1" for="add-severity">Severity</label>
            <select
              id="add-severity"
              class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
              bind:value={addSeverity}
            >
              {#each SEVERITIES as s}<option value={s}>{s}</option>{/each}
            </select>
          </div>
        </div>
        <!-- Comment -->
        <div class="mb-3">
          <label class="block text-xs text-zinc-400 mb-1" for="add-comment">Comment <span class="text-red-500">*</span></label>
          <textarea
            id="add-comment"
            rows="3"
            class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-sky-600 resize-y {addCommentError && addComment !== '' ? 'border-red-600' : ''}"
            placeholder="Describe the feedback…"
            bind:value={addComment}
          ></textarea>
          {#if addCommentError && addComment !== ''}
            <p class="text-xs text-red-400 mt-1">{addCommentError}</p>
          {:else}
            <p class="text-xs text-zinc-600 mt-1">{addComment.trim().length}/2000</p>
          {/if}
        </div>

        <!-- Error -->
        {#if addState === 'error'}
          <div class="mb-3 rounded bg-red-950 border border-red-700 px-3 py-2 text-sm text-red-300">
            {addError}
            {#if addErrorCode}<span class="ml-1 font-mono text-xs text-red-500">[{addErrorCode}]</span>{/if}
          </div>
        {/if}
        <!-- Success -->
        {#if addState === 'ok' && addResult}
          <div class="mb-3 rounded bg-emerald-950 border border-emerald-700 px-3 py-2 text-sm text-emerald-300">
            Feedback added with id: <span class="font-mono">{addResult.entry.id}</span>
          </div>
        {/if}

        <button
          class="px-4 py-2 rounded-md bg-sky-700 text-white text-sm font-medium hover:bg-sky-600 transition-colors disabled:opacity-50"
          on:click={handleAdd}
          disabled={!canAdd}
        >
          {addState === 'loading' ? 'Adding…' : 'Add feedback'}
        </button>

        <!-- Raw write result -->
        {#if writeResultForRaw && (addState === 'ok' || editState === 'ok' || normaliseState === 'ok' || deleteState === 'idle')}
          <div class="mt-3">
            <details>
              <summary class="text-xs text-zinc-500 cursor-pointer hover:text-zinc-400">Raw write result</summary>
              <pre class="mt-2 text-xs text-zinc-400 bg-zinc-950 rounded p-3 overflow-auto max-h-48">{JSON.stringify(writeResultForRaw, null, 2)}</pre>
            </details>
          </div>
        {/if}
      </div>
    </div>

    <!-- Maintenance panel -->
    <div class="rounded-lg bg-zinc-900 border border-zinc-800">
      <div class="px-4 py-3 border-b border-zinc-800">
        <h2 class="text-sm font-semibold text-zinc-400">Maintenance</h2>
      </div>
      <div class="px-4 py-4">
        <p class="text-xs text-zinc-500 mb-3">
          <strong class="text-zinc-400">Normalise feedback IDs</strong> rewrites <code class="font-mono">feedback.md</code> atomically to assign stable hex IDs to any entries that lack them. Entries that already have IDs are unchanged.
        </p>
        {#if normaliseState === 'ok' && normaliseResult}
          <div class="mb-3 rounded bg-emerald-950 border border-emerald-700 px-3 py-2 text-sm text-emerald-300">
            {normaliseResult.normalised} {normaliseResult.normalised === 1 ? 'entry' : 'entries'} assigned new IDs.
          </div>
        {/if}
        {#if normaliseState === 'error'}
          <div class="mb-3 rounded bg-red-950 border border-red-700 px-3 py-2 text-sm text-red-300">{normaliseError}</div>
        {/if}
        <button
          class="px-3 py-1.5 rounded bg-zinc-800 text-zinc-300 text-sm border border-zinc-700 hover:bg-zinc-700 transition-colors disabled:opacity-50"
          on:click={handleNormalise}
          disabled={normaliseState === 'loading'}
        >
          {normaliseState === 'loading' ? 'Running…' : 'Normalise IDs'}
        </button>
      </div>
    </div>

  </div><!-- end left column -->

  <!-- ── RIGHT COLUMN ──────────────────────────────────────────────────────── -->
  <div class="flex flex-col gap-6">

    <!-- Task priority panel -->
    <div class="rounded-lg bg-zinc-900 border border-zinc-800">
      <div class="px-4 py-3 border-b border-zinc-800 flex items-center justify-between gap-2">
        <h2 class="text-sm font-semibold text-zinc-200">Improvement Tasks <span class="text-xs text-zinc-500 font-normal ml-1">(feedback-adjusted)</span></h2>
        {#if tasksState === 'loading'}
          <span class="text-xs text-zinc-500">Loading...</span>
        {/if}
      </div>

      {#if tasksData?.feedback_status === 'error' && tasksData.feedback_errors && (tasksData.feedback_errors as unknown[]).length > 0}
        <div class="mx-4 mt-3 rounded bg-yellow-950 border border-yellow-800 px-3 py-2 text-xs text-yellow-300">
          Feedback weighting unavailable:
          <ul class="mt-1 list-disc list-inside">
            {#each tasksData.feedback_errors as e}
              <li>{typeof e === 'string' ? e : JSON.stringify(e)}</li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if tasksState === 'error'}
        <div class="mx-4 my-3 rounded bg-red-950 border border-red-700 px-3 py-2 text-sm text-red-300">{tasksError}</div>
      {/if}

      <div class="divide-y divide-zinc-800">
        {#if tasksState !== 'loading' && (!tasksData || tasksData.tasks.length === 0)}
          <div class="px-4 py-8 text-center text-sm text-zinc-500">No improvement tasks found.</div>
        {/if}
        {#each (tasksData?.tasks ?? []) as task, idx}
          <div class="px-4 py-3 text-sm">
            <!-- Task header -->
            <div class="flex items-start gap-2 flex-wrap">
              <span class="shrink-0 text-xs font-mono px-1.5 py-0.5 rounded border
                {task.priority >= 4 ? 'bg-red-950 text-red-300 border-red-700' :
                 task.priority >= 3 ? 'bg-orange-950 text-orange-300 border-orange-700' :
                 task.priority >= 2 ? 'bg-yellow-950 text-yellow-300 border-yellow-700' :
                 'bg-zinc-800 text-zinc-400 border-zinc-700'}">
                P{task.priority}
              </span>
              <span class="flex-1 text-zinc-200 font-medium truncate" title={task.path}>{task.path}</span>
            </div>
            <!-- Note / instruction -->
            {#if task.note}
              <p class="mt-1 text-zinc-400 text-xs">{task.note}</p>
            {/if}
            {#if task.instruction}
              <p class="mt-1 text-zinc-300 text-xs italic">{task.instruction}</p>
            {/if}
            <!-- Missing sections -->
            {#if task.missing && task.missing.length > 0}
              <div class="mt-1.5 flex flex-wrap gap-1">
                {#each task.missing as m}
                  <span class="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">missing: {m}</span>
                {/each}
              </div>
            {/if}
            <!-- Constraints -->
            {#if task.constraints && task.constraints.length > 0}
              <div class="mt-1 text-xs text-zinc-500">
                Constraints: {task.constraints.join(', ')}
              </div>
            {/if}
            <!-- Feedback weight -->
            {#if task.feedback_weight}
              <details class="mt-2">
                <summary class="text-xs text-sky-400 cursor-pointer hover:text-sky-300">
                  Feedback weight
                  {#if typeof task.feedback_weight === 'object' && task.feedback_weight !== null && 'score_delta' in task.feedback_weight}
                    <span class="ml-1 font-mono text-sky-500">
                      {(task.feedback_weight as {score_delta: number}).score_delta > 0 ? '+' : ''}{(task.feedback_weight as {score_delta: number}).score_delta}
                    </span>
                  {/if}
                </summary>
                <pre class="mt-1.5 text-xs text-zinc-400 bg-zinc-950 rounded p-2 overflow-auto max-h-32">{JSON.stringify(task.feedback_weight, null, 2)}</pre>
              </details>
            {/if}
          </div>
        {/each}
      </div>

      <!-- Raw tasks JSON -->
      <div class="px-4 py-3 border-t border-zinc-800">
        <details>
          <summary class="text-xs text-zinc-500 cursor-pointer hover:text-zinc-400">Raw tasks response</summary>
          <pre class="mt-2 text-xs text-zinc-400 bg-zinc-950 rounded p-3 overflow-auto max-h-64">{JSON.stringify(tasksData, null, 2)}</pre>
        </details>
      </div>
    </div>

  </div><!-- end right column -->

</div><!-- end grid -->

{/if}<!-- end vault guard -->
