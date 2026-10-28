import re

US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming"
]

US_METROS = [
    "san francisco bay area", "greater new york city area", "greater seattle area",
    "greater boston", "greater chicago area", "dallas-fort worth metroplex",
    "greater los angeles area", "silicon valley", "austin", "seattle", "san jose",
    "chicago", "denver", "miami", "boston"
]

STATE_CODE_REGEX = re.compile(
    r',\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b',
    re.IGNORECASE
)

NON_US_INDICATORS = [
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "delhi",
    "noida", "gurugram", "gurgaon", "chennai", "kolkata", "ahmedabad",
    "united kingdom", " uk", "london", "germany", "berlin", "munich", "frankfurt", "potsdam",
    "france", "paris", "netherlands", "amsterdam", "spain", "barcelona", "madrid",
    "italy", "switzerland", "sweden", "poland", "ukraine", "singapore",
    "denmark", "copenhagen", "belgium", "brussels", "norway", "oslo", "finland", "helsinki",
    "austria", "vienna", "croatia", "zagreb", "serbia", "belgrade", "romania", "czech", "hungary",
    "indonesia", "jakarta", "pakistan", "nigeria", "kenya", "ghana", "south africa",
    "canada", "toronto", "vancouver", "montreal", "australia", "sydney", "melbourne",
    "brazil", "argentina", "colombia", "mexico", "chile",
    "israel", "tel aviv", "uae", "dubai", "ireland", "dublin", "philippines", "vietnam", "thailand"
]

TITLE_BLACKLIST = [
    "president", "engineer", "speaker", "advocate", "manager",
    "developer", "student", "founder", "ceo", "cto", "expert"
]

def is_verified_usa_location(raw_location: str) -> tuple:
    """
    Validates whether an extracted location string corresponds strictly to the United States.
    Returns: (is_usa: bool, reason: str)
    """
    if not raw_location or not isinstance(raw_location, str):
        return False, "Empty location string"
    
    loc = raw_location.strip()
    if len(loc) < 3 or len(loc) > 100:
        return False, f"Invalid length ({len(loc)})"
    
    loc_lower = loc.lower()
    
    # Check title blacklist (detects if a headline/job was scraped instead of location)
    for title in TITLE_BLACKLIST:
        if title in loc_lower:
            return False, f"Contains non-location title keyword: '{title}'"
            
    # Check explicit negative international locations
    for non_us in NON_US_INDICATORS:
        if non_us in loc_lower:
            return False, f"Matches non-US indicator: '{non_us}'"
            
    # Check USA indicators
    if "united states" in loc_lower or "usa" in loc_lower or "u.s.a." in loc_lower:
        return True, "Contains United States / USA"
        
    for metro in US_METROS:
        if metro in loc_lower:
            return True, f"Matches US metro: '{metro}'"
            
    for state in US_STATES:
        if re.search(r'\b' + re.escape(state) + r'\b', loc_lower):
            return True, f"Matches US state: '{state}'"
            
    if STATE_CODE_REGEX.search(loc):
        return True, "Matches US state 2-letter postal code"
        
    return False, "No verified US indicator matched"
