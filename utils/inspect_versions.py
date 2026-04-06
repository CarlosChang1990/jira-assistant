import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.jira_service import JiraService
import config

def list_versions():
    print("正在初始化 Jira Service...")
    jira = JiraService()
    
    if not jira.jira:
        print("❌ Jira 初始化失敗")
        return

    project_key = config.JIRA_PROJECT_KEY
    print(f"正在抓取專案 {project_key} 的 Versions...\n")

    try:
        versions = jira.jira.project_versions(project_key)
        # 排序並顯示最近的 20 個版本
        # 假設版本有名稱，且可能未定發布日期
        sorted_versions = sorted(versions, key=lambda v: getattr(v, 'releaseDate', '0000-00-00'), reverse=True)
        
        print(f"找到 {len(versions)} 個版本。最近 20 筆：")
        for v in sorted_versions[:20]:
            r_date = getattr(v, 'releaseDate', 'No Date')
            print(f"- [{v.name}] (Release: {r_date}, ID: {v.id})")
            
    except Exception as e:
        print(f"❌ 抓取失敗: {e}")

if __name__ == "__main__":
    list_versions()
