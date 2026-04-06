"""
從 Mattermost 抓取使用者，用 email 對應到 users.json，
將 Mattermost 的各種名稱 (username, nickname, first_name, last_name) 加入 users.json。
"""
import json
import sys
import os
from pathlib import Path

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import config

from mattermostautodriver import Driver


def fetch_mattermost_users():
    """從 Mattermost 抓取所有使用者"""
    print("🔍 連接 Mattermost...")
    
    driver = Driver({
        "url": config.MATTERMOST_URL,
        "token": config.MATTERMOST_TOKEN,
        "scheme": config.MATTERMOST_SCHEME,
        "port": config.MATTERMOST_PORT,
        "debug": False,
    })
    driver.login()
    
    print("📥 抓取 Mattermost 使用者...")
    all_users = []
    page = 0
    per_page = 200
    
    while True:
        batch = driver.users.get_users(params={"page": page, "per_page": per_page})
        if not batch:
            break
        all_users.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    
    print(f"   找到 {len(all_users)} 個 Mattermost 使用者")
    return all_users


def main():
    project_root = Path(__file__).parent.parent
    users_json_path = project_root / "users.json"
    
    # 1. 抓取 Mattermost 使用者
    mm_users = fetch_mattermost_users()
    
    # 2. 讀取 users.json
    print(f"📂 讀取 users.json...")
    with open(users_json_path, "r", encoding="utf-8") as f:
        users_data = json.load(f)
    print(f"   現有 {len(users_data)} 個帳號")
    
    # 3. 建立 email -> accountId 的快速查找表
    email_to_account = {}
    for account_id, nicks in users_data.items():
        for nick in nicks:
            if "@" in nick:
                email_to_account[nick.lower()] = account_id
    
    print(f"   建立 email 索引: {len(email_to_account)} 個 email")
    
    # 4. 匹配並更新
    matched = 0
    unmatched = []
    
    for mm_user in mm_users:
        if mm_user.get("is_bot"):
            continue
        
        mm_email = mm_user.get("email", "").lower()
        if not mm_email:
            continue
        
        # 在 users.json 中尋找對應的 accountId
        account_id = email_to_account.get(mm_email)
        
        if account_id:
            matched += 1
            existing_nicks = set(users_data[account_id])
            
            # 收集 Mattermost 的各種名稱
            mm_names = set()
            
            username = mm_user.get("username", "").strip()
            nickname = mm_user.get("nickname", "").strip()
            first_name = mm_user.get("first_name", "").strip()
            last_name = mm_user.get("last_name", "").strip()
            
            if username:
                mm_names.add(username)
            if nickname:
                mm_names.add(nickname)
            if first_name:
                mm_names.add(first_name)
            if last_name:
                mm_names.add(last_name)
            if first_name and last_name:
                mm_names.add(f"{first_name} {last_name}")
            
            # 加入到現有暱稱
            existing_nicks.update(mm_names)
            users_data[account_id] = list(existing_nicks)
        else:
            unmatched.append({
                "email": mm_email,
                "username": mm_user.get("username"),
                "name": f"{mm_user.get('first_name', '')} {mm_user.get('last_name', '')}".strip()
            })
    
    # 5. 寫回檔案
    with open(users_json_path, "w", encoding="utf-8") as f:
        json.dump(users_data, f, indent=4, ensure_ascii=False)
    
    print()
    print("=" * 50)
    print("✅ 更新完成!")
    print(f"   - 成功匹配並更新: {matched} 個使用者")
    print(f"   - 無法匹配 (MM 有但 Jira 沒有): {len(unmatched)} 個")
    print("=" * 50)
    
    # 顯示範例
    print("\n📋 更新範例 (前 3 個):")
    count = 0
    for account_id, nicks in users_data.items():
        if len(nicks) > 4:  # 顯示有較多暱稱的
            print(f"   {account_id[:20]}...:")
            for n in nicks[:6]:
                print(f"     - {n}")
            if len(nicks) > 6:
                print(f"     ... 還有 {len(nicks) - 6} 個")
            count += 1
            if count >= 3:
                break
    
    # 顯示未匹配的
    if unmatched:
        print(f"\n⚠️  未匹配的 Mattermost 使用者 (前 10 個):")
        for u in unmatched[:10]:
            print(f"   {u['email']} ({u['name']})")
        if len(unmatched) > 10:
            print(f"   ... 還有 {len(unmatched) - 10} 個")


if __name__ == "__main__":
    main()
