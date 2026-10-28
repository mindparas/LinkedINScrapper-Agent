// ─────────────────────────────────────────
// background.js — Service Worker (High-Relevance BDE Lead Scraper)
// First-Person Intent Grammar + Zero Tab Navigation + OpenAI Qualification
// ─────────────────────────────────────────

const MAX_POSTS    = 10;    // Target leads to qualify
const SCROLL_DELAY = 2800;  // 2.8s between scroll batches (safe rate limit)
const MAX_SCROLLS  = 20;    // Max scroll attempts
const MAX_POST_AGE_DAYS = 60;

function normalizeForFingerprint(value) {
  return String(value || '').toLowerCase().replace(/https?:\/\/\S+/g, '').replace(/\s+/g, ' ').trim();
}

function postFingerprint(post) {
  return [post.postUrl, post.authorName, post.date, post.content].map(normalizeForFingerprint).join('|').slice(0, 500);
}

function isRecentPost(post, maxDays = MAX_POST_AGE_DAYS) {
  const value = String(post.date || '').toLowerCase().trim();
  if (!value || /now|just/.test(value)) return true;
  const match = value.match(/(\d+)\s*(minute|hour|day|week|month|year|[mhdw])/i);
  if (!match) return true;
  const amount = Number(match[1]);
  const unit = match[2].toLowerCase();
  const days = unit.startsWith('year') || unit === 'y' ? amount * 365 : unit.startsWith('month') ? amount * 30 : unit.startsWith('week') || unit === 'w' ? amount * 7 : unit.startsWith('day') || unit === 'd' ? amount : 0;
  return days <= maxDays;
}

// Location Query Expansions (Solves the LinkedIn location search bottleneck)
const LOCATION_QUERY_MAP = {
  '103644278': '("United States" OR "US remote" OR "remote US")',
  '101165590': '(UK OR "United Kingdom" OR London)',
  '101452733': '(Canada OR Toronto OR Vancouver)',
  '106057199': '(Australia OR Sydney OR Melbourne)',
  '102713980': '(India OR Bangalore OR Hyderabad OR Pune OR Mumbai OR Delhi)',
  '106155005': '(Germany OR Berlin OR Munich)',
  '102890719': 'Singapore',
  '104514075': '(UAE OR Dubai OR "Abu Dhabi")',
  '105080838': '(France OR Paris)',
  '105646813': '(Brazil OR "São Paulo")',
  '90009735': '(Netherlands OR Amsterdam)',
  '102095887': '(Japan OR Tokyo)',
  'worldwide': ''
};

const COUNTRY_NAMES = {
  '103644278': 'United States',
  '101165590': 'United Kingdom',
  '101452733': 'Canada',
  '106057199': 'Australia',
  '102713980': 'India',
  '106155005': 'Germany',
  '102890719': 'Singapore',
  '104514075': 'United Arab Emirates',
  '105080838': 'France',
  '105646813': 'Brazil',
  '90009735': 'Netherlands',
  '102095887': 'Japan',
  'worldwide': 'Worldwide'
};

const USA_LOCATION_EVIDENCE = /\b(usa|united states|u\.s\.a?\.?|us remote|remote\s*[-–]\s*us|remote\s*(in|within|from)?\s*(the\s*)?u\.?s\.?|united states\s*\(remote\)|new york|nyc|california|texas|florida|washington|illinois|massachusetts|colorado|virginia|new jersey|georgia|arizona|ohio|pennsylvania|north carolina|san francisco|sf bay|los angeles|austin|seattle|boston|chicago|denver|atlanta|dallas|houston|miami|philadelphia|san diego|phoenix|raleigh|charlotte|detroit|portland|salt lake city|silicon valley|\b(?:ca|tx|ny|wa|fl|ma|il|co|va|nj|ga|nc|oh|pa|az)\b)\b/i;
const FOREIGN_LOCATION_EVIDENCE = /\b(india|bangalore|bengaluru|hyderabad|pune|mumbai|delhi|noida|gurgaon|gurugram|chennai|ahmedabad|kolkata|dhaka|bangladesh|pakistan|lahore|karachi|islamabad|nigeria|lagos|philippines|manila|vietnam|hanoi|hcmc|egypt|sri lanka|nepal|dubai|uae)\b|(?:\+91|\+880|\+92|\+234|\+63|\+84)\s*\d/i;

// Make the toolbar action open the extension exclusively in Chrome's side panel.
if (chrome.sidePanel?.setPanelBehavior) {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
}

// ─────────────────────────────────────────
// Debug Logger — sends every step to popup in real-time
// ─────────────────────────────────────────
function log(level, message, data) {
  const entry = {
    action:  'LOG_UPDATE',
    level,
    message,
    data:    data !== undefined ? JSON.stringify(data, null, 2) : null,
    time:    new Date().toLocaleTimeString()
  };
  if (level === 'error') console.error('[Scraper]', message, data || '');
  else if (level === 'warn') console.warn('[Scraper]', message, data || '');
  else console.log('[Scraper]', message, data || '');

  chrome.runtime.sendMessage(entry).catch(() => {});
}

// ─────────────────────────────────────────
// Active Scrape State & Persistence Management
// ─────────────────────────────────────────
let activeScrape = {
  status: 'idle',       // 'idle' | 'running' | 'completed' | 'cancelled' | 'error'
  isRunning: false,
  cancelRequested: false,
  keyword: '',
  geoUrn: '103644278',
  sortBy: 'relevance',
  postType: 'organic',
  targetLimit: 10,
  currentCount: 0,
  scrollCount: 0,
  progressText: '',
  posts: [],
  error: null
};

// Restore previous state if background worker wakes up
chrome.storage.local.get(['activeScrapeState'], (data) => {
  if (data.activeScrapeState) {
    activeScrape = { ...activeScrape, ...data.activeScrapeState };
    if (activeScrape.isRunning) {
      activeScrape.isRunning = false;
      activeScrape.status = (activeScrape.posts && activeScrape.posts.length > 0) ? 'completed' : 'idle';
      updateScrapeState({ isRunning: false, status: activeScrape.status });
    }
  }
});

async function updateScrapeState(patch) {
  Object.assign(activeScrape, patch);
  try {
    await chrome.storage.local.set({ activeScrapeState: activeScrape });
  } catch (_) {}
  chrome.runtime.sendMessage({
    action: 'SCRAPE_STATE_UPDATE',
    state: activeScrape
  }).catch(() => {});
}

// ─────────────────────────────────────────
// Message Handler from Popup & Windows
// ─────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'START_SCRAPE') {
    if (activeScrape.isRunning) {
      sendResponse({ success: false, error: 'A scrape task is already actively running in the background!' });
      return false;
    }
    const targetLimit = Number(msg.targetLimit) || 10;
    updateScrapeState({
      status: 'running',
      isRunning: true,
      cancelRequested: false,
      keyword: msg.keyword || '',
      geoUrn: msg.geoUrn || '103644278',
      sortBy: msg.sortBy || 'relevance',
      postType: msg.postType || 'organic',
      targetLimit,
      currentCount: 0,
      scrollCount: 0,
      progressText: 'Initializing LinkedIn...',
      posts: [],
      error: null
    });

    handleScrape({ ...msg, targetLimit }).then((res) => {
      try { sendResponse(res); } catch (_) {}
    }).catch((err) => {
      try { sendResponse({ success: false, error: err.message }); } catch (_) {}
    });
    return true; // Keep channel open for async response
  }

  if (msg.action === 'CANCEL_SCRAPE' || msg.action === 'STOP_SCRAPE') {
    log('warn', '🛑 Stop / Cancel signal received from user.');
    activeScrape.cancelRequested = true;
    updateScrapeState({
      cancelRequested: true,
      progressText: 'Stopping scraper and finalizing collected leads...'
    });
    sendResponse({ success: true, message: 'Stopping scraper...' });
    return false;
  }

  if (msg.action === 'GET_SCRAPE_STATE') {
    sendResponse({ success: true, state: activeScrape });
    return false;
  }

  if (msg.action === 'CLEAR_SCRAPE_STATE') {
    updateScrapeState({
      status: 'idle',
      isRunning: false,
      cancelRequested: false,
      posts: [],
      currentCount: 0,
      scrollCount: 0,
      progressText: '',
      error: null
    });
    sendResponse({ success: true });
    return false;
  }

  if (msg.action === 'INSPECT_PAGE_DOM') {
    handleInspectDOM().then(sendResponse);
    return true;
  }
});

// ─────────────────────────────────────────
// Live DOM Inspector Handler
// ─────────────────────────────────────────
async function handleInspectDOM() {
  try {
    const tabs = await chrome.tabs.query({ url: 'https://www.linkedin.com/*' });
    if (!tabs || tabs.length === 0) {
      throw new Error('No LinkedIn tab found. Please open LinkedIn in a Chrome tab first.');
    }

    const targetTab = tabs.find(t => t.active) || tabs[0];
    log('info', `🔬 Inspecting LinkedIn tab #${targetTab.id}...`);

    const results = await chrome.scripting.executeScript({
      target: { tabId: targetTab.id },
      func: inspectPageAndHighlight
    });

    const data = results[0]?.result;
    if (!data) throw new Error('Script executed but returned no data.');

    log('success', `🔬 DOM Inspection complete — Found ${data.totalCandidateCardsFound} candidate post cards!`, data);
    return { success: true, data };
  } catch (err) {
    log('error', `❌ Inspect Live DOM error: ${err.message}`);
    return { success: false, error: err.message };
  }
}

// ─────────────────────────────────────────
// Main Scrape Orchestrator (Zero Tab Navigation)
// ─────────────────────────────────────────
async function handleScrape({ keyword, geoUrn, sortBy, useAi, aiProvider = 'openai', apiKey, useBde, postType = 'organic', targetLimit = 10 }) {
  try {
    geoUrn = geoUrn || '103644278';
    sortBy = (sortBy === 'date_posted' || sortBy === 'date') ? 'date_posted' : 'relevance';
    postType = 'organic';
    useAi = true;
    aiProvider = 'openai';
    useBde = true;

    // Fallback: check storage or default key if apiKey was not passed directly
    if (!apiKey || !apiKey.startsWith('sk-')) {
      const stored = await chrome.storage.local.get(['aiApiKey', 'gptApiKey']);
      apiKey = stored.aiApiKey || stored.gptApiKey || '';
    }
    const DEFAULT_FALLBACK_KEY = '';
    if (!apiKey || !apiKey.startsWith('sk-')) {
      apiKey = DEFAULT_FALLBACK_KEY;
    }

    const originalKeyword = keyword;
    keyword = prepareSearchQuery(keyword);
    const countryName = COUNTRY_NAMES[geoUrn] || 'United States';
    const locationExpansion = LOCATION_QUERY_MAP[geoUrn] || '("United States" OR "US remote" OR "remote US")';

    log('info', `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    log('info', `🚀 [STEP 1/6: QUERY PREPARATION & BDE INTENT]`);
    log('info', `📥 Raw User Input: "${originalKeyword}"`);
    log('info', `🧠 First-Person Intent Query: "${keyword}"`);
    log('info', `📍 Target Geography: ${countryName} [${locationExpansion}]`);
    log('info', `🎯 Target Goal: Collect up to ${targetLimit} verified USA BDE Leads (Founders, CEOs, CTOs)`);
    log('info', `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);

    await updateScrapeState({
      status: 'running',
      isRunning: true,
      cancelRequested: false,
      targetLimit,
      progressText: 'Connecting to LinkedIn...'
    });

    // 1. Build LinkedIn search URL with First-Person Intent Query & Location
    const searchUrl = buildLinkedInSearchUrl(keyword, geoUrn, sortBy);
    log('info', `🌐 [STEP 2/6: NAVIGATING TO LINKEDIN SEARCH FEED]`);
    log('info', `🔗 Search URL: ${searchUrl}`);

    // 2. Find or create a LinkedIn tab
    const tab = await getOrCreateLinkedInTab();
    log('info', `✅ LinkedIn Tab Connected — Tab ID: ${tab.id}`);

    if (activeScrape.cancelRequested) {
      await updateScrapeState({ status: 'cancelled', isRunning: false, progressText: 'Stopped by user.' });
      return { success: true, posts: [], cancelled: true };
    }

    // 3. Navigate tab and wait for page load
    log('info', `⏳ Loading LinkedIn search results page...`);
    await updateScrapeState({ progressText: 'Navigating to LinkedIn search feed...' });
    await navigateTabAndWait(tab.id, searchUrl);
    log('info', '✅ Search results page loaded successfully');

    if (activeScrape.cancelRequested) {
      await updateScrapeState({ status: 'cancelled', isRunning: false, progressText: 'Stopped by user.' });
      return { success: true, posts: [], cancelled: true };
    }

    // 4. Wait for LinkedIn content to render in DOM
    log('info', `⏳ [STEP 3/6: WAITING FOR DOM FEED TO RENDER]`);
    await updateScrapeState({ progressText: 'Waiting for feed posts to render...' });
    const renderState = await waitForContentToRender(tab.id, 12000);
    log('info', `✅ DOM render state:`, renderState);

    // 5. Run page diagnostic
    const diagResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: diagnosePage
    });
    const diag = diagResults[0]?.result || {};
    log('info', `🔬 DOM Diagnostic: Title: "${diag.title}" | Elements found:`, diag.selectorCounts);
    if (diag.isLoginPage) {
      throw new Error('LinkedIn is showing a login page. Please log in to LinkedIn in your browser first.');
    }
    if (diag.hasNoResults) {
      log('warn', `⚠️ LinkedIn reported "No results found" for this query.`);
    }

    // 6. Run the scraper loop directly on the feed (ZERO tab navigation!)
    const candidateTarget = Math.min(targetLimit * 3, 100);
    const maxScrolls = Math.max(15, Math.ceil(candidateTarget / 1.5));
    log('info', `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    log('info', `📥 [STEP 4/6: EXTRACTING POSTS FROM FEED]`);
    log('info', `Target: ${targetLimit} leads (Harvesting pool of up to ${candidateTarget} raw candidates across max ${maxScrolls} scrolls)...`);

    let rawPosts = await runScraper(tab.id, keyword, candidateTarget, postType, maxScrolls, targetLimit, geoUrn);
    log('info', `📦 Total raw candidate pool collected from feed: ${rawPosts.length} posts`);

    // 7. AI Evaluation & BDE Lead Qualification (OpenAI gpt-4o-mini only)
    let finalPosts = rawPosts;
    if (rawPosts.length > 0) {
      log('info', `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
      log('info', `🤖 [STEP 5/6: OPENAI BDE LEAD QUALIFICATION & SCORING]`);
      log('info', `Sending ${rawPosts.length} collected posts to OpenAI (gpt-4o-mini) for deep BDE sales qualification...`);
      await updateScrapeState({ progressText: `Qualifying ${rawPosts.length} leads with OpenAI gpt-4o-mini...` });
      
      finalPosts = await evaluatePostsWithAI(rawPosts, keyword, geoUrn, countryName, apiKey, useBde);
      
      // Sort qualified leads by BDE Lead Score descending so Top C (Founders, Tech Leaders) appear first
      finalPosts.sort((a, b) => (Number(b.leadScore) || 0) - (Number(a.leadScore) || 0));
      finalPosts = finalPosts.slice(0, targetLimit);
      
      log('info', `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
      log('info', `🎯 [STEP 6/6: FINAL BDE LEAD SELECTION & RANKING]`);
      log('success', `✅ Selected Top ${finalPosts.length} verified BDE leads (Ranked by Decision-Maker Score)`);
    } else {
      finalPosts = [];
    }

    const finalStatus = activeScrape.cancelRequested ? 'cancelled' : 'completed';
    await updateScrapeState({
      status: finalStatus,
      isRunning: false,
      posts: finalPosts,
      currentCount: finalPosts.length,
      progressText: activeScrape.cancelRequested ? `Stopped. ${finalPosts.length} leads preserved.` : `Done! ${finalPosts.length} leads ready.`
    });

    log('success', `🎉 Scraping complete (${finalStatus}) — ${finalPosts.length} leads ready for export!`);
    return { success: true, posts: finalPosts, cancelled: activeScrape.cancelRequested };

  } catch (err) {
    log('error', `❌ Scraping failed: ${err.message}`, { stack: err.stack });
    await updateScrapeState({
      status: 'error',
      isRunning: false,
      error: err.message,
      progressText: `Error: ${err.message}`
    });
    return { success: false, error: err.message };
  }
}

// ─────────────────────────────────────────
// Robust Universal Query Normalizer (BDE Sales Engine)
// Converts ANY user query (skill, inverted title, project, MVP) into the optimal LinkedIn query
// ─────────────────────────────────────────
function prepareSearchQuery(input) {
  let q = String(input || '').trim().replace(/["()]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (!q) return 'looking for AI engineer';

  // 1. Direct Project, MVP, or Solution phrasing (Already has high buying intent)
  if (/\b(building|build|mvp|app|saas|platform|solution|automate|partner|help us build)\b/i.test(q)) {
    return q;
  }

  // 2. Explicit hiring intent prefix already entered by user (Preserve intent)
  if (/^(?:looking for|hiring|we are hiring|we['’]re hiring|seeking|need|wanted|i am hiring|i['’]m hiring)\b/i.test(q)) {
    return q;
  }

  // 3. Invert prepositional phrasing: "developer in python" -> "Python developer"
  q = q.replace(/\b(developer|engineer|lead|architect|specialist|programmer|coder|dev)\s+(?:in|for|with)\s+([a-zA-Z0-9#+.\s-]+)/i, '$2 $1');

  // 4. Strip clutter and stop words
  let cleaned = q.replace(/\b(in|for|a|an|needed|wanted|job|jobs|opening|openings|opportunity|opportunities)\b/gi, ' ').replace(/\s+/g, ' ').trim();
  if (!cleaned) cleaned = q;

  // 5. Check if query already contains a professional role noun
  const hasRoleNoun = /\b(developer|engineer|architect|lead|specialist|designer|scientist|manager|programmer|coder|dev)\b/i.test(cleaned);
  if (hasRoleNoun) {
    return `looking for ${cleaned}`;
  }

  // 6. Technology / Skill normalization: attach professional role suffix
  const lower = cleaned.toLowerCase();
  if (/^(?:ai|artificial intelligence|genai|generative ai|llm|llms|ml|machine learning|deep learning|nlp|computer vision)$/i.test(lower)) {
    return `looking for ${cleaned} engineer`;
  } else if (/^(?:aws|cloud|devops|kubernetes|docker|infrastructure|gcp|azure)$/i.test(lower)) {
    return `looking for ${cleaned} engineer`;
  } else if (/^(?:data science|data analytics|data)$/i.test(lower)) {
    return 'looking for Data Scientist';
  } else {
    return `looking for ${cleaned} developer`;
  }
}

// ─────────────────────────────────────────
// Build LinkedIn Search URL with Smart Location Expansion
// ─────────────────────────────────────────
function buildLinkedInSearchUrl(keyword, geoUrn, sortBy) {
  const base = 'https://www.linkedin.com/search/results/content/';

  let query = keyword.trim();
  const locationExpansion = LOCATION_QUERY_MAP[geoUrn] || '("United States" OR "US remote" OR "remote US")';
  if (locationExpansion && !query.includes(locationExpansion)) {
    query = `${query} ${locationExpansion}`;
  }

  // LinkedIn sortBy parameter:
  // Latest: sortBy=%5B%22date_posted%22%5D
  // Relevance: sortBy=%5B%22relevance%22%5D
  const isLatest = sortBy === 'date' || sortBy === 'date_posted';
  const sortParam = encodeURIComponent(JSON.stringify([isLatest ? 'date_posted' : 'relevance']));

  return `${base}?keywords=${encodeURIComponent(query)}&origin=GLOBAL_SEARCH_HEADER&sortBy=${sortParam}`;
}

// ─────────────────────────────────────────
// AI Evaluation Engine (OpenAI gpt-4o-mini only)
// ─────────────────────────────────────────
async function evaluatePostsWithAI(posts, keyword, geoUrn, countryName, apiKey, useBde = false) {
  log('info', '🔑 Calling OpenAI API (gpt-4o-mini) for deep BDE lead qualification & scoring...');
  const aiResults = await callOpenAIAPI(posts, keyword, countryName, apiKey, useBde);
  if (aiResults && Array.isArray(aiResults) && aiResults.length > 0) {
    const enriched = processAiResults(posts, aiResults, countryName, 'OpenAI', useBde);
    return enriched;
  }
  return [];
}

// ─────────────────────────────────────────
// OpenAI API Caller (gpt-4o-mini, batched in 10s)
// ─────────────────────────────────────────
async function callOpenAIAPI(posts, keyword, countryName, apiKey, useBde = false) {
  const endpoint = 'https://api.openai.com/v1/chat/completions';
  const BATCH_SIZE = 10;
  const allResults = [];

  for (let b = 0; b < posts.length; b += BATCH_SIZE) {
    const batch = posts.slice(b, b + BATCH_SIZE);
    log('info', `🤖 OpenAI evaluating batch ${Math.floor(b / BATCH_SIZE) + 1} (${batch.length} posts)...`);

    const systemPrompt = `You are a B2B sales intelligence AI evaluating scraped LinkedIn posts for an IT agency BDE team.
Your objective is to identify DIRECT BUSINESS OWNERS and TECH LEADERS in the United States who need developers, tech talent, or software solutions to build their product.

QUALIFICATION RULES:
1. TRUE CLIENT BUYING INTENT (NEEDS A TECH SOLUTION):
   - The post must be written by or on behalf of a DIRECT BUSINESS OWNER who needs developers, tech talent, or a software solution to build, scale, or automate their company/product.
   - REJECT all staffing agencies filling internal staffing rosters or marketing other people's candidates.

2. STRICT PERSONA: DIRECT BUSINESS OWNERS & TECH LEADERSHIP ONLY (100% REJECT RECRUITERS & HR):
   - ONLY ACCEPT the following personas:
     * "👔 Founder / Executive" (Founder, Co-Founder, CEO, President, Owner, Managing Partner, C-Level, CIO, CISO) -> +35 pts
     * "💻 Tech Leadership" (CTO, VP of Engineering, Head of Engineering, Director of Engineering, Technical Co-Founder, Lead Architect) -> +30 pts
     * "💼 Product / Business Lead" (VP of Product, Head of Product, Director of Product, Executive Business Partner, Product Manager) -> +20 pts
   - ZERO TOLERANCE (100% REJECT):
     * REJECT ALL Talent Acquisition, Corporate Recruiters, Technical Recruiters, Sourcers, HR Managers, and Talent Partners. The BDE team ONLY wants the business owner who owns the budget!
     * REJECT ALL third-party staffing agencies, bench recruiters, and C2C vendors.
     * REJECT ALL sales persons, BDEs, and agencies pitching development services ("we provide developers", "hire dedicated developers", "need projects", "looking for clients", "outsource to us").
     * REJECT ALL job seekers ("open to work", "hire me", "looking for a role").
     * REJECT ALL thought leadership, blogs, tutorials, and personal retrospectives.

3. STRICT USA GEOGRAPHY:
   - Must be located in or operating in the United States (US Remote, Hybrid, or Onsite in US locations).
   - REJECT any post originating from or hiring exclusively for offshore hubs (India, Pakistan, Vietnam, Bangladesh, Nigeria, Philippines, Dubai/UAE, Latin America, etc.).
   - Extract exact detected location (e.g., "Austin, TX (Onsite)", "US Remote", "San Francisco, CA (Hybrid)", "Miami, FL", "Atlanta, GA") and specify text evidence.

4. CONTACT EXTRACTION:
   - Extract direct corporate email address if present in the post text.

Return JSON in this format:
{
  "evaluations": [
    {
      "id": "post_0",
      "author": "...",
      "isRelevant": true,
      "isUSA": true,
      "detectedLocation": "Austin, TX (Onsite)",
      "locationEvidence": "Location: Austin, TX",
      "jobTitle": "...",
      "personaBadge": "👔 Founder / Executive",
      "personaCategory": "Founder / Executive",
      "contactEmail": "...",
      "hiringIntentScore": 25,
      "decisionMakerScore": 35,
      "geographicMatchScore": 20,
      "directEmployerScore": 15,
      "contactabilityScore": 5,
      "leadScore": 99,
      "reason": "Direct hiring for Senior AI Engineer ($150k-$200k + bonus)"
    }
  ]
}`;

    const userPrompt = `Evaluate these ${batch.length} posts for role: "${keyword}", target country: "${countryName}":
${JSON.stringify(batch.map((p, i) => ({
  id: `post_${b + i}`,
  author: p.authorName,
  headline: p.company,
  feedLocation: p.feedLocation || '',
  subDesc: p.subDescText || '',
  content: p.content.slice(0, 1800)
})))}`;

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        temperature: 0.1,
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ]
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`OpenAI API HTTP ${response.status}: ${errText.slice(0, 120)}`);
    }

    const json = await response.json();
    let content = json.choices?.[0]?.message?.content || '{}';
    // Clean potential markdown code blocks
    content = content.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
    let parsed = {};
    try {
      parsed = JSON.parse(content);
    } catch (_pe) {
      log('warn', `OpenAI returned non-JSON response snippet: ${content.slice(0, 100)}`);
      parsed = {};
    }
    const evals = parsed.evaluations || parsed.posts || parsed.results || (Array.isArray(parsed) ? parsed : []);
    allResults.push(...evals);
  }

  return allResults;
}

// ─────────────────────────────────────────
// Process & Enrich AI Results
// ─────────────────────────────────────────
function processAiResults(posts, aiResults, countryName, providerLabel, useBde = false) {
  const enriched = [];
  let approvedCount = 0;
  let rejectedCount = 0;

  for (let i = 0; i < posts.length; i++) {
    const post = posts[i];
    const expectedId = `post_${i}`;
    const authorClean = (post.authorName || '').trim().toLowerCase();

    const evalItem = aiResults.find(r => {
      if (!r) return false;
      if (r.id === expectedId || r.id === i || r.id === String(i) || r.id === `post_${i}`) return true;
      if (r.index === expectedId || r.index === i || r.index === String(i)) return true;
      if (r.author && authorClean && (r.author.trim().toLowerCase() === authorClean || authorClean.includes(r.author.trim().toLowerCase()) || r.author.trim().toLowerCase().includes(authorClean))) return true;
      if (r.authorName && authorClean && (r.authorName.trim().toLowerCase() === authorClean || authorClean.includes(r.authorName.trim().toLowerCase()) || r.authorName.trim().toLowerCase().includes(authorClean))) return true;
      return false;
    });

    // Explicit check: reject obvious recruiters, staffing firms, or bench vendors from headline
    const headlineAndContent = `${post.company || ''} ${post.content || ''}`;
    const isObviousStaffingOrRecruiter = /\b(recruiter|talent acquisition|talent partner|head of talent|sourcer|headhunter|staffing|bench sales|c2c recruiter|c2c sales|hotlist recruiter|talent marketing)\b/i.test(post.company || '');
    const isSalesPitchAgency = /\b(we provide dedicated developers|hire dedicated developers|outsource your|staff augmentation|looking for clients|looking for new clients|need projects|agency partnership|dm for collaboration|client acquisition|bde\b|business development executive|lead generation)\b/i.test(headlineAndContent) && !/\b(no c2c|no bench|w-?2 only)\b/i.test(post.content || '');

    // Check location evidence
    const evidenceText = `${post.feedLocation || ''} ${post.subDescText || ''} ${post.company || ''} ${post.content || ''} ${evalItem?.locationEvidence || ''} ${evalItem?.detectedLocation || ''}`;
    const hasForeignEvidence = FOREIGN_LOCATION_EVIDENCE.test(evidenceText);
    const hasUsEvidence = USA_LOCATION_EVIDENCE.test(evidenceText) || evalItem?.isUSA === true;
    const validUsLocation = !hasForeignEvidence && (hasUsEvidence || (Number(evalItem?.geographicMatchScore) || 0) >= 10);

    const isQualifiedByAi = evalItem && evalItem.isRelevant === true && evalItem.isUSA === true;
    const passesSanityChecks = !isObviousStaffingOrRecruiter && !isSalesPitchAgency && validUsLocation;

    if (isQualifiedByAi && passesSanityChecks) {
      approvedCount++;
      let personaScore = 30;
      const combo = `${evalItem?.personaCategory || ''} ${evalItem?.personaBadge || ''} ${post.company || ''}`.toLowerCase();
      if (/\b(founder|co-founder|ceo|president|owner|managing partner|c-level|executive)\b/.test(combo)) {
        post.personaBadge = '👔 Founder / Executive';
        post.personaCategory = 'Founder / Executive';
        personaScore = 35;
      } else if (/\b(cto|cio|ciso|vp of engineering|vice president|head of engineering|engineering manager|director of engineering|lead architect|tech lead)\b/.test(combo)) {
        post.personaBadge = '💻 Tech Leadership';
        post.personaCategory = 'Tech Leadership';
        personaScore = 30;
      } else {
        post.personaBadge = '💼 Product / Business Lead';
        post.personaCategory = 'Product / Business Lead';
        personaScore = 25;
      }

      if (!post.company || post.company === 'Unknown' || post.company === '') {
        post.company = evalItem?.jobTitle || evalItem?.personaCategory || 'Direct Business Owner';
      }
      post.companyName = post.company;

      let detectedLoc = evalItem?.detectedLocation || '';
      if (!detectedLoc || detectedLoc === 'Not specified' || detectedLoc.toLowerCase().includes('not specified')) {
        const textToScan = `${post.feedLocation || ''} ${post.content || ''} ${post.company || ''}`;
        const locMatch = textToScan.match(USA_LOCATION_EVIDENCE);
        if (locMatch) {
          detectedLoc = `USA (${locMatch[0].trim()})`;
        } else {
          detectedLoc = post.feedLocation || 'US Remote';
        }
      }
      post.detectedLocation = detectedLoc;
      post.aiBadge = evalItem.aiBadge || `🎯 OpenAI Verified • ${detectedLoc}`;
      post.hiringIntentScore = Number(evalItem.hiringIntentScore) || 25;
      post.decisionMakerScore = personaScore;
      post.geographicMatchScore = Number(evalItem.geographicMatchScore) || 20;
      post.directEmployerScore = Number(evalItem.directEmployerScore) || 15;

      const postEmailMatch = (post.content || '').match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
      if (postEmailMatch) {
        post.contactEmail = postEmailMatch[0].trim().toLowerCase();
      } else if (evalItem.contactEmail && evalItem.contactEmail.includes('@') && !evalItem.contactEmail.includes('@example.com')) {
        post.contactEmail = evalItem.contactEmail.trim().toLowerCase();
      } else {
        post.contactEmail = '';
      }
      post.contactabilityScore = post.contactEmail ? 5 : 0;

      // Exact total score formula
      post.leadScore = Math.min(99, Math.max(65, post.decisionMakerScore + post.hiringIntentScore + post.geographicMatchScore + post.directEmployerScore + post.contactabilityScore));
      post.qualificationReason = evalItem.reason || 'Verified direct hiring in USA';
      post.reviewStatus = post.leadScore >= 80 ? 'Qualified' : 'Needs Review';
      post.aiProvider = 'OpenAI';

      log('info', `✅ [APPROVED LEAD #${approvedCount}] ${post.authorName} (${post.personaBadge})`, {
        score: `${post.leadScore}/100`,
        location: post.detectedLocation,
        email: post.contactEmail || 'None in post text',
        headline: post.company,
        postUrl: post.postUrl || '(missing)',
        reason: post.qualificationReason
      });
      enriched.push(post);
    } else {
      rejectedCount++;
      let rejectReason = 'Rejected by AI lead qualification rules';
      if (isObviousStaffingOrRecruiter) rejectReason = `Recruiter / Staffing role detected in headline: "${post.company}"`;
      else if (isSalesPitchAgency) rejectReason = 'Sales person pitching development services';
      else if (hasForeignEvidence) rejectReason = 'Non-USA location detected in post or profile';
      else if (evalItem?.reason) rejectReason = evalItem.reason;

      log('warn', `❌ [DISCARDED #${rejectedCount}] ${post.authorName || 'Unknown'} — Reason: ${rejectReason}`, {
        headline: post.company || '(No headline)',
        detectedLocation: post.feedLocation || 'Unknown'
      });
    }
  }

  log('info', `📊 Lead Qualification Breakdown: ${posts.length} evaluated → ${approvedCount} Qualified Leads, ${rejectedCount} Discarded`);
  return enriched;
}

// ─────────────────────────────────────────
// Get Existing LinkedIn Tab or Open New One
// ─────────────────────────────────────────
async function getOrCreateLinkedInTab() {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (activeTab && activeTab.url && activeTab.url.includes('linkedin.com')) {
    return activeTab;
  }

  const tabs = await chrome.tabs.query({ url: 'https://www.linkedin.com/*' });
  if (tabs.length > 0) {
    return tabs[0];
  }

  return await chrome.tabs.create({ url: 'https://www.linkedin.com/', active: true });
}

// ─────────────────────────────────────────
// Navigate Tab and Wait for Load
// ─────────────────────────────────────────
function navigateTabAndWait(tabId, url) {
  return new Promise((resolve) => {
    let resolved = false;
    let timer = null;

    function finish() {
      if (!resolved) {
        resolved = true;
        if (timer) clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }

    timer = setTimeout(finish, 10000); // 10s safety timeout

    const listener = (id, changeInfo) => {
      if (id === tabId && changeInfo.status === 'complete') {
        finish();
      }
    };

    chrome.tabs.onUpdated.addListener(listener);

    chrome.tabs.update(tabId, { url, active: true }).catch(() => {
      finish();
    });
  });
}

// ─────────────────────────────────────────
// Wait For Content To Render (Modern Polling)
// ─────────────────────────────────────────
async function waitForContentToRender(tabId, maxWaitMs = 12000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId },
        func: () => {
          const profileLinks = document.querySelectorAll('a[href*="/in/"]');
          const hasProfiles = profileLinks.length > 1;

          const hasSocial = document.querySelectorAll(
            'button[aria-label*="Like" i], button[aria-label*="reaction" i], button[aria-label*="Comment" i]'
          ).length > 0;

          const hasDataView = document.querySelectorAll('div[data-view-name]').length > 0;
          const hasPosts = hasProfiles || hasSocial || hasDataView;

          const text = (document.body ? document.body.innerText : '') || '';
          const hasNoResults = /no results|no matching|couldn\'t find/i.test(text);
          const isLoginPage = window.location.href.includes('/login') ||
                              document.querySelector('form.login__form') !== null;

          return { hasPosts, hasNoResults, isLoginPage, ready: hasPosts || hasNoResults || isLoginPage };
        }
      });

      const state = results[0]?.result;
      if (state && state.ready) {
        await delay(1200); // Let DOM settle
        return state;
      }
    } catch (_e) {}
    await delay(700);
  }
  return { hasPosts: false, timeout: true };
}

// ─────────────────────────────────────────
// Scraper Loop — Scroll & Collect (Fresh Session Isolation)
// ─────────────────────────────────────────
async function runScraper(tabId, keyword, maxCandidates = 30, postType = 'organic', maxScrolls = 20, userTargetLimit = 10, geoUrn = '103644278') {
  const allPosts = [];
  const sessionFingerprints = new Set();
  const sessionPostUrls = new Set();
  let duplicateCount = 0;
  let scrollCount = 0;
  let noNewPostStreak = 0;

  while (scrollCount < maxScrolls && allPosts.length < maxCandidates) {
    if (activeScrape.cancelRequested) {
      log('warn', `🛑 Scraper stopped by user request at scroll #${scrollCount + 1}. Preserving collected leads.`);
      break;
    }

    log('info', `📜 Scroll #${scrollCount + 1}/${maxScrolls} — scraping visible posts from page (mode: ${postType.toUpperCase()})...`);
    await updateScrapeState({
      scrollCount: scrollCount + 1,
      currentCount: Math.min(allPosts.length, userTargetLimit),
      progressText: `Fetching posts... (scroll ${scrollCount + 1})`
    });

    let results;
    try {
      results = await chrome.scripting.executeScript({
        target: { tabId },
        func:   scrapeVisiblePosts,
        args:   [keyword, postType, geoUrn]
      });
    } catch (execErr) {
      log('error', `❌ executeScript failed on scroll #${scrollCount + 1}: ${execErr.message}`);
      break;
    }

    const newPosts = results[0]?.result || [];
    log('info', `🔎 Scroll #${scrollCount + 1} — found ${newPosts.length} posts on page`);

    let addedThisRound = 0;
    for (const post of newPosts) {
      if (allPosts.length >= maxCandidates) break;

      const isDuplicate = allPosts.some(p => {
        if (p.postUrl && post.postUrl && p.postUrl === post.postUrl) return true;
        if (p.authorProfileUrl && post.authorProfileUrl && p.authorProfileUrl === post.authorProfileUrl) return true;
        if (p.content && post.content && p.content.slice(0, 60) === post.content.slice(0, 60)) return true;
        return false;
      });

      const fp = postFingerprint(post);
      if (sessionFingerprints.has(fp)) {
        duplicateCount++;
        continue;
      }
      if (post.postUrl && sessionPostUrls.has(post.postUrl)) {
        duplicateCount++;
        continue;
      }

      if (!isDuplicate) {
        allPosts.push(post);
        sessionFingerprints.add(fp);
        if (post.postUrl) sessionPostUrls.add(post.postUrl);
        addedThisRound++;
        log('info', `📝 Post Candidate #${allPosts.length} Extracted:`, {
          author: post.authorName,
          company: post.company,
          contentPreview: (post.content || '').slice(0, 100) + '...',
          postUrl: post.postUrl || '(missing)',
          postUrlSource: post.postUrlSource || 'none',
          authorProfileUrl: post.authorProfileUrl || '(missing)',
          feedLocation: post.feedLocation || '(none detected in card)'
        });
      }
    }

    log('info', `✅ Added ${addedThisRound} new candidates — total collected so far: ${allPosts.length}`);
    const displayCount = Math.min(allPosts.length, userTargetLimit);
    notifyProgress(displayCount, userTargetLimit, scrollCount + 1);
    await updateScrapeState({
      currentCount: displayCount,
      posts: allPosts,
      metrics: { rawCandidates: allPosts.length, duplicatesSkipped: duplicateCount }
    });

    if (activeScrape.cancelRequested) {
      log('warn', `🛑 Scraper cancellation detected. Halting loop.`);
      break;
    }

    if (addedThisRound === 0) {
      noNewPostStreak++;
      if (noNewPostStreak >= 4) {
        log('warn', `⚠️ No new candidate posts found after 4 consecutive scrolls. Finishing candidate collection.`);
        break;
      }
    } else {
      noNewPostStreak = 0;
    }

    scrollCount++;
    if (allPosts.length < maxCandidates) {
      await chrome.scripting.executeScript({
        target: { tabId },
        func: scrollPageDown
      });
      await delay(SCROLL_DELAY);
    }
  }

  return allPosts;
}

function notifyProgress(count, total, scroll) {
  chrome.runtime.sendMessage({
    action: 'PROGRESS_UPDATE',
    count,
    total,
    scroll
  }).catch(() => {});
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ═══════════════════════════════════════════════════════════════════════════════
// INJECTED PAGE FUNCTIONS (Run INSIDE LinkedIn DOM)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Live DOM Inspector & Element Highlighter
 */
async function inspectPageAndHighlight() {
  const url = window.location.href;
  const title = document.title || '';
  const mainEl = document.querySelector('main') || document.body;

  const counts = {
    'profile /in/ links': document.querySelectorAll('a[href*="/in/"]').length,
    'social buttons (Like/Comment)': document.querySelectorAll('button[aria-label*="Like" i], button[aria-label*="reaction" i], button[aria-label*="Comment" i], button[aria-label*="like"], button[aria-label*="comment"]').length,
    'data-view-name elements': document.querySelectorAll('div[data-view-name]').length,
    'total li': document.querySelectorAll('li').length,
    'articles': document.querySelectorAll('article').length
  };

  const containerSet = new Set();

  // Strategy 1: Walk UP from Comment action button (Each LinkedIn post has exactly 1 Comment button)
  const commentButtons = document.querySelectorAll(
    'button[aria-label*="Comment" i], button[aria-label*="comment"]'
  );
  commentButtons.forEach(btn => {
    let curr = btn.parentElement;
    let postCard = null;
    for (let d = 0; d < 25; d++) {
      if (!curr || curr === document.body || curr.tagName === 'MAIN') break;
      const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
      const innerComments = curr.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
      const text = (curr.innerText || '').trim();

      if (hasAuthor && innerComments === 1 && text.length > 40) {
        postCard = curr;
        if (curr.parentElement) {
          const parentComments = curr.parentElement.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
          if (parentComments > 1) {
            break;
          }
        }
      } else if (innerComments > 1) {
        break;
      }
      curr = curr.parentElement;
    }
    if (postCard) {
      containerSet.add(postCard);
    }
  });

  // Strategy 2: If no comment buttons found, walk UP from Like buttons
  if (containerSet.size === 0) {
    const likeButtons = document.querySelectorAll(
      'button[aria-label*="Like" i], button[aria-label*="like"]'
    );
    likeButtons.forEach(btn => {
      let curr = btn.parentElement;
      let postCard = null;
      for (let d = 0; d < 25; d++) {
        if (!curr || curr === document.body || curr.tagName === 'MAIN') break;
        const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
        const text = (curr.innerText || '').trim();
        if (hasAuthor && text.length > 40) {
          postCard = curr;
          if (curr.parentElement) {
            const authorLinks = Array.from(curr.parentElement.querySelectorAll('a[href*="/in/"]'));
            const uniqueAuthorProfiles = new Set(
              authorLinks.map(a => (a.href || '').split('?')[0].replace(/\/$/, '')).filter(h => h.includes('/in/') && !h.endsWith('/in'))
            );
            if (uniqueAuthorProfiles.size > 1) break;
          }
        }
        curr = curr.parentElement;
      }
      if (postCard) containerSet.add(postCard);
    });
  }

  // Strategy 2: Walk UP from author profile links
  if (containerSet.size === 0) {
    const authorLinks = document.querySelectorAll('a[href*="/in/"]');
    authorLinks.forEach(a => {
      let el = a.parentElement;
      for (let d = 0; d < 18; d++) {
        if (!el || el === document.body || el.tagName === 'MAIN') break;
        const hasSocial = el.querySelector('button[aria-label*="Like" i], button[aria-label*="reaction" i], button[aria-label*="Comment" i], button[aria-label*="like"], button[aria-label*="comment"]');
        const text = (el.innerText || '').trim();
        if (hasSocial && text.length > 40) {
          const canonical = el.closest('li, div.feed-shared-update-v2, div[data-view-name*="update"], div.artdeco-card') || el;
          containerSet.add(canonical);
          break;
        }
        el = el.parentElement;
      }
    });
  }

  // Strategy 3: Check all li elements or card wrappers with author + text
  if (containerSet.size === 0) {
    const allCards = document.querySelectorAll('li, div.artdeco-card, div.feed-shared-update-v2, div[data-view-name*="update"], div[data-urn*="activity"]');
    allCards.forEach(card => {
      const hasAuthor = card.querySelector('a[href*="/in/"]');
      const text = (card.innerText || '').trim();
      if (hasAuthor && text.length > 50 && (text.includes('Follow') || text.includes('•') || text.includes('hiring') || text.includes('Like'))) {
        const canonical = card.closest('li, div.feed-shared-update-v2, div[data-view-name*="update"], div.artdeco-card') || card;
        containerSet.add(canonical);
      }
    });
  }

  const containerList = Array.from(containerSet);
  const cardDetails = [];

  for (let i = 0; i < Math.min(containerList.length, 5); i++) {
    const card = containerList[i];
    const postRoot = card;
    try {
      postRoot.style.outline = '3px solid #10b981';
      postRoot.style.outlineOffset = '2px';
      postRoot.style.position = 'relative';

      const existing = postRoot.querySelector('.scraper-inspect-badge');
      if (existing) existing.remove();

      const badge = document.createElement('div');
      badge.className = 'scraper-inspect-badge';
      badge.style.cssText = 'position:absolute; top:-12px; left:10px; background:#10b981; color:white; font-size:11px; font-weight:bold; padding:2px 8px; border-radius:4px; z-index:999999; box-shadow:0 2px 5px rgba(0,0,0,0.2); font-family:sans-serif;';
      badge.textContent = `🔬 Live Scraper Card #${i + 1}`;
      postRoot.prepend(badge);
    } catch (_) {}

    const authorEl = postRoot.querySelector('a[href*="/in/"]');
    const author = (authorEl ? (authorEl.innerText || authorEl.textContent || '') : 'Unknown').split('\n')[0].replace(/•.*$/, '').trim();
    const descEl = postRoot.querySelector('.feed-shared-update-v2__description, .update-components-text, span.break-words, span[dir="ltr"]');
    const text = (descEl ? (descEl.innerText || descEl.textContent || '') : postRoot.innerText || '').slice(0, 160).replace(/\s+/g, ' ');

    let postUrl = '';
    let postUrlSource = '';

    // Tier 0: Check if card post URL was already cached from earlier pass
    if (postRoot.getAttribute('data-bde-post-url')) {
      postUrl = postRoot.getAttribute('data-bde-post-url');
      postUrlSource = postRoot.getAttribute('data-bde-url-source') || 'cached_card';
    }

    // Tier 1: Candidate permalink anchors inside postRoot
    if (!postUrl) {
      const candidateAnchors = Array.from(postRoot.querySelectorAll(
        'a[href*="/feed/update/urn:li:"], a[href*="/posts/"], a.update-components-actor__sub-description-link'
      ));
      for (const a of candidateAnchors) {
        const href = a.href || '';
        const clean = href.split('?')[0];
        if (clean.includes('/feed/update/urn:li:') || (clean.includes('/posts/') && !clean.endsWith('/posts/') && !clean.endsWith('/posts'))) {
          postUrl = clean.replace(/\/$/, '') + '/';
          postUrlSource = 'card_anchor_link';
          break;
        }
      }
    }

    // Tier 2: Check 3-dots control menu for official link
    if (!postUrl && !postRoot.hasAttribute('data-bde-dots-checked')) {
      postRoot.setAttribute('data-bde-dots-checked', 'true');
      const threeDotsBtn = postRoot.querySelector(
        'button[aria-label*="control menu for post" i], button[aria-label*="control menu" i], button.feed-shared-control-menu__trigger, button.artdeco-dropdown__trigger'
      );
      if (threeDotsBtn) {
        // Clear any previous captured URL
        document.documentElement.removeAttribute('data-last-linkedin-copied-url');
        let interceptedUrl = null;

        const onCopied = (e) => {
          if (e.detail && typeof e.detail === 'string') {
            interceptedUrl = e.detail.trim();
          }
        };
        document.addEventListener('bde-linkedin-copied-url', onCopied, { once: true });

        try {
          // Dismiss any existing open menus before clicking
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
          await new Promise(r => setTimeout(r, 80));

          threeDotsBtn.scrollIntoView({ block: 'center', behavior: 'instant' });
          await new Promise(r => setTimeout(r, 60));
          threeDotsBtn.click();

          // Poll up to 900ms for "Copy link" or "Copy link to post"
          let copyBtn = null;
          for (let a = 0; a < 9; a++) {
            await new Promise(r => setTimeout(r, 100));
            const clickables = Array.from(document.querySelectorAll('div[role="button"], button, li, a, span, p, [aria-label*="copy" i]'));
            copyBtn = clickables.find(el => {
              const txt = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
              return /\bcopy link\b/i.test(txt) || txt.toLowerCase().includes('copy link');
            });
            if (copyBtn) break;
          }

          if (copyBtn) {
            const targetClick = copyBtn.closest('div[role="button"], button, li, a') || copyBtn;
            targetClick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
            targetClick.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
            targetClick.click();

            for (let a = 0; a < 7; a++) {
              if (interceptedUrl) break;
              const attrVal = document.documentElement.getAttribute('data-last-linkedin-copied-url');
              if (attrVal) {
                interceptedUrl = attrVal.trim();
                break;
              }
              await new Promise(r => setTimeout(r, 100));
            }
          }

          // Cleanly close menu
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
          if (threeDotsBtn.getAttribute('aria-expanded') === 'true') {
            threeDotsBtn.click();
          }
          await new Promise(r => setTimeout(r, 80));
        } catch (_) {
        } finally {
          document.removeEventListener('bde-linkedin-copied-url', onCopied);
        }

        if (!interceptedUrl) {
          const attrVal = document.documentElement.getAttribute('data-last-linkedin-copied-url');
          if (attrVal) interceptedUrl = attrVal.trim();
        }

        if (interceptedUrl) {
          let finalUrl = interceptedUrl;
          if (finalUrl.startsWith('/')) finalUrl = 'https://www.linkedin.com' + finalUrl;
          if (finalUrl.startsWith('http://') || finalUrl.startsWith('https://')) {
            postUrl = finalUrl;
            postUrlSource = 'official_linkedin_copy_menu';
          }
        }
      }
    }

    // Tier 3: Fallback to Author Recent Activity Feed if 3-dots link was absent
    if (!postUrl && authorEl && authorEl.href) {
      const profClean = authorEl.href.split('?')[0].replace(/\/$/, '');
      if (profClean.includes('/in/')) {
        postUrl = `${profClean}/recent-activity/all/`;
        postUrlSource = 'author_activity_feed_fallback';
      }
    }

    if (postUrl && postUrlSource !== 'author_activity_feed_fallback') {
      postRoot.setAttribute('data-bde-post-url', postUrl);
      postRoot.setAttribute('data-bde-url-source', postUrlSource);
    }

    cardDetails.push({
      cardIndex: i + 1,
      tagName: card.tagName,
      className: (card.className || '').slice(0, 60),
      height: `${Math.round(card.getBoundingClientRect().height)}px`,
      author,
      textSnippet: text,
      postUrl: postUrl || 'None',
      postUrlSource: postUrlSource || 'none',
      authorProfileUrl: authorEl?.href?.split('?')[0] || 'None'
    });
  }

  return {
    pageUrl: url,
    pageTitle: title,
    totalCandidateCardsFound: containerList.length,
    selectorCounts: counts,
    cardsInspected: cardDetails,
    pageSnippet: (mainEl ? mainEl.innerText : '').slice(0, 250).replace(/\s+/g, ' ')
  };
}

/**
 * Diagnoses the current LinkedIn DOM
 */
function diagnosePage() {
  const url = window.location.href;
  const title = document.title || '';
  const mainEl = document.querySelector('main') || document.body;
  const bodyText = (mainEl ? mainEl.innerText : '').slice(0, 350).replace(/\s+/g, ' ');

  const selectors = {
    'profile /in/ links':    document.querySelectorAll('a[href*="/in/"]').length,
    'social buttons':        document.querySelectorAll('button[aria-label*="Like" i], button[aria-label*="Comment" i], button[aria-label*="reaction" i]').length,
    'data-view-name':        document.querySelectorAll('div[data-view-name]').length,
    'articles':              document.querySelectorAll('article').length,
    'total li':              document.querySelectorAll('li').length,
  };

  const isLoginPage = url.includes('/login') ||
                      url.includes('/checkpoint') ||
                      url.includes('/authwall') ||
                      document.querySelector('form.login__form') !== null ||
                      document.querySelector('#username') !== null;

  const hasNoResults = /no results|no matching|couldn\'t find/i.test(bodyText);

  return {
    url,
    title,
    isLoginPage,
    hasNoResults,
    bodySnippet: bodyText,
    selectorCounts: selectors
  };
}

/**
 * Scrapes visible posts from LinkedIn search results with Direct Anchor & 3-Dots Control Menu Permalink Discovery.
 */
async function scrapeVisiblePosts(keyword, postType = 'organic', geoUrn = '103644278') {
  const posts = [];
  const seenFingerprints = new Set();

  // Try to click any "...see more" buttons to expand truncated post text
  try {
    const seeMoreButtons = document.querySelectorAll(
      'button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label*="see more" i], .see-more'
    );
    seeMoreButtons.forEach(btn => {
      try {
        if (!btn.hasAttribute('data-bde-clicked')) {
          btn.setAttribute('data-bde-clicked', 'true');
          btn.click();
        }
      } catch (_) {}
    });
  } catch (_) {}

  // ── Find Post Containers (Walk UP from Social Buttons & Profile Links) ──────
  const containerSet = new Set();

  // Strategy 1: Walk UP from Comment action button (Each LinkedIn post has exactly 1 Comment button)
  const commentButtons = document.querySelectorAll(
    'button[aria-label*="Comment" i], button[aria-label*="comment"]'
  );
  commentButtons.forEach(btn => {
    let curr = btn.parentElement;
    let postCard = null;
    for (let d = 0; d < 25; d++) {
      if (!curr || curr === document.body || curr.tagName === 'MAIN') break;
      const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
      const innerComments = curr.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
      const text = (curr.innerText || '').trim();

      if (hasAuthor && innerComments === 1 && text.length > 40) {
        postCard = curr;
        if (curr.parentElement) {
          const parentComments = curr.parentElement.querySelectorAll('button[aria-label*="Comment" i], button[aria-label*="comment"]').length;
          if (parentComments > 1) {
            break;
          }
        }
      } else if (innerComments > 1) {
        break;
      }
      curr = curr.parentElement;
    }
    if (postCard) {
      containerSet.add(postCard);
    }
  });

  // Strategy 2: If no comment buttons found, walk UP from Like buttons
  if (containerSet.size === 0) {
    const likeButtons = document.querySelectorAll(
      'button[aria-label*="Like" i], button[aria-label*="like"]'
    );
    likeButtons.forEach(btn => {
      let curr = btn.parentElement;
      let postCard = null;
      for (let d = 0; d < 25; d++) {
        if (!curr || curr === document.body || curr.tagName === 'MAIN') break;
        const hasAuthor = !!curr.querySelector('a[href*="/in/"]');
        const text = (curr.innerText || '').trim();
        if (hasAuthor && text.length > 40) {
          postCard = curr;
          if (curr.parentElement) {
            const authorLinks = Array.from(curr.parentElement.querySelectorAll('a[href*="/in/"]'));
            const uniqueAuthorProfiles = new Set(
              authorLinks.map(a => (a.href || '').split('?')[0].replace(/\/$/, '')).filter(h => h.includes('/in/') && !h.endsWith('/in'))
            );
            if (uniqueAuthorProfiles.size > 1) break;
          }
        }
        curr = curr.parentElement;
      }
      if (postCard) containerSet.add(postCard);
    });
  }

  // Strategy 2: Author profile links walking UP to canonical post container
  if (containerSet.size === 0) {
    const authorLinks = document.querySelectorAll('a[href*="/in/"]');
    authorLinks.forEach(a => {
      let el = a.parentElement;
      for (let d = 0; d < 18; d++) {
        if (!el || el === document.body || el.tagName === 'MAIN') break;
        const hasSocial = el.querySelector(
          'button[aria-label*="Like" i], button[aria-label*="reaction" i], button[aria-label*="Comment" i], button[aria-label*="like"], button[aria-label*="comment"]'
        );
        const text = (el.innerText || '').trim();
        if (hasSocial && text.length > 40) {
          const canonical = el.closest('li, div.feed-shared-update-v2, div[data-view-name*="update"], div.artdeco-card') || el;
          containerSet.add(canonical);
          break;
        }
        el = el.parentElement;
      }
    });
  }

  // Strategy 3: Check all li elements or card wrappers with author + text
  if (containerSet.size === 0) {
    const allCards = document.querySelectorAll(
      'li, div.artdeco-card, div.feed-shared-update-v2, div[data-view-name*="update"], div[data-urn*="activity"]'
    );
    allCards.forEach(card => {
      const hasAuthor = card.querySelector('a[href*="/in/"]');
      const text = (card.innerText || '').trim();
      if (hasAuthor && text.length > 50 && (text.includes('Follow') || text.includes('•') || text.includes('hiring') || text.includes('Like'))) {
        const canonical = card.closest('li, div.feed-shared-update-v2, div[data-view-name*="update"], div.artdeco-card') || card;
        containerSet.add(canonical);
      }
    });
  }

  // ── Regex filters for local heuristics ─────────────────────────────────────
  const ACTIVE_CTA_REGEX = /\b(dm me|pm me|reach out|message me|apply here|apply at|apply via|send your resume|email your resume|send cv|email me at|send resume|drop your resume|share your resume|join our team|join us|open role|open roles|hiring for our team|we are looking for|we['’]re looking for|looking to hire|we have an opening|submit your application|link in comments|link in post|link below|candidates interested in|interested candidates|comment below|fill out the form)\b/i;
  const JOB_SPECS_REGEX = /\b(w-?2 only|salary\s*:|compensation\s*:|benefits\s*:|requirements\s*:|responsibilities\s*:|job type\s*:|location\s*:\s*[a-z0-9, ]+|experience\s*:\s*\d+|hybrid|onsite|remote\s*[-–]\s*us|\$\d+k?[\s–-]+\$\d+k?|\$\d+[\s–-]+\$\d+\s*\/\s*hr|\$\d+\s*[-–]\s*\$\d+)\b/i;
  const JOB_SEEKER_REGEX = /\b(open to work|looking for a job|seeking opportunity|seeking a role|laid off|hire me|actively looking for a? job|open to (?:senior|ai|tech|staff|remote|hybrid|new|full-time)?\s*roles?|no sponsorship required|systems i can walk you through live|available immediately|my resume is attached|i am looking for (?:a|new)?\s*(?:role|job|opportunity))\b/i;
  const EMPLOYER_OVERRIDE = /\b(we are hiring|we['’]re hiring|i['’]m hiring|i am hiring|join our team|our company is looking for|hiring for our team|looking to hire|we have open roles|we['’]re looking for|i['’]m looking for|i am looking for|looking for an?|looking for someone|team is growing|expanding our team|open position|open positions|open role|open roles)\b/i;
  const BENCH_VENDOR_REGEX = /\b(bench sales|c2c recruiter|hotlist recruiter|talent marketing|consultant marketing|available consultants?|hotlist of consultants?|on c2c|share your c2c|opt candidate marketing)\b/i;
  const RESTRICTION_OVERRIDE = /\b(no c2c|no bench|w-?2 only|strictly no c2c)\b/i;

  let postIdx = 0;
  for (const container of containerSet) {
    try {
      const postRoot = container;

      const fullText = (postRoot.innerText || postRoot.textContent || '').trim();
      if (fullText.length < 30) continue;

      let cleanFullText = fullText
        .replace(/^🔬[^\n]*\n?/g, '')
        .replace(/^✅[^\n]*\n?/g, '')
        .replace(/^💼[^\n]*\n?/g, '')
        .replace(/^📝[^\n]*\n?/g, '')
        .replace(/^Feed post\s*/i, '')
        .trim();

      // Job card detection
      const hasJobLink = !!postRoot.querySelector('a[href*="/jobs/view/"], a[href*="/jobs/collections/"], a[href*="/jobs/"]');
      const hasViewJobBtn = Array.from(postRoot.querySelectorAll('button, a, span')).some(el => {
        const txt = (el.innerText || el.textContent || '').trim();
        return /^\s*View job\s*$/i.test(txt) || /^\s*Easy Apply\s*$/i.test(txt);
      });
      const hasJobCardClass = !!postRoot.querySelector(
        '[class*="job-posting"], [class*="job-card"], [class*="entity-result__job"], [data-view-name*="job"]'
      );
      const isJobCard = hasJobLink || hasViewJobBtn || hasJobCardClass;
      if (postType === 'organic' && isJobCard) continue;
      if (postType === 'job_card' && !isJobCard) continue;

      // 1. Author Name
      let authorName = 'Unknown';
      const UI_BUTTON_PREFIX_REGEX = /^(?:connect|follow|following|join|message|view\s+\d+\s+jobs?)$/i;
      const authorLinks = Array.from(postRoot.querySelectorAll('a[href*="/in/"]'));
      for (const a of authorLinks) {
        const raw = (a.innerText || a.textContent || '').trim();
        if (raw) {
          const lines = raw.split('\n').map(l => l.trim()).filter(l => l.length > 0);
          const validLines = lines.filter(l => !UI_BUTTON_PREFIX_REGEX.test(l) && !l.includes('|') && !l.includes('•'));
          if (validLines.length > 0 && validLines[0].length > 2 && validLines[0].length < 45) {
            authorName = validLines[0].replace(/•.*$/, '').trim();
            break;
          }
        }
      }
      if (authorName === 'Unknown' || authorName.includes('|') || authorName.length > 45 || UI_BUTTON_PREFIX_REGEX.test(authorName)) {
        const actorNameEl = postRoot.querySelector(
          '.update-components-actor__name, .update-components-actor__title, .feed-shared-actor__name, [class*="actor__name"], [class*="actor__title"]'
        );
        if (actorNameEl && actorNameEl.innerText && actorNameEl.innerText.trim().length > 1) {
          const lines = actorNameEl.innerText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
          const valid = lines.filter(l => !UI_BUTTON_PREFIX_REGEX.test(l));
          if (valid.length > 0) authorName = valid[0].replace(/•.*$/, '').trim();
        }
      }

      // 2. Author Profile URL
      let authorProfileUrl = '';
      if (authorLinks.length > 0 && authorLinks[0].href) {
        authorProfileUrl = authorLinks[0].href.split('?')[0].replace(/\/$/, '') + '/';
      }

      // 3. Company / Headline
      let company = '';
      const headlineEl = postRoot.querySelector(
        '.update-components-actor__description, .update-components-actor__sub-description, .feed-shared-actor__description, [class*="actor__description"]'
      );
      if (headlineEl && headlineEl.innerText && headlineEl.innerText.trim().length > 3) {
        company = headlineEl.innerText.split('\n')[0].trim();
      }
      if (!company && cleanFullText.includes('•')) {
        const afterBullet = cleanFullText.split('•')[1] || '';
        const lines = afterBullet.split('\n').map(l => l.trim()).filter(l => l.length > 0);
        for (const line of lines) {
          if (/^(?:1st|2nd|3rd\+?|following|follow|connect|message|\d+[smhdw]|now|yesterday)$/i.test(line)) continue;
          if (line.length > 3 && !line.startsWith('http') && line !== authorName && line !== 'Feed post') {
            company = line;
            break;
          }
        }
      }
      if (company === 'Feed post' || company === authorName || /^(?:1st|2nd|3rd\+?|following|follow|connect|message)$/i.test(company) || /^\d+(?:st|nd|rd|th)\+?$/i.test(company)) {
        company = '';
      }

      // 4. Sub-description & Location Metadata (Zero Tab Navigation)
      const subDescEl = postRoot.querySelector(
        '.update-components-actor__sub-description, [class*="actor__sub-description"], .feed-shared-actor__sub-description'
      );
      const subDescText = (subDescEl?.innerText || '').replace(/\s+/g, ' ').trim();

      let feedLocation = '';
      const locMatch = cleanFullText.match(/(?:📍|📌|Location|Based in|Workplace|Role location)\s*[:\-]?\s*([A-Za-z0-9,.\- ]{2,50})/i);
      if (locMatch) {
        feedLocation = locMatch[1].trim();
      } else if (/\b(remote\s*[-–]\s*us|us\s*remote|remote\s*(?:within|in)?\s*(?:the\s*)?u\.?s\.?|united states\s*\(remote\))\b/i.test(cleanFullText)) {
        feedLocation = 'US Remote';
      }

      // 5. Post Content
      let content = '';
      const explicitDesc = postRoot.querySelector(
        '.feed-shared-update-v2__description, .update-components-text, .feed-shared-inline-show-more-text, [class*="update-components-text"]'
      );
      if (explicitDesc && explicitDesc.innerText && explicitDesc.innerText.trim().length > 20) {
        content = explicitDesc.innerText.trim();
      }
      if (!content || content.length < 20) {
        if (cleanFullText.includes('Follow')) {
          const parts = cleanFullText.split(/\bFollow\b/i);
          if (parts.length > 1 && parts[1].trim().length > 15) {
            content = parts.slice(1).join(' ').trim();
          }
        }
      }
      if (!content || content.length < 20) {
        const timeRegex = /\b\d+[smhdw]\b(?:\s*•\s*(?:Edited|Public|Sponsored))?\s*/i;
        const timeMatch = cleanFullText.match(timeRegex);
        if (timeMatch && timeMatch.index !== undefined) {
          const afterTime = cleanFullText.slice(timeMatch.index + timeMatch[0].length).trim();
          const cleanAfter = afterTime.replace(/^(?:Follow|Join)\s*/i, '').trim();
          if (cleanAfter.length > 15) content = cleanAfter;
        }
      }
      if (!content || content.length < 20) {
        let remaining = cleanFullText;
        if (authorName && authorName !== 'Unknown') remaining = remaining.replace(authorName, '');
        if (company) remaining = remaining.replace(company, '');
        remaining = remaining.replace(/^(?:•\s*(?:1st|2nd|3rd\+?|Following|Follow)\s*)+/i, '').trim();
        remaining = remaining.replace(/\b\d+[smhdw]\b/i, '').trim();
        if (remaining.length > 15) content = remaining;
      }
      if (!content || content.length < 15) continue;
      content = content.replace(/\s*\.\.\.see more\s*$/i, '').trim();

      const fp = content.slice(0, 80);
      if (seenFingerprints.has(fp)) continue;
      seenFingerprints.add(fp);

      // 6. Safe Local Candidate Filter:
      // Skip self-pitching job seekers who have no employer/hiring context
      if (JOB_SEEKER_REGEX.test(cleanFullText) && !EMPLOYER_OVERRIDE.test(cleanFullText)) {
        continue;
      }
      // Note: All other candidate posts are preserved and passed to OpenAI for deep BDE qualification

      // 7. Date
      let date = '';
      if (subDescEl) {
        const sm = (subDescEl.innerText || '').match(/\b(\d+[smhdw]|now|yesterday)\b/i);
        if (sm) date = sm[0].trim();
      }
      if (!date) {
        const timeEl = postRoot.querySelector('time');
        if (timeEl) date = (timeEl.innerText || timeEl.getAttribute('datetime') || '').trim();
      }
      if (!date) {
        const dotMatch = fullText.match(/(?:•|\n|^)\s*(\d+[smhdw]|now|yesterday)(?:\s*•|\s+Edited|\n|$)/i);
        if (dotMatch) date = dotMatch[1].trim();
        else {
          const timeMatch = fullText.match(/\b(\d+[smhdw]|now|yesterday|\d+\s*(?:minute|hour|day|week|month)s?\s*ago)\b/i);
          if (timeMatch) date = timeMatch[0].trim();
        }
      }

      // 8. Likes & Comments
      let likes = 0;
      const reactionBtn = postRoot.querySelector(
        'button[aria-label*="reaction" i], button[aria-label*="like" i], [class*="reaction"]'
      );
      if (reactionBtn) {
        const match = (reactionBtn.innerText || reactionBtn.getAttribute('aria-label') || '').match(/\d[\d,.]*/);
        if (match) likes = parseInt(match[0].replace(/,/g, ''), 10) || 0;
      }

      let comments = 0;
      const commentBtn = postRoot.querySelector(
        'button[aria-label*="comment" i], [class*="comment"]'
      );
      if (commentBtn) {
        const match = (commentBtn.innerText || commentBtn.getAttribute('aria-label') || '').match(/\d[\d,.]*/);
        if (match) comments = parseInt(match[0].replace(/,/g, ''), 10) || 0;
      }

      // 9. Post URL (Authentic Permalink Discovery: Direct Link -> 3-Dots Menu Copy -> Feed Fallback)
      let postUrl = '';
      let postUrlSource = '';

      // Tier 0: Check if card post URL was already cached from earlier scroll pass
      if (postRoot.getAttribute('data-bde-post-url')) {
        postUrl = postRoot.getAttribute('data-bde-post-url');
        postUrlSource = postRoot.getAttribute('data-bde-url-source') || 'cached_previous_scroll';
      }

      // Tier 1: Candidate permalink anchors inside postRoot
      if (!postUrl) {
        const candidateAnchors = Array.from(postRoot.querySelectorAll(
          'a[href*="/feed/update/urn:li:"], a[href*="/posts/"], a.update-components-actor__sub-description-link'
        ));
        for (const a of candidateAnchors) {
          const href = a.href || '';
          const clean = href.split('?')[0];
          if (clean.includes('/feed/update/urn:li:') || (clean.includes('/posts/') && !clean.endsWith('/posts/') && !clean.endsWith('/posts'))) {
            postUrl = clean.replace(/\/$/, '') + '/';
            postUrlSource = 'card_anchor_link';
            break;
          }
        }
      }

      // Tier 2: Check 3-dots control menu for official link (LinkedIn shortlink lnkd.in/p/...)
      if (!postUrl) {
        const threeDotsBtn = postRoot.querySelector(
          'button[aria-label*="control menu for post" i], button[aria-label*="control menu" i], button.feed-shared-control-menu__trigger, button.artdeco-dropdown__trigger'
        );
        if (threeDotsBtn) {
          // Clear any previous captured URL and ensure clean state
          document.documentElement.removeAttribute('data-last-linkedin-copied-url');
          let interceptedUrl = null;

          const onCopied = (e) => {
            if (e.detail && typeof e.detail === 'string') {
              interceptedUrl = e.detail.trim();
            }
          };
          document.addEventListener('bde-linkedin-copied-url', onCopied, { once: true });

          try {
            // Dismiss any existing open menus before clicking new button
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
            await new Promise(r => setTimeout(r, 80));

            // Center the button in the viewport so the dropdown menu has maximum vertical space to render
            threeDotsBtn.scrollIntoView({ block: 'center', behavior: 'instant' });
            await new Promise(r => setTimeout(r, 60));
            threeDotsBtn.click();

            // Poll up to 900ms for "Copy link" or "Copy link to post" button to appear
            let copyBtn = null;
            for (let a = 0; a < 9; a++) {
              await new Promise(r => setTimeout(r, 100));
              const clickables = Array.from(document.querySelectorAll('div[role="button"], button, li, a, span, p, [aria-label*="copy" i]'));
              copyBtn = clickables.find(el => {
                const txt = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                return /\bcopy link\b/i.test(txt) || txt.toLowerCase().includes('copy link');
              });
              if (copyBtn) break;
            }

            if (copyBtn) {
              const targetClick = copyBtn.closest('div[role="button"], button, li, a') || copyBtn;
              targetClick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
              targetClick.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
              targetClick.click();

              // Poll up to 700ms for intercepted URL to be captured
              for (let a = 0; a < 7; a++) {
                if (interceptedUrl) break;
                const attrVal = document.documentElement.getAttribute('data-last-linkedin-copied-url');
                if (attrVal) {
                  interceptedUrl = attrVal.trim();
                  break;
                }
                await new Promise(r => setTimeout(r, 100));
              }
            }

            // Cleanly close the dropdown menu
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
            if (threeDotsBtn.getAttribute('aria-expanded') === 'true') {
              threeDotsBtn.click();
            }
            await new Promise(r => setTimeout(r, 80));
          } catch (_) {
          } finally {
            document.removeEventListener('bde-linkedin-copied-url', onCopied);
          }

          if (!interceptedUrl) {
            const attrVal = document.documentElement.getAttribute('data-last-linkedin-copied-url');
            if (attrVal) interceptedUrl = attrVal.trim();
          }

          if (interceptedUrl) {
            let finalUrl = interceptedUrl;
            if (finalUrl.startsWith('/')) finalUrl = 'https://www.linkedin.com' + finalUrl;
            if (finalUrl.startsWith('http://') || finalUrl.startsWith('https://')) {
              postUrl = finalUrl;
              postUrlSource = 'official_linkedin_copy_menu';
            }
          }
        }
      }

      // Tier 3: Clean Fallback to Author Recent Activity Feed if 3-dots link was absent
      if (!postUrl && authorProfileUrl) {
        postUrl = `${authorProfileUrl.replace(/\/$/, '')}/recent-activity/all/`;
        postUrlSource = 'author_activity_feed_fallback';
      }

      // Only cache permanent, authentic post links (so temporary fallbacks can be upgraded on next scroll)
      if (postUrl && postUrlSource !== 'author_activity_feed_fallback') {
        postRoot.setAttribute('data-bde-post-url', postUrl);
        postRoot.setAttribute('data-bde-url-source', postUrlSource);
      }

      // Visual Highlighting on the live LinkedIn page
      postIdx++;
      try {
        container.style.outline = isJobCard ? '3px solid #d97706' : '3px solid #16a34a';
        container.style.outlineOffset = '2px';
        container.style.position = 'relative';

        const existing = container.querySelector('.scraper-active-badge');
        if (existing) existing.remove();

        const badge = document.createElement('div');
        badge.className = 'scraper-active-badge';
        badge.style.cssText = `position:absolute; top:-12px; left:10px; background:${isJobCard ? '#d97706' : '#16a34a'}; color:white; font-size:11px; font-weight:bold; padding:2px 8px; border-radius:4px; z-index:999999; box-shadow:0 2px 5px rgba(0,0,0,0.2); font-family:sans-serif;`;
        badge.textContent = isJobCard ? `💼 Job Card #${postIdx}: ${authorName}` : `📝 Organic Post #${postIdx}: ${authorName}`;
        container.prepend(badge);
      } catch (_) {}

      posts.push({
        authorName,
        company,
        content,
        likes,
        comments,
        date,
        url: postUrl || '',
        postUrl: postUrl || '',
        postUrlStatus: postUrl ? (postUrl.includes('/feed/update/') || postUrl.includes('/posts/') ? 'resolved' : 'author_activity_feed') : 'unavailable',
        postUrlSource: postUrlSource || '',
        authorProfileUrl: authorProfileUrl || '',
        feedLocation: feedLocation || '',
        subDescText: subDescText || '',
        isJobCard,
        postType: isJobCard ? 'job_card' : 'organic'
      });

    } catch (_err) {
      // Ignore individually malformed containers
    }
  }

  return posts;
}

/**
 * Smooth human-like incremental scrolling down the feed
 * Monotonic (forward only) without competing scroll targets.
 */
function scrollPageDown() {
  const scrollDistance = Math.round(window.innerHeight * 0.85);

  // Check if document / window is scrollable
  const doc = document.documentElement;
  const isDocScrollable = (doc.scrollHeight - (window.innerHeight + window.scrollY)) > 50;

  if (isDocScrollable) {
    window.scrollBy({ top: scrollDistance, behavior: 'smooth' });
    return;
  }

  // Fallback: Dedicated scroll container if LinkedIn encapsulates results
  const main = document.querySelector('.scaffold-layout__main') || document.querySelector('main');
  if (main && (main.scrollHeight - (main.clientHeight + main.scrollTop)) > 50) {
    main.scrollBy({ top: scrollDistance, behavior: 'smooth' });
  } else {
    window.scrollBy({ top: scrollDistance, behavior: 'smooth' });
  }
}
