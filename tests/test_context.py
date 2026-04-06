import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_context_retention():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # 模擬對話歷史
    history = [
        {"role": "user", "content": "排車表有 bug , 幫我開票"},
        {"role": "assistant", "content": "好的，請問這是屬於哪個業務單位 (BU) 的問題呢？"}
    ]
    
    current_msg = "短租"
    print(f"\n🔹 歷史: {history}")
    print(f"🔹 當前訊息: {current_msg}")
    
    # 期望: 因為歷史有問 BU，現在回答了 "短租"，
    # needs_clarification 應該判斷: BU 有了，但日期/系統還沒有 -> 回傳 True (但要問不同的問題)
    
    needs = llm.needs_clarification(current_msg, history=history)
    print(f"👉 需要澄清嗎? {needs}")
    
    if needs:
        q = llm.get_clarification_question(current_msg, history=history, known_prefixes=["WP", "CMS"])
        print(f"👉 後續反問: {q}")
        
    # Test Full Flow
    # 假設對話繼續
    history.append({"role": "user", "content": "短租"})
    assistant_reply = q if needs else "Done"
    history.append({"role": "assistant", "content": assistant_reply})
    
    current_msg_2 = "SR" # 使用者補上前綴
    print(f"\n🔹 第二輪輸入: {current_msg_2}")
    
    # 假設這時候 BU/System/Date 都有了? 
    # User said "Short Rental" (BU)
    # User said "SR" (Might be System Prefix? or BU abbreviation?)
    # "排車表有 bug" (Summary)
    # Date maybe missing?
    
    needs_2 = llm.needs_clarification(current_msg_2, history=history)
    print(f"👉 第二輪需澄清? {needs_2}")
    if needs_2:
         q2 = llm.get_clarification_question(current_msg_2, history=history, known_prefixes=["WP", "CMS", "SR"])
         print(f"👉 第二輪反問: {q2}")
    else:
         plan = llm.parse_intent(current_msg_2, history=history)
         print(f"✅ 解析成功: {plan}")

if __name__ == "__main__":
    test_context_retention()
