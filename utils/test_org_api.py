"""
測試 Atlassian Organization API 權限。
這個腳本會嘗試：
1. 用 Basic Auth 測試 Organization API（通常不行）
2. 顯示如何取得正確的認證方式
"""
import sys
import os
import requests
from base64 import b64encode

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import config

def test_basic_auth_org_api():
    """嘗試用 Basic Auth 呼叫 Organization API"""
    print("=" * 60)
    print("測試 Atlassian Organization API")
    print("=" * 60)
    
    # 1. 先印出目前的設定
    print(f"\n📋 目前設定:")
    print(f"   Server: {config.JIRA_SERVER}")
    print(f"   Email:  {config.JIRA_EMAIL}")
    print(f"   Token:  {'*' * 10}..." if config.JIRA_API_TOKEN else "   Token:  (未設定)")
    
    # 2. 測試一般 Jira API（確認 token 有效）
    print(f"\n🔍 測試 Jira REST API...")
    auth_string = f"{config.JIRA_EMAIL}:{config.JIRA_API_TOKEN}"
    auth_header = b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Accept": "application/json"
    }
    
    # Test /myself endpoint
    myself_url = f"{config.JIRA_SERVER}/rest/api/3/myself"
    resp = requests.get(myself_url, headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"   ✅ Token 有效！")
        print(f"   📧 你的 displayName: {data.get('displayName')}")
        print(f"   📧 你的 email: {data.get('emailAddress', '(隱藏)')}")
        print(f"   🔑 你的 accountId: {data.get('accountId')}")
    else:
        print(f"   ❌ API 呼叫失敗: {resp.status_code}")
        print(f"   {resp.text[:200]}")
        return
    
    # 3. 測試抓取其他使用者的 email
    print(f"\n🔍 測試抓取其他使用者（search_users）...")
    search_url = f"{config.JIRA_SERVER}/rest/api/3/user/search?query=."
    resp = requests.get(search_url, headers=headers)
    
    if resp.status_code == 200:
        users = resp.json()
        print(f"   找到 {len(users)} 個使用者")
        
        # 統計有多少人有 email
        with_email = 0
        without_email = 0
        for u in users[:10]:  # 只看前10個
            email = u.get('emailAddress')
            if email:
                with_email += 1
            else:
                without_email += 1
            print(f"   - {u.get('displayName', 'N/A')}: {email or '(無 email)'}")
        
        print(f"\n   📊 前 {min(10, len(users))} 人中:")
        print(f"      有 email: {with_email}")
        print(f"      無 email: {without_email}")
    
    # 4. 嘗試 Organization API（通常會失敗，因為需要 OAuth）
    print(f"\n🔍 嘗試 Organization API（預期會失敗）...")
    org_api_url = "https://api.atlassian.com/admin/v1/orgs"
    
    # 用 Bearer token 試試（不會成功，但可以看錯誤訊息）
    bearer_headers = {
        "Authorization": f"Bearer {config.JIRA_API_TOKEN}",
        "Accept": "application/json"
    }
    resp = requests.get(org_api_url, headers=bearer_headers)
    
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"   🎉 意外成功！你的 token 有 Organization 權限！")
        data = resp.json()
        for org in data.get('data', []):
            print(f"   📁 Org ID: {org.get('id')}")
            print(f"      Name: {org.get('name')}")
    elif resp.status_code == 401:
        print(f"   ❌ 認證失敗 (401)")
        print(f"   💡 Organization API 需要 OAuth 2.0 Token，不支援 API Token")
    elif resp.status_code == 403:
        print(f"   ❌ 權限不足 (403)")
        print(f"   💡 你可能不是 Organization Admin")
    else:
        print(f"   ❌ 錯誤: {resp.text[:200]}")
    
    # 5. 提供下一步建議
    print("\n" + "=" * 60)
    print("📝 結論與建議")
    print("=" * 60)
    print("""
Organization API 需要 OAuth 2.0 認證，無法使用 API Token。

🔹 如果你是 Organization Admin:
   1. 前往 https://developer.atlassian.com/console/myapps/
   2. 建立 OAuth 2.0 App
   3. 加入 scope: read:org.users
   4. 完成授權流程取得 Access Token

🔹 更簡單的替代方案:
   由於 Mattermost 可以取得使用者 email，而你可以用 email
   查詢 Jira 使用者（search_users API），只是結果可能不完整。
   
   建議: 建立一個 email -> accountId 的對應表，當新人加入時
   用腳本自動更新（或手動維護一次）。
""")

if __name__ == "__main__":
    test_basic_auth_org_api()
