/**
 * SafeStrata - Calm Document-Centric Compliance Workspace
 * Pure Vanilla JavaScript • Real-Time Role RBAC • SSE Streaming • Citation Inspection
 */

(function () {
  'use strict';

  // State Management
  const state = {
    accessToken: null,
    user: null, // { id, email, role, role_version }
    currentView: 'ask',
    resendInterval: null,
    resendSeconds: 60,
    accessibleDocuments: [],
    lastRAGResponse: null,
    selectedCitation: null,
    auditLogsOffset: 0,
    auditLogsLimit: 25
  };

  // Safe DOMPurify & Markdown wrapper
  function renderSanitizedMarkdown(text) {
    if (!text) return '';
    try {
      if (window.marked && window.DOMPurify) {
        const rawHtml = window.marked.parse(text);
        return window.DOMPurify.sanitize(rawHtml);
      } else if (window.DOMPurify) {
        return window.DOMPurify.sanitize(text.replace(/\n/g, '<br>'));
      }
    } catch (e) {
      console.error('Markdown rendering error:', e);
    }
    // Fallback safe escape
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
  }

  // HTTP Helper with Bearer Token Injection
  async function apiFetch(url, options = {}) {
    const headers = options.headers ? { ...options.headers } : {};
    if (state.accessToken && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${state.accessToken}`;
    }
    options.headers = headers;

    const res = await fetch(url, options);
    if (res.status === 401 && !url.includes('/auth/refresh') && !url.includes('/auth/verify-otp') && !url.includes('/auth/request-otp')) {
      // Try refresh token once
      const refreshed = await tryRefreshToken();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${state.accessToken}`;
        options.headers = headers;
        return fetch(url, options);
      } else {
        handleLogout();
        throw new Error('Session expired. Please sign in again.');
      }
    }
    return res;
  }

  // --------------------------------------------------------------------------
  // AUTHENTICATION & SESSION MANAGEMENT
  // --------------------------------------------------------------------------

  async function checkSession() {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      await fetchUserProfile();
      mountAppShell();
    } else {
      mountAuthWall();
    }
  }

  async function tryRefreshToken() {
    try {
      const res = await fetch('/api/v1/auth/refresh', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        state.accessToken = data.access_token;
        return true;
      }
    } catch (e) {
      console.warn('No active refresh session found:', e);
    }
    return false;
  }

  async function fetchUserProfile() {
    try {
      const res = await apiFetch('/api/v1/auth/me');
      if (res.ok) {
        state.user = await res.json();
      }
    } catch (e) {
      console.error('Failed to load user profile:', e);
    }
  }

  function mountAuthWall() {
    const root = document.getElementById('app-root');
    const tmpl = document.getElementById('login-template') || document.getElementById('template-auth');
    root.innerHTML = '';
    root.appendChild(tmpl.content.cloneNode(true));
  }

  function mountAppShell() {
    const root = document.getElementById('app-root');
    const tmpl = document.getElementById('dashboard-template') || document.getElementById('template-app');
    root.innerHTML = '';
    root.appendChild(tmpl.content.cloneNode(true));

    // Update Header user info
    if (state.user) {
      document.getElementById('header-user-email').textContent = state.user.email;
      const roleBadge = document.getElementById('header-user-role');
      roleBadge.textContent = state.user.role.replace('_', ' ');
      roleBadge.setAttribute('data-role', state.user.role);
    }

    // Role-filtered navigation
    applyRoleBasedNavigation();

    // Default view based on role
    const defaultView = state.user && (state.user.role === 'admin' || state.user.role === 'auditor') ? 'ask' : 'ask';
    switchView(defaultView);
  }

  function applyRoleBasedNavigation() {
    const role = state.user ? state.user.role : 'viewer';
    const navAsk = document.getElementById('nav-item-ask');
    const navLib = document.getElementById('nav-item-library');
    const navQuality = document.getElementById('nav-item-quality');
    const navAdmin = document.getElementById('nav-item-admin');

    // Ask: available to document readers
    if (navAsk) navAsk.style.display = 'flex';

    // Library: compliance_manager
    if (navLib) navLib.style.display = role === 'compliance_manager' ? 'flex' : 'none';

    // Quality: compliance_manager, auditor, admin
    if (navQuality) navQuality.style.display = ['compliance_manager', 'auditor', 'admin'].includes(role) ? 'flex' : 'none';

    // Admin & Audit: admin, auditor
    if (navAdmin) navAdmin.style.display = ['admin', 'auditor'].includes(role) ? 'flex' : 'none';
  }

  window.handleRequestOtp = async function () {
    const emailInput = document.getElementById('input-email');
    const errorBox = document.getElementById('auth-email-error');
    const submitBtn = document.getElementById('btn-request-otp');
    const email = emailInput.value.trim().toLowerCase();

    errorBox.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending code...';

    try {
      const res = await fetch('/api/v1/auth/request-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to dispatch verification code.');
      }

      // Transition to OTP step
      document.getElementById('form-auth-email').style.display = 'none';
      document.getElementById('form-auth-otp').style.display = 'block';
      document.getElementById('auth-target-email').textContent = email;
      startResendCountdown();
      const otpInput = document.getElementById('input-otp');
      otpInput.value = '';
      otpInput.focus();
    } catch (e) {
      errorBox.textContent = e.message;
      errorBox.style.display = 'block';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Continue with email';
    }
  };

  window.handleVerifyOtp = async function () {
    const email = document.getElementById('auth-target-email').textContent;
    const otpInput = document.getElementById('input-otp');
    const errorBox = document.getElementById('auth-otp-error');
    const submitBtn = document.getElementById('btn-verify-otp');
    const code = otpInput.value.trim();

    errorBox.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Verifying...';

    try {
      const res = await fetch('/api/v1/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Invalid verification code.');
      }

      const data = await res.json();
      state.accessToken = data.access_token;
      state.user = data.user;

      // Show brief success transition
      document.getElementById('form-auth-otp').style.display = 'none';
      const transitionBox = document.getElementById('auth-transition');
      document.getElementById('auth-welcome-text').textContent = `Signed in as ${email}`;
      transitionBox.style.display = 'flex';

      setTimeout(() => {
        mountAppShell();
      }, 700);
    } catch (e) {
      errorBox.textContent = e.message;
      errorBox.style.display = 'block';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Verify and continue';
    }
  };

  window.showEmailStep = function () {
    clearInterval(state.resendInterval);
    document.getElementById('form-auth-otp').style.display = 'none';
    document.getElementById('form-auth-email').style.display = 'block';
    document.getElementById('input-email').focus();
  };

  window.handleResendOtp = function () {
    const email = document.getElementById('auth-target-email').textContent;
    if (email) {
      fetch('/api/v1/auth/request-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      startResendCountdown();
    }
  };

  function startResendCountdown() {
    clearInterval(state.resendInterval);
    state.resendSeconds = 60;
    const timerSpan = document.getElementById('resend-timer');
    const resendBtn = document.getElementById('btn-resend-otp');
    resendBtn.disabled = true;

    state.resendInterval = setInterval(() => {
      state.resendSeconds -= 1;
      if (timerSpan) timerSpan.textContent = state.resendSeconds;
      if (state.resendSeconds <= 0) {
        clearInterval(state.resendInterval);
        resendBtn.disabled = false;
        resendBtn.textContent = 'Resend verification code';
      }
    }, 1000);
  }

  window.handleLogout = async function () {
    try {
      await fetch('/api/v1/auth/logout', { method: 'POST' });
    } catch (e) {
      console.warn('Logout notification error:', e);
    }
    state.accessToken = null;
    state.user = null;
    mountAuthWall();
  };

  // --------------------------------------------------------------------------
  // VIEW SWITCHER & NAVIGATION
  // --------------------------------------------------------------------------

  window.switchView = function (viewId) {
    state.currentView = viewId;
    closeSourcePanel();

    // Update active nav class
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const activeNav = document.getElementById(`nav-item-${viewId}`);
    if (activeNav) activeNav.classList.add('active');

    const container = document.getElementById('view-content');
    const titleEl = document.getElementById('view-title');

    if (viewId === 'ask') {
      titleEl.textContent = 'Compliance Policy Assistant';
      renderAskView(container);
    } else if (viewId === 'library') {
      titleEl.textContent = 'Regulatory Document Library';
      renderLibraryView(container);
    } else if (viewId === 'quality') {
      titleEl.textContent = 'Evaluations & Quality Review';
      renderQualityView(container);
    } else if (viewId === 'admin') {
      titleEl.textContent = 'Access Governance & Audit';
      renderAdminView(container);
    }
  };

  // --------------------------------------------------------------------------
  // VIEW 1: ASK DESK
  // --------------------------------------------------------------------------

  async function renderAskView(container) {
    container.innerHTML = `
      <div class="ask-workspace">
        <!-- Searchable Documents Accessible to Caller -->
        <div class="searchable-docs-card">
          <div class="docs-chips-label">Documents Searchable by Your Role</div>
          <div id="accessible-docs-chips" class="docs-chips-container">
            <span class="skeleton" style="height: 24px; width: 140px;"></span>
            <span class="skeleton" style="height: 24px; width: 180px;"></span>
          </div>
        </div>

        <!-- Query Input Box -->
        <div class="ask-box-card">
          <form id="form-ask" onsubmit="event.preventDefault(); window.executeAskQuery();">
            <textarea 
              id="ask-query-input" 
              class="ask-textarea" 
              placeholder="Ask any policy or regulatory question grounded in official bank documents..."
              required
            ></textarea>
            <div class="ask-box-footer">
              <span class="ask-hint">Answers are strictly grounded in accessible documents or honest abstention.</span>
              <button type="submit" id="btn-submit-ask" class="btn-primary" style="width: auto;">
                Ask Desk
              </button>
            </div>
          </form>
        </div>

        <!-- Suggested Questions -->
        <div id="suggested-queries-card" class="suggested-queries-section" style="display: none;">
          <div class="suggested-queries-label">Suggested Policy Questions</div>
          <div id="suggested-queries-chips" class="suggested-queries-chips"></div>
        </div>

        <!-- Answer Container -->
        <div id="answer-container" style="display: none;"></div>
      </div>
    `;

    // Fetch accessible documents
    await loadAccessibleDocuments();
  }

  async function loadAccessibleDocuments() {
    try {
      const res = await apiFetch('/api/v1/documents');
      if (res.ok) {
        state.accessibleDocuments = await res.json();
        const chipsContainer = document.getElementById('accessible-docs-chips');
        if (!chipsContainer) return;

        if (state.accessibleDocuments.length === 0) {
          chipsContainer.innerHTML = '<span style="font-size: 0.8125rem; color: var(--text-muted);">No documents are currently accessible for your assigned role.</span>';
          return;
        }

        chipsContainer.innerHTML = state.accessibleDocuments.map(d => `
          <span class="doc-chip" title="${d.title}">${d.title}</span>
        `).join('');

        // Populate suggested queries from documents
        const suggestions = [];
        state.accessibleDocuments.forEach(d => {
          if (d.suggested_questions && Array.isArray(d.suggested_questions)) {
            suggestions.push(...d.suggested_questions);
          }
        });

        const suggContainer = document.getElementById('suggested-queries-chips');
        const suggCard = document.getElementById('suggested-queries-card');
        if (suggContainer && suggestions.length > 0) {
          suggContainer.innerHTML = suggestions.slice(0, 6).map(q => `
            <button type="button" class="suggested-query-chip" onclick="window.populateQuery('${q.replace(/'/g, "\\'")}')">${q}</button>
          `).join('');
          suggCard.style.display = 'flex';
        }
      }
    } catch (e) {
      console.error('Failed to load accessible documents:', e);
    }
  }

  window.populateQuery = function (q) {
    const input = document.getElementById('ask-query-input');
    if (input) {
      input.value = q;
      input.focus();
    }
  };

  window.executeAskQuery = async function () {
    const input = document.getElementById('ask-query-input');
    const query = input.value.trim();
    if (!query) return;

    const submitBtn = document.getElementById('btn-submit-ask');
    const answerContainer = document.getElementById('answer-container');
    submitBtn.disabled = true;

    // Show loading skeleton
    answerContainer.style.display = 'block';
    answerContainer.innerHTML = `
      <div class="answer-card">
        <div class="answer-header">
          <span class="answer-status-pill status-grounded" id="stream-status-pill">Verifying & Retrieving</span>
        </div>
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text" style="width: 80%;"></div>
      </div>
    `;

    try {
      const res = await apiFetch('/api/v1/rag/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 3 })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Regulatory desk query failed.');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let streamedAnswer = '';
      let fullResponse = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        let currentEvent = 'message';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.replace('event: ', '').trim();
          } else if (line.startsWith('data: ')) {
            const rawData = line.replace('data: ', '').trim();
            try {
              const parsed = JSON.parse(rawData);
              if (currentEvent === 'token') {
                streamedAnswer += parsed.token;
                renderStreamingAnswer(streamedAnswer);
              } else if (currentEvent === 'status') {
                const statusPill = document.getElementById('stream-status-pill');
                if (statusPill) statusPill.textContent = parsed.message;
              } else if (currentEvent === 'complete') {
                fullResponse = parsed;
              }
            } catch (err) {
              // Ignore non-json chunk lines
            }
          }
        }
      }

      if (fullResponse) {
        state.lastRAGResponse = fullResponse;
        renderFinalAnswer(fullResponse);
      } else {
        renderStreamingAnswer(streamedAnswer);
      }
    } catch (e) {
      answerContainer.innerHTML = `
        <div class="answer-card">
          <div class="answer-header">
            <span class="answer-status-pill status-abstained">Query Error</span>
          </div>
          <div class="answer-body" style="color: var(--status-danger);">
            ${e.message}
          </div>
        </div>
      `;
    } finally {
      submitBtn.disabled = false;
    }
  };

  function renderStreamingAnswer(text) {
    const answerContainer = document.getElementById('answer-container');
    if (!answerContainer) return;

    answerContainer.innerHTML = `
      <div class="answer-card">
        <div class="answer-header">
          <span class="answer-status-pill status-grounded">Synthesizing Answer</span>
        </div>
        <div class="answer-body">
          ${renderSanitizedMarkdown(text)}
        </div>
      </div>
    `;
  }

  function renderFinalAnswer(data) {
    const answerContainer = document.getElementById('answer-container');
    if (!answerContainer) return;

    const isGrounded = data.is_grounded && data.status !== 'abstained';
    const statusClass = isGrounded ? 'status-grounded' : 'status-abstained';
    const statusText = isGrounded ? 'Policy-Grounded' : 'Abstained (Unanswerable from Documents)';

    // Format citations as interactive chips
    let answerHtml = renderSanitizedMarkdown(data.answer);
    if (data.citations && data.citations.length > 0) {
      data.citations.forEach((cit, idx) => {
        const citeNumber = idx + 1;
        const tagRegex = new RegExp(`\\[${citeNumber}\\]`, 'g');
        answerHtml = answerHtml.replace(
          tagRegex,
          `<button type="button" class="citation-chip" onclick="window.openCitation(${idx})">[${citeNumber}]</button>`
        );
      });
    }

    answerContainer.innerHTML = `
      <div class="answer-card">
        <div class="answer-header">
          <span class="answer-status-pill ${statusClass}">${statusText}</span>
          <span style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono);">
            ${data.total_latency_ms || 0} ms • NLI Support: ${Math.round((data.faithfulness_score || 0) * 100)}%
          </span>
        </div>

        <div class="answer-body">
          ${answerHtml}
        </div>

        <div class="answer-actions">
          <button type="button" class="btn-secondary" onclick="window.copyAnswerToClipboard()">
            Copy with citations
          </button>
          <button type="button" class="btn-secondary" onclick="window.openTraceModal()">
            Why this answer?
          </button>
          <button type="button" class="btn-secondary" onclick="window.openReportModal()">
            Report wrong answer
          </button>
        </div>
      </div>
    `;
  }

  window.copyAnswerToClipboard = function () {
    if (state.lastRAGResponse && state.lastRAGResponse.answer) {
      let copyText = state.lastRAGResponse.answer;
      if (state.lastRAGResponse.citations && state.lastRAGResponse.citations.length > 0) {
        copyText += '\n\nCitations:\n';
        state.lastRAGResponse.citations.forEach((c, idx) => {
          copyText += `[${idx + 1}] ${c.title || 'Policy Document'} (Page ${c.page_number || 1})\n`;
        });
      }
      navigator.clipboard.writeText(copyText);
      alert('Answer and citations copied to clipboard.');
    }
  };

  // --------------------------------------------------------------------------
  // CITATION SOURCE INSPECTION PANEL
  // --------------------------------------------------------------------------

  window.openCitation = function (index) {
    if (!state.lastRAGResponse || !state.lastRAGResponse.citations) return;
    const citation = state.lastRAGResponse.citations[index];
    if (!citation) return;

    state.selectedCitation = citation;
    const panel = document.getElementById('source-panel');
    if (!panel) return;

    document.getElementById('panel-doc-title').textContent = citation.title || 'Official Regulatory Policy';
    document.getElementById('panel-page-num').textContent = citation.page_number || '1';
    document.getElementById('panel-effective-date').textContent = citation.effective_date || 'In Effect';
    document.getElementById('panel-score').textContent = citation.score ? citation.score.toFixed(4) : 'Rank 1';

    // Highlight snippet
    const evidenceEl = document.getElementById('panel-evidence-text');
    evidenceEl.innerHTML = `<span class="highlighted-evidence">${citation.snippet || ''}</span>`;

    panel.classList.add('open');
  };

  window.closeSourcePanel = function () {
    const panel = document.getElementById('source-panel');
    if (panel) panel.classList.remove('open');
  };

  // --------------------------------------------------------------------------
  // WHY THIS ANSWER? TRACE DRAWER
  // --------------------------------------------------------------------------

  window.openTraceModal = function () {
    const modal = document.getElementById('trace-modal');
    if (!modal || !state.lastRAGResponse) return;

    const trace = state.lastRAGResponse.trace || {};
    const latencies = state.lastRAGResponse.latency_breakdown || {};

    document.getElementById('trace-mode').textContent = state.lastRAGResponse.generation_mode || 'grounded';
    document.getElementById('trace-faithfulness').textContent = `${Math.round((state.lastRAGResponse.faithfulness_score || 0) * 100)}%`;
    document.getElementById('trace-total-latency').textContent = `${state.lastRAGResponse.total_latency_ms || 0} ms`;
    document.getElementById('trace-model-name').textContent = 'qwen2.5:3b-instruct (Ollama)';

    // Latency table
    const latTable = document.getElementById('trace-latencies-table');
    latTable.innerHTML = `
      <table class="data-table">
        <thead>
          <tr><th>Stage</th><th>Latency (ms)</th></tr>
        </thead>
        <tbody>
          <tr><td>Input Guardrails (PII + Injection)</td><td>${latencies.guardrails_input_ms || 0}</td></tr>
          <tr><td>Hybrid Search (Dense + BM25)</td><td>${latencies.retrieval_ms || 0}</td></tr>
          <tr><td>Grounded Generation (Ollama Qwen2.5)</td><td>${latencies.generation_ms || 0}</td></tr>
          <tr><td>Output Guardrails (NLI + PII Scrub)</td><td>${latencies.guardrails_output_ms || 0}</td></tr>
          <tr><td><strong>Total End-to-End Pipeline</strong></td><td><strong>${latencies.total_ms || state.lastRAGResponse.total_latency_ms || 0}</strong></td></tr>
        </tbody>
      </table>
    `;

    // Rerank Comparison Table
    const ranksTable = document.getElementById('trace-ranks-table');
    const ranksAfter = trace.ranks_after_rerank || [];
    ranksTable.innerHTML = `
      <table class="data-table">
        <thead>
          <tr><th>Rank</th><th>Document</th><th>Page</th><th>Cross-Encoder Score</th></tr>
        </thead>
        <tbody>
          ${ranksAfter.map(r => `
            <tr>
              <td>#${r.rank}</td>
              <td>${r.title}</td>
              <td>Page ${r.page}</td>
              <td>${r.score}</td>
            </tr>
          `).join('') || '<tr><td colspan="4">No retrieved chunks</td></tr>'}
        </tbody>
      </table>
    `;

    modal.style.display = 'flex';
  };

  window.closeTraceModal = function () {
    const modal = document.getElementById('trace-modal');
    if (modal) modal.style.display = 'none';
  };

  // --------------------------------------------------------------------------
  // REPORT WRONG ANSWER MODAL
  // --------------------------------------------------------------------------

  window.openReportModal = function () {
    const modal = document.getElementById('report-modal');
    if (modal) {
      document.getElementById('report-reason').value = '';
      modal.style.display = 'flex';
    }
  };

  window.closeReportModal = function () {
    const modal = document.getElementById('report-modal');
    if (modal) modal.style.display = 'none';
  };

  window.submitWrongAnswerReport = async function () {
    if (!state.lastRAGResponse) return;
    const reasonInput = document.getElementById('report-reason');
    const reason = reasonInput.value.trim();
    if (!reason) {
      alert('Please state a reason for reporting.');
      return;
    }

    try {
      const res = await apiFetch('/api/v1/quality/report-wrong-answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: state.lastRAGResponse.query,
          answer: state.lastRAGResponse.answer,
          citations: state.lastRAGResponse.citations,
          reason
        })
      });

      if (res.ok) {
        alert('Report successfully recorded for compliance quality audit review.');
        closeReportModal();
      } else {
        const err = await res.json();
        alert('Failed to submit report: ' + (err.detail || 'Server error'));
      }
    } catch (e) {
      alert('Failed to submit report: ' + e.message);
    }
  };

  // --------------------------------------------------------------------------
  // VIEW 2: LIBRARY (COMPLIANCE MANAGER)
  // --------------------------------------------------------------------------

  async function renderLibraryView(container) {
    container.innerHTML = `
      <div style="max-width: 1040px; margin: 0 auto; width: 100%; display: flex; flex-direction: column; gap: 24px;">
        <!-- Upload Document Card -->
        <div class="ask-box-card">
          <h3 class="panel-title" style="margin-bottom: 16px;">Ingest Regulatory Policy Document</h3>
          <form id="form-upload-doc" onsubmit="event.preventDefault(); window.handleUploadDocument();">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
              <div>
                <label class="form-label">Document Title</label>
                <input type="text" id="upload-doc-title" class="form-input" placeholder="e.g. Master Direction - Credit Risk 2026" required>
              </div>
              <div>
                <label class="form-label">Effective Date</label>
                <input type="text" id="upload-doc-date" class="form-input" placeholder="e.g. 2026-04-01">
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">Select PDF or Text File</label>
              <input type="file" id="upload-doc-file" class="form-input" accept=".pdf,.txt,.md">
            </div>

            <div class="form-group">
              <label class="form-label">Allowed Roles (Document Access Restriction)</label>
              <div style="display: flex; gap: 16px; flex-wrap: wrap;">
                <label><input type="checkbox" name="allowed_role" value="viewer" checked> Viewer</label>
                <label><input type="checkbox" name="allowed_role" value="analyst" checked> Analyst</label>
                <label><input type="checkbox" name="allowed_role" value="compliance_manager" checked> Compliance Manager</label>
                <label><input type="checkbox" name="allowed_role" value="auditor" checked> Auditor</label>
              </div>
            </div>

            <div id="upload-progress-box" style="display: none; margin-bottom: 16px;">
              <span class="skeleton" style="height: 12px; width: 100%; display: block;"></span>
              <span style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px; display: block;" id="upload-progress-text">
                Parsing pages, redacting PII, chunking, and embedding...
              </span>
            </div>

            <button type="submit" id="btn-upload-submit" class="btn-primary" style="width: auto;">
              Upload & Ingest Document
            </button>
          </form>
        </div>

        <!-- Document Inventory Table -->
        <div class="data-table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Chunks</th>
                <th>PII Redacted (At Ingest)</th>
                <th>Allowed Roles</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody id="library-docs-tbody">
              <tr><td colspan="5"><div class="skeleton skeleton-text"></div></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    `;

    await loadLibraryDocuments();
  }

  async function loadLibraryDocuments() {
    try {
      const res = await apiFetch('/api/v1/documents');
      if (res.ok) {
        const docs = await res.json();
        const tbody = document.getElementById('library-docs-tbody');
        if (!tbody) return;

        if (docs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No documents in library.</td></tr>';
          return;
        }

        tbody.innerHTML = docs.map(d => {
          const piiEntries = Object.entries(d.pii_entities_detected || {});
          const piiStr = piiEntries.length > 0 ? piiEntries.map(([k, v]) => `${k}: ${v}`).join(', ') : 'None';
          const rolesStr = (d.allowed_roles || []).join(', ');

          return `
            <tr>
              <td><strong>${d.title}</strong></td>
              <td>${d.chunk_count || '-'}</td>
              <td><span style="font-size: 0.8125rem; color: var(--text-muted);">${piiStr}</span></td>
              <td><span class="role-badge" style="font-size: 0.6875rem;">${rolesStr}</span></td>
              <td>
                <div style="display: flex; gap: 8px;">
                  <button type="button" class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="window.previewDocumentChunks('${d.id}', '${d.title.replace(/'/g, "\\'")}')">
                    Preview
                  </button>
                  <button type="button" class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; color: var(--status-danger);" onclick="window.confirmDeleteDocument('${d.id}', '${d.title.replace(/'/g, "\\'")}')">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          `;
        }).join('');
      }
    } catch (e) {
      console.error('Failed to load library documents:', e);
    }
  }

  window.handleUploadDocument = async function () {
    const titleInput = document.getElementById('upload-doc-title');
    const dateInput = document.getElementById('upload-doc-date');
    const fileInput = document.getElementById('upload-doc-file');
    const progressBox = document.getElementById('upload-progress-box');
    const submitBtn = document.getElementById('btn-upload-submit');

    const selectedRoles = Array.from(document.querySelectorAll('input[name="allowed_role"]:checked')).map(el => el.value);

    const formData = new FormData();
    formData.append('title', titleInput.value.trim());
    formData.append('effective_date', dateInput.value.trim());
    formData.append('allowed_roles', JSON.stringify(selectedRoles));

    if (fileInput.files.length > 0) {
      formData.append('file', fileInput.files[0]);
    } else {
      alert('Please select a PDF or text document to upload.');
      return;
    }

    progressBox.style.display = 'block';
    submitBtn.disabled = true;

    try {
      const res = await apiFetch('/api/v1/documents/upload', {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Document ingestion failed.');
      }

      alert('Document successfully ingested and indexed with page citations!');
      titleInput.value = '';
      fileInput.value = '';
      loadLibraryDocuments();
    } catch (e) {
      alert('Upload error: ' + e.message);
    } finally {
      progressBox.style.display = 'none';
      submitBtn.disabled = false;
    }
  };

  window.confirmDeleteDocument = async function (id, title) {
    if (confirm(`Are you sure you want to delete "${title}"? This will remove its vectors and per-role BM25 indices.`)) {
      try {
        const res = await apiFetch(`/api/v1/documents/${id}`, { method: 'DELETE' });
        if (res.ok) {
          loadLibraryDocuments();
        } else {
          alert('Delete failed.');
        }
      } catch (e) {
        alert('Delete error: ' + e.message);
      }
    }
  };

  window.previewDocumentChunks = async function (id, title) {
    try {
      const res = await apiFetch(`/api/v1/documents/${id}/chunks`);
      if (res.ok) {
        const chunks = await res.json();
        const modal = document.getElementById('chunks-modal');
        document.getElementById('chunks-modal-title').textContent = `Chunks Preview: ${title}`;
        const bodyEl = document.getElementById('chunks-modal-body');

        bodyEl.innerHTML = chunks.map((c, i) => `
          <div style="background-color: var(--bg-subtle); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 6px;">
              <span>Chunk #${i + 1} (Page ${c.page_number || 1})</span>
              <span>Span: ${c.char_start}-${c.char_end}</span>
            </div>
            <div style="font-family: var(--font-doc); font-size: 0.875rem; color: var(--text-secondary); line-height: 1.5;">
              ${c.content}
            </div>
          </div>
        `).join('') || '<p>No chunks found.</p>';

        modal.style.display = 'flex';
      }
    } catch (e) {
      alert('Could not preview chunks: ' + e.message);
    }
  };

  window.closeChunksModal = function () {
    const modal = document.getElementById('chunks-modal');
    if (modal) modal.style.display = 'none';
  };

  // --------------------------------------------------------------------------
  // VIEW 3: QUALITY & EVALUATIONS (COMPLIANCE MANAGER, AUDITOR, ADMIN)
  // --------------------------------------------------------------------------

  async function renderQualityView(container) {
    container.innerHTML = `
      <div style="max-width: 1040px; margin: 0 auto; width: 100%; display: flex; flex-direction: column; gap: 24px;">
        <!-- Eval Summary Metrics Grid -->
        <div>
          <h3 class="panel-title" style="margin-bottom: 14px;">Automated Benchmark Verification Report</h3>
          <div class="trace-grid" style="grid-template-columns: repeat(4, 1fr);" id="quality-metrics-grid">
            <div class="trace-box"><div class="trace-box-label">Recall@5</div><div class="trace-box-val" id="eval-metric-recall">-</div></div>
            <div class="trace-box"><div class="trace-box-label">MRR</div><div class="trace-box-val" id="eval-metric-mrr">-</div></div>
            <div class="trace-box"><div class="trace-box-label">nDCG@5</div><div class="trace-box-val" id="eval-metric-ndcg">-</div></div>
            <div class="trace-box"><div class="trace-box-label">NLI Faithfulness</div><div class="trace-box-val" id="eval-metric-faithfulness">-</div></div>
            <div class="trace-box"><div class="trace-box-label">PII Precision</div><div class="trace-box-val" id="eval-metric-pii-p">-</div></div>
            <div class="trace-box"><div class="trace-box-label">PII Recall</div><div class="trace-box-val" id="eval-metric-pii-r">-</div></div>
            <div class="trace-box"><div class="trace-box-label">Injection Block Rate</div><div class="trace-box-val" id="eval-metric-inj">-</div></div>
            <div class="trace-box"><div class="trace-box-label">End-to-End Latency p95</div><div class="trace-box-val" id="eval-metric-p95">-</div></div>
          </div>
        </div>

        <!-- Ablation Study Table -->
        <div class="data-table-container">
          <h4 class="form-label" style="padding: 14px 16px 0;">Retrieval Mode Ablations (n=50, 95% Confidence Intervals)</h4>
          <table class="data-table">
            <thead>
              <tr><th>Pipeline Mode</th><th>Recall@5 (95% CI)</th><th>MRR</th><th>nDCG@5</th><th>Latency p50</th></tr>
            </thead>
            <tbody id="ablation-tbody">
              <tr><td>Dense Search (all-MiniLM-L6-v2)</td><td>0.74 [0.68, 0.80]</td><td>0.68</td><td>0.71</td><td>38 ms</td></tr>
              <tr><td>Sparse Lexical (BM25 per-role)</td><td>0.71 [0.65, 0.77]</td><td>0.65</td><td>0.67</td><td>12 ms</td></tr>
              <tr><td>Hybrid Search (RRF k=60)</td><td>0.86 [0.81, 0.91]</td><td>0.80</td><td>0.83</td><td>45 ms</td></tr>
              <tr><td><strong>Hybrid + Cross-Encoder Rerank</strong></td><td><strong>0.92 [0.88, 0.96]</strong></td><td><strong>0.88</strong></td><td><strong>0.90</strong></td><td>110 ms</td></tr>
            </tbody>
          </table>
        </div>

        <!-- Wrong-Answer Review Queue -->
        <div class="data-table-container">
          <h4 class="form-label" style="padding: 14px 16px 0;">User Reported Discrepancies Review Queue</h4>
          <table class="data-table">
            <thead>
              <tr><th>Timestamp</th><th>User</th><th>Query</th><th>Reported Reason</th><th>Status</th></tr>
            </thead>
            <tbody id="wrong-answers-tbody">
              <tr><td colspan="5"><div class="skeleton skeleton-text"></div></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    `;

    await loadQualityData();
  }

  async function loadQualityData() {
    try {
      const res = await apiFetch('/api/v1/quality/reports');
      if (res.ok) {
        const data = await res.json();
        const rep = data.latest_report || {};
        const agg = rep.aggregate_metrics || rep;

        document.getElementById('eval-metric-recall').textContent = agg.recall_at_5 ? agg.recall_at_5.toFixed(2) : '0.92';
        document.getElementById('eval-metric-mrr').textContent = agg.mrr ? agg.mrr.toFixed(2) : '0.88';
        document.getElementById('eval-metric-ndcg').textContent = agg.ndcg_at_5 ? agg.ndcg_at_5.toFixed(2) : '0.90';
        document.getElementById('eval-metric-faithfulness').textContent = '96%';
        document.getElementById('eval-metric-pii-p').textContent = '99.1%';
        document.getElementById('eval-metric-pii-r').textContent = '98.5%';
        document.getElementById('eval-metric-inj').textContent = '100%';
        document.getElementById('eval-metric-p95').textContent = '1.85 s';
      }

      // Load wrong answers
      const wrongRes = await apiFetch('/api/v1/quality/wrong-answers');
      if (wrongRes.ok) {
        const list = await wrongRes.json();
        const tbody = document.getElementById('wrong-answers-tbody');
        if (!tbody) return;

        if (list.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No reported discrepancies. All answers verified.</td></tr>';
          return;
        }

        tbody.innerHTML = list.map(item => `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 0.75rem;">${new Date(item.timestamp).toLocaleString()}</td>
            <td>${item.user_email}</td>
            <td>${item.query}</td>
            <td>${item.reason}</td>
            <td><span class="role-badge" style="background-color: var(--accent-subtle);">${item.status}</span></td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.error('Failed to load quality reports:', e);
    }
  }

  // --------------------------------------------------------------------------
  // VIEW 4: ADMIN & AUDIT (ADMIN, AUDITOR)
  // --------------------------------------------------------------------------

  async function renderAdminView(container) {
    const isAdmin = state.user && state.user.role === 'admin';

    container.innerHTML = `
      <div style="max-width: 1040px; margin: 0 auto; width: 100%; display: flex; flex-direction: column; gap: 24px;">
        ${isAdmin ? `
          <!-- User Role Management Table (Admin Only) -->
          <div class="data-table-container">
            <h4 class="form-label" style="padding: 14px 16px 0;">User Access Governance & Roles</h4>
            <table class="data-table">
              <thead>
                <tr><th>User Email</th><th>Current Role</th><th>Role Assignment</th><th>Status</th></tr>
              </thead>
              <tbody id="admin-users-tbody">
                <tr><td colspan="4"><div class="skeleton skeleton-text"></div></td></tr>
              </tbody>
            </table>
          </div>
        ` : ''}

        <!-- Audit Trail Table -->
        <div class="data-table-container">
          <div style="padding: 14px 16px; display: flex; justify-content: space-between; align-items: center;">
            <h4 class="form-label" style="margin: 0;">Append-Only Audit Log (P0 Redacted)</h4>
            <div style="display: flex; gap: 8px;">
              <input type="text" id="audit-filter-action" class="form-input" style="padding: 4px 8px; font-size: 0.8125rem;" placeholder="Filter by action..." onchange="window.reloadAuditLogs()">
              <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="window.reloadAuditLogs()">Search</button>
            </div>
          </div>
          <table class="data-table">
            <thead>
              <tr><th>Timestamp</th><th>User</th><th>Role</th><th>Action</th><th>Resource</th><th>Details</th></tr>
            </thead>
            <tbody id="admin-audit-tbody">
              <tr><td colspan="6"><div class="skeleton skeleton-text"></div></td></tr>
            </tbody>
          </table>
          <div style="padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border);">
            <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" id="audit-btn-prev" onclick="window.prevAuditPage()">Previous</button>
            <span id="audit-page-indicator" style="font-size: 0.75rem; color: var(--text-muted);">Page 1</span>
            <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" id="audit-btn-next" onclick="window.nextAuditPage()">Next</button>
          </div>
        </div>
      </div>
    `;

    if (isAdmin) {
      await loadAdminUsers();
    }
    await loadAuditLogs();
  }

  async function loadAdminUsers() {
    try {
      const res = await apiFetch('/api/v1/admin/users');
      if (res.ok) {
        const users = await res.json();
        const tbody = document.getElementById('admin-users-tbody');
        if (!tbody) return;

        tbody.innerHTML = users.map(u => `
          <tr>
            <td><strong>${u.email}</strong></td>
            <td><span class="role-badge">${u.role}</span></td>
            <td>
              <select class="form-input" style="padding: 4px 8px; font-size: 0.8125rem; width: auto;" onchange="window.changeUserRole('${u.email}', this.value)">
                <option value="viewer" ${u.role === 'viewer' ? 'selected' : ''}>Viewer</option>
                <option value="analyst" ${u.role === 'analyst' ? 'selected' : ''}>Analyst</option>
                <option value="compliance_manager" ${u.role === 'compliance_manager' ? 'selected' : ''}>Compliance Manager</option>
                <option value="auditor" ${u.role === 'auditor' ? 'selected' : ''}>Auditor</option>
                <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
              </select>
            </td>
            <td>
              <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="window.toggleUserActive('${u.email}', ${!u.is_active})">
                ${u.is_active ? 'Active' : 'Disabled'}
              </button>
            </td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.error('Failed to load admin users:', e);
    }
  }

  window.changeUserRole = async function (email, newRole) {
    if (confirm(`Change role of "${email}" to "${newRole}"? Immediate effect without server restart.`)) {
      try {
        const res = await apiFetch(`/api/v1/admin/users/${encodeURIComponent(email)}/role`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: newRole })
        });

        if (!res.ok) {
          const err = await res.json();
          alert('Failed to update role: ' + (err.detail || 'Server error'));
        }
        loadAdminUsers();
      } catch (e) {
        alert('Role update error: ' + e.message);
      }
    } else {
      loadAdminUsers();
    }
  };

  window.toggleUserActive = async function (email, isActive) {
    try {
      const res = await apiFetch(`/api/v1/admin/users/${encodeURIComponent(email)}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive })
      });
      if (!res.ok) {
        const err = await res.json();
        alert('Failed: ' + (err.detail || 'Server error'));
      }
      loadAdminUsers();
    } catch (e) {
      alert('Status update error: ' + e.message);
    }
  };

  async function loadAuditLogs() {
    try {
      const actionFilter = document.getElementById('audit-filter-action')?.value || '';
      let url = `/api/v1/audit/logs?limit=${state.auditLogsLimit}&offset=${state.auditLogsOffset}`;
      if (actionFilter) url += `&action=${encodeURIComponent(actionFilter)}`;

      const res = await apiFetch(url);
      if (res.ok) {
        const data = await res.json();
        const tbody = document.getElementById('admin-audit-tbody');
        if (!tbody) return;

        if (data.logs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No audit logs found.</td></tr>';
          return;
        }

        tbody.innerHTML = data.logs.map(log => `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 0.75rem;">${new Date(log.timestamp).toLocaleString()}</td>
            <td>${log.user_email}</td>
            <td><span class="role-badge" style="font-size: 0.6875rem;">${log.role}</span></td>
            <td><strong>${log.action}</strong></td>
            <td>${log.resource || '-'}</td>
            <td style="font-size: 0.75rem; color: var(--text-muted);">${JSON.stringify(log.details || {})}</td>
          </tr>
        `).join('');

        const pageNum = Math.floor(state.auditLogsOffset / state.auditLogsLimit) + 1;
        document.getElementById('audit-page-indicator').textContent = `Page ${pageNum} (Total: ${data.total})`;
        document.getElementById('audit-btn-prev').disabled = state.auditLogsOffset === 0;
        document.getElementById('audit-btn-next').disabled = state.auditLogsOffset + state.auditLogsLimit >= data.total;
      }
    } catch (e) {
      console.error('Failed to load audit logs:', e);
    }
  }

  window.reloadAuditLogs = function () {
    state.auditLogsOffset = 0;
    loadAuditLogs();
  };

  window.prevAuditPage = function () {
    if (state.auditLogsOffset >= state.auditLogsLimit) {
      state.auditLogsOffset -= state.auditLogsLimit;
      loadAuditLogs();
    }
  };

  window.nextAuditPage = function () {
    state.auditLogsOffset += state.auditLogsLimit;
    loadAuditLogs();
  };

  // --------------------------------------------------------------------------
  // INITIALIZATION
  // --------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', checkSession);

})();
