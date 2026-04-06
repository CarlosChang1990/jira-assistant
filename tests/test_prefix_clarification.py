import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.jira_service import JiraService
from services.llm_service import LLMService
import config

def test_prefix_clarification():
    print("1. 測試抓取 Jira 系統前綴...")
    jira = JiraService()
    if not jira.jira:
        print("❌ Jira 初始化失敗")
        return

    prefixes = jira.get_project_prefixes(config.JIRA_PROJECT_KEY)
    print(f"✅ 抓取到的前綴: {prefixes}")
    
    print("\n2. 測試 LLM 生成反問句 (帶入前綴)...")
    llm = LLMService()
    
    # 模擬使用者只說了 BU，但沒說系統和日期
    user_input = "幫我開一張短租的票，排車表顯示異常，屬於短租 BU"
    
    question = llm.get_clarification_question(user_input, known_prefixes=prefixes)
    print(f"❓ LLM 反問:\n{question}")

if __name__ == "__main__":
    test_prefix_clarification()
