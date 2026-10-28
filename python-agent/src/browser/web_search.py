import json
import urllib.request
import urllib.parse

def search_web_api(query):
    """
    Performs an instant web search via DuckDuckGo API to verify company details,
    founder backgrounds, or BDE search keywords.
    """
    try:
        enc = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={enc}&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", [])[:3]:
            if "Text" in topic:
                results.append(topic["Text"])
        return results if results else ["No instant summary found; rely on LinkedIn profile details."]
    except Exception as e:
        return [f"Web search note: {e}"]
