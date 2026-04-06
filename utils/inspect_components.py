from services.jira_service import JiraService
import config

def list_components():
    print("正在初始化 Jira Service...")
    jira = JiraService()
    
    if not jira.jira:
        print("❌ Jira 初始化失敗")
        return

    project_key = config.JIRA_PROJECT_KEY
    print(f"正在抓取專案 {project_key} 的 Components...")

    try:
        comps = jira.jira.project_components(project_key)
        print(f"找到 {len(comps)} 個 Components:")
        for c in comps:
            print(f"- {c.name}")
    except Exception as e:
        print(f"❌ 抓取失敗: {e}")

if __name__ == "__main__":
    list_components()
