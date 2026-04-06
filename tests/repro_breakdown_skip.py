import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_breakdown_skip():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # 模擬對話歷史: 已經問了 BU 和 日期/系統
    history = [
        {"role": "user", "content": "排車表有 bug , 幫我開票"},
        {"role": "assistant", "content": "好的，請問這是屬於哪個業務單位 (BU) 的問題呢？"},
        {"role": "user", "content": "短租"},
        {"role": "assistant", "content": "好的，請問預計上版日期與系統別？"}
    ]
    
    # 用戶回答了日期和系統，但完全沒提 Task
    current_msg = "WP, 今天要上"
    
    print(f"\n🔹 歷史: {history}")
    print(f"🔹 當前訊息: {current_msg}")
    
    # 期望: 即使 BU/Date/System 都有了，但因為沒說要不要 Task，應該還是要 needs_clarification = True
    needs = llm.needs_clarification(current_msg, history=history)
    print(f"👉 需要澄清嗎? {needs} (期望 True)")
    
    if needs:
        q = llm.get_clarification_question(current_msg, history=history, known_prefixes=["WP"])
        print(f"👉 反問內容: {q}")
    else:
        print("❌ 失敗: 機器人認為資訊充足，直接開票了。")
        plan = llm.parse_intent(current_msg, history=history)
        print(f"Plan Story: {plan.story}")
        print(f"Plan Tasks: {plan.tasks}")

if __name__ == "__main__":
    test_breakdown_skip()
