#!/usr/bin/env python3
"""
Jira Release Version Utility

自動發布已到期但尚未發布的 Jira 版本：
1. 掃描專案中所有「未發布」且「日期已過」的版本
2. 將版本中「未完成」的票券移除該版本號
3. 發布該版本

Usage:
    # Dry run (只看不做)
    python3 release_versions.py --dry-run

    # 真正執行
    python3 release_versions.py
"""

import argparse
import logging
from datetime import date, datetime

from jira import JIRA

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_jira_client() -> JIRA:
    """Initialize and return Jira client."""
    if not config.JIRA_SERVER or not config.JIRA_API_TOKEN:
        raise RuntimeError("Missing JIRA_SERVER or JIRA_API_TOKEN in config/.env")
    return JIRA(server=config.JIRA_SERVER, basic_auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN))


def get_overdue_unreleased_versions(jira: JIRA, project_key: str) -> list:
    """
    Get all versions that are:
    - Not released
    - Have a release date in the past
    """
    today = date.today()
    all_versions = jira.project_versions(project_key)
    
    overdue = []
    for v in all_versions:
        if not v.released and hasattr(v, 'releaseDate') and v.releaseDate:
            release_date = datetime.strptime(v.releaseDate, "%Y-%m-%d").date()
            if release_date < today:
                overdue.append({
                    "id": v.id,
                    "name": v.name,
                    "releaseDate": v.releaseDate,
                    "version_obj": v
                })
    
    return overdue


def get_unfinished_issues_in_version(jira: JIRA, project_key: str, version_id: str) -> list:
    """
    Find all issues in this version that are NOT done.
    Uses REST API v3 directly since jira library uses deprecated v2 API.
    """
    import requests
    
    jql = f'project = "{project_key}" AND fixVersion = "{version_id}" AND statusCategory != Done'
    url = f"{config.JIRA_SERVER}/rest/api/3/search/jql"
    
    response = requests.get(
        url,
        params={"jql": jql, "fields": "key,summary,status", "maxResults": 500},
        auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN),
        headers={"Accept": "application/json"}
    )
    
    if response.status_code != 200:
        logger.warning(f"Search failed for version {version_id}: {response.status_code}")
        return []
    
    data = response.json()
    return data.get("issues", [])



def release_version(jira: JIRA, version_id: str, version_name: str, release_date: str, dry_run: bool = True):
    """
    Mark a version as released.
    """
    if dry_run:
        logger.info(f"   [DRY RUN] Would release version: {version_name}")
        return
    
    version = jira.version(version_id)
    version.update(released=True, releaseDate=release_date)
    logger.info(f"   🚀 Released version: {version_name}")


def release_overdue_versions(project_key: str, dry_run: bool = True):
    """
    Main function to process and release overdue versions.
    """
    jira = get_jira_client()
    
    mode = "DRY RUN" if dry_run else "LIVE"
    logger.info(f"=== Jira Release Version Utility ({mode}) ===")
    logger.info(f"Project: {project_key}")
    logger.info("")
    
    # Get overdue versions
    overdue_versions = get_overdue_unreleased_versions(jira, project_key)
    
    if not overdue_versions:
        logger.info("✅ No overdue unreleased versions found.")
        return
    
    logger.info(f"Found {len(overdue_versions)} overdue version(s):\n")
    
    for v in overdue_versions:
        logger.info(f"🔍 Processing: {v['name']} (due: {v['releaseDate']})")
        
        # Find unfinished issues
        unfinished = get_unfinished_issues_in_version(jira, project_key, v['id'])
        
        if unfinished:
            # Has unfinished tickets - SKIP this version
            logger.info(f"   ⏭️ SKIP: Found {len(unfinished)} unfinished issue(s)")
            for issue in unfinished:
                issue_key = issue.get("key", "?")
                summary = issue.get("fields", {}).get("summary", "No summary")
                status = issue.get("fields", {}).get("status", {}).get("name", "?")
                logger.info(f"      - {issue_key}: {summary} [{status}]")
            logger.info(f"   ❌ Version NOT released (has unfinished tickets)")
        else:
            # All tickets are done - can release
            logger.info(f"   ✅ All issues in this version are done.")
            release_version(jira, v['id'], v['name'], v['releaseDate'], dry_run)
        
        logger.info("")
    
    logger.info("=== Done ===")
    if dry_run:
        logger.info("This was a dry run. To actually release, run without --dry-run flag.")


def main():
    parser = argparse.ArgumentParser(description="Auto-release overdue Jira versions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be done, don't actually make changes"
    )
    parser.add_argument(
        "--project",
        default=config.JIRA_PROJECT_KEY,
        help=f"Jira project key (default: {config.JIRA_PROJECT_KEY})"
    )
    args = parser.parse_args()
    
    release_overdue_versions(args.project, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
