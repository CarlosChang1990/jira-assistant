import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.jira_service import JiraService
import config

def test_unreleased_prefixes():
    print("正在初始化 Jira Service...")
    jira = JiraService()
    if not jira.jira:
        print("❌ Jira 初始化失敗")
        return

    print("抓取 Unreleased 前綴...")
    prefixes = jira.get_project_prefixes(config.JIRA_PROJECT_KEY)
    print(f"✅ 抓取到的前綴 (Unreleased Only): {prefixes}")
    
    # 簡單驗證：如果列表比之前小，或不包含已知的已發布舊系統，則成功
    # 之前是 50+ 個

if __name__ == "__main__":
    test_unreleased_prefixes()
