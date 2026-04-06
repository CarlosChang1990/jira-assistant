import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_assignee_question():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # Complete request but missing Tasks
    # Summary: 排車表Bug
    # BU: 短租
    # Date: 2/5
    # System: WP
    msg = "幫我開一張短租票，標題是排車表Bug，預計2/5上版，系統WP"
    print(f"\n🔹 訊息: {msg}")
    
    needs = llm.needs_clarification(msg)
    print(f"👉 需要澄清嗎? {needs} (期望 True，因為沒提 Task)")
    
    if needs:
        q = llm.get_clarification_question(msg, known_prefixes=["WP"])
        print(f"👉 反問內容: {q}")
        # Expectation: Question should mention "Task" AND "Assignee" (responsible person)
        if "職能" in q and "負責人" in q:
            print("✅ 成功: 反問包含職能與負責人確認。")
        else:
            print("❌ 失敗: 反問未包含預期的合併問題。")
    else:
        print("❌ 失敗: 機器人認為資訊充足，直接開票了。")

if __name__ == "__main__":
    test_assignee_question()
