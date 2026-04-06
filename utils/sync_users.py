import json
import os
import sys
from pathlib import Path

# Add parent dir to path to import services
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from services.jira_service import JiraService
import config

def sync_users():
    # users.json is in the project root (one level up from utils)
    users_file = Path(__file__).parent.parent / "users.json"
    
    # 1. Load existing users
    existing_data = {}
    if users_file.exists():
        with open(users_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    
    print(f"Loaded {len(existing_data)} existing accounts.")
    
    # 2. Fetch all users from Jira
    service = JiraService()
    if not service.jira:
        print("Error: Jira client not initialized.")
        return

    print("Fetching users from Jira...")
    all_jira_users = []
    start_at = 0
    max_results = 50
    
    while True:
        # Search for all users
        batch = service.jira.search_users(query='.', startAt=start_at, maxResults=max_results)
        if not batch:
            # Try empty query if '.' fails (some servers differ)
            if start_at == 0:
                 batch = service.jira.search_users(query='', startAt=start_at, maxResults=max_results)
            if not batch:
                break
        
        all_jira_users.extend(batch)
        print(f"  Fetched batch {start_at} - {start_at + len(batch)}...")
        if len(batch) < max_results:
            break
        start_at += len(batch)

    print(f"Total Jira users found: {len(all_jira_users)}")
    
    # 3. Merge data
    updated_count = 0
    new_count = 0
    valid_ids = set()
    bot_ids = set()

    # Identify valid and invalid IDs from fetch result
    for u in all_jira_users:
        is_active = u.active
        account_type = getattr(u, 'accountType', 'atlassian')
        
        if is_active and account_type == 'atlassian':
            valid_ids.add(u.accountId)
        else:
            bot_ids.add(u.accountId)

    # Process valid users to add/update
    for u in all_jira_users:
        if u.accountId not in valid_ids:
            continue
            
        account_id = u.accountId
        display_name = u.displayName
        email = getattr(u, 'emailAddress', '')
        
        # Generate candidate nicknames
        new_nicks = set()
        if display_name:
            new_nicks.add(display_name)
            parts = display_name.split()
            if len(parts) > 1:
                new_nicks.add(parts[0]) 
        
        if email:
            new_nicks.add(email)
            new_nicks.add(email.split('@')[0])
        
        # Merge
        if account_id in existing_data:
            current_nicks = set(existing_data[account_id])
            original_len = len(current_nicks)
            current_nicks.update(new_nicks)
            if len(current_nicks) > original_len:
                updated_count += 1
                existing_data[account_id] = list(current_nicks)
        else:
            new_count += 1
            existing_data[account_id] = list(new_nicks)

    # 4. Cleanup (Prune bots)
    removed_count = 0
    for bot_id in bot_ids:
        if bot_id in existing_data:
            del existing_data[bot_id]
            removed_count += 1

    # 5. Write back
    print(f"Summary: {new_count} new accounts added, {updated_count} existing accounts updated.")
    print(f"Removed {removed_count} bot/inactive accounts.")
    
    with open(users_file, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=4, ensure_ascii=False)
    
    print("Done. users.json updated.")

if __name__ == "__main__":
    sync_users()
