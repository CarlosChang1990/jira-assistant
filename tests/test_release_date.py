import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_release_date():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # 必須指定 BU 才會進展到問日期
    test_cases = [
        "幫我開一張短租的票，排車表顯示異常 (未指定日期)",
        "幫我開一張短租的票，排車表顯示異常，預計 2026/02/04 上版" 
    ]

    for text in test_cases:
        print(f"🔹 輸入: {text}")
        needs_clarification = llm.needs_clarification(text)
        print(f"👉 需要澄清嗎? {needs_clarification}")
        
        if needs_clarification:
             question = llm.get_clarification_question(text)
             print(f"   ❓ 反問: {question}")
        else:
             plan = llm.parse_intent(text)
             if plan and plan.story:
                 print(f"   ✅ 解析成功 Story: {plan.story.summary}")
                 print(f"   📅 Expected Release Date: {plan.story.expected_release_date}")
             else:
                 print(f"   ❌ 解析失敗")
        
        print("-" * 30)

if __name__ == "__main__":
    test_release_date()
