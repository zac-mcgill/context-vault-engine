<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchVaults,
    fetchContextState,
    fetchContextPlan,
    isOk,
    type ContextStateData,
    type ContextPlanData,
    type ContextRecommendation,
  } from '../lib/api.ts';
  import { getStoredVault, setStoredVault } from '../lib/vaultState.ts';

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

  type Intent = 'review' | 'export' | 'agent-context' | 'quality' | 'security';
  const INTENTS: { value: Intent; label: string; description: string }[] = [
    { value: 'review', label: 'Review', description: 'General vault health and completeness' },
    { value: 'export', label: 'Export', description: 'Readiness for context bundle export' },
    { value: 'agent-context', label: 'Agent Context', description: 'Readiness for LLM agent use' },
    { value: 'quality', label: 'Quality', description: 'Content quality and coverage gaps' },
    { value: 'security', label: 'Security', description: 'Security findings and risks' },
  ];
  let selectedIntent: Intent = 'review';

  // ---------------------------------------------------------------------------
  // Load state
  // ---------------------------------------------------------------------------

  type LoadState = 'idle' | 'loading' | 'ok' | 'error';
  let stateLoadState: LoadState = 'idle';
  let planLoadState: LoadState = 'idle';

  let stateData: ContextStateData | null = null;
  let planData: ContextPlanData | null = null;

  let stateError = '';
  let planError = '';

  // ---------------------------------------------------------------------------
  // UI state
  // ---------------------------------------------------------------------------

  let showRawStateJson = false;
  let showRawPlanJson = false;

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  onMount(async () => {
    const vr = await fetchVaults();
    vaultsLoading = false;
    if (!isOk(vr)) {
      vaultsError = vr.error.message;
      return;
    }
    vaultList = vr.data.vaults;
    const stored = getStoredVault();
    if (stored && vaultList.includes(stored)) {
      selectedVault = stored;
    } else if (vaultList.length > 0) {
      selectedVault = vaultList[0];
    }
    if (selectedVault) {
      await loadAll();
    }
  });

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  async function loadAll() {
    if (!selectedVault) return;
    await Promise.all([loadState(), loadPlan()]);
  }

  async function loadState() {
    stateLoadState = 'loading';
    stateData = null;
    stateError = '';
    const result = await fetchContextState(selectedVault);
    if (!isOk(result)) {
      stateLoadState = 'error';
      stateError = result.error.message;
      return;
    }
    stateData = result.data;
    stateLoadState = 'ok';
  }

  async function loadPlan() {
    planLoadState = 'loading';
    planData = null;
    planError = '';
    const result = await fetchContextPlan(selectedVault, selectedIntent);
    if (!isOk(result)) {
      planLoadState = 'error';
      planError = result.error.message;
      return;
    }
    planData = result.data;
    planLoadState = 'ok';
  }

  async function handleVaultChange() {
    if (selectedVault) {
      setStoredVault(selectedVault);
      await loadAll();
    }
  }

  async function handleIntentChange() {
    if (selectedVault) {
      await loadPlan();
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  const SEVERITY_COLOUR: Record<string, string> = {
    critical: 'text-red-400',
    high: 'text-orange-400',
    medium: 'text-amber-400',
    low: 'text-sky-400',
    info: 'text-zinc-500',
  };

  const SEVERITY_BG: Record<string, string> = {
    critical: 'bg-red-950 border-red-800',
    high: 'bg-orange-950 border-orange-800',
    medium: 'bg-amber-950 border-amber-800',
    low: 'bg-sky-950 border-sky-800',
    info: 'bg-zinc-800 border-zinc-700',
  };
</script>

<!-- ======================================================================
     Layout
     ====================================================================== -->

<div class="cve-page space-y-6">

  <!-- ── Header ────────────────────────────────────────────────────────── -->
  <div class="cve-page-header">
    <h1 class="cve-page-title text-xl font-semibold text-zinc-100">Context Controller</h1>
    <p class="text-sm text-zinc-500 mt-0.5">
      Deterministic vault state snapshot and action planner. No LLM — all output
      is derived from the current state of your vault.
    </p>
  </div>

  <!-- ── Controls ──────────────────────────────────────────────────────── -->
  {#if vaultsLoading}
    <div class="text-sm text-zinc-500 py-6">Loading vaults…</div>
  {:else if vaultsError}
    <div class="bg-red-950 border border-red-800 rounded-lg p-4 text-sm text-red-300">
      <span class="font-medium">Could not load vaults:</span> {vaultsError}
    </div>
  {:else if vaultList.length === 0}
    <div class="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
      <p class="text-sm text-zinc-400">No vaults registered. Use Vault Setup to create one.</p>
    </div>
  {:else}
    <div class="flex flex-wrap items-center gap-3">
      <label class="text-sm text-zinc-400 shrink-0" for="vault-select">Vault</label>
      <select
        id="vault-select"
        bind:value={selectedVault}
        on:change={handleVaultChange}
        class="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-sky-600"
      >
        {#each vaultList as v}
          <option value={v}>{v}</option>
        {/each}
      </select>

      <label class="text-sm text-zinc-400 shrink-0" for="intent-select">Intent</label>
      <select
        id="intent-select"
        bind:value={selectedIntent}
        on:change={handleIntentChange}
        class="bg-zinc-900 border border-zinc-700 rounded-md px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-sky-600"
      >
        {#each INTENTS as intent}
          <option value={intent.value}>{intent.label} — {intent.description}</option>
        {/each}
      </select>

      <button
        on:click={loadAll}
        disabled={!selectedVault || stateLoadState === 'loading' || planLoadState === 'loading'}
        class="ml-auto px-3 py-1.5 rounded-md bg-zinc-800 text-zinc-300 text-sm hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {stateLoadState === 'loading' || planLoadState === 'loading' ? 'Loading…' : 'Refresh'}
      </button>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════
         Vault State
         ═══════════════════════════════════════════════════════════════ -->
    <section class="space-y-4">
      <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wide">Vault State</h2>

      {#if stateLoadState === 'idle'}
        <p class="text-sm text-zinc-500">Select a vault to load the state snapshot.</p>
      {:else if stateLoadState === 'loading'}
        <p class="text-sm text-zinc-500">Loading state…</p>
      {:else if stateLoadState === 'error'}
        <div class="bg-red-950 border border-red-800 rounded-lg p-4 text-sm text-red-300">
          {stateError}
        </div>
      {:else if stateData}

        <!-- Readiness cards -->
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {#each Object.entries(stateData.readiness) as [key, val]}
            <div class="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 flex items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="text-xs font-medium text-zinc-500 uppercase tracking-wide mb-1">
                  {key.replace(/_/g, ' ')}
                </div>
                <div class="text-sm font-medium {val ? 'text-emerald-400' : 'text-zinc-600'}">
                  {val ? 'Yes' : 'No'}
                </div>
              </div>
              <span class="shrink-0 w-2.5 h-2.5 rounded-full {val ? 'bg-emerald-400' : 'bg-zinc-700'}"></span>
            </div>
          {/each}
        </div>

        <!-- Service summary table -->
        <div class="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          <table class="cve-table w-full text-sm">
            <thead class="bg-zinc-800 border-b border-zinc-700">
              <tr>
                <th class="text-left px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Service</th>
                <th class="text-left px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Status / Value</th>
              </tr>
            </thead>
            <tbody>
              <tr class="border-b border-zinc-800">
                <td class="px-4 py-2.5 text-zinc-300">Validation</td>
                <td class="px-4 py-2.5">
                  <span class="font-mono text-xs {stateData.state.summary.validation_status === 'pass' ? 'text-emerald-400' : 'text-red-400'}">
                    {stateData.state.summary.validation_status}
                  </span>
                </td>
              </tr>
              <tr class="border-b border-zinc-800">
                <td class="px-4 py-2.5 text-zinc-300">Security</td>
                <td class="px-4 py-2.5">
                  <span class="font-mono text-xs {stateData.state.summary.security_status === 'pass' ? 'text-emerald-400' : stateData.state.summary.security_status === 'warning' ? 'text-amber-400' : 'text-red-400'}">
                    {stateData.state.summary.security_status}
                  </span>
                </td>
              </tr>
              <tr class="border-b border-zinc-800">
                <td class="px-4 py-2.5 text-zinc-300">Pending Tasks</td>
                <td class="px-4 py-2.5 font-mono text-xs text-zinc-400">{stateData.state.summary.total_tasks}</td>
              </tr>
              <tr class="border-b border-zinc-800">
                <td class="px-4 py-2.5 text-zinc-300">Missing Concepts</td>
                <td class="px-4 py-2.5 font-mono text-xs text-zinc-400">{stateData.state.summary.total_missing}</td>
              </tr>
              <tr class="border-b border-zinc-800">
                <td class="px-4 py-2.5 text-zinc-300">Feedback Entries</td>
                <td class="px-4 py-2.5 font-mono text-xs text-zinc-400">{stateData.state.summary.feedback_entry_count}</td>
              </tr>
              <tr>
                <td class="px-4 py-2.5 text-zinc-300">Graph Nodes</td>
                <td class="px-4 py-2.5 font-mono text-xs text-zinc-400">{stateData.state.summary.graph_node_count}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Blockers -->
        {#if stateData.blockers.length > 0}
          <div>
            <h3 class="text-xs font-semibold text-red-400 uppercase tracking-wide mb-2">Blockers</h3>
            <ul class="space-y-1.5">
              {#each stateData.blockers as b}
                <li class="bg-red-950 border border-red-800 rounded-md px-3 py-2 text-sm text-red-300">⛔ {b}</li>
              {/each}
            </ul>
          </div>
        {/if}

        <!-- Warnings -->
        {#if stateData.warnings.length > 0}
          <div>
            <h3 class="text-xs font-semibold text-amber-400 uppercase tracking-wide mb-2">Warnings</h3>
            <ul class="space-y-1.5">
              {#each stateData.warnings as w}
                <li class="bg-amber-950 border border-amber-800 rounded-md px-3 py-2 text-sm text-amber-300">⚠ {w}</li>
              {/each}
            </ul>
          </div>
        {/if}

        <!-- Raw JSON toggle -->
        <button
          on:click={() => showRawStateJson = !showRawStateJson}
          class="text-xs text-zinc-600 hover:text-zinc-400 underline"
        >
          {showRawStateJson ? 'Hide' : 'Show'} raw JSON
        </button>
        {#if showRawStateJson}
          <pre class="mt-1 text-xs bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-zinc-400 overflow-auto max-h-64">{JSON.stringify(stateData, null, 2)}</pre>
        {/if}
      {/if}
    </section>

    <!-- ═══════════════════════════════════════════════════════════════
         Recommendation Plan
         ═══════════════════════════════════════════════════════════════ -->
    <section class="space-y-4">
      <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wide">
        Recommendation Plan
        <span class="ml-2 text-xs font-normal text-zinc-600 normal-case">({selectedIntent})</span>
      </h2>

      {#if planLoadState === 'idle'}
        <p class="text-sm text-zinc-500">Select a vault and intent to generate a plan.</p>
      {:else if planLoadState === 'loading'}
        <p class="text-sm text-zinc-500">Building plan…</p>
      {:else if planLoadState === 'error'}
        <div class="bg-red-950 border border-red-800 rounded-lg p-4 text-sm text-red-300">
          {planError}
        </div>
      {:else if planData}

        <!-- Next best action banner -->
        {#if planData.next_best_action}
          <div class="bg-sky-950 border border-sky-800 rounded-lg p-4">
            <p class="text-xs font-semibold text-sky-500 uppercase tracking-wide mb-1">Next Best Action</p>
            <p class="text-sm font-medium text-sky-100">{planData.next_best_action.title}</p>
            <p class="text-xs text-sky-500 font-mono mt-0.5">{planData.next_best_action.action}</p>
          </div>
        {:else}
          <div class="bg-emerald-950 border border-emerald-800 rounded-lg p-4">
            <p class="text-sm text-emerald-300">✅ No actions required for this intent.</p>
          </div>
        {/if}

        <!-- Recommendations list -->
        {#if planData.recommendations.length > 0}
          <div class="space-y-2">
            {#each planData.recommendations as rec}
              <div class="border rounded-lg p-4 {SEVERITY_BG[rec.severity] ?? 'bg-zinc-900 border-zinc-800'}">
                <div class="flex items-start gap-3">
                  <span class="text-xs font-bold text-zinc-600 mt-0.5 shrink-0">#{rec.rank}</span>
                  <div class="flex-1 min-w-0">
                    <div class="flex flex-wrap items-center gap-2 mb-1">
                      <span class="text-sm font-semibold text-zinc-100">{rec.title}</span>
                      <span class="text-xs px-1.5 py-0.5 rounded font-medium border {SEVERITY_COLOUR[rec.severity] ?? 'text-zinc-500 border-zinc-600'} border-current bg-black/20">
                        {rec.severity}
                      </span>
                    </div>
                    <p class="text-sm text-zinc-400 mb-2">{rec.reason}</p>
                    <div class="flex gap-3 text-xs">
                      <a href={rec.links.ui} class="text-sky-400 hover:underline">Open in UI</a>
                      <span class="text-zinc-700">|</span>
                      <span class="text-zinc-600 font-mono">{rec.links.api}</span>
                    </div>
                  </div>
                </div>
              </div>
            {/each}
          </div>
        {/if}

        <!-- Raw JSON toggle -->
        <button
          on:click={() => showRawPlanJson = !showRawPlanJson}
          class="text-xs text-zinc-600 hover:text-zinc-400 underline"
        >
          {showRawPlanJson ? 'Hide' : 'Show'} raw JSON
        </button>
        {#if showRawPlanJson}
          <pre class="mt-1 text-xs bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-zinc-400 overflow-auto max-h-64">{JSON.stringify(planData, null, 2)}</pre>
        {/if}
      {/if}
    </section>
  {/if}
</div>
