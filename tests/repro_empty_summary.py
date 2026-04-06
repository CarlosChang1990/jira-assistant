import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_empty_summary():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # Case 1: Just "幫我開票"
    msg = "幫我開票"
    print(f"\n🔹 訊息: {msg}")
    
    needs = llm.needs_clarification(msg)
    print(f"👉 需要澄清嗎? {needs} (期望 True)")
    
    if needs:
        q = llm.get_clarification_question(msg)
        print(f"👉 反問內容: {q}")
    else:
        print("❌ 失敗: 機器人認為資訊充足，直接開票了。")
        plan = llm.parse_intent(msg)
        print(f"Plan Story Summary: {plan.story.summary}")

    # Case 2: "幫我開票，BU短租" (Still no summary description)
    msg2 = "幫我開票，BU短租"
    print(f"\n🔹 訊息: {msg2}")
    
    needs2 = llm.needs_clarification(msg2)
    print(f"👉 需要澄清嗎? {needs2} (期望 True)")
    if not needs2:
         plan = llm.parse_intent(msg2)
         print(f"Plan Story Summary: {plan.story.summary}")

    # Case 3: Full metadata but NO summary
    msg3 = "BU短租，日期2/5，系統WP，幫我開票"
    print(f"\n🔹 訊息: {msg3}")
    
    needs3 = llm.needs_clarification(msg3)
    print(f"👉 需要澄清嗎? {needs3} (期望 True，因為沒標題)")
    
    if needs3:
        q3 = llm.get_clarification_question(msg3, known_prefixes=["WP"])
        print(f"👉 反問內容: {q3}")
    else:
        print("❌ 失敗: 機器人認為資訊充足，直接開票了。")
        plan = llm.parse_intent(msg3)
        print(f"Plan Story Summary: '{plan.story.summary}'")

if __name__ == "__main__":
    test_empty_summary()
