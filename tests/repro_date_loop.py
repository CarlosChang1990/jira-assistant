import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_date_loop():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # History: 
    # User: 短租系統有問題... (BU=短租)
    # Bot: Title?
    # User: 網頁跑版 (Title=OK)
    # Bot: Date?
    
    history = [
        {"role": "user", "content": "短租系統有問題，幫我開票"},
        {"role": "assistant", "content": "好的，請問這張票的標題或主要內容是什麼？"},
        {"role": "user", "content": "網頁跑版"},
        {"role": "assistant", "content": "好的，網頁跑版。請問預計什麼時候上版呢？"}
    ]
    
    current_msg = "今天要上。WP"
    print(f"\n🔹 歷史: {history}")
    print(f"🔹 當前訊息: {current_msg}")
    
    # Expectation: "今天要上" should be accepted as Date. "WP" as System.
    # needs_clarification should be FALSE (if all fields complete) or TRUE (if breakdown needed).
    # IF it returns TRUE, the question should be about Breakdown (Tasks), NOT Date.
    
    needs = llm.needs_clarification(current_msg, history=history)
    print(f"👉 需要澄清嗎? {needs}")
    
    if needs:
        q = llm.get_clarification_question(current_msg, history=history, known_prefixes=["WP"])
        print(f"👉 反問內容: {q}")
        
        if "時候" in q or "日期" in q:
            print("❌ 失敗: 機器人還在問日期。")
        else:
             print("✅ 成功: 機器人接受了日期。")
    else:
        # If it returns False, it means it thinks it has everything (or maybe defaulted to just story).
        # We need to ensure parsing works too.
        plan = llm.parse_intent(current_msg, history=history)
        print(f"Plan Date: {plan.story.expected_release_date}")
        if "今天" in str(plan.story.expected_release_date) or "Today" in str(plan.story.expected_release_date):
             print("✅ Parse Date Success (Relative)")
        else:
             print(f"⚠️ Parse Result: {plan.story.expected_release_date}")

if __name__ == "__main__":
    test_date_loop()
