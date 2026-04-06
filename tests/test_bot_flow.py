import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import MagicMock
from services.mattermost import MattermostBot
from services.llm_service import LLMService
from services.jira_service import JiraService
import config

def test_bot_flow():
    print("正在初始化 Bot (Mocking Mattermost Connection)...")
    
    # Mock JiraService to avoid creating real tickets during this test if possible,
    # OR use real JiraService but expect it to work.
    # Let's use real services for logic verification, but mock send_message
    
    bot = MattermostBot()
    bot.send_message = MagicMock() # Mock sending message
    
    # Test Case 1: Clarification needed (Missing Date/System)
    # 假設我們輸入一個有 BU 但沒日期的
    msg1 = "幫我開一張短租的票，排車表顯示異常，屬於短租 BU"
    print(f"\n🔹 測試 1: {msg1}")
    bot.handle_message(msg1, "channel_123")
    
    # 檢查是否呼叫了 send_message 並且內容包含反問 (檢查關鍵字)
    args, _ = bot.send_message.call_args
    reply = args[1]
    print(f"👉 Bot 回覆: {reply}")
    if "預計何時上版" in reply and "系統別" in reply:
        print("✅ 成功觸發反問機制 (Date & System)")
    else:
        print("❌ 反問機制失敗")

    # Test Case 2: Full Info (Trigger Hotfix Creation)
    # "WP" is a valid prefix found in previous step
    msg2 = "幫我開一張短租的票，排車表顯示異常，預計 2026/02/05 上版，系統是 WP"
    print(f"\n🔹 測試 2: {msg2}")
    
    # 我們不希望真的開票汙染專案太多，但為了測試...
    # 這裡會真的呼叫 jira.create_issue。
    # 如果要避免，可以 Mock jira_service.create_ticket
    
    # Mock create_ticket to just return a dummy object
    real_create_ticket = bot.jira_service.create_ticket
    bot.jira_service.create_ticket = MagicMock()
    bot.jira_service.create_ticket.return_value = MagicMock(key="TEST-123", link="http://fake")
    
    # But we want to test get_or_create_hotfix_version logic!
    # So we keep get_or_create_hotfix_version real.
    
    bot.handle_message(msg2, "channel_123")
    
    # Check if create_ticket was called with correct draft containing fix_version
    if bot.jira_service.create_ticket.called:
        call_args = bot.jira_service.create_ticket.call_args
        draft = call_args[0][0] # First arg is draft
        print(f"👉 Draft Summary: {draft.summary}")
        print(f"👉 Draft Fix Vers: {draft.fix_version}")
        
        if draft.fix_version and "WP" in draft.fix_version:
            print("✅ 成功計算並填入 Fix Version")
        else:
            print(f"❌ Fix Version 未填入或錯誤: {draft.fix_version}")
    else:
        print("❌ 未嘗試建立票券")

if __name__ == "__main__":
    test_bot_flow()
