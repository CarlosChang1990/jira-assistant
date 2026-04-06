import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.jira_service import JiraService
from models.ticket import TicketDraft
import config

def test_create_ticket():
    print("正在初始化 Jira Service...")
    jira = JiraService()
    
    if not jira.jira:
        print("❌ Jira 初始化失敗，請檢查 .env 設定 (SERVER, EMAIL, API_TOKEN)")
        return

    print("設定測試票券資料...")
    draft = TicketDraft(
        summary="小幫手 hello world",
        description="這是由自動化腳本建立的測試票券，用於驗證系統連線與開票功能。",
        issuetype="Task"
    )
    
    project_key = "CYB"
    print(f"準備在專案 {project_key} 建立票券: {draft.summary}")

    # 自動抓取 Components 以通過必填檢查
    try:
        comps = jira.jira.project_components(project_key)
        if comps:
            first_comp = comps[0].name
            print(f"專案需要 Component，自動選擇第一個可用元件: {first_comp}")
            draft.components = [first_comp]
        else:
            print("⚠️ 警告: 專案沒有元件，但 creation 可能需要它。")
    except Exception as e:
        print(f"無法抓取元件列表: {e}")

    try:
        ticket = jira.create_ticket(draft, project_key)
        print(f"✅ 成功建立票券！")
        print(f"Key: {ticket.key}")
        print(f"Link: {ticket.link}")
    except Exception as e:
        print(f"❌ 建立票券失敗: {e}")

if __name__ == "__main__":
    test_create_ticket()
