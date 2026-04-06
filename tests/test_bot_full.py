import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import MagicMock
from services.mattermost import MattermostBot
import config

def test_bot_full():
    print("正在初始化 Bot (Mocking Mattermost Connection)...")
    
    bot = MattermostBot()
    bot.send_message = MagicMock() 
    
    # CASE 1: 缺少 Task Assignee -> Expect Clarification
    msg1 = "幫我開一張短租的票，排車表異常，需要後端處理，預計 2026/02/05 上版，系統是 WP"
    print(f"\n🔹 測試 1 (缺人): {msg1}")
    bot.handle_message(msg1, "channel_123")
    
    args, _ = bot.send_message.call_args
    reply1 = args[1]
    print(f"👉 Bot 回覆: {reply1}")
    if "哪位同事負責" in reply1:
        print("✅ 成功反問 Assignee")
    else:
        print("❌ 反問失敗")

    # CASE 2: 完整資訊 (含人名) -> Expect Creation
    # David -> 需要先確認 config.USER_MAPPING 有 David，或 Mock find_user
    # 我們 Mock find_user 讓它永遠找到一個假人
    bot.jira_service.find_user = MagicMock(return_value=MagicMock(accountId="acc_david", displayName="David User"))
    bot.jira_service.create_ticket = MagicMock(return_value=MagicMock(key="TEST-1", link="http://link", summary="Summary"))
    bot.jira_service.link_tickets = MagicMock()
    
    msg2 = "幫我開一張短租的票，排車表異常，需要後端處理 (由 David 負責)，預計 2026/02/05 上版，系統是 WP"
    print(f"\n🔹 測試 2 (完整): {msg2}")
    
    # Mock hotfix logic too
    bot.jira_service.get_or_create_hotfix_version = MagicMock(return_value=MagicMock(name="WP2.99.1(260205)"))
    
    bot.handle_message(msg2, "channel_123")
    
    # Check Story assignee
    if bot.jira_service.create_ticket.called:
        calls = bot.jira_service.create_ticket.call_args_list
        story_call = calls[0]
        story_draft = story_call[0][0]
        print(f"👉 Story Assignee: {story_draft.assignee}")
        
        if story_draft.assignee == "me":
            print("✅ Story 自動指派給 me")
        else:
            print(f"❌ Story 指派錯誤: {story_draft.assignee}")
            
        # Check Task assignee
        if len(calls) > 1:
            task_call = calls[1] # Task creation
            task_draft = task_call[0][0]
            print(f"👉 Task Assignee: {task_draft.assignee}")
            if "David" in task_draft.assignee:
                print("✅ Task 指派給 David")
            else:
                 print(f"❌ Task 指派錯誤: {task_draft.assignee}")

if __name__ == "__main__":
    test_bot_full()
