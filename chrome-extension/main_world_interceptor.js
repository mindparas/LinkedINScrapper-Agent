// ─────────────────────────────────────────────────────────────
// main_world_interceptor.js
// Injected into LinkedIn's MAIN execution world at document_start.
// Intercepts LinkedIn's native navigator.clipboard.writeText calls
// and surfaces the authentic post shortlink via a shared DOM attribute.
// ─────────────────────────────────────────────────────────────
(function() {
  if (window.__bdeClipboardInterceptorInstalled) return;
  window.__bdeClipboardInterceptorInstalled = true;

  try {
    const origWriteText = navigator.clipboard && navigator.clipboard.writeText;
    if (navigator.clipboard) {
      navigator.clipboard.writeText = async function(textVal) {
        if (textVal && typeof textVal === 'string' && (textVal.includes('lnkd.in/') || textVal.includes('linkedin.com/'))) {
          const clean = textVal.trim();
          document.documentElement.setAttribute('data-last-linkedin-copied-url', clean);
          document.dispatchEvent(new CustomEvent('bde-linkedin-copied-url', { detail: clean }));
        }
        if (origWriteText) {
          try { return await origWriteText.apply(navigator.clipboard, arguments); } catch(_) {}
        }
        return Promise.resolve();
      };
    }

    if (document.execCommand) {
      const origExec = document.execCommand;
      document.execCommand = function(cmd) {
        if (cmd === 'copy') {
          const selection = window.getSelection ? window.getSelection().toString() : '';
          if (selection && (selection.includes('lnkd.in/') || selection.includes('linkedin.com/'))) {
            const clean = selection.trim();
            document.documentElement.setAttribute('data-last-linkedin-copied-url', clean);
            document.dispatchEvent(new CustomEvent('bde-linkedin-copied-url', { detail: clean }));
          }
        }
        return origExec.apply(this, arguments);
      };
    }
  } catch (_) {}
})();

