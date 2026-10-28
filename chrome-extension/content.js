// ─────────────────────────────────────────
// content.js — Content Script
// Injected into LinkedIn search results pages
// Handles communication with background.js
// ─────────────────────────────────────────

// Signal to background that the content script is ready on this page
chrome.runtime.sendMessage({ action: 'CONTENT_READY' }).catch(() => {});

// Listen for direct scrape commands (optional direct injection fallback)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'PING') {
    sendResponse({ alive: true });
  }
});

