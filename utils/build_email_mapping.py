"""
建立 Mattermost Email → Jira AccountId 對應表。

這個腳本會：
1. 從 Mattermost 抓所有使用者和 email
2. 讀取現有的 users.json（有 accountId → displayName）
3. 嘗試自動比對（透過名稱相似度）
4. 產生報告供人工確認
5. 更新 users.json 加入 email

使用方式: python build_email_mapping.py
"""
import json
import os
import sys
from pathlib import Path
from difflib import SequenceMatcher

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import config

from mattermostautodriver import Driver


def similarity(a: str, b: str) -> float:
    """計算兩個字串的相似度 (0.0 ~ 1.0)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def fetch_mattermost_users():
    """從 Mattermost 抓取所有使用者"""
    print("🔍 連接 Mattermost...")
    
    driver = Driver({
        "url": config.MATTERMOST_URL,
        "token": config.MATTERMOST_TOKEN,
        "scheme": config.MATTERMOST_SCHEME,
        "port": config.MATTERMOST_PORT,
        "debug": False,
    })
    driver.login()
    
    print("📥 抓取 Mattermost 使用者...")
    all_users = []
    page = 0
    per_page = 200
    
    while True:
        batch = driver.users.get_users(params={"page": page, "per_page": per_page})
        if not batch:
            break
        all_users.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    
    print(f"   找到 {len(all_users)} 個 Mattermost 使用者")
    
    # 過濾掉 bot 和無 email 的
    real_users = []
    for u in all_users:
        if u.get("is_bot"):
            continue
        email = u.get("email", "")
        if not email:
            continue
        real_users.append({
            "mm_id": u.get("id"),
            "username": u.get("username"),
            "nickname": u.get("nickname", ""),
            "first_name": u.get("first_name", ""),
            "last_name": u.get("last_name", ""),
            "email": email,
        })
    
    print(f"   其中 {len(real_users)} 個有 email 的真人使用者")
    return real_users


def load_jira_users():
    """讀取現有的 users.json"""
    users_file = Path(__file__).parent.parent / "users.json"
    
    if not users_file.exists():
        print("❌ users.json 不存在！")
        return {}
    
    with open(users_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"📂 讀取 users.json: {len(data)} 個 Jira 帳號")
    return data


def match_users(mm_users: list, jira_users: dict):
    """
    嘗試自動比對 Mattermost 使用者和 Jira 使用者。
    
    Returns:
        matched: list of {"mm_user": {...}, "jira_id": "...", "jira_names": [...], "confidence": float}
        unmatched_mm: list of mm users without match
        unmatched_jira: list of (jira_id, names) without match
    """
    matched = []
    unmatched_mm = []
    matched_jira_ids = set()
    
    for mm in mm_users:
        email = mm["email"]
        email_prefix = email.split("@")[0].lower()
        mm_name = f"{mm['first_name']} {mm['last_name']}".strip().lower()
        mm_username = mm["username"].lower()
        
        best_match = None
        best_score = 0
        
        for jira_id, names in jira_users.items():
            # 檢查 email 是否已經在 names 裡
            names_lower = [n.lower() for n in names]
            
            if email.lower() in names_lower:
                best_match = (jira_id, names)
                best_score = 1.0
                break
            
            if email_prefix in names_lower:
                best_match = (jira_id, names)
                best_score = 0.95
                break
            
            # 比對名稱相似度
            for name in names:
                # 比對 Mattermost 全名
                if mm_name:
                    score = similarity(mm_name, name)
                    if score > best_score:
                        best_score = score
                        best_match = (jira_id, names)
                
                # 比對 username
                score = similarity(mm_username, name)
                if score > best_score:
                    best_score = score
                    best_match = (jira_id, names)
                
                # 比對 email prefix
                score = similarity(email_prefix, name)
                if score > best_score:
                    best_score = score
                    best_match = (jira_id, names)
        
        if best_match and best_score >= 0.6:  # 60% 相似度門檻
            matched.append({
                "mm_user": mm,
                "jira_id": best_match[0],
                "jira_names": best_match[1],
                "confidence": best_score,
            })
            matched_jira_ids.add(best_match[0])
        else:
            unmatched_mm.append(mm)
    
    # 找出未被 match 的 Jira 使用者
    unmatched_jira = [
        (jid, names) for jid, names in jira_users.items()
        if jid not in matched_jira_ids
    ]
    
    return matched, unmatched_mm, unmatched_jira


def generate_report(matched, unmatched_mm, unmatched_jira):
    """產生報告"""
    print("\n" + "=" * 70)
    print("📊 比對結果報告")
    print("=" * 70)
    
    # 高信心度 match
    high_conf = [m for m in matched if m["confidence"] >= 0.9]
    med_conf = [m for m in matched if 0.6 <= m["confidence"] < 0.9]
    
    print(f"\n✅ 高信心比對 (≥90%): {len(high_conf)} 筆")
    for m in high_conf[:10]:  # 只顯示前10筆
        mm = m["mm_user"]
        print(f"   {mm['email']} → {m['jira_names'][0]} ({m['confidence']:.0%})")
    if len(high_conf) > 10:
        print(f"   ... 和另外 {len(high_conf) - 10} 筆")
    
    print(f"\n⚠️  中等信心比對 (60-90%): {len(med_conf)} 筆 (需人工確認)")
    for m in med_conf:
        mm = m["mm_user"]
        print(f"   {mm['email']} → {m['jira_names'][0]} ({m['confidence']:.0%}) ❓")
    
    print(f"\n❌ 無法比對的 Mattermost 使用者: {len(unmatched_mm)} 筆")
    for mm in unmatched_mm[:10]:
        print(f"   {mm['email']} ({mm['first_name']} {mm['last_name']})")
    if len(unmatched_mm) > 10:
        print(f"   ... 和另外 {len(unmatched_mm) - 10} 筆")
    
    print(f"\n❌ 無法比對的 Jira 使用者: {len(unmatched_jira)} 筆")
    for jid, names in unmatched_jira[:10]:
        print(f"   {names[0] if names else jid}")
    if len(unmatched_jira) > 10:
        print(f"   ... 和另外 {len(unmatched_jira) - 10} 筆")
    
    return high_conf, med_conf


def update_users_json(matches_to_apply: list, jira_users: dict):
    """更新 users.json，加入 email"""
    users_file = Path(__file__).parent.parent / "users.json"
    
    for m in matches_to_apply:
        jira_id = m["jira_id"]
        email = m["mm_user"]["email"]
        
        if jira_id in jira_users:
            names = jira_users[jira_id]
            # 加入 email 和 email prefix
            if email not in names:
                names.append(email)
            prefix = email.split("@")[0]
            if prefix not in names:
                names.append(prefix)
    
    # 寫回檔案
    with open(users_file, "w", encoding="utf-8") as f:
        json.dump(jira_users, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ 已更新 users.json，加入 {len(matches_to_apply)} 筆 email 對應")


def main():
    print("=" * 70)
    print("🔄 Mattermost ↔ Jira 使用者對應工具")
    print("=" * 70)
    
    # 1. 抓取資料
    mm_users = fetch_mattermost_users()
    jira_users = load_jira_users()
    
    if not mm_users or not jira_users:
        print("❌ 無法取得使用者資料")
        return
    
    # 2. 比對
    matched, unmatched_mm, unmatched_jira = match_users(mm_users, jira_users)
    
    # 3. 產生報告
    high_conf, med_conf = generate_report(matched, unmatched_mm, unmatched_jira)
    
    # 4. 詢問是否要更新
    print("\n" + "=" * 70)
    if high_conf:
        print(f"🔧 準備自動套用 {len(high_conf)} 筆高信心比對到 users.json")
        confirm = input("   確認套用？ (y/n): ").strip().lower()
        
        if confirm == 'y':
            update_users_json(high_conf, jira_users)
        else:
            print("   已取消")
    else:
        print("沒有足夠信心的比對可以自動套用")
    
    # 5. 匯出未比對的供人工處理
    if unmatched_mm:
        output_file = Path(__file__).parent / "unmatched_mm_users.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(unmatched_mm, f, indent=2, ensure_ascii=False)
        print(f"\n📄 未比對的 Mattermost 使用者已匯出到: {output_file}")


if __name__ == "__main__":
    main()
