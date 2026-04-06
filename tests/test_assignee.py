import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_assignee_clarification():
    print("正在初始化 LLM Service...")
    
    # Mock prefix list string for prompt
    # In real flow this is passed, but for unit test of logic we can just test 'parse_intent' and 'needs_clarification'
    
    llm = LLMService()

    test_cases = [
        "幫我開一張短租的票，排車表異常，需要後端處理，預計 2026/02/05 上版，系統是 WP", # 缺 assignee
        "幫我開一張短租的票，排車表異常，需要後端處理 (由 David 負責)，預計 2026/02/05 上版，系統是 WP" # 有 assignee
    ]

    for text in test_cases:
        print(f"🔹 輸入: {text}")
        needs_clarification = llm.needs_clarification(text)
        print(f"👉 需要澄清嗎? {needs_clarification}")
        
        if needs_clarification:
             question = llm.get_clarification_question(text, known_prefixes=["WP"])
             print(f"   ❓ 反問: {question}")
        else:
             plan = llm.parse_intent(text)
             if plan:
                 print(f"   ✅ 解析成功")
                 if plan.story:
                    print(f"      Story Assignee: {plan.story.assignee} (預設 None, 稍後會轉為 me)")
                 for t in plan.tasks:
                    print(f"      Task [{t.summary}] Assignee: {t.assignee}")
             else:
                 print(f"   ❌ 解析失敗")
        
        print("-" * 30)

if __name__ == "__main__":
    test_assignee_clarification()
