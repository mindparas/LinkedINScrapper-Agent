import re

def parse_post_age(raw_time_str):
    """
    Parses LinkedIn relative timestamp strings into float days.
    Examples: '2h', '1d', '3w', '1mo', 'just now'
    """
    if not raw_time_str:
        return 99.0
    s = raw_time_str.lower().strip()
    s = re.sub(r'•.*$', '', s).strip()
    
    if any(x in s for x in ['now', 'just now', 'moment', 'sec', 's']):
        return 0.0
    
    m_min = re.search(r'(\d+)\s*(?:m|min|minute)', s)
    if m_min:
        return float(m_min.group(1)) / (60 * 24)
        
    m_hr = re.search(r'(\d+)\s*(?:h|hr|hour)', s)
    if m_hr:
        return float(m_hr.group(1)) / 24.0
        
    m_day = re.search(r'(\d+)\s*(?:d|day)', s)
    if m_day:
        return float(m_day.group(1))
        
    m_wk = re.search(r'(\d+)\s*(?:w|wk|week)', s)
    if m_wk:
        return float(m_wk.group(1)) * 7.0
        
    m_mo = re.search(r'(\d+)\s*(?:mo|month)', s)
    if m_mo:
        return float(m_mo.group(1)) * 30.0
        
    m_yr = re.search(r'(\d+)\s*(?:y|yr|year)', s)
    if m_yr:
        return float(m_yr.group(1)) * 365.0
        
    if re.search(r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', s):
        return 30.0

    return 99.0

