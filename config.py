import json
import os
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

# 強制讀取專案根目錄的 .env
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Jira 設定
JIRA_SERVER = os.getenv("JIRA_SERVER", "https://your-domain.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "KAN")
JIRA_BOARD_ID = os.getenv("JIRA_BOARD_ID", "")  # Board ID for Sprint fetching

# Mattermost 設定
MATTERMOST_URL = os.getenv("MATTERMOST_URL", "")
MATTERMOST_TOKEN = os.getenv("MATTERMOST_TOKEN", "")
MATTERMOST_SCHEME = os.getenv("MATTERMOST_SCHEME", "https")
MATTERMOST_PORT = int(os.getenv("MATTERMOST_PORT", 443))
MATTERMOST_TEAM = os.getenv("MATTERMOST_TEAM", "")

# Google Cloud Run 設定 (For Local Takeover)
CLOUD_RUN_SERVICE_NAME = os.getenv("CLOUD_RUN_SERVICE_NAME", "")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "")

# Google AI 設定
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# 機器人設定
BOT_NAME = os.getenv("BOT_NAME", "JiraBot")

# 人員對應表 (Nickname -> Jira Account ID or Email)
# users.json format: { "accountId": ["nickname1", "nickname2"] }
# users.json format: { "accountId": ["nickname1", "nickname2"] }

USER_NICKNAME_INDEX = defaultdict(set)  # nickname (lower) -> set of accountIds (use set to avoid duplicates)
users_file = Path(__file__).parent / "users.json"

if users_file.exists():
    try:
        with open(users_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            # raw_data: { accountId: [nicks...] }

            for account_id, nicknames in raw_data.items():
                for nick in nicknames:
                    USER_NICKNAME_INDEX[nick.lower()].add(account_id)  # use add() for set

    except Exception as e:
        print(f"Warning: Failed to load users.json: {e}")


# Helper to look up account IDs by nickname (exact match only)
def get_account_ids_by_nickname(nickname: str):
    return list(USER_NICKNAME_INDEX.get(nickname.lower(), set()))


def search_account_ids_by_nickname(query: str) -> dict:
    """
    Search for account IDs by nickname with fuzzy matching (Solution E).
    
    Priority:
    1. Exact match (query == nickname)
    2. Fuzzy match (query is substring of nickname, or nickname is substring of query)
    
    Returns:
        dict: {
            'exact': set of account_ids,      # Exact matches
            'fuzzy': set of account_ids,      # Substring matches (excluding exact)
        }
    """
    query_lower = query.lower().strip()
    exact_matches = set()
    fuzzy_matches = set()
    
    for nickname, account_ids in USER_NICKNAME_INDEX.items():
        nickname_lower = nickname.lower()
        
        # Exact match
        if query_lower == nickname_lower:
            exact_matches.update(account_ids)
        # Fuzzy match: query is substring of nickname OR nickname is substring of query
        elif query_lower in nickname_lower or nickname_lower in query_lower:
            fuzzy_matches.update(account_ids)
    
    # Remove exact matches from fuzzy to avoid duplicates
    fuzzy_matches -= exact_matches
    
    return {
        'exact': exact_matches,
        'fuzzy': fuzzy_matches,
    }


# Helper for "me"
def get_my_account_id():
    ids = get_account_ids_by_nickname("me")
    if ids:
        return ids[0]
    return None


# Backward compatibility for code accessing USER_MAPPING directly (if any)
# We can expose a simple mapping for "me" or single-match cases if needed, but safer to use functions.
USER_MAPPING = {}
if get_my_account_id():
    USER_MAPPING["me"] = get_my_account_id()
elif JIRA_EMAIL:
    USER_MAPPING["me"] = JIRA_EMAIL
