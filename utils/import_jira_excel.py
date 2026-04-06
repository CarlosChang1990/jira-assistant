"""
從 Admin 匯出的 jira_user_list.xlsx 更新 users.json。

將每個使用者的 email 和 email prefix 加入到對應的 accountId。
"""
import json
import pandas as pd
from pathlib import Path


def main():
    # 路徑
    project_root = Path(__file__).parent.parent
    excel_path = project_root / "jira_user_list.xlsx"
    users_json_path = project_root / "users.json"
    
    # 1. 讀取 Excel
    print(f"📂 讀取 Excel: {excel_path}")
    df = pd.read_excel(excel_path)
    print(f"   找到 {len(df)} 筆 Jira 使用者")
    
    # 2. 讀取現有的 users.json
    print(f"📂 讀取 users.json: {users_json_path}")
    if users_json_path.exists():
        with open(users_json_path, "r", encoding="utf-8") as f:
            users_data = json.load(f)
        print(f"   現有 {len(users_data)} 個帳號")
    else:
        users_data = {}
        print("   (檔案不存在，將建立新檔案)")
    
    # 3. 更新資料
    added_emails = 0
    new_accounts = 0
    
    for _, row in df.iterrows():
        account_id = str(row["User id"]).strip()
        display_name = str(row["User name"]).strip() if pd.notna(row["User name"]) else ""
        email = str(row["email"]).strip() if pd.notna(row["email"]) else ""
        
        if not account_id or account_id == "nan":
            continue
        
        # 準備要加入的暱稱
        new_nicks = set()
        if display_name and display_name != "nan":
            new_nicks.add(display_name)
        if email and email != "nan":
            new_nicks.add(email)
            # 也加入 email prefix
            prefix = email.split("@")[0]
            if prefix:
                new_nicks.add(prefix)
        
        if account_id in users_data:
            # 合併現有的暱稱
            existing_nicks = set(users_data[account_id])
            before_count = len(existing_nicks)
            existing_nicks.update(new_nicks)
            
            if len(existing_nicks) > before_count:
                added_emails += 1
            
            users_data[account_id] = list(existing_nicks)
        else:
            # 新帳號
            new_accounts += 1
            users_data[account_id] = list(new_nicks)
    
    # 4. 寫回檔案
    with open(users_json_path, "w", encoding="utf-8") as f:
        json.dump(users_data, f, indent=4, ensure_ascii=False)
    
    print()
    print("=" * 50)
    print("✅ 更新完成!")
    print(f"   - 新增 email 到現有帳號: {added_emails} 個")
    print(f"   - 新建帳號: {new_accounts} 個")
    print(f"   - 總帳號數: {len(users_data)} 個")
    print("=" * 50)
    
    # 5. 顯示幾個範例
    print("\n📋 範例更新 (前 5 個):")
    count = 0
    for acc_id, nicks in users_data.items():
        emails_in_nicks = [n for n in nicks if "@" in n]
        if emails_in_nicks:
            print(f"   {nicks[0]}: {emails_in_nicks[0]}")
            count += 1
            if count >= 5:
                break


if __name__ == "__main__":
    main()
