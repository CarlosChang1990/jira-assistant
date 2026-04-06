import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_summary_loop():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # History from screenshot
    # User: 短租後台系統前端有 bug，幫我開票
    # Bot: 好的，請問這張票的標題或主要內容是什麼？
    # User: 就前端有 bug
    # Bot: 請問這張票的標題或主要內容是什麼？
    
    history = [
        {"role": "user", "content": "短租後台系統前端有 bug，幫我開票"},
        {"role": "assistant", "content": "好的，請問這張票的標題或主要內容是什麼？"},
        {"role": "user", "content": "就前端有 bug"},
        {"role": "assistant", "content": "請問這張票的標題或主要內容是什麼？"}
    ]
    
    current_msg = "網頁跑版"
    print(f"\n🔹 歷史: {history}")
    print(f"🔹 當前訊息: {current_msg}")
    
    # Check needs_clarification
    # It SHOULD be True because BU/Date/System might be missing or incomplete, 
    # BUT the question generated should NOT be about Summary anymore.
    
    needs = llm.needs_clarification(current_msg, history=history)
    print(f"👉 需要澄清嗎? {needs}")
    
    if needs:
        q = llm.get_clarification_question(current_msg, history=history, known_prefixes=["WP"])
        print(f"👉 反問內容: {q}")
        
        # We expect the bot to accept "網頁跑版" as summary, and move on to ask about 
        # Date or System (since BU '短租' was in the first message).
        # Wait, the first message "短租後台系統..." contains BU "短租".
        # So BU is known.
        
        if "標題" in q or "主要內容" in q:
             print("❌ 失敗: 機器人還在問標題。")
        else:
             print("✅ 成功: 機器人不再問標題了。")

if __name__ == "__main__":
    test_summary_loop()
