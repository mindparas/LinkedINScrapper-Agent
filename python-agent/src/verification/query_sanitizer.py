import re

def clean_linkedin_boolean_query(query_str):
    """
    Cleans and sanitizes search query syntax for LinkedIn content search:
    - Strips unsupported field qualifiers (location:, geo:, date:, etc.)
    - Preserves exact multi-word phrase anchors in double quotes (e.g. "San Francisco", "founding engineer", "US only")
    - Unquotes single words (e.g. "engineer" -> engineer) so stem matching works (engineers, engineering)
    - Unquotes full sentences (> 40 chars) to prevent 0-result exact character mismatches
    - Cleans unbalanced quotes and dangling boolean operators
    """
    if not query_str:
        return ""
    q = query_str.strip()
    
    # 1. Strip invalid search box operators that cause zero results
    q = re.sub(r'\b(?:location|posted|date|geo|industry)\s*:\s*(?:\"[^\"]*\"|\'[^\']*\'|[^\s()]+)', '', q, flags=re.I)
    
    # 2. Standardize single quotes to double quotes
    q = q.replace("'", '"')

    # 3. Strip full outer quotes if entire query was wrapped in quotes (e.g. "San Francisco founding engineer" -> San Francisco founding engineer)
    if q.startswith('"') and q.endswith('"') and q.count('"') == 2:
        q = q[1:-1].strip()

    # 4. Handle quoted segments: preserve 2-4 word key phrases, unquote single words or long sentences
    def handle_quotes(match):
        inner = match.group(1).strip()
        words = inner.split()
        if len(words) == 1:
            # Single word: unquote for stem matching (e.g. "engineer" -> engineer matches engineers/engineering)
            return inner
        elif len(words) >= 2 and len(inner) <= 45:
            # Multi-word key phrase anchor: keep exact quotes! (e.g. "San Francisco", "founding engineer", "US only")
            return f'"{inner}"'
        else:
            # Full sentence: unquote to avoid 0 results
            return inner

    q = re.sub(r'\"([^\"]+)\"', handle_quotes, q)

    # 5. Clean unbalanced quotes if any remain
    if q.count('"') % 2 != 0:
        q = q.replace('"', '')

    # 6. Sanitize boolean operators
    for _ in range(3):
        q = re.sub(r'\(\s*\)', '', q)
        q = re.sub(r'\s+(?:AND|OR)\s+(?=(?:AND|OR|\)|$))', ' ', q, flags=re.I)
        q = re.sub(r'\(\s*(?:AND|OR)\s+', '(', q, flags=re.I)
    q = re.sub(r'\s+', ' ', q).strip()
    return q
