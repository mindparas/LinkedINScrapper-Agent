# 🌐 LinkedIn Post Scraper (Chrome Extension)

A lightweight, interactive Chrome Extension (Manifest V3) for scraping LinkedIn posts by keyword and location, featuring live side-panel docking, pop-out windows, and OpenAI lead qualification.

---

## 🚀 Features

- **Side Panel & Pop-out Window:** Keeps the scraper open docked to the right of your browser or in an independent window that never closes when clicking away.
- **Intent Keyword Expansion:** Formulates clean, unquoted search queries tailored to finding hiring founders and MVP requests.
- **AI Qualification:** Evaluates posts directly against BDE criteria via OpenAI (`gpt-4o-mini`).
- **Live Feed Interceptor:** Intercepts LinkedIn search queries and captures authentic post URLs.
- **One-Click Export:** Download qualified leads in structured CSV or JSON formats.

---

## 📦 How to Install & Load in Google Chrome

1. Open Google Chrome.
2. Navigate to `chrome://extensions/` in your address bar.
3. Enable **Developer mode** using the toggle switch in the top-right corner.
4. Click the **"Load unpacked"** button in the top-left corner.
5. In the file dialog, navigate to and select this directory:
   ```
   LinkedIn Scrapper/chrome-extension/
   ```
6. The extension icon will appear in your Chrome toolbar. Pin it for quick access!

---

## ⚙️ Configuration

1. Click the extension icon in your Chrome toolbar or open the **Side Panel**.
2. Expand the **AI Lead Qualification** settings section.
3. Enter your **OpenAI API Key** (`sk-...`). Keys are stored locally in `chrome.storage.local`.
4. Enter target keywords, select geographic regions or post freshness, and click **Start Scraping**.

---

## 📂 File Structure

```
chrome-extension/
├── icons/                    # Extension icons (16px, 48px, 128px)
├── background.js             # Service worker handling network requests & AI calls
├── content.js                # Content script injected into LinkedIn search pages
├── main_world_interceptor.js # Main world script for intercepting fetch/XHR
├── manifest.json             # Manifest V3 extension configuration
├── popup.css                 # Modern UI styles for popup & side-panel
├── popup.html                # Main UI markup
├── popup.js                  # User interaction and messaging controller
└── README.md                 # This installation guide
```

