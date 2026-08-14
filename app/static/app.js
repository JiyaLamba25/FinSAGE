const STORAGE_KEY = 'finsage_conversations_v1';
const THEME_KEY = 'finsage_theme_pref';
const DEFAULT_SESSION_ID = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}`);
const EXAMPLE_QUESTIONS = [
  'Show top 5 products by sales',
  'Compare profit by region',
  'Which category had the highest discount?',
  'What are the biggest sales trends this year?',
  'Show the top 10 customers by revenue',
  'Which region is driving the most profit?',
  'Compare discount rates across categories',
  'What products have the strongest margin?',
  'Show the fastest-growing segment by sales',
  'Which ship mode produces the highest profit?',
];

const LOADING_STAGE_DELAY_MS = 3000;
let loadingStageTimer = null;
let recognitionInstance = null;
let micInputPending = false;

const appState = {
  conversations: [],
  activeConversationId: null,
  activeTab: 'chat',
  readOnlyMode: false,
  isLoading: false,
  loadingStage: 'thinking',
  isListening: false,
  voiceChainActive: false,
  sessionId: DEFAULT_SESSION_ID(),
  authToken: null,
  themePreference: localStorage.getItem(THEME_KEY) || 'light',
};

const elements = {
  conversationList: document.getElementById('conversation-list'),
  chatContent: document.getElementById('chat-content'),
  chatThread: document.getElementById('chat-thread'),
  landingState: document.getElementById('landing-state'),
  exampleChips: document.querySelector('.example-chips'),
  chatForm: document.getElementById('chat-form'),
  chatInput: document.getElementById('chat-input'),
  chatSendButton: document.querySelector('#chat-form button[type="submit"]'),
  micButton: document.getElementById('mic-btn'),
  statusBanner: document.getElementById('status-banner'),
  searchForm: document.getElementById('search-form'),
  searchResults: document.getElementById('search-results'),
  recentRecords: document.getElementById('recent-records'),
  adminAuth: document.getElementById('admin-auth'),
  adminContent: document.getElementById('admin-content'),
  themePref: document.getElementById('theme-pref'),
  settingsLogoutBtn: document.getElementById('settings-logout-btn'),
  recentRecordsLimit: document.getElementById('recent-records-limit'),
};

function init() {
  appState.conversations = loadConversations();
  elements.themePref.value = appState.themePreference;
  if (elements.recentRecordsLimit) {
    elements.recentRecordsLimit.value = '5';
  }
  applyTheme(appState.themePreference);
  bindEvents();
  renderExampleChips();
  renderSidebar();
  renderViews();
  renderChat();
  renderAdmin();
  renderSettingsView();
}

function bindEvents() {
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.addEventListener('click', () => switchView(button.dataset.view));
  });

  document.getElementById('new-chat-btn').addEventListener('click', startNewChat);
  document.getElementById('clear-history-btn').addEventListener('click', clearHistory);
  elements.chatForm.addEventListener('submit', handleChatSubmit);
  if (elements.micButton) {
    elements.micButton.addEventListener('click', handleMicClick);
  }
  if (elements.chatInput) {
    elements.chatInput.addEventListener('input', () => {
      micInputPending = false;
      appState.voiceChainActive = false;
    });
  }
  if (elements.exampleChips) {
    elements.exampleChips.addEventListener('click', (event) => {
      const chip = event.target.closest('.chip');
      if (!chip) {
        return;
      }
      micInputPending = false;
      elements.chatInput.value = chip.dataset.question;
      elements.chatForm.requestSubmit();
    });
  }

  elements.searchForm.addEventListener('submit', (event) => {
    event.preventDefault();
    searchRecords();
  });

  document.getElementById('refresh-records-btn').addEventListener('click', loadRecentRecords);
  if (elements.recentRecordsLimit) {
    elements.recentRecordsLimit.addEventListener('change', loadRecentRecords);
  }
  elements.themePref.addEventListener('change', (event) => {
    const theme = event.target.value;
    appState.themePreference = theme;
    localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
    showStatus('Theme updated.', 'success');
  });
  document.getElementById('clear-settings-btn').addEventListener('click', clearHistory);
  elements.settingsLogoutBtn.addEventListener('click', handleLogout);

  elements.conversationList.addEventListener('click', (event) => {
    const deleteButton = event.target.closest('.conv-delete');
    if (deleteButton) {
      removeConversation(deleteButton.dataset.id);
      return;
    }
    const item = event.target.closest('.conv-item');
    if (item) {
      loadConversation(item.dataset.id);
    }
  });
}

function scrollChatToBottom() {
  if (elements.chatContent) {
    elements.chatContent.scrollTop = elements.chatContent.scrollHeight;
  }
}

// --- Voice input ---
function handleMicClick() {
  const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionClass) {
    showStatus('Voice input is not supported in this browser. Try Chrome.', 'error');
    return;
  }

  if (appState.isListening) {
    recognitionInstance?.stop();
    return;
  }

  recognitionInstance = new SpeechRecognitionClass();
  recognitionInstance.lang = 'en-US';
  recognitionInstance.continuous = false;
  recognitionInstance.interimResults = false;
  recognitionInstance.maxAlternatives = 1;

  recognitionInstance.onstart = () => {
    appState.isListening = true;
    elements.micButton.classList.add('listening');
  };

  recognitionInstance.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    elements.chatInput.value = transcript;
    micInputPending = true;
    elements.chatInput.focus();
  };

  recognitionInstance.onerror = () => {
    showStatus('Could not hear that clearly — please try again.', 'error');
  };

  recognitionInstance.onend = () => {
    appState.isListening = false;
    elements.micButton.classList.remove('listening');
  };

  recognitionInstance.start();
}

// --- Voice output ---
function buildSpokenSummary(text) {
  if (!text) return '';

  let cleaned = text
    .replace(/\|.*\|/g, ' ')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`/g, '')
    .replace(/#+\s*/g, '');

  const lines = cleaned.split('\n').map((l) => l.trim()).filter(Boolean);
  const contentLines = lines.filter((l) => !/^assumption:/i.test(l) && !/^-{2,}$/.test(l));
  if (!contentLines.length) return '';

  const bulletPattern = /^(\d+[.)]|[-•])\s*/;
  const introLines = [];
  const listLines = [];
  contentLines.forEach((line) => {
    if (bulletPattern.test(line)) {
      listLines.push(line.replace(bulletPattern, ''));
    } else {
      introLines.push(line);
    }
  });

  let spoken = introLines.slice(0, 1).join(' ');
  if (listLines.length) {
    spoken += (spoken ? '. ' : '') + `Top result: ${listLines[0]}`;
  }

  return spoken || contentLines[0];
}

function speakConcise(text) {
  if (!appState.voiceChainActive) return;
  if (!('speechSynthesis' in window)) return;
  const spoken = buildSpokenSummary(text);
  if (!spoken) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(spoken);
  utterance.lang = 'en-US';
  utterance.rate = 1;
  window.speechSynthesis.speak(utterance);
}

function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (error) {
    console.warn('Unable to load conversations', error);
    return [];
  }
}

function saveConversations() {
  const trimmed = appState.conversations.slice(0, 20);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
}

function renderSidebar() {
  if (!appState.conversations.length) {
    elements.conversationList.innerHTML = '<li class="muted">No conversations yet.</li>';
    return;
  }

  const visibleConversations = [...appState.conversations];
  elements.conversationList.innerHTML = '';
  visibleConversations.forEach((conversation) => {
    const item = document.createElement('li');
    item.className = `conv-item${conversation.id === appState.activeConversationId ? ' active' : ''}`;
    item.dataset.id = conversation.id;
    item.innerHTML = `
      <div class="conv-title">${escapeHtml(conversation.title || 'Conversation')}</div>
      <button class="conv-delete" data-id="${conversation.id}" type="button" aria-label="Delete conversation">×</button>
    `;
    elements.conversationList.appendChild(item);
  });
}

function renderViews() {
  document.querySelectorAll('.view').forEach((view) => view.classList.remove('active'));
  document.querySelectorAll('.view').forEach((view) => view.classList.add('hidden'));
  const current = document.getElementById(`${appState.activeTab}-view`);
  if (current) {
    current.classList.remove('hidden');
    current.classList.add('active');
  }
  document.querySelectorAll('.nav-btn').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === appState.activeTab);
  });
  elements.chatForm.classList.toggle('hidden', appState.activeTab !== 'chat');
}

function switchView(viewName) {
  appState.activeTab = viewName;
  renderViews();
  if (viewName === 'records') {
    loadRecentRecords();
  }
  if (viewName === 'search') {
    elements.searchResults.innerHTML = '<p>Enter an order ID to begin.</p>';
  }
  if (viewName === 'admin') {
    renderAdmin();
  }
  if (viewName === 'settings') {
    renderSettingsView();
  }
}

function startNewChat() {
  appState.activeTab = 'chat';
  appState.activeConversationId = null;
  appState.readOnlyMode = false;
  appState.sessionId = DEFAULT_SESSION_ID();
  renderViews();
  renderSidebar();
  renderChat();
  elements.chatInput.focus();
}

function setChatSubmitting(isSubmitting) {
  appState.isLoading = isSubmitting;

  if (loadingStageTimer) {
    clearTimeout(loadingStageTimer);
    loadingStageTimer = null;
  }

  if (isSubmitting) {
    appState.loadingStage = 'thinking';
    loadingStageTimer = setTimeout(() => {
      appState.loadingStage = 'preparing';
      loadingStageTimer = null;
      renderChat();
      scrollChatToBottom();
    }, LOADING_STAGE_DELAY_MS);
  } else {
    appState.loadingStage = 'thinking';
  }

  if (elements.chatInput) {
    elements.chatInput.disabled = isSubmitting;
  }
  if (elements.chatSendButton) {
    elements.chatSendButton.disabled = isSubmitting;
    elements.chatSendButton.textContent = isSubmitting ? 'Sending...' : 'Send';
  }
  renderChat();
  scrollChatToBottom();
}

function renderChat() {
  const conversation = getActiveConversation();
  const messages = conversation?.messages || [];
  if (!messages.length) {
    elements.landingState.classList.remove('hidden');
    elements.chatThread.classList.add('hidden');
    renderExampleChips();
    return;
  }

  elements.landingState.classList.add('hidden');
  elements.chatThread.classList.remove('hidden');
  elements.chatThread.innerHTML = '';
  messages.forEach((message, index) => {
    const messageEl = document.createElement('div');
    messageEl.className = `message ${message.role}`;

    // Chart renders BEFORE the text (issue #2 — visuals first, easier to read).
    if (message.chart) {
      const img = document.createElement('img');
      img.src = `data:image/png;base64,${message.chart}`;
      img.alt = 'Generated chart';
      messageEl.appendChild(img);
    }

    const text = document.createElement('div');
    text.className = 'message-text';
    if (message.role === 'assistant') {
      text.innerHTML = renderMarkdown(message.text);
    } else {
      text.textContent = message.text;
    }
    messageEl.appendChild(text);

    if (message.anomalies?.length) {
      const anomalyBanner = document.createElement('div');
      anomalyBanner.className = 'anomaly-banner';
      anomalyBanner.innerHTML = `
        <div class="anomaly-banner-title">⚠ Insight${message.anomalies.length > 1 ? 's' : ''}</div>
        <ul>${message.anomalies.map((a) => `<li>${escapeHtml(a.message)}</li>`).join('')}</ul>
      `;
      messageEl.appendChild(anomalyBanner);
    }

    if (message.role === 'assistant') {
      const actions = document.createElement('div');
      actions.className = 'message-actions';
      const howButton = document.createElement('button');
      howButton.className = 'badge-btn';
      howButton.type = 'button';
      howButton.textContent = message.explanation ? 'Hide How' : 'How?';
      howButton.dataset.index = index;
      howButton.addEventListener('click', () => toggleExplanation(index));
      actions.appendChild(howButton);
      messageEl.appendChild(actions);

      if (message.options?.length) {
        const optionsRow = document.createElement('div');
        optionsRow.className = 'options-row';
        message.options.forEach((option) => {
          const optionButton = document.createElement('button');
          optionButton.type = 'button';
          optionButton.textContent = option;
          optionButton.addEventListener('click', () => handleClarificationChoice(option));
          optionsRow.appendChild(optionButton);
        });
        messageEl.appendChild(optionsRow);
      }

      if (message.explanation) {
        const explanationBox = document.createElement('div');
        explanationBox.className = 'explanation-box';
        explanationBox.innerHTML = `
          <div><strong>Explanation</strong></div>
          <div>${escapeHtml(message.explanation)}</div>
          <pre>${escapeHtml(message.sql || '')}</pre>
          <div>Rows: ${message.rowCount ?? 0}</div>
        `;
        messageEl.appendChild(explanationBox);
      }
    }

    elements.chatThread.appendChild(messageEl);
  });

  if (appState.isLoading) {
    const pending = document.createElement('div');
    pending.className = 'message assistant';
    pending.textContent = appState.loadingStage === 'preparing' ? 'Preparing your answer...' : 'Thinking...';
    elements.chatThread.appendChild(pending);
  }
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const question = elements.chatInput.value.trim();
  if (!question || appState.readOnlyMode || appState.isLoading) {
    return;
  }

  appState.voiceChainActive = micInputPending;
  micInputPending = false;

  const conversation = ensureConversation();
  conversation.messages.push({ role: 'user', text: question });
  saveConversations();
  renderSidebar();
  elements.chatInput.value = '';
  setChatSubmitting(true);

  try {
    const data = await fetchJson('/chat/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: appState.sessionId }),
    });

    conversation.messages.push({
      role: 'assistant',
      text: data?.answer || 'I have an update for you.',
      chart: data?.chart || null,
      options: data?.options || [],
      needsClarification: Boolean(data?.needs_clarification),
      generatedSql: data?.generated_sql || null,
      anomalies: data?.anomalies || [],
    });
    conversation.title = deriveTitle(question);
    saveConversations();
    renderSidebar();
    speakConcise(data?.answer);
  } catch (error) {
    showStatus(error.message, 'error');
    conversation.messages.push({ role: 'assistant', text: `Sorry — ${error.message}` });
    saveConversations();
    speakConcise(error.message);
  } finally {
    setChatSubmitting(false);
  }
}

async function handleClarificationChoice(option) {
  if (option === 'Other') {
    elements.chatInput.focus();
    return;
  }
  const conversation = getActiveConversation();
  if (appState.isLoading) {
    return;
  }

  conversation.messages.push({ role: 'user', text: option });
  saveConversations();
  renderChat();
  scrollChatToBottom();
  setChatSubmitting(true);
  try {
    const data = await fetchJson('/chat/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: option, session_id: appState.sessionId }),
    });
    conversation.messages.push({
      role: 'assistant',
      text: data?.answer || 'I have an update for you.',
      chart: data?.chart || null,
      options: data?.options || [],
      needsClarification: Boolean(data?.needs_clarification),
      generatedSql: data?.generated_sql || null,
      anomalies: data?.anomalies || [],
    });
    saveConversations();
    speakConcise(data?.answer);
  } catch (error) {
    showStatus(error.message, 'error');
    conversation.messages.push({ role: 'assistant', text: `Sorry — ${error.message}` });
    saveConversations();
    speakConcise(error.message);
  } finally {
    setChatSubmitting(false);
  }
}

async function toggleExplanation(index) {
  const conversation = getActiveConversation();
  if (!conversation) return;
  const message = conversation.messages[index];
  if (!message) return;

  if (message.explanation) {
    message.explanation = null;
    renderChat();
    return;
  }

  try {
    const data = await fetchJson('/chat/explain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: appState.sessionId }),
    });
    message.explanation = data?.explanation;
    message.sql = data?.sql;
    message.rowCount = data?.row_count;
    saveConversations();
    renderChat();
  } catch (error) {
    showStatus(error.message, 'error');
  }
}

async function searchRecords() {
  const orderId = document.getElementById('order-id-input').value.trim();
  if (!orderId) {
    elements.searchResults.innerHTML = '<p>Please enter an order ID.</p>';
    return;
  }

  try {
    const data = await fetchJson(`/records/search/${encodeURIComponent(orderId)}`);
    renderRecordTable(elements.searchResults, data, ['row_id', 'product_name', 'category', 'sub_category', 'region', 'quantity', 'sales', 'profit']);
  } catch (error) {
    elements.searchResults.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

async function loadRecentRecords() {
  const limit = elements.recentRecordsLimit?.value || '5';
  try {
    const data = await fetchJson(`/records/recent?limit=${encodeURIComponent(limit)}`);
    renderRecordTable(elements.recentRecords, data, ['row_id', 'product_name', 'category', 'region', 'quantity', 'sales', 'profit']);
  } catch (error) {
    elements.recentRecords.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function renderRecordTable(container, rows, columns) {
  if (!rows?.length) {
    container.innerHTML = '<p>No matching records.</p>';
    return;
  }

  const table = document.createElement('table');
  table.className = 'results-table';
  table.innerHTML = `
    <thead>
      <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr>
    </thead>
    <tbody></tbody>
  `;
  const body = table.querySelector('tbody');
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    columns.forEach((column) => {
      const td = document.createElement('td');
      td.textContent = row[column] ?? '';
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  container.innerHTML = '';
  container.appendChild(table);
}

function renderAdmin() {
  if (!appState.authToken) {
    elements.adminAuth.innerHTML = `
      <form id="login-form" class="admin-form">
        <input id="username" placeholder="Username" required />
        <input id="password" type="password" placeholder="Password" required />
        <button type="submit">Login</button>
      </form>
    `;
    elements.adminContent.classList.add('hidden');
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    return;
  }

  elements.adminAuth.innerHTML = '<p class="muted">Authenticated</p>';
  elements.adminContent.classList.remove('hidden');
  elements.adminContent.innerHTML = `
    <section class="admin-section">
      <h3>Add Record</h3>
      <form id="add-record-form" class="admin-form">
        <div class="admin-form-stack">
          <fieldset class="admin-form-group">
            <legend>Order Info</legend>
            <div class="admin-form-grid">
              <label class="admin-field"><span class="field-title">Order ID</span><input name="order_id" placeholder="Order ID" required /></label>
              <label class="admin-field"><span class="field-title">Order Date</span><input name="order_date" type="date" required /></label>
              <label class="admin-field"><span class="field-title">Ship Date</span><input name="ship_date" type="date" required /></label>
              <label class="admin-field"><span class="field-title">Ship Mode</span><select name="ship_mode" required>
                <option value="Standard Class">Standard Class</option>
                <option value="Second Class">Second Class</option>
                <option value="First Class">First Class</option>
                <option value="Same Day">Same Day</option>
              </select></label>
            </div>
          </fieldset>
          <fieldset class="admin-form-group">
            <legend>Customer Info</legend>
            <div class="admin-form-grid">
              <label class="admin-field"><span class="field-title">Customer ID</span><input name="customer_id" placeholder="Customer ID" required /></label>
              <label class="admin-field"><span class="field-title">Customer Name</span><input name="customer_name" placeholder="Customer Name" required /></label>
              <label class="admin-field"><span class="field-title">Segment</span><select name="segment" required>
                <option value="Consumer">Consumer</option>
                <option value="Corporate">Corporate</option>
                <option value="Home Office">Home Office</option>
              </select></label>
            </div>
          </fieldset>
          <fieldset class="admin-form-group">
            <legend>Location</legend>
            <div class="admin-form-grid">
              <label class="admin-field"><span class="field-title">Country</span><input name="country" placeholder="Country" required /></label>
              <label class="admin-field"><span class="field-title">City</span><input name="city" placeholder="City" required /></label>
              <label class="admin-field"><span class="field-title">State</span><input name="state" placeholder="State" required /></label>
              <label class="admin-field"><span class="field-title">Postal Code</span><input name="postal_code" type="number" placeholder="e.g. 10001" min="0" required /></label>
              <label class="admin-field"><span class="field-title">Region</span><select name="region" required>
                <option value="Central">Central</option>
                <option value="East">East</option>
                <option value="South">South</option>
                <option value="West">West</option>
              </select></label>
            </div>
            <small class="field-help">Use a valid postal code number.</small>
          </fieldset>
          <fieldset class="admin-form-group">
            <legend>Product Info</legend>
            <div class="admin-form-grid">
              <label class="admin-field"><span class="field-title">Product ID</span><input name="product_id" placeholder="Product ID" required /></label>
              <label class="admin-field"><span class="field-title">Category</span><input name="category" placeholder="Category" required /></label>
              <label class="admin-field"><span class="field-title">Sub Category</span><input name="sub_category" placeholder="Sub Category" required /></label>
              <label class="admin-field"><span class="field-title">Product Name</span><input name="product_name" placeholder="Product Name" required /></label>
            </div>
          </fieldset>
          <fieldset class="admin-form-group">
            <legend>Financials</legend>
            <div class="admin-form-grid">
              <label class="admin-field"><span class="field-title">Sales</span><input name="sales" type="number" step="0.01" min="0" placeholder="Sales" required /></label>
              <label class="admin-field"><span class="field-title">Quantity</span><input name="quantity" type="number" step="1" min="0" placeholder="Quantity" required /></label>
              <label class="admin-field"><span class="field-title">Discount</span><input name="discount" type="number" step="0.01" min="0" max="1" placeholder="Discount" required /></label>
              <label class="admin-field"><span class="field-title">Profit</span><input name="profit" type="number" step="0.01" min="0" placeholder="Profit" required /></label>
            </div>
          </fieldset>
        </div>
        <button type="submit">Add Record</button>
      </form>
    </section>
    <section class="admin-section">
      <h3>Edit / Delete Records</h3>
      <form id="admin-search-form" class="admin-form">
        <input id="admin-order-id" placeholder="Order ID" required />
        <button type="submit">Find</button>
      </form>
      <div id="admin-record-list"></div>
    </section>
    <section class="admin-section">
      <h3>System Stats</h3>
      <div class="view-card-head">
        <p class="muted">Query cache performance</p>
        <button id="refresh-cache-stats-btn" class="secondary-btn" type="button">Refresh</button>
      </div>
      <div id="cache-stats-panel" class="results-panel"></div>
    </section>
  `;
  document.getElementById('add-record-form').addEventListener('submit', handleAddRecord);
  document.getElementById('admin-search-form').addEventListener('submit', handleAdminSearch);
  document.getElementById('refresh-cache-stats-btn').addEventListener('click', loadCacheStats);
  loadCacheStats();
}

async function loadCacheStats() {
  const panel = document.getElementById('cache-stats-panel');
  if (!panel) return;
  try {
    const data = await fetchJson('/admin/cache-stats', {
      headers: { Authorization: `Bearer ${appState.authToken}` },
    });
    panel.innerHTML = `
      <ul class="stats-list">
        <li><strong>Hit rate:</strong> ${data.hit_rate_pct}%</li>
        <li><strong>Cache hits:</strong> ${data.cache_hits} / ${data.total_lookups} lookups</li>
        <li><strong>Estimated Gemini calls saved:</strong> ${data.estimated_calls_saved}</li>
        <li><strong>Estimated cost saved:</strong> $${data.estimated_cost_saved_usd}</li>
        <li><strong>Current cache size:</strong> ${data.current_cache_size} entries</li>
      </ul>
    `;
  } catch (error) {
    panel.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  try {
    const data = await fetchJson('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    appState.authToken = data?.access_token;
    renderAdmin();
    renderSettingsView();
    showStatus('Logged in successfully.', 'success');
  } catch (error) {
    showStatus(error.message, 'error');
  }
}

async function handleAddRecord(event) {
  event.preventDefault();
  const formData = new FormData(event.target);
  const payload = Object.fromEntries(formData.entries());
  payload.postal_code = Number(payload.postal_code);
  payload.sales = Number(payload.sales);
  payload.quantity = Number(payload.quantity);
  payload.discount = Number(payload.discount);
  payload.profit = Number(payload.profit);

  try {
    await fetchJson('/records', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${appState.authToken}`,
      },
      body: JSON.stringify(payload),
    });
    event.target.reset();
    showStatus('Record added.', 'success');
  } catch (error) {
    showStatus(error.message, 'error');
  }
}

async function handleAdminSearch(event) {
  event.preventDefault();
  const orderId = document.getElementById('admin-order-id').value.trim();
  const list = document.getElementById('admin-record-list');
  try {
    const data = await fetchJson(`/records/search/${encodeURIComponent(orderId)}`);
    list.innerHTML = '';
    data.forEach((record) => {
      const card = document.createElement('div');
      card.className = 'view-card admin-record-card';
      card.innerHTML = `
        <p><strong>${escapeHtml(record.product_name || '')}</strong></p>
        <p>Row ID: ${escapeHtml(String(record.row_id ?? ''))}</p>
        <p>Category: ${escapeHtml(record.category || '')}</p>
        <p>Sales: ${escapeHtml(String(record.sales ?? ''))}</p>
        <div class="options-row">
          <button class="badge-btn" type="button" data-action="edit" data-id="${record.row_id}">Edit</button>
          <button class="badge-btn" type="button" data-action="delete" data-id="${record.row_id}">Delete</button>
        </div>
        <form class="admin-edit-form hidden" data-row-id="${record.row_id}">
          <div class="admin-form-stack">
            <fieldset class="admin-form-group">
              <legend>Quick Edit</legend>
              <div class="admin-form-grid">
                <label class="admin-field"><span class="field-title">Sales</span><input name="sales" type="number" min="0" step="0.01" value="" /></label>
                <label class="admin-field"><span class="field-title">Quantity</span><input name="quantity" type="number" min="0" step="1" value="" /></label>
                <label class="admin-field"><span class="field-title">Discount</span><input name="discount" type="number" min="0" step="0.01" value="" /></label>
                <label class="admin-field"><span class="field-title">Profit</span><input name="profit" type="number" min="0" step="0.01" value="" /></label>
                <label class="admin-field"><span class="field-title">Ship Mode</span><select name="ship_mode">
                  <option value="Standard Class">Standard Class</option>
                  <option value="Second Class">Second Class</option>
                  <option value="First Class">First Class</option>
                  <option value="Same Day">Same Day</option>
                </select></label>
                <label class="admin-field"><span class="field-title">Region</span><select name="region">
                  <option value="Central">Central</option>
                  <option value="East">East</option>
                  <option value="South">South</option>
                  <option value="West">West</option>
                </select></label>
              </div>
            </fieldset>
            <fieldset class="admin-form-group">
              <legend>More Fields</legend>
              <button class="toggle-section-btn" type="button" aria-expanded="false">+ More fields</button>
              <div class="admin-form-grid edit-more-fields hidden">
                <label class="admin-field"><span class="field-title">Order ID</span><input name="order_id" value="" /></label>
                <label class="admin-field"><span class="field-title">Order Date</span><input name="order_date" type="date" value="" /></label>
                <label class="admin-field"><span class="field-title">Ship Date</span><input name="ship_date" type="date" value="" /></label>
                <label class="admin-field"><span class="field-title">Customer ID</span><input name="customer_id" value="" /></label>
                <label class="admin-field"><span class="field-title">Customer Name</span><input name="customer_name" value="" /></label>
                <label class="admin-field"><span class="field-title">Segment</span><select name="segment">
                  <option value="Consumer">Consumer</option>
                  <option value="Corporate">Corporate</option>
                  <option value="Home Office">Home Office</option>
                </select></label>
                <label class="admin-field"><span class="field-title">Country</span><input name="country" value="" /></label>
                <label class="admin-field"><span class="field-title">City</span><input name="city" value="" /></label>
                <label class="admin-field"><span class="field-title">State</span><input name="state" value="" /></label>
                <label class="admin-field"><span class="field-title">Postal Code</span><input name="postal_code" type="number" min="0" value="" /></label>
                <label class="admin-field"><span class="field-title">Product ID</span><input name="product_id" value="" /></label>
                <label class="admin-field"><span class="field-title">Category</span><input name="category" value="" /></label>
                <label class="admin-field"><span class="field-title">Sub Category</span><input name="sub_category" value="" /></label>
                <label class="admin-field"><span class="field-title">Product Name</span><input name="product_name" value="" /></label>
              </div>
            </fieldset>
          </div>
          <button type="submit">Save</button>
        </form>
      `;
      const editButton = card.querySelector('button[data-action="edit"]');
      const form = card.querySelector('form.admin-edit-form');
      const toggleButton = card.querySelector('.toggle-section-btn');
      const extraFields = card.querySelector('.edit-more-fields');
      editButton.addEventListener('click', async () => {
        try {
          const fullRecord = await fetchJson(`/records/${record.row_id}`, {
            headers: { Authorization: `Bearer ${appState.authToken}` },
          });
          populateEditForm(form, fullRecord);
          form.classList.remove('hidden');
          form.querySelector('input[name="sales"]').focus();
        } catch (error) {
          showStatus(error.message, 'error');
        }
      });
      if (toggleButton && extraFields) {
        toggleButton.addEventListener('click', () => {
          const expanded = toggleButton.getAttribute('aria-expanded') === 'true';
          toggleButton.setAttribute('aria-expanded', String(!expanded));
          extraFields.classList.toggle('hidden', expanded);
          toggleButton.textContent = expanded ? '+ More fields' : '− Less fields';
        });
      }
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        updateRecord(record.row_id, form, form.dataset.originalRecord ? JSON.parse(form.dataset.originalRecord) : null);
      });
      list.appendChild(card);
    });
    list.querySelectorAll('button[data-action="delete"]').forEach((button) => {
      button.addEventListener('click', () => deleteRecord(button.dataset.id));
    });
  } catch (error) {
    list.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function populateEditForm(form, record) {
  const fields = form.querySelectorAll('input, select');
  fields.forEach((field) => {
    const value = record?.[field.name];
    field.value = value === null || value === undefined ? '' : value;
  });
  form.dataset.originalRecord = JSON.stringify(record || {});
}

function normalizeFieldValue(key, value) {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed === '') {
      return '';
    }
    if (['quantity', 'sales', 'discount', 'profit', 'postal_code'].includes(key)) {
      const numericValue = Number(trimmed);
      return Number.isFinite(numericValue) ? numericValue : trimmed;
    }
    return trimmed;
  }
  if (['quantity', 'sales', 'discount', 'profit', 'postal_code'].includes(key) && typeof value === 'number') {
    return value;
  }
  return value;
}

function buildUpdatePayload(form, originalRecord = {}) {
  const payload = {};
  const formData = new FormData(form);

  for (const [key, value] of formData.entries()) {
    const currentValue = normalizeFieldValue(key, value);
    const previousValue = normalizeFieldValue(key, originalRecord?.[key]);
    if (currentValue !== previousValue && !['row_id', 'id'].includes(key)) {
      payload[key] = currentValue;
    }
  }
  return payload;
}

async function updateRecord(rowId, form, originalRecord) {
  const payload = buildUpdatePayload(form, originalRecord);
  if (!Object.keys(payload).length) {
    showStatus('No changes made.', 'error');
    return;
  }
  try {
    await fetchJson(`/records/${rowId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${appState.authToken}`,
      },
      body: JSON.stringify(payload),
    });
    showStatus('Record updated.', 'success');
  } catch (error) {
    showStatus(error.message, 'error');
  }
}

async function deleteRecord(rowId) {
  if (!window.confirm('Delete this record?')) {
    return;
  }
  try {
    await fetchJson(`/records/${rowId}`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${appState.authToken}`,
      },
    });
    showStatus('Record deleted.', 'success');
  } catch (error) {
    showStatus(error.message, 'error');
  }
}

function clearHistory() {
  appState.conversations = [];
  appState.activeConversationId = null;
  appState.readOnlyMode = false;
  localStorage.removeItem(STORAGE_KEY);
  renderSidebar();
  renderChat();
  showStatus('Conversation history cleared.', 'success');
}

async function fetchJson(url, options = {}, fallbackMessage = 'Something went wrong processing that request. Please try again.') {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    throw new Error(fallbackMessage);
  }

  let bodyText = '';
  try {
    bodyText = await response.text();
  } catch (error) {
    throw new Error(fallbackMessage);
  }

  if (!response.ok) {
    throw new Error(fallbackMessage);
  }

  if (!bodyText) {
    return null;
  }

  try {
    return JSON.parse(bodyText);
  } catch (error) {
    throw new Error(fallbackMessage);
  }
}

function renderSettingsView() {
  if (!elements.settingsLogoutBtn) {
    return;
  }
  elements.settingsLogoutBtn.classList.toggle('hidden', !appState.authToken);
}

function handleLogout() {
  appState.authToken = null;
  renderSettingsView();
  renderAdmin();
  showStatus('Logged out.', 'success');
}

function applyTheme(theme) {
  document.body.classList.toggle('dark-mode', theme === 'dark');
}

function getActiveConversation() {
  return appState.conversations.find((conversation) => conversation.id === appState.activeConversationId) || null;
}

function ensureConversation() {
  let conversation = getActiveConversation();
  if (!conversation) {
    conversation = { id: crypto.randomUUID(), title: 'New conversation', messages: [] };
    appState.conversations.unshift(conversation);
    appState.activeConversationId = conversation.id;
    appState.readOnlyMode = false;
  }
  return conversation;
}

function loadConversation(conversationId) {
  appState.activeConversationId = conversationId;
  appState.readOnlyMode = true;
  appState.activeTab = 'chat';
  renderViews();
  renderSidebar();
  renderChat();
  scrollChatToBottom();
  showStatus('Loaded conversation history.', 'success');
}

function removeConversation(conversationId) {
  appState.conversations = appState.conversations.filter((conversation) => conversation.id !== conversationId);
  if (appState.activeConversationId === conversationId) {
    appState.activeConversationId = null;
    appState.readOnlyMode = false;
  }
  saveConversations();
  renderSidebar();
  renderChat();
}

function deriveTitle(question) {
  return question.split(' ').slice(0, 5).join(' ').slice(0, 44) || 'Conversation';
}

function showStatus(message, type = 'success') {
  elements.statusBanner.textContent = message;
  elements.statusBanner.className = `status-banner ${type}`;
  elements.statusBanner.classList.remove('hidden');
  clearTimeout(showStatus.timeout);
  showStatus.timeout = setTimeout(() => {
    elements.statusBanner.classList.add('hidden');
  }, 3000);
}

function renderExampleChips() {
  if (!elements.exampleChips) {
    return;
  }

  const shuffled = shuffleArray(EXAMPLE_QUESTIONS);
  const selected = shuffled.slice(0, 3);
  elements.exampleChips.innerHTML = selected
    .map((question) => `<button class="chip" data-question="${escapeHtml(question)}" type="button">${escapeHtml(question)}</button>`)
    .join('');
}

function shuffleArray(items) {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]];
  }
  return copy;
}

function renderMarkdown(text) {
  if (typeof window !== 'undefined' && window.marked && typeof window.marked.parse === 'function') {
    return window.marked.parse(String(text || ''));
  }
  return escapeHtml(text || '');
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

document.addEventListener('DOMContentLoaded', init);