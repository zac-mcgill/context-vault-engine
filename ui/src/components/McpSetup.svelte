<script lang="ts">
  /*
    McpSetup.svelte - Phase 39

    Static, read-only guidance page for configuring an MCP client to
    connect to this repository's local MCP stdio server. The page does
    not invoke any backend route and does not perform any write action.

    All copy is conservative: it does not claim compatibility with any
    specific external MCP client unless the repository actually tests
    that client. The repository only verifies its own stdio handshake
    via `py run.py mcp-smoke`.
  */

  let copyState: Record<string, 'idle' | 'copied' | 'failed'> = {};

  const stdioConfigSnippet = `{
  "servers": {
    "contextVaultEngine": {
      "type": "stdio",
      "command": "py",
      "args": ["run.py", "mcp"]
    }
  }
}`;

  const startCommand = 'py run.py mcp';
  const smokeCommand = 'py run.py mcp-smoke';
  const altStartCommand = 'python3 run.py mcp';

  async function copy(key: string, text: string): Promise<void> {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(text);
        copyState = { ...copyState, [key]: 'copied' };
        setTimeout(() => {
          copyState = { ...copyState, [key]: 'idle' };
        }, 1500);
        return;
      }
    } catch {
      // fall through
    }
    copyState = { ...copyState, [key]: 'failed' };
    setTimeout(() => {
      copyState = { ...copyState, [key]: 'idle' };
    }, 1500);
  }

  function label(key: string): string {
    const s = copyState[key];
    if (s === 'copied') return 'Copied';
    if (s === 'failed') return 'Copy failed';
    return 'Copy';
  }
</script>

<div class="cve-page">
  <header class="cve-toolbar">
    <div class="cve-toolbar__main">
      <h1 class="cve-toolbar__title">MCP Setup</h1>
      <div class="cve-toolbar__meta">
        <span>Local stdio</span>
        <span>Read-only guidance</span>
        <span>No backend call</span>
      </div>
    </div>
  </header>

  <div class="cve-banner cve-banner--info">
    <div class="cve-banner__body">
      The MCP server uses local stdio. It is not an HTTP endpoint and it
      does not use Private Cloud bearer-token authentication. Configure
      your MCP client to run the command from the repository root. The
      MCP surface exposed by this project is read-only with respect to
      vault notes: it can inspect vault state, query notes, build
      context, and return prompts/resources, but it must not directly
      create, edit, or delete notes. The only mutation pathway is the
      preview-first pending-change proposal workflow, which always
      requires explicit human acceptance in the local UI.
    </div>
  </div>

  <section class="cve-section" aria-label="What MCP stdio is">
    <h2 class="cve-section-title">What this is</h2>
    <p>
      The Context Vault Engine ships a local MCP server that speaks
      JSON-RPC 2.0 over stdin and stdout. An MCP-aware client launches
      the server as a subprocess and exchanges newline-delimited
      messages on the subprocess's stdio. There is no HTTP listener,
      no socket, and no network access required.
    </p>
    <p>
      The MCP stdio server is independent from the local web UI
      (<code>py run.py app</code>) and the local HTTP API. The web UI
      is not required to use MCP, and the MCP server does not require
      the web UI to be running.
    </p>
  </section>

  <section class="cve-section" aria-label="Start command">
    <h2 class="cve-section-title">Start command</h2>
    <p>
      Run the MCP stdio server from the <strong>repository root</strong>.
      The working directory must be the repository root so that
      <code>run.py</code> resolves <code>config/config.yaml</code> and
      the vault paths correctly.
    </p>
    <div class="cve-raw-block">
      <div class="cve-raw-block__toolbar">
        <span class="cve-raw-block__label">Windows (Python launcher)</span>
        <button
          type="button"
          class="cve-btn cve-btn-secondary"
          on:click={() => copy('start', startCommand)}
          data-testid="mcp-copy-start"
        >
          {label('start')}
        </button>
      </div>
      <pre class="cve-raw-block__body"><code>{startCommand}</code></pre>
    </div>
    <div class="cve-raw-block">
      <div class="cve-raw-block__toolbar">
        <span class="cve-raw-block__label">macOS / Linux</span>
        <button
          type="button"
          class="cve-btn cve-btn-secondary"
          on:click={() => copy('startAlt', altStartCommand)}
          data-testid="mcp-copy-start-alt"
        >
          {label('startAlt')}
        </button>
      </div>
      <pre class="cve-raw-block__body"><code>{altStartCommand}</code></pre>
    </div>
  </section>

  <section class="cve-section" aria-label="Generic stdio config snippet">
    <h2 class="cve-section-title">Generic stdio configuration</h2>
    <p>
      Example for MCP clients that support a stdio
      <code>command</code> / <code>args</code> / working-directory
      configuration. Adapt this snippet to your client's configuration
      format. Client configuration formats may vary.
    </p>
    <div class="cve-raw-block">
      <div class="cve-raw-block__toolbar">
        <span class="cve-raw-block__label">stdio config (example)</span>
        <button
          type="button"
          class="cve-btn cve-btn-secondary"
          on:click={() => copy('stdio', stdioConfigSnippet)}
          data-testid="mcp-copy-stdio"
        >
          {label('stdio')}
        </button>
      </div>
      <pre class="cve-raw-block__body"><code>{stdioConfigSnippet}</code></pre>
    </div>
    <p>
      A copy of this snippet is also committed at
      <code>.vscode/mcp.json</code> as a known-working workspace
      example. It contains no secrets and no absolute personal paths.
      Other MCP clients use different configuration schemas; consult
      your client's documentation.
    </p>
  </section>

  <section class="cve-section" aria-label="Connection test">
    <h2 class="cve-section-title">Connection test</h2>
    <p>
      To verify this repository's MCP stdio handshake without launching
      an external MCP client, run the deterministic smoke test from the
      repository root:
    </p>
    <div class="cve-raw-block">
      <div class="cve-raw-block__toolbar">
        <span class="cve-raw-block__label">Smoke test</span>
        <button
          type="button"
          class="cve-btn cve-btn-secondary"
          on:click={() => copy('smoke', smokeCommand)}
          data-testid="mcp-copy-smoke"
        >
          {label('smoke')}
        </button>
      </div>
      <pre class="cve-raw-block__body"><code>{smokeCommand}</code></pre>
    </div>
    <p>
      The smoke test spawns the MCP stdio server as a subprocess, sends
      a minimal JSON-RPC sequence
      (<code>initialize</code>, <code>tools/list</code>,
      <code>resources/list</code>, <code>prompts/list</code>, and a
      safe <code>cve_list_vaults</code> tool call), verifies that every
      stdout line parses as JSON-RPC 2.0, and exits non-zero on any
      failure. It does not modify any vault note. It does not require
      internet access.
    </p>
    <div class="cve-banner cve-banner--warning">
      <div class="cve-banner__body">
        The smoke test verifies this repository's MCP stdio handshake
        and advertised tools/resources/prompts. It does not prove
        compatibility with every external MCP client. Client
        configuration formats vary.
      </div>
    </div>
  </section>

  <section class="cve-section" aria-label="Troubleshooting">
    <h2 class="cve-section-title">Troubleshooting</h2>
    <ul>
      <li>
        <strong>Wrong working directory.</strong> The MCP client must
        launch the subprocess with the repository root as the working
        directory; otherwise vault paths and config will not resolve.
      </li>
      <li>
        <strong>Python launcher unavailable.</strong> On systems where
        <code>py</code> is not installed, use
        <code>python3 run.py mcp</code> or your platform's equivalent.
      </li>
      <li>
        <strong>Dependencies missing.</strong> Install with
        <code>pip install -r requirements.txt</code> inside the
        repository virtual environment before launching MCP.
      </li>
      <li>
        <strong>Stdout polluted by logs.</strong> Stdout is reserved
        for JSON-RPC 2.0 messages. Anything else on stdout will fail
        the smoke test and break MCP clients. Logs should go to stderr.
      </li>
      <li>
        <strong>JSON-RPC parse error in the client.</strong> Confirm
        the client speaks JSON-RPC 2.0 with newline-delimited messages.
      </li>
      <li>
        <strong>Client config format differs.</strong> The snippet
        above is a generic example. Adapt keys and paths to match your
        client's schema.
      </li>
      <li>
        <strong>No vaults found.</strong> Run
        <code>py run.py validate</code> first to confirm at least one
        configured vault is reachable.
      </li>
      <li>
        <strong>Private Cloud auth confusion.</strong> Private Cloud
        bearer-token authentication applies only to the local HTTP API
        when Private Cloud Mode is enabled. It does not apply to local
        MCP stdio.
      </li>
    </ul>
  </section>

  <section class="cve-section" aria-label="Compatibility caveat">
    <h2 class="cve-section-title">Compatibility caveat</h2>
    <div class="cve-banner cve-banner--info">
      <div class="cve-banner__body">
        This page verifies the repository's MCP stdio handshake, not
        every external MCP client. The repository does not claim
        compatibility with any specific MCP client unless that client
        has been tested against this server. Client configuration
        formats may vary.
      </div>
    </div>
  </section>
</div>
