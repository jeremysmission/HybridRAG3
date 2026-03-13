from __future__ import annotations

import html


def build_login_page_html(*, deployment_mode: str, auth_label: str) -> str:
    """Return the browser login page for shared deployments."""
    safe_mode = html.escape(str(deployment_mode or "development"))
    safe_label = html.escape(str(auth_label or "shared-token"))
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HybridRAG Shared Login</title>
  <style>
    :root {{
      --bg-a: #f4efe1;
      --bg-b: #dce9e3;
      --panel: rgba(255, 255, 255, 0.88);
      --ink: #143126;
      --muted: #4e6a5d;
      --accent: #0f7660;
      --accent-strong: #0a4f40;
      --border: rgba(20, 49, 38, 0.12);
      --danger: #8f2d2d;
      --shadow: 0 24px 60px rgba(20, 49, 38, 0.16);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Bahnschrift", "Aptos", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(218, 161, 94, 0.22), transparent 32%),
        radial-gradient(circle at bottom right, rgba(15, 118, 96, 0.20), transparent 28%),
        linear-gradient(145deg, var(--bg-a), var(--bg-b));
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .shell {{
      width: min(960px, 100%);
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 20px;
      align-items: stretch;
    }}
    .hero, .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .hero {{
      padding: 32px;
      display: grid;
      gap: 18px;
    }}
    .eyebrow {{
      margin: 0;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.78rem;
      color: var(--accent);
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.3rem);
      line-height: 0.96;
    }}
    .subcopy {{
      margin: 0;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.6;
      max-width: 38ch;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(15, 118, 96, 0.09);
      color: var(--accent-strong);
      font-size: 0.88rem;
      font-weight: 700;
    }}
    .panel {{
      padding: 28px;
      display: grid;
      gap: 16px;
      align-content: start;
    }}
    label {{
      font-size: 0.88rem;
      font-weight: 700;
      color: var(--muted);
    }}
    input {{
      width: 100%;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(20, 49, 38, 0.16);
      background: rgba(255, 255, 255, 0.96);
      color: var(--ink);
      font: inherit;
    }}
    button {{
      border: 0;
      border-radius: 14px;
      padding: 14px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      color: #fff;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      transition: transform 120ms ease, filter 120ms ease;
    }}
    button:hover {{
      transform: translateY(-1px);
      filter: brightness(1.03);
    }}
    .hint {{
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .feedback {{
      min-height: 1.4em;
      margin: 0;
      color: var(--danger);
      font-size: 0.92rem;
      font-weight: 700;
    }}
    @media (max-width: 860px) {{
      .shell {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">HybridRAG Shared Deployment</p>
      <h1>Browser access for the shared query console.</h1>
      <p class="subcopy">
        The API already exposes status, queue, audit, and query activity surfaces.
        This browser login issues a short-lived session cookie so the dashboard
        can poll those protected endpoints without repeating the shared token
        on every request.
      </p>
      <div class="badge-row">
        <span class="badge">Mode: {deployment_mode}</span>
        <span class="badge">Actor label: {auth_label}</span>
      </div>
    </section>
    <section class="panel">
      <h2 style="margin:0;">Sign in</h2>
      <p class="hint">
        Enter the shared deployment token for <strong>{auth_label}</strong>.
        The browser session stays same-origin, HTTP-only, and expires automatically.
      </p>
      <form id="login-form">
        <label for="token">Shared token</label>
        <input id="token" name="token" type="password" autocomplete="current-password" required>
        <button type="submit">Open dashboard</button>
      </form>
      <p class="feedback" id="feedback"></p>
      <p class="hint">
        If this deployment sits behind a trusted reverse proxy that injects user
        identity headers and a shared proof header, direct dashboard access can
        work without this form.
      </p>
    </section>
  </main>
  <script>
    const form = document.getElementById("login-form");
    const tokenInput = document.getElementById("token");
    const feedback = document.getElementById("feedback");
    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      feedback.textContent = "Signing in...";
      try {{
        const response = await fetch("/auth/login", {{
          method: "POST",
          credentials: "same-origin",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }},
          body: JSON.stringify({{ token: tokenInput.value }})
        }});
        const data = await response.json().catch(() => ({{ detail: "Sign-in failed." }}));
        if (!response.ok) {{
          feedback.textContent = data.detail || "Sign-in failed.";
          return;
        }}
        window.location.href = data.redirect_to || "/dashboard";
      }} catch (error) {{
        feedback.textContent = error instanceof Error ? error.message : "Sign-in failed.";
      }}
    }});
  </script>
</body>
</html>
""".format(
        deployment_mode=safe_mode,
        auth_label=safe_label,
    )


def build_dashboard_page_html() -> str:
    """Return the shared deployment dashboard shell."""
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HybridRAG Shared Console</title>
  <style>
    :root {{
      --bg-a: #eef3e5;
      --bg-b: #d9e7f2;
      --panel: rgba(255, 255, 255, 0.88);
      --line: rgba(18, 37, 51, 0.12);
      --ink: #122533;
      --muted: #506578;
      --accent: #0c7a63;
      --accent-alt: #c07a2a;
      --danger: #8b2f39;
      --shadow: 0 24px 60px rgba(18, 37, 51, 0.15);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Bahnschrift", "Aptos", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(192, 122, 42, 0.20), transparent 28%),
        radial-gradient(circle at bottom right, rgba(12, 122, 99, 0.16), transparent 24%),
        linear-gradient(150deg, var(--bg-a), var(--bg-b));
      padding: 20px;
    }}
    .shell {{
      max-width: 1240px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }}
    .hero, .panel, .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .hero {{
      padding: 24px;
      display: grid;
      gap: 16px;
    }}
    .hero-top {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }}
    .hero-copy {{
      display: grid;
      gap: 8px;
    }}
    .eyebrow {{
      margin: 0;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.78rem;
      color: var(--accent);
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3rem);
      line-height: 0.96;
    }}
    .summary {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      max-width: 54ch;
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    button, .link-button {{
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      transition: transform 120ms ease, filter 120ms ease;
    }}
    .primary {{
      color: #fff;
      background: linear-gradient(135deg, var(--accent), #095646);
    }}
    .secondary {{
      color: var(--ink);
      background: rgba(18, 37, 51, 0.08);
    }}
    button:hover, .link-button:hover {{
      transform: translateY(-1px);
      filter: brightness(1.03);
    }}
    button:disabled {{
      cursor: default;
      opacity: 0.56;
      transform: none;
      filter: none;
    }}
    .status-line {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-size: 0.95rem;
      align-items: center;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 7px 12px;
      border-radius: 999px;
      background: rgba(12, 122, 99, 0.10);
      color: #0b5b49;
      font-weight: 700;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }}
    .metric {{
      padding: 18px;
      display: grid;
      gap: 8px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .metric-value {{
      font-size: clamp(1.3rem, 3vw, 2.1rem);
      font-weight: 800;
      line-height: 1;
    }}
    .metric-meta {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .panel {{
      padding: 18px;
      display: grid;
      gap: 14px;
    }}
    .panel.wide {{
      grid-column: 1 / -1;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
    }}
    .panel h2 {{
      margin: 0;
      font-size: 1.05rem;
    }}
    .panel-note {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .kv {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 14px;
    }}
    .kv div {{
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(18, 37, 51, 0.05);
    }}
    .kv dt {{
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 700;
    }}
    .kv dd {{
      margin: 0;
      font-size: 1rem;
      font-weight: 700;
      word-break: break-word;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid rgba(18, 37, 51, 0.08);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .empty {{
      color: var(--muted);
      padding: 10px 8px;
      text-align: center;
    }}
    .query-form {{
      display: grid;
      gap: 12px;
    }}
    .query-form textarea {{
      width: 100%;
      min-height: 132px;
      resize: vertical;
      border-radius: 16px;
      border: 1px solid rgba(18, 37, 51, 0.12);
      background: rgba(255, 255, 255, 0.95);
      color: var(--ink);
      padding: 14px 16px;
      font: inherit;
      line-height: 1.5;
    }}
    .query-toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }}
    .query-status {{
      color: var(--muted);
      font-size: 0.92rem;
      font-weight: 700;
    }}
    .answer-shell {{
      display: grid;
      gap: 12px;
      padding: 16px;
      border-radius: 18px;
      background: rgba(18, 37, 51, 0.05);
    }}
    .answer-copy {{
      white-space: pre-wrap;
      line-height: 1.6;
    }}
    .source-list {{
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
      color: var(--muted);
    }}
    .danger {{
      color: var(--danger);
    }}
    @media (max-width: 980px) {{
      .metrics, .grid {{
        grid-template-columns: 1fr 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      body {{
        padding: 14px;
      }}
      .metrics, .grid, .kv {{
        grid-template-columns: 1fr;
      }}
      .hero-top {{
        align-items: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-copy">
          <p class="eyebrow">HybridRAG Shared Console</p>
          <h1>Deployment dashboard</h1>
          <p class="summary">
            Read-only deployment visibility for status, shared query capacity,
            indexing, recent queries, and network-gate audit activity. The page
            polls the existing FastAPI shared surfaces and redirects to browser
            login if the session expires.
          </p>
        </div>
        <div class="hero-actions">
          <button id="refresh-button" class="primary" type="button">Refresh now</button>
          <button id="logout-button" class="secondary" type="button">Sign out</button>
          <a class="link-button secondary" href="/docs">API docs</a>
        </div>
      </div>
      <div class="status-line">
        <span class="pill" id="banner-pill">Waiting for data</span>
        <span id="last-updated">Not loaded yet</span>
      </div>
    </section>

    <section class="metrics">
      <article class="metric">
        <span class="metric-label">Deployment</span>
        <span class="metric-value" id="metric-deployment">-</span>
        <span class="metric-meta" id="metric-user">-</span>
      </article>
      <article class="metric">
        <span class="metric-label">Query Queue</span>
        <span class="metric-value" id="metric-queue">-</span>
        <span class="metric-meta" id="metric-queue-meta">-</span>
      </article>
      <article class="metric">
        <span class="metric-label">Queries</span>
        <span class="metric-value" id="metric-queries">-</span>
        <span class="metric-meta" id="metric-queries-meta">-</span>
      </article>
      <article class="metric">
        <span class="metric-label">Network</span>
        <span class="metric-value" id="metric-network">-</span>
        <span class="metric-meta" id="metric-network-meta">-</span>
      </article>
    </section>

    <section class="grid">
      <article class="panel">
        <div class="panel-head">
          <h2>Auth context</h2>
          <span class="panel-note">Resolved request posture</span>
        </div>
        <dl class="kv">
          <div><dt>Actor</dt><dd id="auth-actor">-</dd></div>
          <div><dt>Auth mode</dt><dd id="auth-mode">-</dd></div>
          <div><dt>Actor source</dt><dd id="auth-source">-</dd></div>
          <div><dt>Client host</dt><dd id="auth-host">-</dd></div>
          <div><dt>Session</dt><dd id="auth-session">-</dd></div>
          <div><dt>Session expiry</dt><dd id="auth-session-expiry">-</dd></div>
          <div><dt>Time remaining</dt><dd id="auth-session-remaining">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Indexer status</h2>
          <span class="panel-note">Live in-memory snapshot</span>
        </div>
        <dl class="kv">
          <div><dt>Current file</dt><dd id="index-current-file">-</dd></div>
          <div><dt>Progress</dt><dd id="index-progress">-</dd></div>
          <div><dt>Processed</dt><dd id="index-processed">-</dd></div>
          <div><dt>Latest run</dt><dd id="index-latest-run">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Recent queries</h2>
          <span class="panel-note">Newest completed first</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>Actor</th>
              <th>Status</th>
              <th>Mode</th>
              <th>Latency</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="queries-table">
            <tr><td colspan="6" class="empty">Loading...</td></tr>
          </tbody>
        </table>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Latest recent query</h2>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <span class="panel-note">Most recent completed answer preview</span>
            <button id="recent-detail-reuse" class="secondary" type="button" disabled>Reuse</button>
          </div>
        </div>
        <dl class="kv">
          <div><dt>Question</dt><dd id="recent-detail-question">-</dd></div>
          <div><dt>Actor</dt><dd id="recent-detail-actor">-</dd></div>
          <div><dt>Status</dt><dd id="recent-detail-status">-</dd></div>
          <div><dt>Transport</dt><dd id="recent-detail-transport">-</dd></div>
        </dl>
        <div class="answer-shell">
          <div class="panel-head">
            <h2 style="font-size:0.98rem;">Answer preview</h2>
            <span class="panel-note" id="recent-detail-meta">No recent completed query.</span>
          </div>
          <div class="answer-copy" id="recent-detail-answer">Run a browser query or wait for recent shared activity.</div>
          <ol class="source-list" id="recent-detail-sources">
            <li>No recent source paths yet.</li>
          </ol>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Conversation threads</h2>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <span class="panel-note" id="thread-active-label">No active thread selected.</span>
            <span class="panel-note" id="thread-retention-note">Retention policy loading...</span>
            <button id="thread-export-button" class="secondary" type="button" disabled>Export thread</button>
            <button id="thread-clear-button" class="secondary" type="button" disabled>New thread</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Thread</th>
              <th>Actor</th>
              <th>Turns</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="threads-table">
            <tr><td colspan="5" class="empty">Loading...</td></tr>
          </tbody>
        </table>
        <div class="answer-shell">
          <div class="panel-head">
            <h2 style="font-size:0.98rem;">Selected thread</h2>
            <span class="panel-note" id="thread-detail-meta">Choose a saved conversation to inspect or resume.</span>
          </div>
          <ol class="source-list" id="thread-detail-turns">
            <li>No saved thread selected.</li>
          </ol>
        </div>
      </article>
      <article class="panel wide">
        <div class="panel-head">
          <h2>Ask the shared deployment</h2>
          <span class="panel-note">Runs through the same FastAPI `/query` and `/query/stream` paths</span>
        </div>
        <form id="query-form" class="query-form">
          <textarea
            id="query-input"
            name="question"
            placeholder="Ask a grounded question against the indexed corpus..."
            required
          ></textarea>
          <div class="query-toolbar">
            <div class="query-status" id="query-status">Ready</div>
            <label style="display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-weight:700;">
              <input id="query-stream-toggle" type="checkbox" checked>
              Stream response
            </label>
            <div style="display:inline-flex;gap:10px;">
              <button id="query-submit" class="primary" type="submit">Ask question</button>
              <button id="query-cancel" class="secondary" type="button" style="display:none;">Cancel</button>
            </div>
          </div>
        </form>
        <section class="answer-shell">
          <div class="panel-head">
            <h2 style="font-size:0.98rem;">Latest answer</h2>
            <span class="panel-note" id="answer-meta">No browser query submitted yet.</span>
          </div>
          <div class="answer-copy" id="answer-copy">Use the form above to run a shared browser query.</div>
          <ol class="source-list" id="answer-sources">
            <li>No sources yet.</li>
          </ol>
        </section>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Recent network activity</h2>
          <span class="panel-note">Newest checks first</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Host</th>
              <th>Purpose</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody id="network-table">
            <tr><td colspan="4" class="empty">Loading...</td></tr>
          </tbody>
        </table>
      </article>
    </section>
  </main>

  <script>
    const AUTO_REFRESH_MS = 15000;
    let activeQueryController = null;
    let activeThreadId = null;
    let selectedThreadId = null;

    function text(id, value) {{
      document.getElementById(id).textContent = value ?? "-";
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => {{
        return {{
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          "\"": "&quot;",
          "'": "&#39;"
        }}[char];
      }});
    }}

    async function fetchJson(url, options = {{}}) {{
      const response = await fetch(url, {{
        credentials: "same-origin",
        cache: "no-store",
        headers: {{ "Accept": "application/json" }},
        ...options
      }});
      if (response.status === 401) {{
        window.location.href = "/auth/login";
        throw new Error("Session expired");
      }}
      if (!response.ok) {{
        const detail = await response.json().then((data) => data.detail || response.statusText).catch(() => response.statusText);
        throw new Error(detail || "Request failed");
      }}
      return response.json();
    }}

    function renderQueryRows(items) {{
      const target = document.getElementById("queries-table");
      if (!Array.isArray(items) || items.length === 0) {{
        target.innerHTML = '<tr><td colspan="6" class="empty">No recent query activity.</td></tr>';
        return;
      }}
      target.innerHTML = items.slice(0, 8).map((item) => {{
        const statusClass = item.status === "error" ? "danger" : "";
        const latency = item.latency_ms == null ? "-" : `${{item.latency_ms.toFixed(1)}} ms`;
        const questionText = escapeHtml(item.question_text || item.question_preview || "");
        return `
          <tr>
            <td>${{escapeHtml(item.question_preview)}}</td>
            <td>${{escapeHtml(item.actor)}}</td>
            <td class="${{statusClass}}">${{escapeHtml(item.status)}}</td>
            <td>${{escapeHtml(item.mode)}}</td>
            <td>${{escapeHtml(latency)}}</td>
            <td><button class="secondary reuse-query-button" type="button" data-question="${{questionText}}">Reuse</button></td>
          </tr>
        `;
      }}).join("");
    }}

    function renderNetworkRows(items) {{
      const target = document.getElementById("network-table");
      if (!Array.isArray(items) || items.length === 0) {{
        target.innerHTML = '<tr><td colspan="4" class="empty">No network-gate activity recorded yet.</td></tr>';
        return;
      }}
      target.innerHTML = items.slice(0, 8).map((item) => {{
        const verdict = item.allowed ? "allowed" : "denied";
        const verdictClass = item.allowed ? "" : "danger";
        return `
          <tr>
            <td>${{escapeHtml(item.timestamp_iso)}}</td>
            <td>${{escapeHtml(item.host)}}</td>
            <td>${{escapeHtml(item.purpose)}}</td>
            <td class="${{verdictClass}}">${{escapeHtml(verdict)}}</td>
          </tr>
        `;
      }}).join("");
    }}

    function setActiveThread(threadId, label) {{
      activeThreadId = threadId ? String(threadId) : null;
      text(
        "thread-active-label",
        activeThreadId ? `Active thread: ${{label || activeThreadId}}` : "No active thread selected."
      );
      document.getElementById("thread-clear-button").disabled = !activeThreadId;
    }}

    function setThreadExportButton(threadId) {{
      const button = document.getElementById("thread-export-button");
      const key = String(threadId || "").trim();
      button.disabled = !key;
      button.dataset.threadId = key;
    }}

    function updateThreadRetentionNote(history) {{
      const total = Number(history?.total_threads ?? 0);
      const maxThreads = Number(history?.max_threads ?? 0);
      const maxTurns = Number(history?.max_turns_per_thread ?? 0);
      if (maxThreads > 0 && maxTurns > 0) {{
        text(
          "thread-retention-note",
          `Saved ${{total}} threads / cap ${{maxThreads}} / ${{maxTurns}} turns per thread`
        );
        return;
      }}
      text("thread-retention-note", `Saved ${{total}} threads`);
    }}

    function renderThreadRows(items) {{
      const target = document.getElementById("threads-table");
      if (!Array.isArray(items) || items.length === 0) {{
        target.innerHTML = '<tr><td colspan="5" class="empty">No saved conversation threads yet.</td></tr>';
        return;
      }}
      target.innerHTML = items.slice(0, 8).map((item) => {{
        const statusClass = item.last_status === "error" ? "danger" : "";
        const threadLabel = escapeHtml(item.title || item.last_question_preview || item.thread_id || "Conversation");
        return `
          <tr>
            <td>${{threadLabel}}</td>
            <td>${{escapeHtml(item.last_actor || item.created_by_actor || "-")}}</td>
            <td>${{escapeHtml(item.turn_count)}}</td>
            <td class="${{statusClass}}">${{escapeHtml(item.last_status || "-")}}</td>
            <td><button class="secondary thread-resume-button" type="button" data-thread-id="${{escapeHtml(item.thread_id)}}" data-thread-label="${{threadLabel}}">Resume</button></td>
          </tr>
        `;
      }}).join("");
    }}

    function renderThreadDetail(snapshot) {{
      if (!snapshot || !snapshot.thread) {{
        text("thread-detail-meta", "Choose a saved conversation to inspect or resume.");
        document.getElementById("thread-detail-turns").innerHTML = "<li>No saved thread selected.</li>";
        setThreadExportButton(null);
        return;
      }}

      const thread = snapshot.thread;
      const turns = Array.isArray(snapshot.turns) ? snapshot.turns : [];
      const meta = [];
      meta.push(`${{thread.turn_count}} turns`);
      if (thread.last_actor) meta.push(`Last actor: ${{thread.last_actor}}`);
      if (thread.last_status) meta.push(`Status: ${{thread.last_status}}`);
      text("thread-detail-meta", meta.join(" / "));
      setThreadExportButton(thread.thread_id);

      if (!turns.length) {{
        document.getElementById("thread-detail-turns").innerHTML = "<li>No saved turns yet.</li>";
        return;
      }}

      document.getElementById("thread-detail-turns").innerHTML = turns.slice(-6).map((turn) => {{
        const answer = escapeHtml(turn.answer_preview || turn.answer_text || turn.error || "No answer stored.");
        return `
          <li>
            <strong>Q:</strong> ${{escapeHtml(turn.question_preview || turn.question_text || "-")}}<br>
            <strong>A:</strong> ${{answer}}
          </li>
        `;
      }}).join("");
    }}

    async function loadThreadDetail(threadId, options = {{}}) {{
      const key = String(threadId || "").trim();
      if (!key) {{
        renderThreadDetail(null);
        return;
      }}
      const snapshot = await fetchJson(`/history/threads/${{encodeURIComponent(key)}}`);
      selectedThreadId = key;
      renderThreadDetail(snapshot);
      if (options.makeActive) {{
        setActiveThread(
          key,
          snapshot.thread.title || snapshot.thread.last_question_preview || key
        );
      }}
    }}

    async function refreshThreadHistory(preferredThreadId = null) {{
      try {{
        const history = await fetchJson("/history/threads?limit=8");
        const threads = Array.isArray(history.threads) ? history.threads : [];
        updateThreadRetentionNote(history);
        renderThreadRows(threads);
        const targetId = preferredThreadId || selectedThreadId || activeThreadId;
        if (targetId) {{
          await loadThreadDetail(targetId, {{ makeActive: false }});
        }} else if (threads.length) {{
          await loadThreadDetail(threads[0].thread_id, {{ makeActive: false }});
        }} else {{
          renderThreadDetail(null);
        }}
      }} catch (_error) {{
        text("thread-retention-note", "Conversation retention unavailable.");
        document.getElementById("threads-table").innerHTML =
          '<tr><td colspan="5" class="empty">Conversation history unavailable.</td></tr>';
        renderThreadDetail(null);
      }}
    }}

    async function adoptQueryThread(result) {{
      const threadId = String(result?.thread_id || "").trim();
      if (!threadId) {{
        return;
      }}
      await loadThreadDetail(threadId, {{ makeActive: true }});
    }}

    function clearActiveThread() {{
      activeThreadId = null;
      selectedThreadId = null;
      setActiveThread(null, "");
      renderThreadDetail(null);
      setThreadExportButton(null);
      document.getElementById("query-status").textContent = "New standalone question ready.";
    }}

    function renderRecentQueryDetail(items) {{
      const latest = Array.isArray(items) && items.length ? items[0] : null;
      if (!latest) {{
        text("recent-detail-question", "-");
        text("recent-detail-actor", "-");
        text("recent-detail-status", "-");
        text("recent-detail-transport", "-");
        text("recent-detail-meta", "No recent completed query.");
        document.getElementById("recent-detail-answer").textContent = "Run a browser query or wait for recent shared activity.";
        document.getElementById("recent-detail-sources").innerHTML = "<li>No recent source paths yet.</li>";
        document.getElementById("recent-detail-reuse").disabled = true;
        document.getElementById("recent-detail-reuse").dataset.question = "";
        return;
      }}

      text("recent-detail-question", latest.question_preview || "-");
      text("recent-detail-actor", latest.actor || "-");
      text("recent-detail-status", latest.status || "-");
      text("recent-detail-transport", latest.transport || "-");

      const meta = [];
      if (latest.mode) meta.push(`Mode: ${{latest.mode}}`);
      if (Number.isFinite(latest.latency_ms)) meta.push(`Latency: ${{latest.latency_ms.toFixed(1)}} ms`);
      if (Number.isFinite(latest.chunks_used)) meta.push(`Chunks: ${{latest.chunks_used}}`);
      text("recent-detail-meta", meta.length ? meta.join(" / ") : "Recent query detail");
      document.getElementById("recent-detail-answer").textContent =
        latest.answer_preview || latest.error || "No answer preview stored.";

      const sourceList = document.getElementById("recent-detail-sources");
      const paths = Array.isArray(latest.source_paths) ? latest.source_paths : [];
      const reuseButton = document.getElementById("recent-detail-reuse");
      reuseButton.disabled = !(latest.question_text || latest.question_preview);
      reuseButton.dataset.question = latest.question_text || latest.question_preview || "";
      if (!paths.length) {{
        sourceList.innerHTML = "<li>No recent source paths yet.</li>";
        return;
      }}
      sourceList.innerHTML = paths.map((path) => `<li>${{escapeHtml(path)}}</li>`).join("");
    }}

    function reuseRecentQuestion(question) {{
      const value = String(question || "").trim();
      if (!value) {{
        return;
      }}
      const input = document.getElementById("query-input");
      input.value = value;
      input.focus();
      input.setSelectionRange(value.length, value.length);
      document.getElementById("query-status").textContent = "Loaded recent question into composer.";
    }}

    function renderAnswer(result) {{
      const meta = [];
      if (result.mode) meta.push(`Mode: ${{result.mode}}`);
      if (Number.isFinite(result.latency_ms)) meta.push(`Latency: ${{result.latency_ms.toFixed(1)}} ms`);
      if (Number.isFinite(result.chunks_used)) meta.push(`Chunks: ${{result.chunks_used}}`);
      document.getElementById("answer-meta").textContent = meta.length ? meta.join(" / ") : "Answer received";
      document.getElementById("answer-copy").textContent = result.answer || result.error || "No answer returned.";

      const sources = Array.isArray(result.sources) ? result.sources : [];
      const sourceList = document.getElementById("answer-sources");
      if (!sources.length) {{
        sourceList.innerHTML = "<li>No cited sources returned.</li>";
        return;
      }}
      sourceList.innerHTML = sources.slice(0, 6).map((source) => {{
        const path = source.path || "unknown source";
        const chunks = source.chunks == null ? "-" : source.chunks;
        const score = source.avg_relevance == null ? "-" : source.avg_relevance;
        return `<li><strong>${{escapeHtml(path)}}</strong> <span>chunks=${{escapeHtml(chunks)}} score=${{escapeHtml(score)}}</span></li>`;
      }}).join("");
    }}

    function resetAnswerShell(message) {{
      document.getElementById("answer-meta").textContent = "Waiting for answer";
      document.getElementById("answer-copy").textContent = message || "Working...";
      document.getElementById("answer-sources").innerHTML = "<li>No sources yet.</li>";
    }}

    function setQueryBusy(isBusy) {{
      document.getElementById("query-submit").disabled = isBusy;
      document.getElementById("query-cancel").style.display = isBusy ? "inline-flex" : "none";
    }}

    function renderDashboard(status, auth, queries, network) {{
      text("banner-pill", status.status === "ok" ? "Server ready" : status.status);
      text("last-updated", `Last updated ${{new Date().toLocaleTimeString()}}`);

      text("metric-deployment", `${{status.deployment_mode}} / ${{status.mode}}`);
      text("metric-user", `Current user: ${{status.current_user}}`);

      if (status.query_queue.enabled) {{
        text("metric-queue", `${{status.query_queue.active_queries}} active`);
        text(
          "metric-queue-meta",
          `${{status.query_queue.waiting_queries}} waiting / ${{status.query_queue.available_slots}} open slots`
        );
      }} else {{
        text("metric-queue", "disabled");
        text("metric-queue-meta", "Shared queue limit is not configured.");
      }}

      text("metric-queries", `${{status.query_activity.active_queries}} active`);
      text(
        "metric-queries-meta",
        `${{status.query_activity.total_completed}} complete / ${{status.query_activity.total_failed}} failed`
      );

      text("metric-network", `${{status.network_audit.allowed}} allowed`);
      text(
        "metric-network-meta",
        `${{status.network_audit.denied}} denied across ${{status.network_audit.unique_hosts_contacted.length}} hosts`
      );

      text("auth-actor", auth.actor);
      text("auth-mode", auth.auth_mode);
      text("auth-source", auth.actor_source);
      text("auth-host", auth.client_host);
      text("auth-session", auth.session_cookie_active ? "active" : "not in use");
      text("auth-session-expiry", auth.session_expires_at || "n/a");
      text("auth-session-remaining", formatRemaining(auth.session_seconds_remaining));

      text("index-current-file", status.indexing.current_file || "Idle");
      text("index-progress", `${{status.indexing.progress_pct}}% in ${{status.indexing.elapsed_seconds}}s`);
      text(
        "index-processed",
        `${{status.indexing.files_processed}} / ${{status.indexing.files_total}} files`
      );
      if (status.latest_index_run) {{
        text(
          "index-latest-run",
          `${{status.latest_index_run.status}} on ${{status.latest_index_run.host}} by ${{status.latest_index_run.user}}`
        );
      }} else {{
        text("index-latest-run", "No persisted run summary");
      }}

      renderQueryRows(queries.recent || []);
      renderRecentQueryDetail(queries.recent || []);
      renderNetworkRows(network.entries || []);

      const logout = document.getElementById("logout-button");
      logout.style.display = auth.auth_required ? "inline-flex" : "none";
    }}

    async function refreshDashboard() {{
      try {{
        const snapshot = await fetchJson("/dashboard/data");
        renderDashboard(
          snapshot.status || {{}},
          snapshot.auth || {{}},
          snapshot.queries || {{}},
          snapshot.network || {{}}
        );
        await refreshThreadHistory();
      }} catch (error) {{
        text("banner-pill", "Refresh failed");
        text("last-updated", error instanceof Error ? error.message : "Refresh failed");
      }}
    }}

    function formatRemaining(seconds) {{
      if (!Number.isFinite(seconds) || seconds < 0) {{
        return "n/a";
      }}
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${{mins}}m ${{secs}}s`;
    }}

    async function submitBrowserQuery(event) {{
      event.preventDefault();
      const input = document.getElementById("query-input");
      const status = document.getElementById("query-status");
      const streamToggle = document.getElementById("query-stream-toggle");
      const question = input.value.trim();
      if (!question) {{
        status.textContent = "Question required.";
        return;
      }}

      resetAnswerShell("Preparing query...");
      setQueryBusy(true);
      status.textContent = streamToggle.checked ? "Streaming query..." : "Query running...";
      try {{
        if (streamToggle.checked) {{
          await submitStreamingBrowserQuery(question, status);
        }} else {{
          const payload = {{ question }};
          if (activeThreadId) {{
            payload.thread_id = activeThreadId;
          }}
          const result = await fetchJson("/query", {{
            method: "POST",
            headers: {{
              "Accept": "application/json",
              "Content-Type": "application/json"
            }},
            body: JSON.stringify(payload)
          }});
          renderAnswer(result);
          await adoptQueryThread(result);
          status.textContent = result.error ? "Completed with backend warning." : "Query complete.";
          await refreshDashboard();
        }}
      }} catch (error) {{
        if (error && error.name === "AbortError") {{
          document.getElementById("answer-meta").textContent = "Query canceled";
          if (!document.getElementById("answer-copy").textContent) {{
            document.getElementById("answer-copy").textContent = "Streaming query canceled by operator.";
          }}
          status.textContent = "Query canceled.";
          return;
        }}
        document.getElementById("answer-meta").textContent = "Query failed";
        document.getElementById("answer-copy").textContent = error instanceof Error ? error.message : "Query failed.";
        document.getElementById("answer-sources").innerHTML = "<li>No sources returned.</li>";
        status.textContent = "Query failed.";
      }} finally {{
        activeQueryController = null;
        setQueryBusy(false);
      }}
    }}

    async function submitStreamingBrowserQuery(question, statusTarget) {{
      activeQueryController = new AbortController();
      document.getElementById("answer-meta").textContent = "Streaming answer";
      document.getElementById("answer-copy").textContent = "";
      const response = await fetch("/query/stream", {{
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {{
          "Accept": "text/event-stream",
          "Content-Type": "application/json"
        }},
        body: JSON.stringify(activeThreadId ? {{ question, thread_id: activeThreadId }} : {{ question }}),
        signal: activeQueryController.signal
      }});
      if (response.status === 401) {{
        window.location.href = "/auth/login";
        throw new Error("Session expired");
      }}
      if (!response.ok) {{
        const detail = await response.text().catch(() => response.statusText);
        throw new Error(detail || "Streaming request failed");
      }}
      if (!response.body) {{
        throw new Error("Streaming response body unavailable");
      }}

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let renderedToken = false;

      while (true) {{
        const {{ value, done }} = await reader.read();
        if (done) {{
          break;
        }}
        buffer += decoder.decode(value, {{ stream: true }});
        const parts = buffer.split("\\n\\n");
        buffer = parts.pop() || "";
        for (const part of parts) {{
          const event = parseSseEvent(part);
          if (!event) {{
            continue;
          }}
          if (event.type === "phase") {{
            statusTarget.textContent = `Streaming: ${{event.data}}`;
            continue;
          }}
          if (event.type === "token") {{
            if (!renderedToken) {{
              document.getElementById("answer-copy").textContent = "";
              renderedToken = true;
            }}
            document.getElementById("answer-copy").textContent += event.data;
            continue;
          }}
          if (event.type === "done") {{
            const result = JSON.parse(event.data || "{{}}");
            renderAnswer(result);
            await adoptQueryThread(result);
            statusTarget.textContent = result.error ? "Completed with backend warning." : "Query complete.";
            await refreshDashboard();
            continue;
          }}
          if (event.type === "error") {{
            throw new Error(event.data || "Streaming query failed");
          }}
        }}
      }}
    }}

    function parseSseEvent(rawBlock) {{
      const lines = String(rawBlock || "").split("\\n");
      let type = "message";
      const data = [];
      for (const line of lines) {{
        if (line.startsWith("event:")) {{
          type = line.slice(6).trim();
        }} else if (line.startsWith("data:")) {{
          data.push(line.slice(5).trimStart());
        }}
      }}
      if (!type && data.length === 0) {{
        return null;
      }}
      return {{ type, data: data.join("\\n") }};
    }}

    document.getElementById("refresh-button").addEventListener("click", refreshDashboard);
    document.getElementById("logout-button").addEventListener("click", async () => {{
      try {{
        const response = await fetchJson("/auth/logout", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        window.location.href = response.redirect_to || "/auth/login";
      }} catch (_error) {{
        window.location.href = "/auth/login";
      }}
    }});
    document.getElementById("query-cancel").addEventListener("click", () => {{
      if (activeQueryController) {{
        activeQueryController.abort();
        activeQueryController = null;
        setQueryBusy(false);
        document.getElementById("query-status").textContent = "Query canceled.";
        document.getElementById("answer-meta").textContent = "Query canceled";
        if (!document.getElementById("answer-copy").textContent) {{
          document.getElementById("answer-copy").textContent = "Streaming query canceled by operator.";
        }}
      }}
    }});
    document.getElementById("recent-detail-reuse").addEventListener("click", (event) => {{
      reuseRecentQuestion(event.currentTarget.dataset.question || "");
    }});
    document.getElementById("queries-table").addEventListener("click", (event) => {{
      const button = event.target.closest(".reuse-query-button");
      if (!button) {{
        return;
      }}
      reuseRecentQuestion(button.dataset.question || "");
    }});
    document.getElementById("threads-table").addEventListener("click", async (event) => {{
      const button = event.target.closest(".thread-resume-button");
      if (!button) {{
        return;
      }}
      const threadId = button.dataset.threadId || "";
      const threadLabel = button.dataset.threadLabel || threadId;
      setActiveThread(threadId, threadLabel);
      await loadThreadDetail(threadId, {{ makeActive: false }});
      document.getElementById("query-status").textContent = "Loaded saved thread for follow-up.";
    }});
    document.getElementById("thread-export-button").addEventListener("click", () => {{
      const key = String(
        document.getElementById("thread-export-button").dataset.threadId || selectedThreadId || activeThreadId || ""
      ).trim();
      if (!key) {{
        return;
      }}
      window.location.href = `/history/threads/${{encodeURIComponent(key)}}/export`;
    }});
    document.getElementById("thread-clear-button").addEventListener("click", clearActiveThread);
    document.getElementById("query-form").addEventListener("submit", submitBrowserQuery);

    refreshDashboard();
    window.setInterval(refreshDashboard, AUTO_REFRESH_MS);
  </script>
</body>
</html>
"""


def build_admin_console_html() -> str:
    """Return the Admin web console shell."""
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HybridRAG Admin Console</title>
  <style>
    :root {{
      --bg-a: #f1ede3;
      --bg-b: #dce5ee;
      --panel: rgba(255, 255, 255, 0.9);
      --line: rgba(19, 33, 49, 0.12);
      --ink: #132131;
      --muted: #556577;
      --accent: #9a4f14;
      --accent-strong: #6d340c;
      --accent-soft: rgba(154, 79, 20, 0.10);
      --shadow: 0 24px 60px rgba(19, 33, 49, 0.14);
      --danger: #8a2f38;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Bahnschrift", "Aptos", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(154, 79, 20, 0.18), transparent 28%),
        radial-gradient(circle at bottom right, rgba(12, 88, 117, 0.16), transparent 24%),
        linear-gradient(155deg, var(--bg-a), var(--bg-b));
      padding: 20px;
    }}
    .shell {{
      max-width: 1320px;
      margin: 0 auto;
      display: grid;
      gap: 18px;
    }}
    .hero, .panel, .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .hero {{
      padding: 24px;
      display: grid;
      gap: 16px;
    }}
    .hero-top {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }}
    .eyebrow {{
      margin: 0;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.78rem;
      color: var(--accent);
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3rem);
      line-height: 0.96;
    }}
    .summary {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.55;
      max-width: 60ch;
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    button, .link-button {{
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      transition: transform 120ms ease, filter 120ms ease;
    }}
    .primary {{
      color: #fff;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
    }}
    .secondary {{
      color: var(--ink);
      background: rgba(19, 33, 49, 0.08);
    }}
    button:hover, .link-button:hover {{
      transform: translateY(-1px);
      filter: brightness(1.03);
    }}
    .status-line {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--muted);
      font-size: 0.95rem;
      align-items: center;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 7px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      font-weight: 700;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }}
    .metric {{
      padding: 18px;
      display: grid;
      gap: 8px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    .metric-value {{
      font-size: clamp(1.3rem, 3vw, 2.1rem);
      font-weight: 800;
      line-height: 1;
    }}
    .metric-meta {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .panel {{
      padding: 18px;
      display: grid;
      gap: 14px;
    }}
    .panel.wide {{
      grid-column: 1 / -1;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
    }}
    .panel h2 {{
      margin: 0;
      font-size: 1.05rem;
    }}
    .panel-note {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .kv {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px 14px;
    }}
    .kv div {{
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(19, 33, 49, 0.05);
    }}
    .kv dt {{
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 700;
    }}
    .kv dd {{
      margin: 0;
      font-size: 1rem;
      font-weight: 700;
      word-break: break-word;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid rgba(19, 33, 49, 0.08);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .trace-box {{
      margin: 0;
      padding: 16px;
      border-radius: 18px;
      background: #0f1721;
      color: #d9e4ef;
      font: 0.9rem/1.45 Consolas, "Courier New", monospace;
      white-space: pre-wrap;
      overflow-x: auto;
      min-height: 220px;
    }}
    .trace-layout {{
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }}
    .trace-list {{
      display: grid;
      gap: 10px;
    }}
    .trace-item {{
      width: 100%;
      border: 1px solid rgba(19, 33, 49, 0.1);
      border-radius: 16px;
      background: rgba(244, 247, 250, 0.92);
      padding: 12px 14px;
      text-align: left;
      color: var(--ink);
      display: grid;
      gap: 4px;
      cursor: pointer;
    }}
    .trace-item:hover {{
      border-color: rgba(19, 33, 49, 0.22);
      box-shadow: 0 10px 18px rgba(19, 33, 49, 0.08);
    }}
    .trace-item.is-active {{
      border-color: var(--accent);
      background: rgba(220, 236, 255, 0.92);
      box-shadow: 0 12px 20px rgba(20, 83, 148, 0.14);
    }}
    .trace-item-time {{
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 700;
    }}
    .trace-item-query {{
      font-size: 0.96rem;
      font-weight: 700;
      line-height: 1.35;
      word-break: break-word;
    }}
    .trace-item-meta {{
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .empty {{
      color: var(--muted);
      padding: 10px 8px;
      text-align: center;
    }}
    @media (max-width: 980px) {{
      .metrics, .grid {{
        grid-template-columns: 1fr 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      body {{
        padding: 14px;
      }}
      .metrics, .grid, .kv {{
        grid-template-columns: 1fr;
      }}
      .trace-layout {{
        grid-template-columns: 1fr;
      }}
      .hero-top {{
        align-items: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div>
          <p class="eyebrow">HybridRAG Operator Surface</p>
          <h1>Unified Admin Console</h1>
          <p class="summary">
            Operator-focused visibility for deployment status, queue pressure, network audit,
            runtime config, and the latest retrieval trace. This shell is the first Sprint 7
            bridge from endpoint-only diagnostics into a coherent web console.
          </p>
        </div>
        <div class="hero-actions">
          <button id="refresh-button" class="primary" type="button">Refresh admin data</button>
          <button id="start-index-button" class="secondary" type="button">Start indexing</button>
          <button id="reindex-stale-button" class="secondary" type="button">Reindex if stale</button>
          <button id="stop-index-button" class="secondary" type="button" disabled>Stop indexing</button>
          <a class="link-button secondary" href="/dashboard">Shared console</a>
          <a class="link-button secondary" href="/docs">API docs</a>
          <button id="logout-button" class="secondary" type="button">Sign out</button>
        </div>
      </div>
      <div class="status-line">
        <span class="pill" id="banner-pill">Waiting for admin data</span>
        <span id="last-updated">Not loaded yet</span>
      </div>
    </section>

    <section class="metrics">
      <article class="metric">
        <span class="metric-label">Deployment</span>
        <span class="metric-value" id="metric-deployment">-</span>
        <span class="metric-meta" id="metric-user">-</span>
      </article>
      <article class="metric">
        <span class="metric-label">Queue</span>
        <span class="metric-value" id="metric-queue">-</span>
        <span class="metric-meta" id="metric-queue-meta">-</span>
      </article>
      <article class="metric">
        <span class="metric-label">Indexing</span>
        <span class="metric-value" id="metric-indexing">-</span>
        <span class="metric-meta" id="metric-indexing-meta">-</span>
      </article>
      <article class="metric">
        <span class="metric-label">Trace</span>
        <span class="metric-value" id="metric-trace">-</span>
        <span class="metric-meta" id="metric-trace-meta">-</span>
      </article>
    </section>

    <section class="grid">
      <article class="panel">
        <div class="panel-head">
          <h2>Auth context</h2>
          <span class="panel-note">Resolved operator posture</span>
        </div>
        <dl class="kv">
          <div><dt>Actor</dt><dd id="auth-actor">-</dd></div>
          <div><dt>Auth mode</dt><dd id="auth-mode">-</dd></div>
          <div><dt>Actor source</dt><dd id="auth-source">-</dd></div>
          <div><dt>Client host</dt><dd id="auth-host">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Runtime config</h2>
          <span class="panel-note">Current shared query/runtime settings</span>
        </div>
        <dl class="kv">
          <div><dt>Mode</dt><dd id="config-mode">-</dd></div>
          <div><dt>Embedding</dt><dd id="config-embedding">-</dd></div>
          <div><dt>Ollama</dt><dd id="config-ollama">-</dd></div>
          <div><dt>API model</dt><dd id="config-api">-</dd></div>
          <div><dt>Retrieval</dt><dd id="config-retrieval">-</dd></div>
          <div><dt>Reranker</dt><dd id="config-reranker">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Runtime safety</h2>
          <span class="panel-note">Current auth, profile, proxy, and path boundaries</span>
        </div>
        <dl class="kv">
          <div><dt>Deployment</dt><dd id="safety-deployment">-</dd></div>
          <div><dt>Shared online</dt><dd id="safety-shared-online">-</dd></div>
          <div><dt>Active profile</dt><dd id="safety-profile">-</dd></div>
          <div><dt>Query policy</dt><dd id="safety-query-policy">-</dd></div>
          <div><dt>Auth label</dt><dd id="safety-auth">-</dd></div>
          <div><dt>Browser session</dt><dd id="safety-session">-</dd></div>
          <div><dt>Trusted proxy</dt><dd id="safety-proxy">-</dd></div>
          <div><dt>History protection</dt><dd id="safety-history">-</dd></div>
          <div><dt>Data paths</dt><dd id="safety-paths">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Data protection</h2>
          <span class="panel-note">Protected-root posture for the main and history databases</span>
        </div>
        <dl class="kv">
          <div><dt>Summary</dt><dd id="storage-summary">-</dd></div>
          <div><dt>Mode</dt><dd id="storage-mode">-</dd></div>
          <div><dt>Required</dt><dd id="storage-required">-</dd></div>
          <div><dt>Protected roots</dt><dd id="storage-roots">-</dd></div>
          <div><dt>Protected paths</dt><dd id="storage-paths-protected">-</dd></div>
          <div><dt>Unprotected paths</dt><dd id="storage-paths-unprotected">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Policy review</h2>
          <span class="panel-note">Active role maps, document-tag rules, and deny posture</span>
        </div>
        <dl class="kv">
          <div><dt>Default tags</dt><dd id="policy-default-tags">-</dd></div>
          <div><dt>Role map</dt><dd id="policy-role-map">-</dd></div>
          <div><dt>Role tag policy</dt><dd id="policy-role-tags">-</dd></div>
          <div><dt>Document tag rules</dt><dd id="policy-doc-rules">-</dd></div>
          <div><dt>Deny audit</dt><dd id="policy-denied">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Index schedule</h2>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <span class="panel-note">Scheduled indexing cadence and latest runner state</span>
            <button id="pause-schedule-button" class="secondary" type="button">Pause schedule</button>
            <button id="resume-schedule-button" class="secondary" type="button">Resume schedule</button>
          </div>
        </div>
        <dl class="kv">
          <div><dt>Status</dt><dd id="schedule-status">-</dd></div>
          <div><dt>Interval</dt><dd id="schedule-interval">-</dd></div>
          <div><dt>Next run</dt><dd id="schedule-next">-</dd></div>
          <div><dt>Last run</dt><dd id="schedule-last">-</dd></div>
          <div><dt>Source</dt><dd id="schedule-source">-</dd></div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Freshness and drift</h2>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <span class="panel-note">Source changes since the last recorded index run</span>
            <button id="recheck-freshness-button" class="secondary" type="button">Recheck freshness</button>
          </div>
        </div>
        <dl class="kv">
          <div><dt>Freshness</dt><dd id="freshness-status">-</dd></div>
          <div><dt>Last index</dt><dd id="freshness-last-index">-</dd></div>
          <div><dt>Latest source update</dt><dd id="freshness-source-update">-</dd></div>
          <div><dt>Drift</dt><dd id="freshness-drift">-</dd></div>
          <div><dt>Source path</dt><dd id="freshness-source-path">-</dd></div>
        </dl>
      </article>
      <article class="panel wide">
        <div class="panel-head">
          <h2>Active alerts</h2>
          <span class="panel-note" id="alerts-summary">No active alerts.</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Severity</th>
              <th>Code</th>
              <th>Message</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="alerts-table">
            <tr><td colspan="4" class="empty">No active alerts.</td></tr>
          </tbody>
        </table>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Security activity</h2>
          <span class="panel-note" id="security-summary">No recent security activity.</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Event</th>
              <th>Host</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody id="security-table">
            <tr><td colspan="4" class="empty">No recent security activity.</td></tr>
          </tbody>
        </table>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Recent queries</h2>
          <span class="panel-note">Newest completed first</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>Actor</th>
              <th>Status</th>
              <th>Mode</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody id="queries-table">
            <tr><td colspan="5" class="empty">Loading...</td></tr>
          </tbody>
        </table>
      </article>
      <article class="panel wide">
        <div class="panel-head">
          <h2>Conversation history</h2>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <span class="panel-note" id="admin-thread-retention-note">Retention policy loading...</span>
            <button id="admin-thread-export-button" class="secondary" type="button" disabled>Export thread</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Thread</th>
              <th>Actor</th>
              <th>Turns</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="admin-threads-table">
            <tr><td colspan="5" class="empty">Loading...</td></tr>
          </tbody>
        </table>
        <div class="answer-shell">
          <div class="panel-head">
            <h2 style="font-size:0.98rem;">Selected thread</h2>
            <span class="panel-note" id="admin-thread-detail-meta">Choose a saved conversation to inspect or export.</span>
          </div>
          <ol class="source-list" id="admin-thread-detail-turns">
            <li>No saved thread selected.</li>
          </ol>
        </div>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Operator logs</h2>
          <span class="panel-note" id="operator-log-file">Recent structured app events</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Event</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody id="operator-log-table">
            <tr><td colspan="3" class="empty">Loading...</td></tr>
          </tbody>
        </table>
        <div class="panel-head" style="margin-top:16px;">
          <h2>Index reports</h2>
          <span class="panel-note">Newest files first</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Report</th>
              <th>Modified</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody id="index-report-table">
            <tr><td colspan="3" class="empty">Loading...</td></tr>
          </tbody>
        </table>
      </article>
      <article class="panel">
        <div class="panel-head">
          <h2>Network audit</h2>
          <span class="panel-note">Newest checks first</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Host</th>
              <th>Purpose</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody id="network-table">
            <tr><td colspan="4" class="empty">Loading...</td></tr>
          </tbody>
        </table>
      </article>
      <article class="panel wide">
        <div class="panel-head">
          <h2>Latest retrieval trace</h2>
          <span class="panel-note" id="trace-status">No query trace captured yet.</span>
        </div>
        <div class="trace-layout">
          <div class="trace-list" id="trace-list">
            <div class="empty">No query trace captured yet.</div>
          </div>
          <pre class="trace-box" id="trace-text">No query trace captured yet.</pre>
        </div>
      </article>
    </section>
  </main>

  <script>
    const AUTO_REFRESH_MS = 15000;
    let selectedTraceId = "";
    let selectedAdminThreadId = "";

    function text(id, value) {{
      document.getElementById(id).textContent = value ?? "-";
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, (char) => {{
        return {{
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          "\"": "&quot;",
          "'": "&#39;"
        }}[char];
      }});
    }}

    async function fetchJson(url, options = {{}}) {{
      const response = await fetch(url, {{
        credentials: "same-origin",
        cache: "no-store",
        headers: {{ "Accept": "application/json" }},
        ...options
      }});
      if (response.status === 401) {{
        window.location.href = "/auth/login";
        throw new Error("Session expired");
      }}
      if (!response.ok) {{
        const detail = await response.json().then((data) => data.detail || response.statusText).catch(() => response.statusText);
        throw new Error(detail || "Request failed");
      }}
      return response.json();
    }}

    function setAdminIndexButtons(indexing) {{
      const start = document.getElementById("start-index-button");
      const stale = document.getElementById("reindex-stale-button");
      const stop = document.getElementById("stop-index-button");
      const active = !!(indexing && indexing.active);
      start.disabled = active;
      stale.disabled = active;
      stop.disabled = !active;
    }}

    function setAdminScheduleButtons(schedule) {{
      const pause = document.getElementById("pause-schedule-button");
      const resume = document.getElementById("resume-schedule-button");
      const enabled = !!(schedule && schedule.enabled);
      pause.disabled = !enabled;
      resume.disabled = enabled;
    }}

    async function startAdminIndexing() {{
      try {{
        setAdminIndexButtons({{ active: true }});
        const response = await fetchJson("/index", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }},
          body: JSON.stringify({{}})
        }});
        text("banner-pill", "Indexing start requested");
        text("last-updated", response.message || "Indexing start requested.");
        await refreshAdminConsole();
      }} catch (error) {{
        text("banner-pill", "Indexing start failed");
        text("last-updated", error instanceof Error ? error.message : "Indexing start failed");
        await refreshAdminConsole();
      }}
    }}

    async function stopAdminIndexing() {{
      try {{
        const response = await fetchJson("/admin/index/stop", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        text("banner-pill", "Indexing stop requested");
        text("last-updated", response.message || "Indexing stop requested.");
        await refreshAdminConsole();
      }} catch (error) {{
        text("banner-pill", "Indexing stop failed");
        text("last-updated", error instanceof Error ? error.message : "Indexing stop failed");
        await refreshAdminConsole();
      }}
    }}

    async function reindexIfStale() {{
      try {{
        const response = await fetchJson("/admin/index/reindex-if-stale", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        text("banner-pill", "Maintenance action complete");
        text("last-updated", response.message || "Maintenance action complete.");
        await refreshAdminConsole();
      }} catch (error) {{
        text("banner-pill", "Maintenance action failed");
        text("last-updated", error instanceof Error ? error.message : "Maintenance action failed");
        await refreshAdminConsole();
      }}
    }}

    async function recheckFreshness() {{
      try {{
        const response = await fetchJson("/admin/freshness/recheck", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        text("banner-pill", response.stale ? "Freshness rechecked / attention" : "Freshness rechecked");
        text("last-updated", response.summary || "Freshness rechecked.");
        await refreshAdminConsole();
      }} catch (error) {{
        text("banner-pill", "Freshness recheck failed");
        text("last-updated", error instanceof Error ? error.message : "Freshness recheck failed");
        await refreshAdminConsole();
      }}
    }}

    async function pauseAdminSchedule() {{
      try {{
        const response = await fetchJson("/admin/index-schedule/pause", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        text("banner-pill", "Schedule paused");
        text("last-updated", response.message || "Recurring schedule paused.");
        await refreshAdminConsole();
      }} catch (error) {{
        text("banner-pill", "Schedule pause failed");
        text("last-updated", error instanceof Error ? error.message : "Schedule pause failed");
        await refreshAdminConsole();
      }}
    }}

    async function resumeAdminSchedule() {{
      try {{
        const response = await fetchJson("/admin/index-schedule/resume", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        text("banner-pill", "Schedule resumed");
        text("last-updated", response.message || "Recurring schedule resumed.");
        await refreshAdminConsole();
      }} catch (error) {{
        text("banner-pill", "Schedule resume failed");
        text("last-updated", error instanceof Error ? error.message : "Schedule resume failed");
        await refreshAdminConsole();
      }}
    }}

    function renderQueryRows(items) {{
      const target = document.getElementById("queries-table");
      if (!Array.isArray(items) || items.length === 0) {{
        target.innerHTML = '<tr><td colspan="5" class="empty">No recent query activity.</td></tr>';
        return;
      }}
      target.innerHTML = items.slice(0, 10).map((item) => {{
        const statusClass = item.status === "error" ? "danger" : "";
        const latency = item.latency_ms == null ? "-" : `${{item.latency_ms.toFixed(1)}} ms`;
        return `
          <tr>
            <td>${{escapeHtml(item.question_preview)}}</td>
            <td>${{escapeHtml(item.actor)}}</td>
            <td class="${{statusClass}}">${{escapeHtml(item.status)}}</td>
            <td>${{escapeHtml(item.mode)}}</td>
            <td>${{escapeHtml(latency)}}</td>
          </tr>
        `;
      }}).join("");
    }}

    function renderNetworkRows(items) {{
      const target = document.getElementById("network-table");
      if (!Array.isArray(items) || items.length === 0) {{
        target.innerHTML = '<tr><td colspan="4" class="empty">No network-gate activity recorded yet.</td></tr>';
        return;
      }}
      target.innerHTML = items.slice(0, 10).map((item) => {{
        const verdict = item.allowed ? "allowed" : "denied";
        const verdictClass = item.allowed ? "" : "danger";
        return `
          <tr>
            <td>${{escapeHtml(item.timestamp_iso)}}</td>
            <td>${{escapeHtml(item.host)}}</td>
            <td>${{escapeHtml(item.purpose)}}</td>
            <td class="${{verdictClass}}">${{escapeHtml(verdict)}}</td>
          </tr>
        `;
      }}).join("");
    }}

    function renderOperatorLogRows(snapshot) {{
      const target = document.getElementById("operator-log-table");
      const entries = Array.isArray(snapshot?.app_log_entries) ? snapshot.app_log_entries : [];
      text("operator-log-file", snapshot?.app_log_file || "Recent structured app events");
      if (!entries.length) {{
        target.innerHTML = '<tr><td colspan="3" class="empty">No recent structured app log events.</td></tr>';
        return;
      }}
      target.innerHTML = entries.map((item) => `
        <tr>
          <td>${{escapeHtml(item.timestamp || "-")}}</td>
          <td>${{escapeHtml(item.event || "-")}}</td>
          <td>${{escapeHtml(item.summary || "-")}}</td>
        </tr>
      `).join("");
    }}

    function renderIndexReportRows(items) {{
      const target = document.getElementById("index-report-table");
      const reports = Array.isArray(items) ? items : [];
      if (!reports.length) {{
        target.innerHTML = '<tr><td colspan="3" class="empty">No recent index reports.</td></tr>';
        return;
      }}
      target.innerHTML = reports.map((item) => `
        <tr>
          <td>${{escapeHtml(item.file_name || "-")}}</td>
          <td>${{escapeHtml(item.modified_at || "-")}}</td>
          <td>${{escapeHtml(String(item.size_bytes ?? "-"))}}</td>
        </tr>
      `).join("");
    }}

    function renderAlertRows(summary) {{
      const target = document.getElementById("alerts-table");
      const items = Array.isArray(summary?.items) ? summary.items : [];
      text(
        "alerts-summary",
        items.length
          ? `${{summary.total || items.length}} alerts / ${{summary.error_count || 0}} errors / ${{summary.warning_count || 0}} warnings`
          : "No active alerts."
      );
      if (!items.length) {{
        target.innerHTML = '<tr><td colspan="4" class="empty">No active alerts.</td></tr>';
        return;
      }}
      target.innerHTML = items.map((item) => {{
        const severity = item.severity || "-";
        const severityClass = severity === "error" ? "danger" : "";
        return `
          <tr>
            <td class="${{severityClass}}">${{escapeHtml(severity)}}</td>
            <td>${{escapeHtml(item.code || "-")}}</td>
            <td>${{escapeHtml(item.message || "-")}}</td>
            <td>${{escapeHtml(item.action || "-")}}</td>
          </tr>
        `;
      }}).join("");
    }}

    function renderSecurityRows(summary) {{
      const target = document.getElementById("security-table");
      const items = Array.isArray(summary?.entries) ? summary.entries : [];
      const uniqueHosts = Array.isArray(summary?.unique_hosts) ? summary.unique_hosts : [];
      text(
        "security-summary",
        items.length
          ? `${{summary.recent_total || items.length}} events / ${{summary.recent_failures || 0}} denied / ${{summary.recent_rate_limited || 0}} rate-limited / hosts ${{uniqueHosts.join(", ") || "unknown"}}`
          : "No recent security activity."
      );
      if (!items.length) {{
        target.innerHTML = '<tr><td colspan="4" class="empty">No recent security activity.</td></tr>';
        return;
      }}
      target.innerHTML = items.map((item) => {{
        const outcomeClass = item.outcome === "denied" ? "danger" : "";
        return `
          <tr>
            <td>${{escapeHtml(item.timestamp_iso || "-")}}</td>
            <td class="${{outcomeClass}}">${{escapeHtml(item.event || "-")}}</td>
            <td>${{escapeHtml(item.client_host || "-")}}</td>
            <td>${{escapeHtml(item.detail || item.path || "-")}}</td>
          </tr>
        `;
      }}).join("");
    }}

    function setAdminThreadExportButton(threadId) {{
      const button = document.getElementById("admin-thread-export-button");
      const key = String(threadId || "").trim();
      button.disabled = !key;
      button.dataset.threadId = key;
    }}

    function updateAdminThreadRetentionNote(history) {{
      const total = Number(history?.total_threads ?? 0);
      const maxThreads = Number(history?.max_threads ?? 0);
      const maxTurns = Number(history?.max_turns_per_thread ?? 0);
      if (maxThreads > 0 && maxTurns > 0) {{
        text(
          "admin-thread-retention-note",
          `Saved ${{total}} threads / cap ${{maxThreads}} / ${{maxTurns}} turns per thread`
        );
        return;
      }}
      text("admin-thread-retention-note", `Saved ${{total}} threads`);
    }}

    function renderAdminThreadRows(items) {{
      const target = document.getElementById("admin-threads-table");
      if (!Array.isArray(items) || items.length === 0) {{
        target.innerHTML = '<tr><td colspan="5" class="empty">No saved conversation threads yet.</td></tr>';
        return;
      }}
      target.innerHTML = items.slice(0, 10).map((item) => {{
        const statusClass = item.last_status === "error" ? "danger" : "";
        const threadLabel = escapeHtml(item.title || item.last_question_preview || item.thread_id || "Conversation");
        return `
          <tr>
            <td>${{threadLabel}}</td>
            <td>${{escapeHtml(item.last_actor || item.created_by_actor || "-")}}</td>
            <td>${{escapeHtml(item.turn_count)}}</td>
            <td class="${{statusClass}}">${{escapeHtml(item.last_status || "-")}}</td>
            <td><button class="secondary admin-thread-open-button" type="button" data-thread-id="${{escapeHtml(item.thread_id)}}">Inspect</button></td>
          </tr>
        `;
      }}).join("");
    }}

    function renderAdminThreadDetail(snapshot) {{
      if (!snapshot || !snapshot.thread) {{
        text("admin-thread-detail-meta", "Choose a saved conversation to inspect or export.");
        document.getElementById("admin-thread-detail-turns").innerHTML = "<li>No saved thread selected.</li>";
        setAdminThreadExportButton(null);
        return;
      }}

      const thread = snapshot.thread;
      const turns = Array.isArray(snapshot.turns) ? snapshot.turns : [];
      const meta = [];
      meta.push(`${{thread.turn_count}} turns`);
      if (thread.last_actor) meta.push(`Last actor: ${{thread.last_actor}}`);
      if (thread.last_status) meta.push(`Status: ${{thread.last_status}}`);
      text("admin-thread-detail-meta", meta.join(" / "));
      setAdminThreadExportButton(thread.thread_id);

      if (!turns.length) {{
        document.getElementById("admin-thread-detail-turns").innerHTML = "<li>No saved turns yet.</li>";
        return;
      }}

      document.getElementById("admin-thread-detail-turns").innerHTML = turns.slice(-8).map((turn) => {{
        const answer = escapeHtml(turn.answer_preview || turn.answer_text || turn.error || "No answer stored.");
        return `
          <li>
            <strong>Q:</strong> ${{escapeHtml(turn.question_preview || turn.question_text || "-")}}<br>
            <strong>A:</strong> ${{answer}}
          </li>
        `;
      }}).join("");
    }}

    async function loadAdminThreadDetail(threadId) {{
      const key = String(threadId || "").trim();
      if (!key) {{
        renderAdminThreadDetail(null);
        return;
      }}
      const snapshot = await fetchJson(`/history/threads/${{encodeURIComponent(key)}}`);
      selectedAdminThreadId = key;
      renderAdminThreadDetail(snapshot);
    }}

    async function refreshAdminThreadHistory(preferredThreadId = null) {{
      try {{
        const history = await fetchJson("/history/threads?limit=10");
        const threads = Array.isArray(history.threads) ? history.threads : [];
        updateAdminThreadRetentionNote(history);
        renderAdminThreadRows(threads);
        const targetId = preferredThreadId || selectedAdminThreadId;
        if (targetId) {{
          await loadAdminThreadDetail(targetId);
        }} else if (threads.length) {{
          await loadAdminThreadDetail(threads[0].thread_id);
        }} else {{
          renderAdminThreadDetail(null);
        }}
      }} catch (_error) {{
        text("admin-thread-retention-note", "Conversation retention unavailable.");
        document.getElementById("admin-threads-table").innerHTML =
          '<tr><td colspan="5" class="empty">Conversation history unavailable.</td></tr>';
        renderAdminThreadDetail(null);
      }}
    }}

    function renderTraceDetail(trace) {{
      const detail = trace || {{}};
      text(
        "trace-status",
        detail.available
          ? `Trace: ${{detail.query || "(unnamed query)"}}`
          : "No query trace captured yet."
      );
      text("trace-text", detail.formatted_text || "No query trace captured yet.");
    }}

    async function loadTrace(traceId) {{
      if (!traceId) {{
        return;
      }}
      selectedTraceId = traceId;
      try {{
        const trace = await fetchJson(`/admin/traces/${{encodeURIComponent(traceId)}}`);
        renderTraceDetail(trace);
        renderTraceList(window.__adminRecentTraces || []);
      }} catch (error) {{
        text("trace-status", error instanceof Error ? error.message : "Trace load failed");
      }}
    }}

    function renderTraceList(items) {{
      const target = document.getElementById("trace-list");
      const traces = Array.isArray(items) ? items : [];
      window.__adminRecentTraces = traces;

      if (traces.length === 0) {{
        target.innerHTML = '<div class="empty">No query trace captured yet.</div>';
        return;
      }}

      const knownIds = traces.map((item) => item.trace_id).filter(Boolean);
      if (!selectedTraceId || !knownIds.includes(selectedTraceId)) {{
        selectedTraceId = knownIds[0] || "";
      }}

      target.innerHTML = traces.map((item) => {{
        const active = item.trace_id === selectedTraceId ? "is-active" : "";
        const mode = item.mode || "unknown";
        const profile = item.active_profile || "(base)";
        const streamLabel = item.stream ? "stream" : "sync";
        const meta = `${{item.decision_path || "trace"}} / ${{mode}} / ${{profile}} / ${{item.final_hit_count}} final hits / ${{streamLabel}}`;
        return `
          <button class="trace-item ${{active}}" type="button" data-trace-id="${{escapeHtml(item.trace_id)}}">
            <span class="trace-item-time">${{escapeHtml(item.captured_at || "unknown time")}}</span>
            <span class="trace-item-query">${{escapeHtml(item.query || "(unnamed query)")}}</span>
            <span class="trace-item-meta">${{escapeHtml(meta)}}</span>
          </button>
        `;
      }}).join("");

      target.querySelectorAll("[data-trace-id]").forEach((element) => {{
        element.addEventListener("click", () => loadTrace(element.getAttribute("data-trace-id")));
      }});
    }}

    async function renderAdminConsole(snapshot) {{
      const dashboard = snapshot.dashboard;
      const auth = dashboard.auth;
      const status = dashboard.status;
      const config = snapshot.config;
      const safety = snapshot.runtime_safety;
      const storageProtection = snapshot.storage_protection || {{}};
      const accessPolicy = snapshot.access_policy;
      const operatorLogs = snapshot.operator_logs;
      const alerts = snapshot.alerts || {{}};
      const securityActivity = snapshot.security_activity || {{}};
      const latestTrace = snapshot.latest_query_trace;
      const recentTraces = snapshot.recent_query_traces || [];

      text("banner-pill", status.status === "ok" ? "Admin console ready" : status.status);
      text("last-updated", `Last updated ${{new Date().toLocaleTimeString()}}`);

      text("metric-deployment", `${{status.deployment_mode}} / ${{status.mode}}`);
      text("metric-user", `Current user: ${{status.current_user}}`);

      if (status.query_queue.enabled) {{
        text("metric-queue", `${{status.query_queue.active_queries}} active`);
        text(
          "metric-queue-meta",
          `${{status.query_queue.waiting_queries}} waiting / ${{status.query_queue.available_slots}} open slots`
        );
      }} else {{
        text("metric-queue", "disabled");
        text("metric-queue-meta", "Shared queue limit is not configured.");
      }}

      text("metric-indexing", status.indexing.active ? `${{status.indexing.progress_pct}}%` : "idle");
      text(
        "metric-indexing-meta",
        `${{status.indexing.files_processed}} processed / ${{status.indexing.files_errored}} errors`
      );
      setAdminIndexButtons(status.indexing);

      text("metric-trace", recentTraces.length > 0 ? `${{recentTraces.length}} captured` : "empty");
      text(
        "metric-trace-meta",
        latestTrace.available
          ? `${{latestTrace.decision_path || "trace"}} / ${{latestTrace.captured_at || "unknown time"}}`
          : "No query trace captured yet."
      );

      text("auth-actor", auth.actor);
      text("auth-mode", auth.auth_mode);
      text("auth-source", auth.actor_source);
      text("auth-host", auth.client_host);

      text("config-mode", config.mode);
      text("config-embedding", `${{config.embedding_model}} / dim ${{config.embedding_dimension}}`);
      text("config-ollama", `${{config.ollama_model}} @ ${{config.ollama_base_url}}`);
      text("config-api", config.api_endpoint_configured ? config.api_model : "not configured");
      text("config-retrieval", `top_k=${{config.top_k}} / min_score=${{config.min_score}}`);
      text(
        "config-reranker",
        config.reranker_backend_available
          ? (config.reranker_enabled ? "enabled" : "available but off")
          : "backend unavailable"
      );
      text("safety-deployment", `${{safety.deployment_mode}} / auth ${{safety.api_auth_required ? "required" : "open"}}`);
      text("safety-profile", safety.active_profile || "(base)");
      text(
        "safety-query-policy",
        `grounding=${{safety.grounding_bias}} / open knowledge ${{safety.allow_open_knowledge ? "enabled" : "disabled"}}`
      );
      text("safety-auth", safety.api_auth_required ? safety.api_auth_label : "open deployment");
      text(
        "safety-shared-online",
        safety.shared_online_enforced
          ? (safety.shared_online_ready ? "ready" : "blocked by offline mode")
          : "not enforced"
      );
      text(
        "safety-session",
        safety.browser_sessions_enabled
          ? `${{safety.browser_session_ttl_seconds}}s / ${{safety.browser_session_secure_cookie ? "secure cookie" : "http-local cookie"}} / ${{safety.browser_session_secret_source || "unknown"}} / ${{safety.browser_session_rotation_enabled ? "rotation enabled" : "single secret"}}${{safety.browser_session_invalid_before ? ` / invalid before ${{safety.browser_session_invalid_before}}` : ""}}`
          : "disabled"
      );
      text(
        "safety-proxy",
        safety.trusted_proxy_identity_enabled
          ? `${{(safety.trusted_proxy_hosts || []).join(", ")}} / ${{(safety.trusted_proxy_user_headers || []).join(", ")}} / ${{safety.proxy_identity_secret_rotation_enabled ? "rotation enabled" : "single secret"}}`
          : "disabled"
      );
      text(
        "safety-history",
        safety.history_encryption_enabled
          ? `${{safety.history_encryption_source || "unknown"}} / ${{safety.history_encryption_rotation_enabled ? "rotation enabled" : "single secret"}} / ${{safety.history_secure_delete_enabled ? "secure delete" : "normal delete"}} / ${{safety.history_database_path || "uninitialized"}}`
          : `${{safety.history_encryption_source || "disabled"}} / ${{safety.history_secure_delete_enabled ? "secure delete" : "normal delete"}} / ${{safety.history_database_path || "uninitialized"}}`
      );
      text("safety-paths", `${{safety.source_folder}} -> ${{safety.database_path}}`);
      text("storage-summary", storageProtection.summary || "No storage-protection summary available.");
      text("storage-mode", storageProtection.mode || "disabled");
      text("storage-required", storageProtection.required ? "yes" : "no");
      text(
        "storage-roots",
        (storageProtection.roots || []).join(" | ") || "not configured"
      );
      text(
        "storage-paths-protected",
        (storageProtection.protected_paths || []).join(" | ")
          || (storageProtection.all_paths_protected ? "all tracked paths protected" : "none")
      );
      text(
        "storage-paths-unprotected",
        (storageProtection.unprotected_paths || []).join(" | ")
          || (storageProtection.all_paths_protected ? "none" : "none detected")
      );
      text("policy-default-tags", (accessPolicy.default_document_tags || []).join(", ") || "(none)");
      text("policy-role-map", (accessPolicy.role_map || []).join(" | ") || "no explicit actor-role mappings");
      text("policy-role-tags", (accessPolicy.role_tag_policies || []).join(" | ") || "using default role-tag policy");
      text("policy-doc-rules", (accessPolicy.document_tag_rules || []).join(" | ") || "default document tags only");
      text(
        "policy-denied",
        accessPolicy.recent_denied_traces
          ? `${{accessPolicy.recent_denied_traces}} recent / latest ${{accessPolicy.latest_denied_trace_id || "unknown"}} / ${{accessPolicy.latest_denied_query || "no query preview"}}`
          : "no denied retrieval traces recorded"
      );
      const indexSchedule = snapshot.index_schedule || {{}};
      text(
        "schedule-status",
        indexSchedule.enabled
          ? (indexSchedule.indexing_active ? "running now" : indexSchedule.last_status || "idle")
          : "disabled"
      );
      text(
        "schedule-interval",
        indexSchedule.enabled
          ? `${{indexSchedule.interval_seconds || 0}}s / runs=${{indexSchedule.total_runs || 0}} ok=${{indexSchedule.total_success || 0}} fail=${{indexSchedule.total_failed || 0}}`
          : "not configured"
      );
      text(
        "schedule-next",
        indexSchedule.enabled
          ? (indexSchedule.next_run_at || (indexSchedule.due_now ? "due now" : "waiting"))
          : "-"
      );
      text(
        "schedule-last",
        indexSchedule.last_finished_at
          ? `${{indexSchedule.last_status || "completed"}} / ${{indexSchedule.last_finished_at}}${{indexSchedule.last_error ? ` / ${{indexSchedule.last_error}}` : ""}}`
          : "no scheduled runs yet"
      );
      text("schedule-source", indexSchedule.source_folder || "(inherits configured source folder)");
      setAdminScheduleButtons(indexSchedule);
      const freshness = snapshot.freshness || {{}};
      text(
        "freshness-status",
        freshness.stale
          ? `attention / ${{freshness.summary || "stale content detected"}}`
          : `fresh / ${{freshness.summary || "up to date"}}`
      );
      text(
        "freshness-last-index",
        freshness.last_index_finished_at
          ? `${{freshness.last_index_status || "completed"}} / ${{freshness.last_index_finished_at}} / age ${{freshness.freshness_age_hours ?? "-"}}h`
          : "no completed index run recorded"
      );
      text(
        "freshness-source-update",
        freshness.latest_source_update_at
          ? freshness.latest_source_update_at
          : (freshness.source_exists ? "no indexable source files found" : "source folder missing")
      );
      text(
        "freshness-drift",
        `${{freshness.files_newer_than_index || 0}} newer files / ${{freshness.total_indexable_files || 0}} tracked / warn after ${{freshness.warn_after_hours || 24}}h`
      );
      text(
        "freshness-source-path",
        freshness.latest_source_path || freshness.source_folder || "(no source path)"
      );

      renderAlertRows(alerts);
      renderSecurityRows(securityActivity);
      renderQueryRows(dashboard.queries.recent || []);
      await refreshAdminThreadHistory(selectedAdminThreadId);
      renderOperatorLogRows(operatorLogs);
      renderIndexReportRows(operatorLogs?.index_reports || []);
      renderNetworkRows(dashboard.network.entries || []);
      renderTraceList(recentTraces);
      if (selectedTraceId && recentTraces.some((item) => item.trace_id === selectedTraceId)) {{
        if (selectedTraceId === (latestTrace.trace_id || "")) {{
          renderTraceDetail(latestTrace);
        }} else {{
          await loadTrace(selectedTraceId);
        }}
      }} else {{
        selectedTraceId = latestTrace.trace_id || "";
        renderTraceList(recentTraces);
        renderTraceDetail(latestTrace);
      }}

      const logout = document.getElementById("logout-button");
      logout.style.display = auth.auth_required ? "inline-flex" : "none";
    }}

    async function refreshAdminConsole() {{
      try {{
        const snapshot = await fetchJson("/admin/data");
        await renderAdminConsole(snapshot);
      }} catch (error) {{
        text("banner-pill", "Refresh failed");
        text("last-updated", error instanceof Error ? error.message : "Refresh failed");
      }}
    }}

    document.getElementById("refresh-button").addEventListener("click", refreshAdminConsole);
    document.getElementById("start-index-button").addEventListener("click", startAdminIndexing);
    document.getElementById("reindex-stale-button").addEventListener("click", reindexIfStale);
    document.getElementById("recheck-freshness-button").addEventListener("click", recheckFreshness);
    document.getElementById("stop-index-button").addEventListener("click", stopAdminIndexing);
    document.getElementById("pause-schedule-button").addEventListener("click", pauseAdminSchedule);
    document.getElementById("resume-schedule-button").addEventListener("click", resumeAdminSchedule);
    document.getElementById("admin-threads-table").addEventListener("click", async (event) => {{
      const button = event.target.closest(".admin-thread-open-button");
      if (!button) {{
        return;
      }}
      await loadAdminThreadDetail(button.dataset.threadId || "");
    }});
    document.getElementById("admin-thread-export-button").addEventListener("click", () => {{
      const key = String(
        document.getElementById("admin-thread-export-button").dataset.threadId || selectedAdminThreadId || ""
      ).trim();
      if (!key) {{
        return;
      }}
      window.location.href = `/history/threads/${{encodeURIComponent(key)}}/export`;
    }});
    document.getElementById("logout-button").addEventListener("click", async () => {{
      try {{
        const response = await fetchJson("/auth/logout", {{
          method: "POST",
          headers: {{
            "Accept": "application/json",
            "Content-Type": "application/json"
          }}
        }});
        window.location.href = response.redirect_to || "/auth/login";
      }} catch (_error) {{
        window.location.href = "/auth/login";
      }}
    }});

    refreshAdminConsole();
    window.setInterval(refreshAdminConsole, AUTO_REFRESH_MS);
  </script>
</body>
</html>
"""
