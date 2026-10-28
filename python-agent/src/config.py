import os
import sys
import json
import logging
from datetime import datetime

# ── Base Directory (points to python-agent root) ─────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Color Formatter for Interactive Terminal ─────────────────
class Style:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    RED     = "\033[31m"
    WHITE   = "\033[37m"

def log_agent_thought(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n{Style.DIM}[{timestamp}]{Style.RESET} {Style.CYAN}{Style.BOLD}🧠 [AGENT REASONING]{Style.RESET}\n{msg}")

def log_tool_call(tool_name, args):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Style.DIM}[{timestamp}]{Style.RESET} {Style.BLUE}{Style.BOLD}🛠️  [TOOL CALL: {tool_name}]{Style.RESET} {json.dumps(args, ensure_ascii=False)}")

def log_tool_result(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Style.DIM}[{timestamp}]{Style.RESET} {Style.MAGENTA}👁️  [OBSERVATION]{Style.RESET} {msg}")

def log_qualified(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Style.DIM}[{timestamp}]{Style.RESET} {Style.GREEN}{Style.BOLD}🏆 [QUALIFIED LEAD]{Style.RESET} {msg}")

def log_skipped(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"{Style.DIM}[{timestamp}]{Style.RESET} {Style.YELLOW}⚠️  [SKIPPED]{Style.RESET} {msg}")

# ── Load API Key ─────────────────────────────────────────────
def load_openai_key():
    for candidate in [os.path.join(BASE_DIR, ".env"), ".env"]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("gpt-apikey="):
                        return line.split("gpt-apikey=")[1].strip()
                    elif line.startswith("OPENAI_API_KEY="):
                        return line.split("OPENAI_API_KEY=")[1].strip()
                    elif line.startswith("sk-"):
                        return line
    return os.environ.get("OPENAI_API_KEY", "")

OPENAI_API_KEY = load_openai_key()

# ── Session Logging Setup ─────────────────────────────────────
def setup_file_logger():
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = os.path.join(log_dir, f"bde_pipeline_session_{timestamp}.log")
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_format)
    
    logger = logging.getLogger("BDE_Autonomous_Agent")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    return logger, log_file

