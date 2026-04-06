import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.llm_service import LLMService

def test_task_breakdown():
    print("正在初始化 LLM Service...")
    llm = LLMService()

    # Case 1: Vague request -> Expect Clarification (Task Breakdown)
    msg1 = "幫我開一張短租的票，排車表顯示異常，屬於短租 BU，系統 WP，預計 2026/02/05 上版"
    print(f"\n🔹 測試 1 (模糊): {msg1}")
    needs_clari = llm.needs_clarification(msg1)
    print(f"👉 需要澄清嗎? {needs_clari} (期望 True，因未指定職能)")
    if needs_clari:
        q = llm.get_clarification_question(msg1)
        print(f"👉 反問: {q}")

    # Case 2: Specific Quantity -> Expect Parsing
    msg2 = "幫我開一張短租的票，排車表顯示異常，BU短租，系統 WP，預計 2026/02/05 上版。我需要一張後端 (by John) 和兩張前端 (by Allen, Grey)"
    print(f"\n🔹 測試 2 (明確數量): {msg2}")
    needs_clari2 = llm.needs_clarification(msg2)
    print(f"👉 需要澄清嗎? {needs_clari2} (期望 False)")
    
    if not needs_clari2:
        plan = llm.parse_intent(msg2)
        print("✅ 解析結果:")
        print(f"Story: {plan.story.summary}")
        for t in plan.tasks:
            print(f"Task: {t.summary} | Assignee: {t.assignee} | Component: {t.components}")

if __name__ == "__main__":
    test_task_breakdown()
