import logging
import re
from datetime import datetime
from typing import List, Optional

from jira import JIRA

import config
from models.ticket import TicketCreated, TicketDraft

logger = logging.getLogger(__name__)


class AmbiguousUserError(Exception):
    """當使用者暱稱對應到多個 Jira 帳號時拋出。"""
    def __init__(self, query: str, candidates: list):
        """
        Args:
            query: 原始查詢的暱稱
            candidates: list of dict, 每個 dict 包含 account_id, display_name, email
        """
        self.query = query
        self.candidates = candidates
        super().__init__(f"Ambiguous user nickname '{query}'")
    
    def format_options(self) -> str:
        """格式化候選人清單供使用者選擇"""
        lines = [f"找到多個 '{self.query}'，請指定是哪一位："]
        for i, c in enumerate(self.candidates, 1):
            email = c.get('email', 'N/A')
            name = c.get('display_name', 'Unknown')
            lines.append(f"  {i}. {name} ({email})")
        return "\n".join(lines)


class AmbiguousComponentError(Exception):
    """當 Component 名稱不明確或找不到時拋出。"""
    def __init__(self, query: str, candidates: list):
        self.query = query
        self.candidates = candidates
        super().__init__(f"Ambiguous component '{query}'")

    def format_options(self) -> str:
        lines = [f"找不到 Component '{self.query}'，您是指："]
        for i, c in enumerate(self.candidates, 1):
            lines.append(f"  {i}. {c}")
        return "\n".join(lines)


class JiraService:
    def __init__(self):
        # 我們將其包裝在 try-except 中或延遲載入，以避免開發期間因缺少設定而崩潰
        if config.JIRA_SERVER and config.JIRA_API_TOKEN:
            self.jira = JIRA(server=config.JIRA_SERVER, basic_auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN))
        else:
            self.jira = None
            logger.warning(" 缺少 Jira 設定")

    def get_component_description(self, project_key: str, component_name: str) -> Optional[str]:
        """Fetch the description of a component, which contains the BU prefix (e.g. 'CRD')."""
        try:
            comps = self.jira.project_components(project_key)
            for c in comps:
                if c.name == component_name:
                    return getattr(c, "description", None)
        except Exception as e:
            logger.error(f"Error fetching component description for {component_name}: {e}")
        return None

    def get_issue(self, issue_key: str) -> Optional[dict]:
        """
        取得 Jira Issue 的基本資訊。

        Args:
            issue_key: Issue key (e.g., 'PROJ-1234')

        Returns:
            dict: {
                'key': 'PROJ-1234',
                'summary': '...',
                'issuetype': 'Story',
                'components': ['短租(SR)'],
                'sprint_id': 123 or None,
                'fix_versions': ['WP1.2.3'],
                'assignee_id': '...' or None
            }
            或 None (如果找不到)
        """
        if not self.jira:
            return None

        try:
            issue = self.jira.issue(issue_key)
            fields = issue.fields

            # Extract components
            components = [c.name for c in (fields.components or [])]

            # Extract fix versions
            fix_versions = [v.name for v in (fields.fixVersions or [])]

            # Extract sprint ID (from customfield, usually)
            sprint_id = None
            # Sprint is often in a custom field - try common field names
            for attr in ['sprint', 'customfield_10020', 'customfield_10104']:
                sprint_data = getattr(fields, attr, None)
                if sprint_data:
                    # Sprint data can be a list of sprint objects
                    if isinstance(sprint_data, list) and len(sprint_data) > 0:
                        # Get the first active/future sprint
                        for s in sprint_data:
                            if hasattr(s, 'id'):
                                sprint_id = s.id
                                break
                            elif isinstance(s, str):
                                # Parse sprint string like "com.atlassian.greenhopper...id=123..."
                                import re
                                match = re.search(r'id=(\d+)', s)
                                if match:
                                    sprint_id = int(match.group(1))
                                    break
                    break

            # Extract assignee
            assignee_id = None
            if fields.assignee:
                assignee_id = fields.assignee.accountId

            return {
                'key': issue.key,
                'summary': fields.summary,
                'issuetype': fields.issuetype.name,
                'components': components,
                'sprint_id': sprint_id,
                'fix_versions': fix_versions,
                'assignee_id': assignee_id,
            }
        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {e}")
            return None

    def create_ticket(self, draft: TicketDraft, project_key: str, caller_account_id: str = None) -> TicketCreated:
        """
        根據草稿模型建立 Jira 票券。

        Args:
            draft: TicketDraft model
            project_key: Jira project key
            caller_account_id: Caller's Jira Account ID (for dynamic "me" resolution)
        """
        issue_dict = {
            "project": {"key": project_key},
            "summary": draft.summary,
            "description": draft.description,
            "issuetype": {"name": draft.issuetype},
        }

        # Set reporter to the caller (person chatting with bot)
        if caller_account_id:
            issue_dict["reporter"] = {"accountId": caller_account_id}
            # Get user display name for logging
            try:
                reporter_user = self.jira.user(caller_account_id)
                reporter_name = reporter_user.displayName if reporter_user else "Unknown"
            except Exception:
                reporter_name = "Unknown"
            logger.debug(f"Setting reporter to: {reporter_name} ({caller_account_id})")

        if draft.assignee:
            user = self.find_user(draft.assignee, caller_account_id=caller_account_id)
            if user:
                issue_dict["assignee"] = {"accountId": user.accountId}

        if draft.components:
            issue_dict["components"] = [{"name": c} for c in draft.components]

        if draft.labels:
            issue_dict["labels"] = draft.labels

        if draft.fix_versions:
            # fix_versions is a list of version names
            issue_dict["fixVersions"] = [{"name": v} for v in draft.fix_versions]

        # NOTE: due_date (duedate) intentionally NOT sent to Jira.
        # Dates should go through expected_release_date → fix_versions instead.

        # Create the issue first
        new_issue = self.jira.create_issue(fields=issue_dict)

        # Set Sprint (must be done after issue creation via separate API)
        if draft.sprint_id:
            try:
                self.jira.add_issues_to_sprint(draft.sprint_id, [new_issue.key])
                logger.debug(f" Added {new_issue.key} to sprint {draft.sprint_id}")
            except Exception as e:
                logger.warning(f" Failed to add to sprint: {e}")

        return TicketCreated(key=new_issue.key, summary=new_issue.fields.summary, link=new_issue.permalink())

    def get_or_create_version(self, project_key: str, version_name: str, release_date: Optional[str] = None):
        """檢查版本是否存在，若不存在則建立。"""
        project_versions = self.jira.project_versions(project_key)
        existing = next((v for v in project_versions if v.name == version_name), None)

        if existing:
            return existing

        # 建立新版本
        return self.jira.create_version(name=version_name, project=project_key, releaseDate=release_date)

    def find_user(self, query: str, caller_account_id: str = None):
        """
        透過名稱、暱稱或 Email 尋找使用者。
        
        Solution E 邏輯:
        1. Exact match → 使用
        2. Single fuzzy match → 使用
        3. Multiple fuzzy matches → 拋出 AmbiguousUserError 讓使用者選擇

        Args:
            query: 使用者名稱或暱稱 (e.g., "me", "Grey", "john@example.com")
            caller_account_id: 呼叫者的 Jira Account ID (用於動態解析 "me")

        Returns:
            Jira User object or None
        """
        # Special case: "me" with caller context
        if query.lower() == "me" and caller_account_id:
            logger.info(f"使用動態 'me' 解析: caller_account_id = {caller_account_id}")
            try:
                user = self.jira.user(caller_account_id)
                return user
            except Exception as e:
                logger.error(f"Error fetching caller user by ID {caller_account_id}: {e}")
                # Fall through to static mapping

        # Solution E: Smart matching with fuzzy search
        search_result = config.search_account_ids_by_nickname(query)
        exact_matches = search_result['exact']
        fuzzy_matches = search_result['fuzzy']
        
        logger.debug(f"[find_user] query='{query}', exact={len(exact_matches)}, fuzzy={len(fuzzy_matches)}")

        # Case 1: Exact match found
        if len(exact_matches) == 1:
            account_id = list(exact_matches)[0]
            logger.info(f"Exact match: {query} -> {account_id}")
            try:
                return self.jira.user(account_id)
            except Exception as e:
                logger.error(f"Error fetching user by ID {account_id}: {e}")
        
        elif len(exact_matches) > 1:
            # Multiple exact matches (e.g., "Jimmy" in multiple users' nicknames)
            candidates = self._build_candidates_list(exact_matches)
            logger.warning(f"Multiple exact matches for '{query}': {[c['display_name'] for c in candidates]}")
            raise AmbiguousUserError(query, candidates)

        # Case 2: No exact match, check fuzzy matches
        if len(fuzzy_matches) == 1:
            account_id = list(fuzzy_matches)[0]
            logger.info(f"Single fuzzy match: {query} -> {account_id}")
            try:
                return self.jira.user(account_id)
            except Exception as e:
                logger.error(f"Error fetching user by ID {account_id}: {e}")
        
        elif len(fuzzy_matches) > 1:
            # Multiple fuzzy matches - ask user to choose
            candidates = self._build_candidates_list(fuzzy_matches)
            logger.warning(f"Multiple fuzzy matches for '{query}': {[c['display_name'] for c in candidates]}")
            raise AmbiguousUserError(query, candidates)

        # Case 3: No matches in users.json - fallback to Jira API search
        try:
            users = self.jira.search_users(query=query)
            if users:
                user = users[0]
                email = getattr(user, "emailAddress", "N/A")
                logger.debug(f" Found user via Jira API: {user.displayName} (email: {email}, accountId: {user.accountId})")
                return user
        except Exception as e:
            logger.warning(f"搜尋使用者失敗: {e}")

        return None

    def _build_candidates_list(self, account_ids: set) -> list:
        """Build a list of candidate dicts for AmbiguousUserError."""
        candidates = []
        for acc_id in account_ids:
            try:
                user = self.jira.user(acc_id)
                candidates.append({
                    'account_id': acc_id,
                    'display_name': user.displayName,
                    'email': getattr(user, 'emailAddress', None) or self._get_email_from_config(acc_id),
                })
            except Exception:
                candidates.append({
                    'account_id': acc_id,
                    'display_name': self._get_display_name_from_config(acc_id),
                    'email': self._get_email_from_config(acc_id),
                })
        return candidates

    def _get_email_from_config(self, account_id: str) -> str:
        """從 users.json 中取得使用者的 email"""
        import json
        from pathlib import Path
        users_file = Path(__file__).parent.parent / "users.json"
        if users_file.exists():
            with open(users_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            nicks = data.get(account_id, [])
            for nick in nicks:
                if "@" in nick:
                    return nick
        return "N/A"

    def _get_display_name_from_config(self, account_id: str) -> str:
        """從 users.json 中取得使用者的 display name (第一個非 email 的暱稱)"""
        import json
        from pathlib import Path
        users_file = Path(__file__).parent.parent / "users.json"
        if users_file.exists():
            with open(users_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            nicks = data.get(account_id, [])
            for nick in nicks:
                if "@" not in nick:
                    return nick
            # 如果全都是 email，就回傳第一個
            if nicks:
                return nicks[0]
        return account_id[:20] + "..."

    def link_tickets(self, source_key: str, target_key: str, link_type: str = "Relates"):
        """連結兩個票券。"""
        self.jira.create_issue_link(type=link_type, inwardIssue=source_key, outwardIssue=target_key)

    def get_board_sprints(self, board_id: str) -> List[dict]:
        """
        取得 Board 上所有的 Sprint (包含 active, future, closed)。
        Returns: List of dict with keys: id, name, state
        """
        if not self.jira or not board_id:
            return []

        sprints = []
        try:
            # Fetch sprints for each state
            for state in ["active", "future"]:
                result = self.jira.sprints(board_id, state=state)
                for s in result:
                    sprints.append({"id": s.id, "name": s.name, "state": s.state})

            # Sort: active first, then future
            state_order = {"active": 0, "future": 1, "closed": 2}
            sprints.sort(key=lambda x: state_order.get(x["state"], 99))

            logger.debug(f" Found {len(sprints)} sprints")
            return sprints
        except Exception as e:
            logger.error(f"Error fetching sprints: {e}")
            return []

    def get_project_prefixes(self, project_key: str) -> List[str]:
        """抓取專案中所有 **未發布 (Unreleased)** 版本的系統前綴 (例如 'OPS', 'Car2go')。"""
        try:
            versions = self.jira.project_versions(project_key)
            prefixes = set()
            # 使用 Regex 抓取開頭的英文字串 + 數字 (直到遇到 "空白+數字+點" 或 "數字+點")
            # 支援: "OPS1.58.0" -> "OPS", "Car2go 1.140" -> "Car2go", "My Sys 1.0" -> "My Sys"
            pattern = re.compile(r"^(.+?)(?=\s?\d+\.\d+)")

            for v in versions:
                # 只看未發布的版本 (Unreleased)
                if getattr(v, "released", False):
                    continue

                match = pattern.match(v.name)
                if match:
                    # 去除前後空白
                    prefix = match.group(1).strip()
                    if prefix:
                        prefixes.add(prefix)

            return sorted(list(prefixes))
        except Exception as e:
            logger.error(f"Error fetching prefixes: {e}")
            return []

    def get_version_prefixes(self, project_key: str) -> List[str]:
        # Alias if needed, or just remove. For safety, keeping alias to get_project_prefixes
        return self.get_project_prefixes(project_key)

    def get_or_create_hotfix_version(
        self, project_key: str, system_prefix: str, target_date_str: str, dry_run: bool = False
    ):
        """
        根據目標日期與系統前綴，取得現有版本或建立 Hotfix 版本。
        邏輯：
        1. 找是否有同日期的版本 -> 回傳
        2. 找該日期前最後一個版本 (V_prev)
        3. Hotfix Name = V_prev 版本號+1 (+YYMMDD) - 維持 V_prev 的格式與前綴
        """
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        target_yymmdd = target_date.strftime("%y%m%d")

        # 1. 抓取該 Prefix 的所有版本
        all_versions = self.jira.project_versions(project_key)

        # 過濾出同 System Prefix 的版本
        system_versions = []
        for v in all_versions:
            # 如果 system_prefix 不為空，就用 startswith 過濾；若為空，則全列考慮 (危險? 通常 Hotfix 都有命名前綴)
            if system_prefix and v.name.startswith(system_prefix):
                if hasattr(v, "releaseDate"):
                    system_versions.append(v)
            elif not system_prefix:
                # 如果沒有 prefix，我們假設所有版本都是同一系列 (或簡單過濾)
                if hasattr(v, "releaseDate"):
                    system_versions.append(v)

        # 2. 檢查是否有當天版本
        for v in system_versions:
            if v.releaseDate == target_date_str:
                logger.info(f"找到現有版本: {v.name}")
                return v

        # 3. 找前一個版本 (Previous Version)
        # 用日期排序
        sorted_versions = sorted(system_versions, key=lambda v: v.releaseDate)

        v_prev = None
        for v in sorted_versions:
            v_date = datetime.strptime(v.releaseDate, "%Y-%m-%d").date()
            if v_date < target_date:
                v_prev = v
            else:
                break  # 超過目標日期就停

        if not v_prev:
            # 如果完全沒有前一個版本，無法計算 Hotfix
            # 回退到建立一個 .0 版本或報錯
            sep = "" if not system_prefix else " "
            # 若無前版本，只能用 prefix 接
            new_name = f"{system_prefix}{sep}1.0.0({target_yymmdd})"
            logger.info(f"無前一版本，建立初始版本: {new_name}")
            return self.jira.create_version(project=project_key, name=new_name, releaseDate=target_date_str)

        # 4. 計算 Hotfix 版本號 - 基於 V_prev 的命名模式
        logger.info(f"參照前一版本: {v_prev.name}")

        # 嘗試抓取版本號部分 (Major.Minor.Patch)
        # \d+\.\d+\.\d+
        version_pattern = re.compile(r"(\d+\.\d+\.)(\d+)")
        match = version_pattern.search(v_prev.name)

        if match:
            # group 1: "2.97." (Base)
            # group 2: "4" (Patch)
            base_ver = match.group(1)
            patch_ver = int(match.group(2))
            new_patch = patch_ver + 1
            
            # 使用 split/replace 替換版本號與日期，保持前綴不變
            # 方法: 找到 match 的 span，替換掉 patch，然後處理日期
            start, end = match.span()
            prefix_part = v_prev.name[:start]
            
            # 判斷 V_prev 是否有 (YYMMDD) 日期後綴
            date_pattern = re.compile(r"\(\d{6}\)$")
            name_suffix = v_prev.name[end:]
            
            # 如果後綴包含日期，替換成新日期
            if date_pattern.search(name_suffix):
                 name_suffix = date_pattern.sub(f"({target_yymmdd})", name_suffix)
            else:
                 # 若原本沒有日期，就補上? user 沒說，但通常 hotfix 需要日期區隔
                 name_suffix += f"({target_yymmdd})"

            # 重組
            new_name = f"{prefix_part}{base_ver}{new_patch}{name_suffix}"

            logger.info(f"建立 Hotfix 版本: {new_name}")
            return self.jira.create_version(project=project_key, name=new_name, releaseDate=target_date_str)
        else:
            # 解析失敗，fallback
            new_name = f"{v_prev.name}_hotfix_({target_yymmdd})"
            logger.warning(f"版本號解析失敗，使用備案名稱: {new_name}")
            return self.jira.create_version(project=project_key, name=new_name, releaseDate=target_date_str)
