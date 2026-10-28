// ─────────────────────────────────────────
// popup.js — Extension Popup Controller
// ─────────────────────────────────────────

// Detect Pop-out Window or Side Panel Mode
if (window.location.search.includes('mode=window')) {
  document.body.classList.add('mode-window');
}

// DOM References
const riskBanner      = document.getElementById('risk-warning');
const keyword         = document.getElementById('keyword');
const locationSel     = document.getElementById('location');
const sortBySel       = document.getElementById('sortby');
const postLimitSel    = document.getElementById('post-limit');
const customLimit     = document.getElementById('custom-limit');
const scrapeBtn       = document.getElementById('scrape-btn');
const cancelBtn       = document.getElementById('cancel-btn');
const openWindowBtn   = document.getElementById('open-window-btn');
const openSidepanelBtn= document.getElementById('open-sidepanel-btn');
const btnText         = document.getElementById('btn-text');
const btnLoader       = document.getElementById('btn-loader');
const progressWrap    = document.getElementById('progress-wrap');
const progressText    = document.getElementById('progress-text');
const progressCount   = document.getElementById('progress-count');
const progressFill    = document.getElementById('progress-fill');
const resultsSection  = document.getElementById('results-section');
const resultsSummary  = document.getElementById('results-summary');
const postsList       = document.getElementById('posts-list');
const downloadBtn     = document.getElementById('download-btn');
const emptyState      = document.getElementById('empty-state');
const errorState      = document.getElementById('error-state');
const errorMessage    = document.getElementById('error-message');

// Debug Panel DOM References
const debugSection    = document.getElementById('debug-section');
const debugLog        = document.getElementById('debug-log');
const rawDataBtn      = document.getElementById('raw-data-btn');
const clearLogBtn     = document.getElementById('clear-log-btn');
const toggleDebugBtn  = document.getElementById('toggle-debug-btn');
const openDebugBtn    = document.getElementById('open-debug-btn');
const rawModal        = document.getElementById('raw-modal');
const rawDataContent  = document.getElementById('raw-data-content');
const closeRawBtn     = document.getElementById('close-raw-btn');

// AI Filter DOM References
const aiToggle        = document.getElementById('ai-toggle');
const aiProviderSel   = document.getElementById('ai-provider');
const aiKeyInput      = document.getElementById('ai-key');
const aiHint          = document.getElementById('ai-hint');
const aiKeyContainer  = document.getElementById('ai-key-container');
const inspectDomBtn   = document.getElementById('inspect-dom-btn');
const bdeToggle       = document.getElementById('bde-toggle');
const postTypeSel     = document.getElementById('post-type');

// State
let scrapedPosts = [];
let rawScrapedData = null;  // Holds last raw JSON for viewer

function updateAiHint() {
  if (aiHint) {
    aiHint.innerHTML = 'Using <strong>OpenAI (gpt-4o-mini)</strong>. Enter your key from <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a>';
  }
}

// ─────────────────────────────────────────
// 1. Auto-dismiss Risk Warning after 6 seconds
// ─────────────────────────────────────────
setTimeout(() => {
  riskBanner.classList.add('hidden');
}, 6000);

// ─────────────────────────────────────────
// 2. Pop-out Window & Side Panel Controls
// ─────────────────────────────────────────
if (openWindowBtn) {
  if (window.location.search.includes('mode=window')) {
    openWindowBtn.style.display = 'none';
  } else {
    openWindowBtn.addEventListener('click', () => {
      chrome.windows.create({
        url: chrome.runtime.getURL('popup.html?mode=window'),
        type: 'popup',
        width: 440,
        height: 740
      });
      window.close();
    });
  }
}

if (openSidepanelBtn) {
  if (chrome.sidePanel && chrome.sidePanel.open) {
    openSidepanelBtn.addEventListener('click', async () => {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) {
          await chrome.sidePanel.open({ tabId: tab.id });
          window.close();
        }
      } catch (err) {
        console.warn('Could not open side panel:', err);
      }
    });
  } else {
    openSidepanelBtn.style.display = 'none';
  }
}

// ─────────────────────────────────────────
// 3. Post Limit / Target Leads Selector
// ─────────────────────────────────────────
function getSelectedLimit() {
  if (postLimitSel && postLimitSel.value === 'custom') {
    const val = parseInt(customLimit.value, 10);
    return isNaN(val) || val < 1 ? 10 : Math.min(val, 300);
  }
  return parseInt(postLimitSel ? postLimitSel.value : '10', 10) || 10;
}

if (postLimitSel) {
  postLimitSel.addEventListener('change', () => {
    if (postLimitSel.value === 'custom') {
      customLimit.classList.remove('hidden');
      customLimit.focus();
    } else {
      customLimit.classList.add('hidden');
    }
    chrome.storage.local.set({ lastPostLimit: postLimitSel.value });
  });
}

if (customLimit) {
  customLimit.addEventListener('input', () => {
    chrome.storage.local.set({ lastCustomLimit: customLimit.value });
  });
}

// ─────────────────────────────────────────
// 4. Cancel / Stop Scraping Button
// ─────────────────────────────────────────
if (cancelBtn) {
  cancelBtn.addEventListener('click', async () => {
    cancelBtn.innerHTML = '<span>⏳ Stopping...</span>';
    cancelBtn.disabled = true;
    addLogEntry('warn', new Date().toLocaleTimeString(), '🛑 Stop signal sent. Finalizing collected leads...');
    try {
      await chrome.runtime.sendMessage({ action: 'CANCEL_SCRAPE' });
    } catch (_) {}
  });
}

// ─────────────────────────────────────────
// 5. Restore last used settings from storage
// ─────────────────────────────────────────
chrome.storage.local.get(['lastKeyword', 'lastLocation', 'lastSort', 'useAiFilter', 'aiProvider', 'aiApiKey', 'geminiKey', 'useBdeMode', 'lastPostType', 'lastPostLimit', 'lastCustomLimit'], (data) => {
  if (data.lastKeyword)  keyword.value       = data.lastKeyword;
  locationSel.value = '103644278';
  if (data.lastSort && sortBySel) {
    sortBySel.value = data.lastSort;
  }
  if (data.lastPostType && postTypeSel) {
    postTypeSel.value = 'organic';
  }
  if (data.lastPostLimit && postLimitSel) {
    postLimitSel.value = data.lastPostLimit;
    if (data.lastPostLimit === 'custom' && customLimit) {
      customLimit.classList.remove('hidden');
      if (data.lastCustomLimit) customLimit.value = data.lastCustomLimit;
    }
  }
  if (data.aiProvider && aiProviderSel) {
    aiProviderSel.value = data.aiProvider;
  }
  if (data.useAiFilter !== undefined) {
    aiToggle.checked = data.useAiFilter;
    aiKeyContainer.style.display = data.useAiFilter ? 'block' : 'none';
  }
  if (data.useBdeMode !== undefined) {
    bdeToggle.checked = data.useBdeMode;
  }
  const DEFAULT_FALLBACK_KEY = '';
  const savedKey = data.aiApiKey || data.geminiKey || DEFAULT_FALLBACK_KEY;
  if (savedKey && aiKeyInput) {
    aiKeyInput.value = savedKey;
  }
  updateAiHint();
});

aiToggle.addEventListener('change', () => {
  aiKeyContainer.style.display = aiToggle.checked ? 'block' : 'none';
  chrome.storage.local.set({ useAiFilter: aiToggle.checked });
});

bdeToggle.addEventListener('change', () => {
  chrome.storage.local.set({ useBdeMode: bdeToggle.checked });
});

if (sortBySel) {
  sortBySel.addEventListener('change', () => {
    chrome.storage.local.set({ lastSort: sortBySel.value });
  });
}

if (aiProviderSel) {
  aiProviderSel.addEventListener('change', () => {
    chrome.storage.local.set({ aiProvider: aiProviderSel.value });
    updateAiHint();
  });
}

if (aiKeyInput) {
  aiKeyInput.addEventListener('input', () => {
    const val = aiKeyInput.value.trim();
    chrome.storage.local.set({ aiApiKey: val });
    if (aiProviderSel && aiProviderSel.value === 'auto') {
      if (val.startsWith('sk-')) {
        aiHint.innerHTML = '✨ <strong>OpenAI Key Detected</strong> (Will use <code>gpt-4o-mini</code>)';
      } else if (val.length === 0) {
        updateAiHint();
      }
    }
  });
}

// ─────────────────────────────────────────
// 6. Background State Synchronization & Restoration
// ─────────────────────────────────────────
function applyScrapeState(state) {
  if (!state) return;

  if (state.isRunning) {
    setLoadingState(true);
    showProgress(true);
    const total = state.targetLimit || 10;
    const count = state.currentCount || 0;
    const pct = Math.round((count / total) * 100);
    progressFill.style.width = Math.min(pct, 100) + '%';
    progressCount.textContent = `${count} / ${total}`;
    progressText.textContent = state.progressText || `Fetching posts... (scroll ${state.scrollCount || 1})`;
    if (state.keyword && !keyword.value) keyword.value = state.keyword;
  } else if (state.status === 'completed') {
    setLoadingState(false);
    showProgress(false);
    if (state.posts && state.posts.length > 0) {
      scrapedPosts = state.posts;
      rawScrapedData = state.posts;
      rawDataBtn.classList.remove('hidden');
      renderResults(state.keyword || keyword.value, state.posts);
    } else {
      showEmptyState();
    }
  } else if (state.status === 'cancelled') {
    setLoadingState(false);
    showProgress(false);
    if (state.posts && state.posts.length > 0) {
      scrapedPosts = state.posts;
      rawScrapedData = state.posts;
      rawDataBtn.classList.remove('hidden');
      renderResults(state.keyword || keyword.value, state.posts);
      resultsSummary.textContent = `🛑 Stopped — ${state.posts.length} leads preserved for "${state.keyword || keyword.value}"`;
    } else {
      showEmptyState();
    }
  } else if (state.status === 'error') {
    setLoadingState(false);
    showProgress(false);
    showError(state.error || 'Scraping failed.');
  }
}

// Reconnect to active background scrape on popup open
chrome.runtime.sendMessage({ action: 'GET_SCRAPE_STATE' }, (resp) => {
  if (chrome.runtime.lastError) return;
  if (resp && resp.success && resp.state) {
    applyScrapeState(resp.state);
  }
});

// ─────────────────────────────────────────
// 7. Scrape Button — Main Action
// ─────────────────────────────────────────
scrapeBtn.addEventListener('click', async () => {
  const kw  = keyword.value.trim();
  const geo = '103644278';
  const sort = sortBySel ? sortBySel.value : 'relevance';
  const limit = getSelectedLimit();

  // Validate
  if (!kw) {
    showError('Please enter a keyword to search.');
    return;
  }

  // Save preferences
  const pType = 'organic';
  chrome.storage.local.set({
    lastKeyword: kw,
    lastLocation: geo,
    lastSort: sort,
    lastPostType: pType,
    lastPostLimit: postLimitSel ? postLimitSel.value : '10'
  });

  // Reset UI
  resetUI();
  setLoadingState(true);
  showProgress(true);
  progressCount.textContent = `0 / ${limit}`;
  progressFill.style.width = '0%';
  progressText.textContent = 'Connecting to LinkedIn...';
  openDebugPanel();
  addLogEntry('info', new Date().toLocaleTimeString(), `🔄 Scrape initiated from popup — Target: ${limit} leads, Post Type: ${pType.toUpperCase()}`);

  try {
    const pProvider = 'openai';
    const pKey = aiKeyInput ? aiKeyInput.value.trim() : '';

    const response = await chrome.runtime.sendMessage({
      action: 'START_SCRAPE',
      keyword: kw,
      geoUrn: geo,
      sortBy: sort,
      useAi: true,
      aiProvider: pProvider,
      apiKey: pKey,
      useBde: bdeToggle.checked,
      postType: 'organic',
      targetLimit: limit
    });

    if (response && response.success) {
      if (response.posts) {
        scrapedPosts   = response.posts;
        rawScrapedData = response.posts;
        if (scrapedPosts.length === 0) {
          showEmptyState();
        } else {
          rawDataBtn.classList.remove('hidden');
          renderResults(kw, scrapedPosts);
        }
      }
    } else if (response && response.error) {
      showError(response.error);
    }
  } catch (err) {
    console.log('Scrape message channel note:', err.message);
  } finally {
    // Check background state to see if still running or finished
    chrome.runtime.sendMessage({ action: 'GET_SCRAPE_STATE' }, (resp) => {
      if (chrome.runtime.lastError) return;
      if (resp && resp.state && resp.state.isRunning) {
        setLoadingState(true);
      } else {
        setLoadingState(false);
        showProgress(false);
      }
    });
  }
});

// ─────────────────────────────────────────
// 8. Listen for messages from background.js
// Handles: SCRAPE_STATE_UPDATE, PROGRESS_UPDATE, LOG_UPDATE
// ─────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === 'SCRAPE_STATE_UPDATE') {
    applyScrapeState(msg.state);
  }

  // Progress bar update
  if (msg.action === 'PROGRESS_UPDATE') {
    const pct = Math.round((msg.count / msg.total) * 100);
    progressFill.style.width = pct + '%';
    progressCount.textContent = `${msg.count} / ${msg.total}`;
    progressText.textContent  = `Fetching posts... (scroll ${msg.scroll})`;
  }

  // Real-time debug log entry from background
  if (msg.action === 'LOG_UPDATE') {
    addLogEntry(msg.level, msg.time, msg.message, msg.data);

    // If scraping completed successfully, show Raw Data button
    if (msg.level === 'success' && rawScrapedData) {
      rawDataBtn.classList.remove('hidden');
    }
    // If error, make sure debug panel is visible
    if (msg.level === 'error') {
      openDebugPanel();
    }
  }
});

// ─────────────────────────────────────────
// 5. Render Results
// ─────────────────────────────────────────
function renderResults(kw, posts) {
  const loc = locationSel.options[locationSel.selectedIndex].text;
  resultsSummary.textContent = `✅ ${posts.length} posts found for "${kw}" in ${loc}`;

  postsList.innerHTML = '';
  posts.forEach((post) => {
    const card = document.createElement('div');
    card.className = 'post-card';
    card.innerHTML = `
      <div class="author-row">
        <div>
          <div class="author-name">
            ${escapeHtml(post.authorName || 'Unknown')}
            ${post.personaBadge ? `<span class="persona-badge">${escapeHtml(post.personaBadge)}</span>` : ''}
            ${post.isJobCard ? '<span class="badge-jobcard">💼 Job Card</span>' : '<span class="badge-organic">📝 Organic Post</span>'}
          </div>
          <div class="company">${escapeHtml(post.company || '')}</div>
        </div>
        <div class="post-date">${escapeHtml(post.date || '')}</div>
      </div>
      ${post.aiBadge ? `<div class="ai-badge">${escapeHtml(post.aiBadge)}</div>` : ''}
      <div class="post-content">${escapeHtml(post.content || '')}</div>
      ${post.contactEmail ? `<div class="email-badge">✉️ Contact Email: <strong>${escapeHtml(post.contactEmail)}</strong></div>` : ''}
      <div class="post-meta">
        <span>❤️ ${post.likes || 0}</span>
        <span>💬 ${post.comments || 0}</span>
        ${post.detectedLocation ? `<span class="location-badge">📍 ${escapeHtml(post.detectedLocation)}</span>` : ''}
        ${post.leadScore ? `<span class="location-badge" style="background:#fef3c7; color:#92400e;">⭐ Score: ${escapeHtml(post.leadScore)}/100</span>` : ''}
      </div>
      <div class="card-action-links">
        ${(post.postUrl || (post.url && !post.url.includes('/in/')) || post.authorProfileUrl) ? `<a class="post-link" href="${escapeHtml(post.postUrl || (post.url && !post.url.includes('/in/') ? post.url : (post.authorProfileUrl ? (post.authorProfileUrl.replace(/\/$/, '') + '/recent-activity/all/') : '')))}" target="_blank">${(post.postUrl && post.postUrl.includes('/recent-activity/')) ? '🔗 View Recent Posts' : '🔗 View Post'}</a>` : ''}
        ${(post.authorProfileUrl || (post.url && post.url.includes('/in/'))) ? `<a class="profile-link" href="${escapeHtml(post.authorProfileUrl || (post.url.includes('/in/') ? post.url : ''))}" target="_blank">👤 View Profile</a>` : ''}
      </div>
    `;
    postsList.appendChild(card);
  });

  resultsSection.classList.remove('hidden');
}

// ─────────────────────────────────────────
// 6. Download CSV
// ─────────────────────────────────────────
downloadBtn.addEventListener('click', () => {
  if (!scrapedPosts.length) return;

  const headers = [
    'Author Profile URL',
    'Post URL',
    'Fit Score'
  ];

  const rows = scrapedPosts.map(p => {
    const profileLink = p.authorProfileUrl || (p.url && p.url.includes('/in/') ? p.url : '');
    const postPermalink = p.postUrl || (p.url && !p.url.includes('/in/') ? p.url : (p.authorProfileUrl ? (p.authorProfileUrl.replace(/\/$/, '') + '/recent-activity/all/') : ''));
    const fitScore = p.leadScore || p.fitScore || p.score || '';

    return [
      profileLink,
      postPermalink,
      fitScore
    ];
  });

  const csvContent = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const kw   = keyword.value.trim().replace(/\s+/g, '_');
  const date  = new Date().toISOString().slice(0, 10);

  chrome.downloads.download({
    url:      url,
    filename: `bde_linkedin_leads_${kw}_${date}.csv`,
    saveAs:   false
  });
});

// ─────────────────────────────────────────
// 7. Debug Panel — Log Entries
// ─────────────────────────────────────────
function addLogEntry(level, time, message, data) {
  const entry = document.createElement('div');
  entry.className = `log-entry log-${level}`;

  const levelIcons = { info: 'ℹ️', warn: '⚠️', error: '❌', success: '✅' };
  entry.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-msg">${levelIcons[level] || '•'} ${escapeHtml(message)}</span>
    ${data ? `<pre class="log-data">${escapeHtml(data)}</pre>` : ''}
  `;

  debugLog.appendChild(entry);
  // Auto-scroll to latest log
  debugLog.scrollTop = debugLog.scrollHeight;
}

// ─────────────────────────────────────────
// 8. Debug Panel Controls
// ─────────────────────────────────────────

// Open debug panel
function openDebugPanel() {
  debugSection.classList.remove('hidden');
  openDebugBtn.classList.add('hidden');
  toggleDebugBtn.textContent = '▲ Hide';
}

// Open debug button (bottom bar)
openDebugBtn.addEventListener('click', () => {
  openDebugPanel();
});

// Toggle hide/show debug panel
toggleDebugBtn.addEventListener('click', () => {
  const isHidden = debugLog.style.display === 'none';
  debugLog.style.display = isHidden ? 'block' : 'none';
  toggleDebugBtn.textContent = isHidden ? '▲ Hide' : '▼ Show';
});

// Clear log
clearLogBtn.addEventListener('click', () => {
  debugLog.innerHTML = '';
  addLogEntry('info', new Date().toLocaleTimeString(), 'Log cleared');
});

// Show raw scraped data modal
rawDataBtn.addEventListener('click', () => {
  if (!rawScrapedData) return;
  rawDataContent.textContent = JSON.stringify(rawScrapedData, null, 2);
  rawModal.classList.remove('hidden');
});

// Close raw data modal
closeRawBtn.addEventListener('click', () => {
  rawModal.classList.add('hidden');
});

// 🔬 Live DOM Inspector Button
inspectDomBtn.addEventListener('click', async () => {
  openDebugPanel();
  addLogEntry('info', new Date().toLocaleTimeString(), '🔬 Inspecting active LinkedIn tab DOM live...');
  inspectDomBtn.disabled = true;
  inspectDomBtn.textContent = '⏳ Inspecting...';

  try {
    const res = await chrome.runtime.sendMessage({ action: 'INSPECT_PAGE_DOM' });
    if (res && res.success) {
      addLogEntry('success', new Date().toLocaleTimeString(), `✅ Live DOM Inspection Complete — Found ${res.data.totalCandidateCardsFound} Post Cards!`, res.data);
      // Also open raw modal with this inspection report for crystal-clear viewing!
      rawScrapedData = res.data;
      rawDataBtn.classList.remove('hidden');
    } else {
      addLogEntry('error', new Date().toLocaleTimeString(), res?.error || 'Could not inspect DOM. Please ensure a LinkedIn tab is open.');
    }
  } catch (err) {
    addLogEntry('error', new Date().toLocaleTimeString(), `Inspection error: ${err.message}`);
  } finally {
    inspectDomBtn.disabled = false;
    inspectDomBtn.textContent = '🔬 Inspect Live DOM';
  }
});

// ─────────────────────────────────────────
// Helper Functions
// ─────────────────────────────────────────
function setLoadingState(loading) {
  scrapeBtn.disabled = loading;
  scrapeBtn.classList.toggle('hidden', loading);
  if (cancelBtn) {
    cancelBtn.classList.toggle('hidden', !loading);
    cancelBtn.disabled = false;
    cancelBtn.innerHTML = '<span>🛑 Stop / Keep Leads</span>';
  }
  btnText.classList.toggle('hidden', loading);
  btnLoader.classList.toggle('hidden', !loading);
}

function showProgress(show) {
  progressWrap.classList.toggle('hidden', !show);
  if (show) {
    const limit = getSelectedLimit();
    progressFill.style.width = '0%';
    progressCount.textContent = `0 / ${limit}`;
    progressText.textContent  = 'Initializing LinkedIn...';
  }
}

function showEmptyState() {
  emptyState.classList.remove('hidden');
}

function showError(msg) {
  errorMessage.textContent = msg;
  errorState.classList.remove('hidden');
}

function resetUI() {
  scrapedPosts    = [];
  rawScrapedData  = null;
  resultsSection.classList.add('hidden');
  emptyState.classList.add('hidden');
  errorState.classList.add('hidden');
  rawDataBtn.classList.add('hidden');
  rawModal.classList.add('hidden');
  postsList.innerHTML = '';
  debugLog.innerHTML  = '';
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

