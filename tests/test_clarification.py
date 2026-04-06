import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_clarification():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    test_cases = [
        "APP 首頁字體太小，需要前端和UX調整",  # 這裡只說 APP，沒說 BU -> 應需要澄清
        "幫我開一張短租的票，排車表顯示異常",       # 有 BU -> 不需要澄清
        "後端 API 回應過慢"                     # 沒說 BU -> 應需要澄清
    ]

    for text in test_cases:
        print(f"🔹 輸入: {text}")
        needs_clarification = llm.needs_clarification(text)
        print(f"👉 需要澄清嗎? {needs_clarification}")
        
        if needs_clarification:
             question = llm.get_clarification_question(text)
             print(f"   ❓ 反問: {question}")
        else:
             # 只有不需要澄清時才嘗試 Parse，看看是否真的有 BU
             plan = llm.parse_intent(text)
             if plan and plan.story:
                 print(f"   ✅ 解析成功 Story: {plan.story.summary}")
             else:
                 print(f"   ❌ 解析失敗")
        
        print("-" * 30)

if __name__ == "__main__":
    test_clarification()
