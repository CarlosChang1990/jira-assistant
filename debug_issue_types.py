# Debug script to list valid issue types for the project
import os
import config
from services.jira_service import JiraService

def list_project_issue_types():
    print(f"Connecting to Jira project: {config.JIRA_PROJECT_KEY}")
    try:
        service = JiraService()
        if not service.jira:
            print("Failed to initialize Jira client. Check .env")
            return

        # Get project meta data to find creatable issue types
        # /rest/api/2/issue/createmeta?projectKeys=...&expand=projects.issuetypes
        meta = service.jira.createmeta(projectKeys=config.JIRA_PROJECT_KEY, expand='projects.issuetypes')
        
        if not meta or 'projects' not in meta or not meta['projects']:
            print(f"No metadata found for project {config.JIRA_PROJECT_KEY}")
            return

        project = meta['projects'][0]
        print(f"Project: {project['name']} ({project['key']})")
        print("Available Issue Types:")
        for itype in project['issuetypes']:
            print(f" - Name: '{itype['name']}', ID: {itype['id']}, Subtask: {itype['subtask']}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_project_issue_types()
