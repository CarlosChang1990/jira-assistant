import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.jira_service import JiraService
import config

def test_user_mapping():
    print("正在初始化 Jira Service...")
    jira = JiraService()
    
    # 測試對應表中的名字
    # 假設 .env 裡的 JIRA_EMAIL 是有效的
    test_names = ["me", "k2447", "unknown_user"] 
    
    for name in test_names:
        print(f"\n🔹 搜尋使用者: '{name}'")
        user = jira.find_user(name)
        if user:
            print(f"✅ 找到: {user.displayName} (AccountId: {user.accountId})")
        else:
            print(f"❌ 找不到使用者")

if __name__ == "__main__":
    test_user_mapping()
