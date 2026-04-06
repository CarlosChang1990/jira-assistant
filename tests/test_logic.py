import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService
import config

def test_logic():
    print("正在初始化 LLM Service...")
    llm = LLMService()
    
    if not llm.llm:
        print("❌ LLM 初始化失敗")
        return

    test_cases = [
        "幫我開一張短租的票，排車表顯示異常，需要後端處理",
        "APP 首頁字體太小，需要前端和UX調整",
        "機接的派單邏輯錯誤"
    ]

    print(f"開始測試 {len(test_cases)} 個案例...\n")

    for text in test_cases:
        print(f"🔹 輸入: {text}")
        plan = llm.parse_intent(text)
        if plan and plan.story:
            print(f"👉 [Story] Summary: {plan.story.summary}")
            print(f"   Components: {plan.story.components}")
            
            if plan.tasks:
                for t in plan.tasks:
                    print(f"   └─ [Task] Summary: {t.summary}")
                    print(f"      Components: {t.components}")
        else:
            print(f"❌ 解析失敗或格式錯誤: {plan}")
        print("-" * 30)

if __name__ == "__main__":
    test_logic()
