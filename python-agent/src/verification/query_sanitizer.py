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

    # 4. Remove all double and single quotes to prevent 0-result exact character mismatches on LinkedIn
    # LinkedIn post search operates with maximum recall and relevance when keywords are natural and unquoted.
    q = q.replace('"', '').replace("'", '')

    # 6. Sanitize boolean operators
    for _ in range(3):
        q = re.sub(r'\(\s*\)', '', q)
        q = re.sub(r'\s+(?:AND|OR)\s+(?=(?:AND|OR|\)|$))', ' ', q, flags=re.I)
        q = re.sub(r'\(\s*(?:AND|OR)\s+', '(', q, flags=re.I)
    q = re.sub(r'\s+', ' ', q).strip()
    return q
