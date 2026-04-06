import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.jira_service import JiraService
import config

def test_hotfix():
    print("正在初始化 Jira Service (Dry Run 模擬)...")
    jira = JiraService()
    
    # 使用者案例
    # WP2.97.4(260102) -> 假設這是最新的
    # 新日期 2026-02-04
    # 預期: WP2.97.5(260204)
    
    prefix = "WP"
    date = "2026-02-05" # 260205 should be new
    
    print(f"測試請求: System={prefix}, Date={date}")
    
    try:
        # 由於這會真的建立版本，我們可能需要小心。
        # 但為了驗證邏輯，我們可以在 JiraService 加個 debug flag 或直接跑
        # 這裡直接跑，因為是測試專案
        version = jira.get_or_create_hotfix_version(config.JIRA_PROJECT_KEY, prefix, date)
        if version:
            print(f"✅ 結果版本: {version.name} (ID: {version.id})")
        else:
            print("❌ 失敗")

    except Exception as e:
        print(f"❌ 錯誤: {e}")

if __name__ == "__main__":
    test_hotfix()
