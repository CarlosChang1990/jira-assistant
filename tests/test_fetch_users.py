import sys
import os
# Add parent directory to path to find services
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from services.jira_service import JiraService
import config

# Mock/Patch config if needed, or rely on .env being loaded by config import
# config.py loads .env automatically at module level.

def test_fetch_users():
    print("Initializing Jira Service...")
    # Initialize implementation directly
    service = JiraService()
    
    if not service.jira:
        print("Failed to initialize Jira client. Check config.")
        return

    print("Attempting to search all users...")
    try:
        # Generic query to find users. '.' is a common wildcard in Jira.
        # Alternatively query='' might work but usually requires at least one char.
        # Some setups accept '%'.
        # Let's try '.'
        users = service.jira.search_users(query='.', maxResults=50)
        
        if not users:
             print("Query '.' returned no results. Trying empty string ''...")
             users = service.jira.search_users(query='', maxResults=50)

        print(f"Found {len(users)} users.")
        for u in users:
            # Handle potential missing attributes
            email = getattr(u, 'emailAddress', 'No Email')
            display_name = u.displayName
            account_id = u.accountId
            print(f"User: {display_name} | Email: {email} | AccountId: {account_id}")

    except Exception as e:
        print(f"Error fetching users: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fetch_users()
