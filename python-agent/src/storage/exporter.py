import os
import csv
import json
from datetime import datetime
from src.config import BASE_DIR

class LiveLeadExporter:
    """
    Session-Isolated Single CSV/JSON Accumulator for BDE Leads.
    Maintains one fresh CSV and JSON file for the active session, ignoring prior sessions.
    Outputs comprehensive BDE outreach collateral ready for immediate sales execution.
    """
    def __init__(self, session_id=None):
        export_dir = os.path.join(BASE_DIR, "exports")
        os.makedirs(export_dir, exist_ok=True)
        if not session_id:
            session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.session_id = session_id
        
        # Dedicated single CSV and JSON for current session
        self.csv_path = os.path.join(export_dir, f"usa_genuine_sales_leads_{self.session_id}.csv")
        self.json_path = os.path.join(export_dir, f"usa_genuine_sales_leads_{self.session_id}.json")
        
        # Primary clean pointer to latest session leads
        self.current_csv_path = os.path.join(export_dir, "latest_usa_sales_leads.csv")
        self.current_json_path = os.path.join(export_dir, "latest_usa_sales_leads.json")
        # Backward-compatibility mirrors
        self.legacy_csv_path = os.path.join(export_dir, "current_session_leads.csv")
        self.legacy_json_path = os.path.join(export_dir, "current_session_leads.json")
        
        # Fresh start for this session
        self.leads = []
        
        # Comprehensive BDE Sales Lead Schema
        self.fieldnames = [
            "Lead ID",
            "Author Name",
            "First Name",
            "Title / Headline",
            "Company Name",
            "Verified Location",
            "Profile URL",
            "Post URL",
            "Post Age",
            "Fit Score",
            "Commercial Intent Category",
            "Identified Pain Point",
            "Target Tech Stack",
            "LinkedIn Connection Note (<300 chars)",
            "Full BDE InMail / Cold Pitch",
            "Buying Intent Signal",
            "Custom Outreach Hook",
            "Reasoning"
        ]
        
        # Initialize brand new CSV file for this session with header only
        for path in [self.csv_path, self.current_csv_path, self.legacy_csv_path]:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
            
        for path in [self.json_path, self.current_json_path, self.legacy_json_path]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

    def append_lead(self, lead_dict):
        prof = (lead_dict.get("Profile URL") or "").strip().lower()
        post = (lead_dict.get("Post URL") or "").strip().lower()
        auth = (lead_dict.get("Author Name") or "").strip().lower()
        
        # De-duplicate strictly within the current session's leads
        for existing in self.leads:
            ex_prof = (existing.get("Profile URL") or "").strip().lower()
            ex_post = (existing.get("Post URL") or "").strip().lower()
            ex_auth = (existing.get("Author Name") or "").strip().lower()
            
            if prof and ex_prof and prof == ex_prof:
                return False
            if post and ex_post and post == ex_post and "unknown" not in post:
                return False
            if auth and ex_auth and auth == ex_auth and auth != "unknown":
                return False

        # Assign Lead ID
        lead_dict["Lead ID"] = f"BDE-{len(self.leads) + 1:03d}"
        
        # Ensure backward compatibility aliases
        if "Buying Intent Signal" not in lead_dict:
            lead_dict["Buying Intent Signal"] = lead_dict.get("Commercial Intent Category", "Active technical need")
        if "Custom Outreach Hook" not in lead_dict:
            lead_dict["Custom Outreach Hook"] = lead_dict.get("LinkedIn Connection Note (<300 chars)", "")

        self.leads.append(lead_dict)
        
        # Save to all session pointers
        for path in [self.csv_path, self.current_csv_path, self.legacy_csv_path]:
            with open(path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames, extrasaction="ignore")
                writer.writerow(lead_dict)
                
        for path in [self.json_path, self.current_json_path, self.legacy_json_path]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.leads, f, indent=2, ensure_ascii=False)
                
        return True
