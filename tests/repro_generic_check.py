import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_generic_summary_and_missing_fields():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # Case 1: "System has bug" (Generic) + Missing Date/System
    # User input: "短租系統有bug，幫我開一張前端票給jenny"
    # Should be Unclear because:
    # 1. "短租系統有bug" is too generic (User wants this rejected)
    # 2. Missing Release Date
    # 3. Missing System Prefix (maybe "短租系統" implies SR, but date is definitely missing)
    
    msg1 = "短租系統有bug，幫我開一張前端票給jenny"
    print(f"\n🔹 訊息 1: {msg1}")
    
    needs1 = llm.needs_clarification(msg1)
    print(f"👉 需要澄清嗎? {needs1} (期望 True)")
    
    if needs1:
        q1 = llm.get_clarification_question(msg1)
        print(f"👉 反問內容: {q1}")
        # Expect question about Summary OR Date/System
    else:
        print("❌ 失敗: 機器人認為資訊充足，直接開票了 (漏問日期/系統，或接受了模糊標題)。")
        plan = llm.parse_intent(msg1)
        print(f"Plan: {plan}")

    # Case 2: Specific Summary + Missing Date
    # User input: "短租系統網頁跑版，幫我開一張前端票給jenny"
    # Should be Unclear because Missing Date
    msg2 = "短租系統網頁跑版，幫我開一張前端票給jenny"
    print(f"\n🔹 訊息 2: {msg2}")
    
    needs2 = llm.needs_clarification(msg2)
    print(f"👉 需要澄清嗎? {needs2} (期望 True - 因缺日期)")


if __name__ == "__main__":
    test_generic_summary_and_missing_fields()
