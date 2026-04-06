import google.generativeai as genai
import config
import os

def list_models():
    api_key = config.GOOGLE_API_KEY
    if not api_key:
        print("❌ GOOGLE_API_KEY not found in config")
        return

    genai.configure(api_key=api_key)
    
    print("正在查詢可用模型...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"❌ 查詢失敗: {e}")

if __name__ == "__main__":
    list_models()
