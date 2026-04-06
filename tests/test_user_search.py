import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.jira_service import JiraService
import config

def test_user_search():
    print("正在初始化 Jira Service...")
    jira = JiraService()
    
    # 測試幾個常見的名字，看回傳結果
    test_names = ["k2447", "admin", "test"] 
    # 注意: 若 user 本身知道一些真實存在的員工名字，可以手動替換測試
    
    for name in test_names:
        print(f"\n🔹 搜尋使用者: '{name}'")
        try:
            user = jira.find_user(name)
            if user:
                print(f"✅ 找到: {user.displayName} (AccountId: {user.accountId})")
            else:
                print(f"❌ 找不到使用者")
        except Exception as e:
            print(f"❌ 搜尋錯誤: {e}")

if __name__ == "__main__":
    test_user_search()
