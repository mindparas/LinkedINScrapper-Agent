import re

def clean_linkedin_boolean_query(query_str):
    """
    Cleans and sanitizes search query syntax for LinkedIn content search:
    - Strips unsupported field qualifiers (location:, geo:, etc.)
    - Removes unnecessary wrapping double quotes that force verbatim matches and cause 0 results
    - Cleans unbalanced quotes and dangling boolean operators
    """
    if not query_str:
        return ""
    q = query_str.strip()
    # Strip invalid search box operators that cause zero results
    q = re.sub(r'\b(?:location|posted|date|geo|industry)\s*:\s*(?:\"[^\"]*\"|\'[^\']*\'|[^\s()]+)', '', q, flags=re.I)
    
    # Strip full outer quotes if entire query was wrapped in quotes (e.g. "building an MVP" -> building an MVP)
    if (q.startswith('"') and q.endswith('"')) or (q.startswith("'") and q.endswith("'")):
        if q.count('"') == 2 or q.count("'") == 2:
            q = q[1:-1].strip()

    # Clean double or single quotes wrapping keywords or phrases (e.g. "engineer" -> engineer, "stealth startup" -> stealth startup)
    q = re.sub(r'["\']([a-zA-Z0-9_\-\s]+)["\']', r'\1', q)

    # Clean unbalanced quotes if any remain
    if q.count('"') % 2 != 0:
        q = q.replace('"', '')
    if q.count("'") % 2 != 0:
        q = q.replace("'", "")

    # Sanitize boolean operators
    for _ in range(3):
        q = re.sub(r'\(\s*\)', '', q)
        q = re.sub(r'\s+(?:AND|OR)\s+(?=(?:AND|OR|\)|$))', ' ', q, flags=re.I)
        q = re.sub(r'\(\s*(?:AND|OR)\s+', '(', q, flags=re.I)
    q = re.sub(r'\s+', ' ', q).strip()
    return q
