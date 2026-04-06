"""
Shared Bot Logic - Core ticket creation workflow used by both LocalBot and MattermostBot.
"""

import logging
from collections import defaultdict
from typing import Callable, Optional

import difflib
import config
from services.jira_service import JiraService, AmbiguousUserError, AmbiguousComponentError
from services.llm_service import LLMService
from services.component_matcher import ComponentMatcher

logger = logging.getLogger(__name__)


class BotLogicMixin:
    """
    Mixin that provides shared ticket creation logic.

    The host class must provide:
    - self.jira_service: JiraService instance
    - self.llm_service: LLMService instance
    - self.history: defaultdict(list) for conversation history
    - self.dry_run: bool (optional, defaults to False)
    - self.send_message(channel_id, message): method to send messages
    - self._mock_create_ticket, _mock_create_version, _mock_link_tickets (for dry run)
    """

    def __init_bot_logic__(self):
        """Initialize bot logic state. Call this in host's __init__."""
        # Pending sprint selection: {channel_id: {'plan': plan, 'sprints': [...]}}
        self.pending_sprint_selection = {}
        # Pending user selection: {channel_id: {'plan': plan, 'field': 'assignee', 'candidates': [...], 'original_query': '...'}}
        self.pending_user_selection = {}
        # Pending component selection: {channel_id: {'plan': plan, 'query': '...', 'candidates': [...]}}
        self.pending_component_selection = {}
        # Pending BU selection: {channel_id: {'user_input': '...', 'candidates': [...]}}
        self.pending_bu_selection = {}
        # Pending System selection: {channel_id: {'user_input': '...', 'candidates': [...]}}
        self.pending_system_selection = {}
        # Pending Ticket Type selection: {channel_id: {'user_input': '...', 'conflict_types': [...]}}
        self.pending_ticket_type_selection = {}
        
        # Caller context: {channel_id: jira_account_id} - for dynamic "me" resolution
        self.caller_context = {}
        
        # Resolved Context
        # {channel_id: {'name': '...', 'prefix': '...'}}
        self.resolved_bu = {}
        # {channel_id: 'PREFIX'} e.g. 'WP'
        self.resolved_system = {}
        
        # Component Matcher
        self.component_matcher = ComponentMatcher(self.jira_service)
        self.component_matcher.refresh_cache(config.JIRA_PROJECT_KEY)

    def _send_and_log(self, channel_id: str, message: str, msg_type: str = "reply"):
        """Send message and log it for debugging."""
        logger.debug("=" * 60)
        logger.debug(f"[Bot 回覆] ({msg_type}): {message[:200]}..." if len(message) > 200 else f"[Bot 回覆] ({msg_type}): {message}")
        logger.debug("=" * 60)
        self.send_message(channel_id, message)

    def _clear_session_state(self, channel_id: str):
        """Clear all session state (history, pending selections, resolved context) for a fresh start."""
        self.history[channel_id] = []
        if channel_id in self.pending_component_selection: del self.pending_component_selection[channel_id]
        if channel_id in self.pending_bu_selection: del self.pending_bu_selection[channel_id]
        if channel_id in self.pending_system_selection: del self.pending_system_selection[channel_id]
        if channel_id in self.pending_user_selection: del self.pending_user_selection[channel_id]
        if channel_id in self.pending_ticket_type_selection: del self.pending_ticket_type_selection[channel_id]
        if channel_id in self.pending_sprint_selection: del self.pending_sprint_selection[channel_id]
        if channel_id in self.resolved_bu: del self.resolved_bu[channel_id]
        if channel_id in self.resolved_system: del self.resolved_system[channel_id]
        if channel_id in self.caller_context: del self.caller_context[channel_id]
        logger.debug(f"Session state cleared for {channel_id}")

    def handle_message(self, user_input: str, channel_id: str, caller_account_id: str = None, user_nickname: str = None):
        """
        Main message handler with full ticket creation workflow.

        Args:
            user_input: The user's message
            channel_id: The channel/session identifier
            caller_account_id: Optional Jira Account ID of the caller (for dynamic "me" resolution)
            user_nickname: Optional Mattermost nickname for logging
        """
        # Store caller context for this channel
        if caller_account_id:
            self.caller_context[channel_id] = caller_account_id

        # Store nickname for display (fallback to "User" if not provided)
        display_name = user_nickname or "User"
        
        # Log user input
        logger.debug(f"Received message from {channel_id} ({display_name}): {user_input}")

        history = self.history[channel_id]

        # 00. Help Command
        lowered_input = user_input.strip().lower()
        if lowered_input in ["help", "/help", "說明", "使用說明", "功能列表", "指令", "指令列表"]:
            help_msg = (
                "🤖 **Jira Assistant 使用說明**\n\n"
                "我可以協助您建立以下類型的 Jira 票券，請直接對我說出您的需求：\n\n"
                "**1. 功能票 (Feature)**\n"
                "   - 用途：新功能開發、需求變更\n"
                "   - 關鍵字：「功能」、「需求」、「開發」、「新功能」\n"
                "   - 範例：「短租要開發新功能，排車表新增欄位，明天上 WP」\n\n"
                "**2. Bug 票 (Bug)**\n"
                "   - 用途：系統錯誤修復\n"
                "   - 關鍵字：「Bug」、「錯誤」、「異常」、「壞掉」、「修復」\n"
                "   - 範例：「短租有 Bug，搜尋壞掉了，給 John」\n\n"
                "**3. 維運票 (Operational Task)**\n"
                "   - 用途：資料庫調整、設定變更、提取數據\n"
                "   - 關鍵字：「維運」、「Operational」、「OP」\n"
                "   - 範例：「短租維運票，幫我撈上週訂單資料，給 John」\n\n"
                "**4. 補建 Task (Add Task)**\n"
                "   - 用途：幫既有的 Story 補開子任務 (Feature Task)\n"
                "   - 關鍵字：「補建 Task」、「加 Task」、「新增 Task」\n"
                "   - 範例：「幫 PROJ-123 補一個後端 Task 給我」\n\n"
                "💡 **小撇步**：\n"
                "   - 您可以一次說完：「短租功能票，新增按鈕，給前端 John，明天上 WP」\n"
                "   - 若資訊不足，我會再反問您。"
            )
            self._send_and_log(channel_id, help_msg, "help")
            
            # Clear history and reset state
            self._clear_session_state(channel_id)
            return

        # 0. Check if pending component selection
        if channel_id in self.pending_component_selection:
            self._handle_component_selection(user_input, channel_id)
            return

        # 0.1 Check if pending BU selection
        if channel_id in self.pending_bu_selection:
            self._handle_bu_selection(user_input, channel_id)
            return

        # 0.2 Check if pending System selection
        if channel_id in self.pending_system_selection:
            self._handle_system_selection(user_input, channel_id)
            return

        # 0.3 Check if pending user selection (ambiguous user)
        if channel_id in self.pending_user_selection:
            self._handle_user_selection(user_input, channel_id)
            return

        # 0.4 Check if pending ticket type selection (conflict)
        if channel_id in self.pending_ticket_type_selection:
            self._handle_ticket_type_selection(user_input, channel_id)
            return

        # 0.5 Check if pending sprint selection
        if channel_id in self.pending_sprint_selection:
            self._handle_sprint_selection(user_input, channel_id)
            return

        # 1. Update History (store nickname for logging)
        history.append({"role": "user", "content": user_input, "nickname": display_name})

        # Log conversation history with nicknames
        logger.debug("=" * 60)
        logger.debug("[對話歷史]")
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                nickname = msg.get("nickname", "User")
                logger.debug(f"  [{nickname}]: {content}")
            else:
                logger.debug(f"  [Bot]: {content}")
        logger.debug("=" * 60)
        logger.debug(f"[{display_name} 當前訊息]: {user_input}")

        # Keep only last 30 messages
        if len(history) > 30:
            self.history[channel_id] = self.history[channel_id][-30:]

        # 2. Pre-detect intent type (before BU matching)
        # This allows us to skip BU matching for add_task mode
        detection_result = self.llm_service._detect_ticket_type_from_history(history, user_input)
        pre_detected_type = detection_result.get("type", "unknown")
        logger.debug(f"[PRE-DETECT INTENT] {detection_result}")

        # 2.0.1 Handle ticket type conflict - ask user to choose
        if pre_detected_type == "conflict":
            conflict_types = detection_result.get("conflict_types", [])
            declaration_matches = detection_result.get("declaration_matches", {})
            
            self.pending_ticket_type_selection[channel_id] = {
                'user_input': user_input,
                'conflict_types': conflict_types,
                'declaration_matches': declaration_matches,
                'history_snapshot': list(history),
            }
            
            # Build message showing which keywords triggered which types
            type_labels = {
                'feature': '功能票 (Feature)',
                'bug': 'Bug 票',
                'operational': '維運票 (Operational)'
            }
            options = []
            for i, t in enumerate(conflict_types, 1):
                keywords = declaration_matches.get(t, [])
                keyword_str = f"（因為您說了「{'、'.join(keywords)}」）" if keywords else ""
                options.append(f"  {i}. {type_labels.get(t, t)}{keyword_str}")
            
            msg = (
                "⚠️ 偵測到多種可能的票券類型，請選擇：\n\n"
                + "\n".join(options)
                + "\n\n請輸入數字選擇："
            )
            self._send_and_log(channel_id, msg, "ticket_type_selection")
            return

        # 2.1 Match BU Component (skip for add_task mode - we'll get it from the Story)
        resolved_bu = None
        if pre_detected_type != "add_task":
            bu_match = self.component_matcher.match(user_input)
            logger.debug(f"[BU MATCH] type={bu_match.match_type}, components={[c['name'] for c in bu_match.components]}")
            
            if bu_match.match_type == 'single':
                resolved_bu = bu_match.components[0]
                self.resolved_bu[channel_id] = resolved_bu
                logger.info(f"BU 已匹配: {resolved_bu['name']}")
            elif bu_match.match_type == 'multiple':
                # Ask user to choose
                self.pending_bu_selection[channel_id] = {
                    'user_input': user_input,
                    'candidates': bu_match.components,
                    'history_snapshot': list(history),
                }
                msg = self.component_matcher.format_options(bu_match.components)
                self._send_and_log(channel_id, msg, "bu_selection")
                return
            elif bu_match.match_type == 'none':
                # Check if we already have a resolved BU for this session
                if channel_id in self.resolved_bu:
                    resolved_bu = self.resolved_bu[channel_id]
                    logger.debug(f"Using previously resolved BU: {resolved_bu['name']}")
                else:
                    # Show all BU options
                    all_bus = self.component_matcher.get_all_bu_components()
                    if all_bus:
                        self.pending_bu_selection[channel_id] = {
                            'user_input': user_input,
                            'candidates': all_bus,
                            'history_snapshot': list(history),
                        }
                        msg = "無法辨識業務單位 (BU)，" + self.component_matcher.format_options(all_bus)
                        self._send_and_log(channel_id, msg, "bu_selection")
                        return
        else:
            logger.debug("[ADD_TASK MODE] Skipping BU matching - will inherit from Story")

        # 3. Check Clarification
        prefixes = self.jira_service.get_project_prefixes(config.JIRA_PROJECT_KEY)
        clarification_result = self.llm_service.needs_clarification(user_input, history, known_prefixes=prefixes)
        logger.debug(f"[CLARIFICATION] {clarification_result}")
        
        intent_type = clarification_result.get("intent_type", "feature")  # Extract intent type
        if clarification_result.get("needs_clarification", False):
            missing_fields = clarification_result.get("missing_fields", [])
            # Remove BU from missing fields if already resolved
            if resolved_bu and "BU" in missing_fields:
                missing_fields.remove("BU")
            if missing_fields:  # Still have missing fields
                logger.debug(f"[MISSING FIELDS] {missing_fields}")
                question = self.llm_service.get_clarification_question(
                    user_input, history, known_prefixes=prefixes, missing_fields=missing_fields
                )
                self._send_and_log(channel_id, question, "clarification")
                return

        # Special handling for add_task intent
        if intent_type == "add_task":
            story_key = clarification_result.get("story_key")
            if not story_key:
                # Try to extract from message
                story_key = self.llm_service._extract_story_key(user_input)
            
            if not story_key:
                self._send_and_log(channel_id, "❌ 無法識別 Story Key，請提供 Story 的票號（例如 PROJ-1234）或 Jira 連結。", "error")
                return
            
            # Validate Story exists
            story_info = self.jira_service.get_issue(story_key)
            if not story_info:
                self._send_and_log(channel_id, f"❌ 找不到 Story `{story_key}`，請確認票號是否正確。", "error")
                return
            
            # Validate it's a Story type (not a Bug or Task)
            if story_info.get('issuetype') not in ['Story', 'Epic']:
                self._send_and_log(
                    channel_id, 
                    f"⚠️ `{story_key}` 是 {story_info.get('issuetype')} 類型，不是 Story。您確定要為此票補建 Task 嗎？\n"
                    f"Story Summary: {story_info.get('summary', 'N/A')}", 
                    "warning"
                )
                # For now, proceed anyway - user might want to add tasks to other types
            
            logger.info(f"[ADD_TASK] Found Story: {story_key} - {story_info.get('summary', 'N/A')}")
            
            # Get BU prefix from parent Story's component description (before LLM call)
            bu_prefix = None
            bu_component_name = None
            if story_info.get('components'):
                for comp_name in story_info['components']:
                    if comp_name not in ['BE', 'FE', 'APP', 'UX']:
                        bu_component_name = comp_name
                        # Get the description as prefix (e.g., "SR" for "短租(SR)")
                        description = self.jira_service.get_component_description(config.JIRA_PROJECT_KEY, comp_name)
                        if description:
                            bu_prefix = description
                        break
            
            logger.debug(f"[ADD_TASK] BU Component: {bu_component_name}, Prefix: {bu_prefix}")
            
            # Parse add_task intent with correct BU prefix
            plan = self.llm_service.parse_add_task_intent(
                user_input, history, story_info=story_info, bu_prefix=bu_prefix
            )
            if not plan:
                self._send_and_log(channel_id, "抱歉，無法理解任務需求。請說明需要哪些職能（BE/FE/APP/UX）及負責人。", "error")
                return
            
            # Ensure parent_story_key is set
            plan.parent_story_key = story_key
            
            # Inherit Sprint from Story if available
            if story_info.get('sprint_id'):
                for task in plan.tasks:
                    if not task.sprint_id:
                        task.sprint_id = story_info['sprint_id']
            
            logger.info(f"[ADD_TASK Plan] {plan}")
            
            # Process plan (skip component validation since we inherit from Story)
            self._process_add_task_plan(plan, channel_id, story_info)
            return

        # 3.1 Match System Prefix (After clarification, before parsing intent)
        # Only if it's Feature or Bug (Operational usually implies specific system or none)
        resolved_system = self.resolved_system.get(channel_id)
        
        if not resolved_system and (intent_type in ["feature", "bug", "operational"]):
             # Try to match against prefixes
             # prefixes are ['OPS', 'WP', ...]
             matches = []
             user_input_upper = user_input.upper()
             
             # Exact/Keyword match with Word Boundary
             import re
             for p in prefixes:
                 # Escape prefix to handle special chars if any
                 # Check for word boundary using regex
                 # \b won't work well if prefix has non-word chars, but usually prefixes are alphanumeric.
                 # Let's assume alphanumeric for now, safe for "YES", "WP", "OPS".
                 pattern = r'(?<![a-zA-Z0-9])' + re.escape(p) + r'(?![a-zA-Z0-9])'
                 
                 # Check if pattern matches anywhere in user_input
                 if re.search(pattern, user_input, re.IGNORECASE):
                     matches.append(p)
             
             if len(matches) == 1:
                 resolved_system = matches[0]
                 self.resolved_system[channel_id] = resolved_system
                 logger.info(f"System Prefix Auto-matched: {resolved_system}")
             elif len(matches) > 1:
                 # Ambiguous
                 self.pending_system_selection[channel_id] = {
                    'user_input': user_input,
                    'candidates': matches,
                    'history_snapshot': list(history),
                    'intent_type': intent_type
                 }
                 msg = "找到多個可能的系統，請選擇：\n" + "\n".join([f"{i+1}. {m}" for i, m in enumerate(matches)])
                 self._send_and_log(channel_id, msg, "system_selection")
                 return
             else:
                 # No match found.
                 # Previously we forced prompt here.
                 # Revised Logic: If LLM (Step 3) already said clarification is NOT needed,
                 # it implies System might be optional (e.g. Release Date waived).
                 # So we TRUST the LLM and do NOT force selection here.
                 # It will just be None, and parse_intent will handle it (or LLM infers it).
                 pass
        
        # Remove System from missing_fields if resolved (just in case LLM asked for it)
        # Actually we do this inside Clarification block above? No, we just did Clarification.
        # If we just resolved it here, we should probably re-run clarification check or just proceed.
        # Proceeding is fine.

        # 4. Parse Intent with resolved BU and System
        plan = self.llm_service.parse_intent(
            user_input, history, intent_type=intent_type, 
            resolved_bu=resolved_bu, resolved_system=resolved_system
        )
        logger.debug(f"[PARSED PLAN] {plan}")
        if not plan:
            self._send_and_log(channel_id, "抱歉，無法理解需求。", "error")
            return

        logger.info(f"[Plan] {plan}")

        # 3.4 - 3.8 Process Plan (Validation, Versions, Sprint, Creation)
        self._process_plan(plan, channel_id)

    def _process_plan(self, plan, channel_id: str):
        """Execute the ticket creation steps from validation to creation."""
        # 3.4 Validate Components
        try:
            self._validate_components(plan)
        except AmbiguousComponentError as e:
            self.pending_component_selection[channel_id] = {
                "plan": plan,
                "query": e.query,
                "candidates": e.candidates,
            }
            self._send_and_log(channel_id, e.format_options(), "clarification")
            return

        # 3.5 Calculate Fix Versions
        self._calculate_fix_versions(plan)

        # 3.6 Deduplicate Tasks
        self._deduplicate_tasks(plan)

        # 3.7 Pre-validate assignees
        ambiguous_result = self._check_ambiguous_assignees(plan)
        if ambiguous_result:
            sprints = []
            if config.JIRA_BOARD_ID:
                sprints = self.jira_service.get_board_sprints(config.JIRA_BOARD_ID)
            
            self.pending_user_selection[channel_id] = {
                "plan": plan,
                "field": "assignee",
                "candidates": ambiguous_result["candidates"],
                "original_query": ambiguous_result["query"],
                "target_draft": ambiguous_result.get("target_draft"),
                "sprints": sprints,
            }
            self._send_and_log(channel_id, ambiguous_result["message"], "clarification")
            return

        # 3.8 Fetch Sprints and ask user to select
        if config.JIRA_BOARD_ID:
            sprints = self.jira_service.get_board_sprints(config.JIRA_BOARD_ID)
            if sprints:
                is_operational_mode = plan.intent_type == "operational"
                
                # For Operational Mode: Auto-assign Active Sprint
                if is_operational_mode:
                    active_sprint = next((s for s in sprints if s["state"] == "active"), None)
                    if active_sprint:
                        logger.info(f"Auto-assigning Operational ticket to Active Sprint: {active_sprint['name']}")
                        # Assign to all tasks
                        for task in plan.tasks:
                            task.sprint_id = active_sprint["id"]
                        
                        # Skip sprint selection and create tickets directly
                        self._create_tickets(plan, channel_id)
                        return

                self.pending_sprint_selection[channel_id] = {"plan": plan, "sprints": sprints}
                is_bug_mode = plan.intent_type == "bug"
                
                if is_bug_mode:
                    ticket_count = len(plan.tasks)
                    ticket_summary = f"📋 將建立 {ticket_count} 張 Bug 票\n\n"
                elif is_operational_mode:
                    ticket_count = len(plan.tasks)
                    ticket_summary = f"📋 將建立 {ticket_count} 張維運票 (Operational Task)\n\n"
                else:
                    ticket_count = 1 + len(plan.tasks)
                    ticket_summary = f"📋 將建立 {ticket_count} 張票 (1 Story + {len(plan.tasks)} Tasks)\n\n"

                sprint_options = []
                for i, s in enumerate(sprints, 1):
                    state_label = f" [{s['state']}]" if s["state"] else ""
                    sprint_options.append(f"  {i}. {s['name']}{state_label}")
                backlog_num = len(sprints) + 1
                sprint_options.append(f"  {backlog_num}. 不指定 Sprint (放入 Backlog)")

                msg = (
                    ticket_summary
                    + "請選擇 Sprint（可分別指定，或輸入數字放入 Backlog）：\n"
                    + "\n".join(sprint_options)
                    + "\n\n可直接輸入數字，或說明分配方式(票可以分配到不同sprint中)："
                )
                self._send_and_log(channel_id, msg, "sprint_selection")
                return

        # Proceed to create tickets
        self._create_tickets(plan, channel_id)

    def _process_add_task_plan(self, plan, channel_id: str, story_info: dict):
        """
        Process add_task plan - create tasks and link them to the parent Story.
        
        Args:
            plan: TicketPlan with parent_story_key set
            channel_id: Channel identifier
            story_info: Info about the parent Story from get_issue()
        """
        # Deduplicate tasks
        self._deduplicate_tasks(plan)

        # Pre-validate assignees
        ambiguous_result = self._check_ambiguous_assignees(plan)
        if ambiguous_result:
            sprints = []
            if config.JIRA_BOARD_ID:
                sprints = self.jira_service.get_board_sprints(config.JIRA_BOARD_ID)
            
            self.pending_user_selection[channel_id] = {
                "plan": plan,
                "field": "assignee",
                "candidates": ambiguous_result["candidates"],
                "original_query": ambiguous_result["query"],
                "target_draft": ambiguous_result.get("target_draft"),
                "sprints": sprints,
                "is_add_task_mode": True,
                "story_info": story_info,
            }
            self._send_and_log(channel_id, ambiguous_result["message"], "clarification")
            return

        # Check if sprint is already set (inherited from Story)
        all_have_sprint = all(task.sprint_id for task in plan.tasks)
        
        if not all_have_sprint and config.JIRA_BOARD_ID:
            sprints = self.jira_service.get_board_sprints(config.JIRA_BOARD_ID)
            if sprints:
                self.pending_sprint_selection[channel_id] = {
                    "plan": plan, 
                    "sprints": sprints,
                    "is_add_task_mode": True,
                    "story_info": story_info,
                }
                ticket_count = len(plan.tasks)
                ticket_summary = f"📋 將為 **{plan.parent_story_key}** 補建 {ticket_count} 張 Task\n\n"

                sprint_options = []
                for i, s in enumerate(sprints, 1):
                    state_label = f" [{s['state']}]" if s["state"] else ""
                    sprint_options.append(f"  {i}. {s['name']}{state_label}")
                backlog_num = len(sprints) + 1
                sprint_options.append(f"  {backlog_num}. 不指定 Sprint (放入 Backlog)")

                msg = (
                    ticket_summary
                    + "請選擇 Sprint：\n"
                    + "\n".join(sprint_options)
                    + "\n\n可直接輸入數字選擇："
                )
                self._send_and_log(channel_id, msg, "sprint_selection")
                return

        # Create tasks
        self._create_add_task_tickets(plan, channel_id)

    def _validate_components(self, plan):
        """Validate that components exist in Jira."""
        if not hasattr(self.jira_service, "jira") or not self.jira_service.jira:
            return

        logger.debug("Fetching real components from Jira...")
        jira_components = self.jira_service.jira.project_components(config.JIRA_PROJECT_KEY)
        valid_names = {c.name for c in jira_components}
        valid_list = sorted(list(valid_names))

        # Check all drafts
        all_drafts = [d for d in [plan.story] + (plan.tasks or []) if d is not None]
        for draft in all_drafts:
            # We iterate backwards to allow safe removal if needed, but here we just check validity
            # Actually, if unique component fails, we interrupt.
            new_components = []
            for comp_name in draft.components:
                if comp_name in valid_names:
                    new_components.append(comp_name)
                    logger.debug(f"[Jira] Component '{comp_name}' ✅ Exists")
                else:
                    logger.warning(f"Component '{comp_name}' not found.")
                    # Fuzzy match
                    matches = difflib.get_close_matches(comp_name, valid_list, n=3, cutoff=0.3) # 0.3 is loose, maybe 0.5
                    
                    if matches:
                        # Ambiguous - ask user
                        raise AmbiguousComponentError(comp_name, matches)
                    else:
                        # No close match - what to do? User said "list possible".
                        # If list is small, show all? If large, maybe just show close matches or empty?
                        # The error class handles display. We can pass top 10 frequent ones?
                        # Or just pass empty and let user handle it?
                        # Let's try to match loosely or just pass failure.
                        # For now, treat no match as error with no suggestions.
                        # Wait, user said "if not sure, list possible".
                        # Maybe just list top 5? Or alphabetical?
                        raise AmbiguousComponentError(comp_name, valid_list[:10] if not matches else matches)
            
            # Since we might interrupt, we can't update plan inplace partially until we resolve.
            # But the logic above raises Exception on FIRST failure.
            # So plan is untouched until resolved.
            pass

    def _handle_bu_selection(self, user_input: str, channel_id: str):
        """Handle user choice for BU component when ambiguous or not found."""
        pending = self.pending_bu_selection.get(channel_id)
        if not pending:
            return

        candidates = pending["candidates"]
        original_input = pending["user_input"]
        history = pending.get("history_snapshot", [])
        
        user_input = user_input.strip()
        selected_bu = None

        try:
            choice = int(user_input)
            if 1 <= choice <= len(candidates):
                selected_bu = candidates[choice - 1]
            else:
                self._send_and_log(channel_id, f"請輸入 1-{len(candidates)} 的數字", "validation")
                return
        except ValueError:
            # Maybe typed the name?
            for c in candidates:
                if user_input.lower() in c['name'].lower() or user_input.lower() == c['prefix'].lower():
                    selected_bu = c
                    break
            if not selected_bu:
                self._send_and_log(channel_id, "無效的選擇，請輸入數字。", "validation")
                return

        # Store resolved BU
        self.resolved_bu[channel_id] = selected_bu
        logger.info(f"User selected BU: {selected_bu['name']}")
        
        # Clear pending state
        del self.pending_bu_selection[channel_id]
        
        # Re-process the original input with resolved BU
        # Get intent type from clarification
        prefixes = self.jira_service.get_project_prefixes(config.JIRA_PROJECT_KEY)
        clarification_result = self.llm_service.needs_clarification(original_input, history, known_prefixes=prefixes)
        intent_type = clarification_result.get("intent_type", "feature")
        
        if clarification_result.get("needs_clarification", False):
            missing_fields = clarification_result.get("missing_fields", [])
            # Remove BU from missing fields since we just resolved it
            if "BU" in missing_fields:
                missing_fields.remove("BU")
            if missing_fields:
                question = self.llm_service.get_clarification_question(
                    original_input, history, known_prefixes=prefixes, missing_fields=missing_fields
                )
                self._send_and_log(channel_id, question, "clarification")
                return
        
        # Parse with resolved BU
        plan = self.llm_service.parse_intent(original_input, history, intent_type=intent_type, resolved_bu=selected_bu)
        if not plan:
            self._send_and_log(channel_id, "抱歉，無法理解需求。", "error")
            return
        
        # Continue with normal flow
        self._process_plan(plan, channel_id)

    def _handle_system_selection(self, user_input: str, channel_id: str):
        """Handle user choice for System Prefix."""
        pending = self.pending_system_selection.get(channel_id)
        if not pending:
            return

        candidates = pending["candidates"]
        intent_type = pending["intent_type"]
        original_input = pending["user_input"] # Note: this is original user input that triggered matching, or should we use the user selection input?
        # Actually in handle_system_selection, user_input IS the selection (e.g. "1"). 
        # But we need to proceed with the ORIGINAL input that started the flow?
        # WAIT. If I triggered system selection, I stopped processing the original message.
        # So "original_input" stored in pending IS the original command (e.g. "Bug fix something").
        # The current 'user_input' is just "1".
        
        # So yes, we need original input.
        # But `pending["user_input"]` stored the *original command*.
        
        original_command = pending["user_input"]
        history = pending.get("history_snapshot", [])
        
        selection_input = user_input.strip()
        selected_system = None

        try:
            choice = int(selection_input)
            if 1 <= choice <= len(candidates):
                selected_system = candidates[choice - 1]
            else:
                self._send_and_log(channel_id, f"請輸入 1-{len(candidates)} 的數字", "validation")
                return
        except ValueError:
            # Maybe typed the name?
            for c in candidates:
                if selection_input.lower() == c.lower():
                    selected_system = c
                    break
            if not selected_system:
                self._send_and_log(channel_id, "無效的選擇，請輸入數字。", "validation")
                return

        # Store resolved System
        self.resolved_system[channel_id] = selected_system
        logger.info(f"User selected System: {selected_system}")
        
        # Clear pending state
        del self.pending_system_selection[channel_id]
        
        # Re-process using parse_intent
        # We need resolved BU as well (should be in validation state?)
        resolved_bu = self.resolved_bu.get(channel_id) # Should have been resolved before this step
        
        # Parse Intent with resolved BU and System
        plan = self.llm_service.parse_intent(
            original_command, history, intent_type=intent_type, 
            resolved_bu=resolved_bu, resolved_system=selected_system
        )
        
        if not plan:
            self._send_and_log(channel_id, "抱歉，無法理解需求。", "error")
            return
            
        self._process_plan(plan, channel_id)

    def _handle_ticket_type_selection(self, user_input: str, channel_id: str):
        """Handle user choice for conflicting ticket types."""
        pending = self.pending_ticket_type_selection.get(channel_id)
        if not pending:
            return

        conflict_types = pending["conflict_types"]
        original_input = pending["user_input"]
        history = pending.get("history_snapshot", [])
        
        user_input = user_input.strip()
        selected_type = None

        # Type name mapping for text matching
        type_aliases = {
            'feature': ['功能', '功能票', 'feature', '1'],
            'bug': ['bug', 'bug票', '2'],
            'operational': ['維運', '維運票', 'operational', 'op', '3']
        }

        try:
            choice = int(user_input)
            if 1 <= choice <= len(conflict_types):
                selected_type = conflict_types[choice - 1]
            else:
                self._send_and_log(channel_id, f"請輸入 1-{len(conflict_types)} 的數字", "validation")
                return
        except ValueError:
            # Maybe typed the type name?
            user_lower = user_input.lower()
            for t in conflict_types:
                if user_lower in type_aliases.get(t, []) or user_lower == t:
                    selected_type = t
                    break
            if not selected_type:
                self._send_and_log(channel_id, "無效的選擇，請輸入數字。", "validation")
                return

        logger.info(f"User selected ticket type: {selected_type}")
        
        # Clear pending state
        del self.pending_ticket_type_selection[channel_id]
        
        # Re-process the original input with confirmed intent type
        # Add the user's choice to history so LLM knows the type
        history.append({"role": "user", "content": original_input})
        history.append({"role": "assistant", "content": f"您選擇了 {selected_type} 票"})
        
        # Check for BU matching first
        resolved_bu = self.resolved_bu.get(channel_id)
        if not resolved_bu:
            bu_match = self.component_matcher.match(original_input)
            if bu_match.match_type == 'single':
                resolved_bu = bu_match.components[0]
                self.resolved_bu[channel_id] = resolved_bu
            elif bu_match.match_type == 'multiple':
                self.pending_bu_selection[channel_id] = {
                    'user_input': original_input,
                    'candidates': bu_match.components,
                    'history_snapshot': list(history),
                    'forced_intent_type': selected_type,  # Remember the selected type
                }
                msg = self.component_matcher.format_options(bu_match.components)
                self._send_and_log(channel_id, msg, "bu_selection")
                return
            elif bu_match.match_type == 'none':
                all_bus = self.component_matcher.get_all_bu_components()
                if all_bus:
                    self.pending_bu_selection[channel_id] = {
                        'user_input': original_input,
                        'candidates': all_bus,
                        'history_snapshot': list(history),
                        'forced_intent_type': selected_type,
                    }
                    msg = "無法辨識業務單位 (BU)，" + self.component_matcher.format_options(all_bus)
                    self._send_and_log(channel_id, msg, "bu_selection")
                    return
        
        # Check clarification (with forced intent type - skip Ticket Type question)
        prefixes = self.jira_service.get_project_prefixes(config.JIRA_PROJECT_KEY)
        clarification_result = self.llm_service.needs_clarification(original_input, history, known_prefixes=prefixes)
        
        # Override intent_type with user's selection
        clarification_result["intent_type"] = selected_type
        
        # Remove "Ticket Type" from missing fields since user just selected it
        missing_fields = clarification_result.get("missing_fields", [])
        if "Ticket Type" in missing_fields:
            missing_fields.remove("Ticket Type")
        if resolved_bu and "BU" in missing_fields:
            missing_fields.remove("BU")
        
        if missing_fields:
            question = self.llm_service.get_clarification_question(
                original_input, history, known_prefixes=prefixes, missing_fields=missing_fields
            )
            self._send_and_log(channel_id, question, "clarification")
            return
        
        # Parse with confirmed intent type
        resolved_system = self.resolved_system.get(channel_id)
        plan = self.llm_service.parse_intent(
            original_input, history, intent_type=selected_type,
            resolved_bu=resolved_bu, resolved_system=resolved_system
        )
        
        if not plan:
            self._send_and_log(channel_id, "抱歉，無法理解需求。", "error")
            return
        
        self._process_plan(plan, channel_id)

    def _handle_component_selection(self, user_input: str, channel_id: str):
        """Handle user choice for ambiguous component."""
        pending = self.pending_component_selection.get(channel_id)
        if not pending:
            return

        plan = pending["plan"]
        query = pending["query"]
        candidates = pending["candidates"]
        
        user_input = user_input.strip()
        selected_component = None

        try:
            choice = int(user_input)
            if 1 <= choice <= len(candidates):
                selected_component = candidates[choice - 1]
            else:
                 self._send_and_log(channel_id, f"請輸入 1-{len(candidates)} 的數字", "validation")
                 return
        except ValueError:
             # Maybe typed the name?
             if user_input in candidates:
                 selected_component = user_input
             else:
                 self._send_and_log(channel_id, "無效的選擇，請輸入數字。", "validation")
                 return

        # Fetch component description (Prefix) from Jira
        new_prefix = selected_component
        description = self.jira_service.get_component_description(config.JIRA_PROJECT_KEY, selected_component)
        if description:
            # Assume description IS the prefix (e.g. "CRD")
            new_prefix = description.strip()
        else:
            # Fallback: Try regex if no description
            import re
            match = re.search(r'\((.+?)\)', selected_component)
            if match:
                new_prefix = match.group(1)

        # Replace component in plan AND update summary prefix
        logger.info(f"User selected component: {selected_component} (replacing {query})")
        all_drafts = [d for d in [plan.story] + (plan.tasks or []) if d is not None]
        for draft in all_drafts:
            if query in draft.components:
                # Update Summary: Replace [Query] or [Query-Role]
                if draft.summary:
                    # e.g. Replace "[授信]" with "[CRD]"
                    draft.summary = draft.summary.replace(f"[{query}]", f"[{new_prefix}]")
                    # e.g. Replace "[授信-BE]" with "[CRD-BE]"
                    draft.summary = draft.summary.replace(f"[{query}-", f"[{new_prefix}-")

                # Remove old, add new
                draft.components = [c for c in draft.components if c != query]
                if selected_component not in draft.components:
                     draft.components.append(selected_component)

        # Clear pending
        del self.pending_component_selection[channel_id]

        # Resume processing
        self._process_plan(plan, channel_id)

    @staticmethod
    def _is_hotfix_version(version_name: str) -> bool:
        """
        判斷版本名稱是否為非例行更版 (Hotfix)。
        
        版本號格式範例：
          - WP2.100.6(260303)   → patch=6 → True  (臨時上版)
          - FNMD_26.0317.2(260401) → patch=2 → True
          - MD_26.0320.0(260320) → patch=0 → False (例行更版)
        
        判斷邏輯：取版本號中最後一段數字（括號日期之前），若 ≠ 0 則為 Hotfix。
        """
        import re
        # Match the last number segment before the (YYMMDD) date suffix
        # e.g. "WP2.100.6(260303)" → captures "6"
        # e.g. "FNMD_26.0317.2(260401)" → captures "2"
        # e.g. "MD_26.0320.0(260320)" → captures "0"
        match = re.search(r'\.(\d+)\(\d{6}\)$', version_name)
        if match:
            patch = int(match.group(1))
            return patch != 0
        
        # Fallback: try generic X.Y.Z pattern without date suffix
        match = re.search(r'(\d+\.\d+\.)(\d+)', version_name)
        if match:
            patch = int(match.group(2))
            return patch != 0
        
        return False

    def _calculate_fix_versions(self, plan):
        """Calculate Fix Versions based on system_prefixes and release date."""
        dry_run = getattr(self, "dry_run", False)

        # Determine source ticket (Story for Feature, Bug ticket for Bug mode)
        if plan.story:
            source_ticket = plan.story
        elif plan.tasks:
            source_ticket = plan.tasks[0]  # Bug ticket
        else:
            return

        # Fallback: if LLM filled due_date instead of expected_release_date, copy it over
        if not source_ticket.expected_release_date and source_ticket.due_date:
            logger.debug(f"[Fix Version] Falling back: due_date ({source_ticket.due_date}) → expected_release_date")
            source_ticket.expected_release_date = source_ticket.due_date
            source_ticket.due_date = None

        if source_ticket.expected_release_date and source_ticket.system_prefixes:
            for prefix in source_ticket.system_prefixes:
                try:
                    logger.debug(
                        f"Fetching/Calculating version for {prefix} on {source_ticket.expected_release_date}..."
                    )
                    version = self.jira_service.get_or_create_hotfix_version(
                        config.JIRA_PROJECT_KEY, prefix, source_ticket.expected_release_date, dry_run=dry_run
                    )
                    if version:
                        logger.debug(f"[Version] Target Version: {version.name} (Existing or Planned)")
                        source_ticket.fix_versions.append(version.name)

                        # Auto-tag "Hotfix" label if version is non-routine (patch != 0)
                        if self._is_hotfix_version(version.name):
                            if "Hotfix" not in source_ticket.labels:
                                source_ticket.labels.append("Hotfix")
                                logger.info(f"[Hotfix] 版本 {version.name} 非例行更版，已加上 Hotfix label")
                except Exception as e:
                    logger.warning(f" Version calculation failed for {prefix}: {e}")

    def _deduplicate_tasks(self, plan):
        """No-op: dedup disabled to allow multiple same-role tasks (e.g. 3x FE with same summary)."""
        pass

    def _check_ambiguous_assignees(self, plan):
        """
        Pre-validate all assignees to check for ambiguous users.
        Uses fuzzy matching to match the behavior of jira_service.find_user.
        Returns dict with ambiguous info if found, None otherwise.
        """
        # Collect all drafts that have assignees
        drafts_to_check = []
        if plan.story and plan.story.assignee:
            drafts_to_check.append(("Story", plan.story))
        for i, task in enumerate(plan.tasks or []):
            if task.assignee:
                drafts_to_check.append((f"Task {i+1}", task))
        
        # Check each assignee
        for label, draft in drafts_to_check:
            query = draft.assignee
            if not query:
                continue
            
            # Skip if already an account ID (starts with valid pattern)
            if query.startswith("712020:") or len(query) == 24:
                continue
            
            # Skip "me" - it will be resolved dynamically
            if query.lower() == "me":
                continue
            
            # Check for ambiguous using fuzzy search (matches find_user behavior)
            search_result = config.search_account_ids_by_nickname(query)
            exact_matches = search_result['exact']
            fuzzy_matches = search_result['fuzzy']
            
            logger.debug(f"[_check_ambiguous_assignees] query='{query}', exact={len(exact_matches)}, fuzzy={len(fuzzy_matches)}")
            
            # Determine if ambiguous based on find_user logic:
            # - Multiple exact matches -> ambiguous
            # - No exact match + multiple fuzzy matches -> ambiguous
            is_ambiguous = False
            candidates_ids = set()
            
            if len(exact_matches) > 1:
                is_ambiguous = True
                candidates_ids = exact_matches
            elif len(exact_matches) == 0 and len(fuzzy_matches) > 1:
                is_ambiguous = True
                candidates_ids = fuzzy_matches
            
            if is_ambiguous:
                # Ambiguous - collect candidate info
                candidates = []
                for acc_id in candidates_ids:
                    candidates.append({
                        'account_id': acc_id,
                        'display_name': self.jira_service._get_display_name_from_config(acc_id),
                        'email': self.jira_service._get_email_from_config(acc_id),
                    })
                
                # Format message
                lines = [f"找到多個 '{query}'，請指定是哪一位："]
                for i, c in enumerate(candidates, 1):
                    email = c.get('email', 'N/A')
                    name = c.get('display_name', 'Unknown')
                    lines.append(f"  {i}. {name} ({email})")
                
                return {
                    "query": query,
                    "candidates": candidates,
                    "target_draft": draft,
                    "message": "\n".join(lines),
                }
        
        return None

    def _handle_sprint_selection(self, user_input: str, channel_id: str):
        """Handle user's sprint selection using LLM for complex assignments."""
        pending = self.pending_sprint_selection.get(channel_id)
        if not pending:
            return

        plan = pending["plan"]
        sprints = pending["sprints"]
        user_input = user_input.strip()

        # Build ticket list for LLM (Bug mode has no story)
        tickets = []
        if plan.story:
            tickets.append({"type": "Story", "summary": plan.story.summary})
        for task in plan.tasks:
            tickets.append({"type": task.issuetype, "summary": task.summary})

        # Optimization: If input is pure digit, skip LLM and use fallback directly
        if user_input.isdigit():
            # print(f"[DEBUG] Input '{user_input}' is digit, skipping LLM...") # Removed debug print
            sprint_assignments = {}  # Empty dict triggers fallback
        else:
            # Use LLM to parse Sprint assignment
            sprint_assignments = self.llm_service.parse_sprint_assignment(user_input, tickets, sprints)

        # print(f"[DEBUG] LLM Sprint assignment result: {sprint_assignments}")

        if sprint_assignments:
            # Apply assignments (null = Backlog, don't set sprint_id)
            # For Bug mode, index 0 refers to the Bug ticket, not Story
            if plan.story and 0 in sprint_assignments:
                if sprint_assignments[0] is not None:
                    plan.story.sprint_id = sprint_assignments[0]
                    logger.debug(f"Story -> Sprint {sprint_assignments[0]}")
                else:
                    logger.debug("Story -> Backlog")

            # Handle tasks/bugs
            task_start_idx = 1 if plan.story else 0
            for i, task in enumerate(plan.tasks, start=task_start_idx):
                if i in sprint_assignments:
                    if sprint_assignments[i] is not None:
                        task.sprint_id = sprint_assignments[i]
                        logger.debug(f"{task.issuetype} {i} -> Sprint {sprint_assignments[i]}")
                    else:
                        logger.debug(f"{task.issuetype} {i} -> Backlog")

            # Clear pending state
            is_add_task_mode = pending.get("is_add_task_mode", False)
            del self.pending_sprint_selection[channel_id]

            # Proceed to create tickets
            if is_add_task_mode:
                self._create_add_task_tickets(plan, channel_id)
            else:
                self._create_tickets(plan, channel_id)
        else:
            # Fallback: try simple number parsing
            backlog_num = len(sprints) + 1
            try:
                choice = int(user_input)
                if choice == backlog_num:
                    # Backlog - no sprint assignment
                    logger.debug("User chose Backlog (no Sprint)")
                    is_add_task_mode = pending.get("is_add_task_mode", False)
                    del self.pending_sprint_selection[channel_id]
                    if is_add_task_mode:
                        self._create_add_task_tickets(plan, channel_id)
                    else:
                        self._create_tickets(plan, channel_id)
                elif 1 <= choice <= len(sprints):
                    selected_sprint = sprints[choice - 1]
                    sprint_id = selected_sprint["id"]

                    # Set sprint_id on ALL tickets (handle Bug mode)
                    if plan.story:
                        plan.story.sprint_id = sprint_id
                    for task in plan.tasks:
                        task.sprint_id = sprint_id

                    logger.debug(f"Fallback: All tickets -> Sprint {sprint_id}")
                    is_add_task_mode = pending.get("is_add_task_mode", False)
                    del self.pending_sprint_selection[channel_id]
                    if is_add_task_mode:
                        self._create_add_task_tickets(plan, channel_id)
                    else:
                        self._create_tickets(plan, channel_id)
                else:
                    self._send_and_log(channel_id, f"請輸入 1-{backlog_num} 的數字 ({backlog_num} = Backlog)，或說明如何分配", "validation")
            except ValueError:
                self._send_and_log(channel_id, f"無法解析，請輸入數字 ({backlog_num} = Backlog) 或說明分配方式", "validation")

    def _handle_user_selection(self, user_input: str, channel_id: str):
        """Handle user's selection when there are ambiguous users."""
        pending = self.pending_user_selection.get(channel_id)
        if not pending:
            return
        
        plan = pending["plan"]
        candidates = pending["candidates"]
        field = pending["field"]  # 'assignee' or future fields
        original_query = pending["original_query"]
        target_draft = pending.get("target_draft")  # Which ticket draft to update
        sprints = pending.get("sprints", [])  # Saved sprints for later
        
        user_input = user_input.strip()
        selected_account_id = None
        selected_display_name = None
        
        # Try to parse as number
        try:
            choice = int(user_input)
            if 1 <= choice <= len(candidates):
                selected = candidates[choice - 1]
                selected_account_id = selected["account_id"]
                selected_display_name = selected["display_name"]
            else:
                self._send_and_log(channel_id, f"請輸入 1-{len(candidates)} 的數字來選擇", "validation")
                return
        except ValueError:
            # User might type the name instead of number
            matched = None
            for c in candidates:
                if user_input.lower() in c["display_name"].lower() or user_input.lower() in c.get("email", "").lower():
                    if matched:
                        self._send_and_log(channel_id, f"仍有多個符合，請輸入數字來選擇", "validation")
                        return
                    matched = c
            
            if matched:
                selected_account_id = matched["account_id"]
                selected_display_name = matched["display_name"]
            else:
                self._send_and_log(channel_id, f"無法辨識，請輸入數字來選擇", "validation")
                return
        
        # Apply selection
        logger.info(f"User selected: {selected_display_name} (accountId: {selected_account_id})")
        
        if target_draft:
            target_draft.assignee = selected_account_id
            logger.debug(f"Updated {field} to {selected_account_id} for ticket: {target_draft.summary}")
        else:
            if plan.story and plan.story.assignee == original_query:
                plan.story.assignee = selected_account_id
            for task in plan.tasks:
                if task.assignee == original_query:
                    task.assignee = selected_account_id
        
        # Clear pending user selection
        del self.pending_user_selection[channel_id]
        
        # Check if there are more ambiguous assignees
        next_ambiguous = self._check_ambiguous_assignees(plan)
        if next_ambiguous:
            # Still have more ambiguous users to resolve
            self.pending_user_selection[channel_id] = {
                "plan": plan,
                "field": "assignee",
                "candidates": next_ambiguous["candidates"],
                "original_query": next_ambiguous["query"],
                "target_draft": next_ambiguous.get("target_draft"),
                "sprints": sprints,
            }
            self._send_and_log(channel_id, next_ambiguous["message"], "clarification")
            return
        
        # All assignees resolved - now continue to sprint selection (if applicable)
        is_add_task_mode = pending.get("is_add_task_mode", False)
        story_info = pending.get("story_info")
        
        if sprints:
            self.pending_sprint_selection[channel_id] = {
                "plan": plan, 
                "sprints": sprints,
                "is_add_task_mode": is_add_task_mode,
                "story_info": story_info,
            }
            
            is_bug_mode = plan.intent_type == "bug"
            is_operational_mode = plan.intent_type == "operational"
            
            if is_add_task_mode:
                ticket_count = len(plan.tasks)
                ticket_summary = f"📋 將為 **{plan.parent_story_key}** 補建 {ticket_count} 張 Task\n\n"
            elif is_bug_mode:
                ticket_count = len(plan.tasks)
                ticket_summary = f"📋 將建立 {ticket_count} 張 Bug 票\n\n"
            elif is_operational_mode:
                ticket_count = len(plan.tasks)
                ticket_summary = f"📋 將建立 {ticket_count} 張維運票 (Operational Task)\n\n"
            else:
                ticket_count = 1 + len(plan.tasks)
                ticket_summary = f"📋 將建立 {ticket_count} 張票 (1 Story + {len(plan.tasks)} Tasks)\n\n"

            sprint_options = []
            for i, s in enumerate(sprints, 1):
                state_label = f" [{s['state']}]" if s["state"] else ""
                sprint_options.append(f"  {i}. {s['name']}{state_label}")
            backlog_num = len(sprints) + 1
            sprint_options.append(f"  {backlog_num}. 不指定 Sprint (放入 Backlog)")

            msg = (
                ticket_summary
                + "請選擇 Sprint（可分別指定，或輸入數字放入 Backlog）：\n"
                + "\n".join(sprint_options)
                + "\n\n輸入數字或說明分配方式："
            )
            self._send_and_log(channel_id, msg, "sprint_selection")
        else:
            # No sprints - directly create tickets
            if is_add_task_mode:
                self._create_add_task_tickets(plan, channel_id)
            else:
                self._create_tickets(plan, channel_id)

    def _create_tickets(self, plan, channel_id: str):
        """Create Story and Task tickets (or just Bug ticket)."""
        dry_run = getattr(self, "dry_run", False)
        caller_account_id = self.caller_context.get(channel_id)

        # Check if this is a Bug or Operational ticket (no Story)
        is_bug_mode = plan.intent_type == "bug"
        is_operational_mode = plan.intent_type == "operational"

        if is_bug_mode or is_operational_mode:
            # Bug/Operational mode: Create single ticket from tasks[0]
            if not plan.tasks:
                ticket_type_name = "Bug" if is_bug_mode else "維運"
                self._send_and_log(channel_id, f"❌ 無法建立 {ticket_type_name} 票，缺少票券資訊。", "error")
                return

            bug_draft = plan.tasks[0]
            ticket_emoji = "🐛" if is_bug_mode else "🛠️"
            ticket_label = "Bug" if is_bug_mode else "Operational Task"
            if dry_run:
                bug_ticket = self.jira_service.create_ticket(bug_draft, config.JIRA_PROJECT_KEY, caller_account_id)
                sprint_info = f" [Sprint ID: {bug_draft.sprint_id}]" if bug_draft.sprint_id else ""
                fix_ver_info = f" [Fix Version: {', '.join(bug_draft.fix_versions)}]" if bug_draft.fix_versions else ""
                self._send_and_log(
                    channel_id, f"[Dry Run] {ticket_emoji} {ticket_label}: {bug_ticket.key} - {bug_draft.summary}{sprint_info}{fix_ver_info}", "ticket_created"
                )
            else:
                try:
                    bug_ticket = self.jira_service.create_ticket(bug_draft, config.JIRA_PROJECT_KEY, caller_account_id)
                    self._send_and_log(
                        channel_id,
                        f"{ticket_emoji} **{ticket_label} 建立成功**\nSummary: {bug_draft.summary}\nKey: [{bug_ticket.key}]({bug_ticket.link})",
                        "ticket_created"
                    )
                    # Success: Clear history for this session
                    self._clear_session_state(channel_id)
                except AmbiguousUserError as aue:
                    # Save state for user selection
                    self.pending_user_selection[channel_id] = {
                        "plan": plan,
                        "field": "assignee",
                        "candidates": aue.candidates,
                        "original_query": aue.query,
                        "target_draft": bug_draft,
                    }
                    self._send_and_log(channel_id, aue.format_options(), "clarification")
                except ValueError as ve:
                    self._send_and_log(channel_id, f"❌ 無法建立票券: {ve}", "error")
                except Exception as e:
                    logger.error(f"建立 {ticket_label} 票時發生錯誤: {e}")
                    self._send_and_log(channel_id, f"❌ 建立 {ticket_label} 票失敗，請檢查系統日誌或稍後再試。", "error")
            return

        # Feature mode: Create Story + Tasks
        # If LLM didn't create a Story (but we're in feature mode), create one from the first Task
        if not plan.story:
            if plan.tasks:
                # Convert first task to story
                first_task = plan.tasks[0]
                from models.ticket import TicketDraft
                plan.story = TicketDraft(
                    summary=first_task.summary.replace("-BE]", "]").replace("-FE]", "]").replace("-APP]", "]").replace("-UX]", "]"),
                    description=first_task.description,
                    issuetype="Story",
                    assignee=first_task.assignee,
                    components=[c for c in first_task.components if c not in ["BE", "FE", "APP", "UX"]],
                    labels=first_task.labels,
                    fix_versions=first_task.fix_versions,
                    due_date=first_task.due_date,
                    expected_release_date=first_task.expected_release_date,
                    system_prefixes=first_task.system_prefixes,
                )
                # Clear tasks since user said no task breakdown
                plan.tasks = []
                logger.info(f"Created Story from Task: {plan.story.summary}")
            else:
                self._send_and_log(channel_id, "❌ 無法建立 Feature 票，缺少票券資訊。", "error")
                return

        # Ensure Story has default assignee "me" (will be resolved to caller's ID later)
        if not plan.story.assignee:
            plan.story.assignee = "me"

        if dry_run:
            # A. 建立 Story
            story_ticket = self.jira_service.create_ticket(plan.story, config.JIRA_PROJECT_KEY, caller_account_id)
            sprint_info = f" [Sprint ID: {plan.story.sprint_id}]" if plan.story.sprint_id else ""
            reply_messages = [f"[Dry Run] ✅ Story: {story_ticket.key} - {plan.story.summary}{sprint_info}"]

            # B. 建立 Tasks 並連結
            if plan.tasks:
                for task_draft in plan.tasks:
                    task_ticket = self.jira_service.create_ticket(task_draft, config.JIRA_PROJECT_KEY, caller_account_id)
                    # Link: Task blocks Story
                    self._mock_link_tickets(task_ticket.key, story_ticket.key, "Blocks")
                    assignee_str = f" (Assignee: {task_draft.assignee})" if task_draft.assignee else ""
                    reply_messages.append(f"   └─ 🔨 Task: {task_ticket.key} - {task_draft.summary}{assignee_str}")

            self._send_and_log(channel_id, "\n".join(reply_messages), "ticket_created")
        else:
            # Real ticket creation
            try:
                story_ticket = self.jira_service.create_ticket(plan.story, config.JIRA_PROJECT_KEY, caller_account_id)
                reply_messages = [
                    f"✅ **Story 建立成功**\nSummary: {plan.story.summary}\nKey: [{story_ticket.key}]({story_ticket.link})"
                ]

                if plan.tasks:
                    for task_draft in plan.tasks:
                        task_ticket = self.jira_service.create_ticket(task_draft, config.JIRA_PROJECT_KEY, caller_account_id)
                        try:
                            self.jira_service.link_tickets(task_ticket.key, story_ticket.key, "Blocks")
                            link_status = "(已連結 - Blocks)"
                        except Exception as le:
                            logger.warning(f"連結失敗: {le}")
                            link_status = "(連結失敗)"
                        reply_messages.append(
                            f"   └─ 🔨 **Task**: [{task_ticket.key}]({task_ticket.link}) {link_status}"
                        )

                self._send_and_log(channel_id, "\n".join(reply_messages), "ticket_created")
                # Success: Clear history for this session
                self._clear_session_state(channel_id)

            except AmbiguousUserError as aue:
                # Save state for user selection - fallback if pre-check missed it
                # Note: Story may have been created if error occurred during Task creation
                self.pending_user_selection[channel_id] = {
                    "plan": plan,
                    "field": "assignee",
                    "candidates": aue.candidates,
                    "original_query": aue.query,
                    "target_draft": None,  # Unknown which draft caused it at this point
                }
                self._send_and_log(channel_id, aue.format_options(), "clarification")
            except ValueError as ve:
                logger.error(f"輸入資料錯誤: {ve}")
                self._send_and_log(channel_id, f"❌ 無法建立票券: {ve}", "error")
            except Exception as e:
                logger.error(f"建立票券時發生錯誤: {e}")
                self._send_and_log(channel_id, "❌ 建立票券失敗，請檢查系統日誌或稍後再試。", "error")

    def _create_add_task_tickets(self, plan, channel_id: str):
        """
        Create Task tickets for an existing Story (add_task mode).
        
        Args:
            plan: TicketPlan with parent_story_key set and tasks to create
            channel_id: Channel identifier
        """
        dry_run = getattr(self, "dry_run", False)
        caller_account_id = self.caller_context.get(channel_id)
        parent_story_key = plan.parent_story_key

        if not plan.tasks:
            self._send_and_log(channel_id, "❌ 沒有要建立的 Task。", "error")
            return

        if not parent_story_key:
            self._send_and_log(channel_id, "❌ 缺少 Story Key，無法建立 Task。", "error")
            return

        if dry_run:
            reply_messages = [f"[Dry Run] 📎 為 **{parent_story_key}** 補建 Task："]
            for task_draft in plan.tasks:
                task_ticket = self.jira_service.create_ticket(task_draft, config.JIRA_PROJECT_KEY, caller_account_id)
                # Link: Task blocks Story
                self._mock_link_tickets(task_ticket.key, parent_story_key, "Blocks")
                assignee_str = f" (Assignee: {task_draft.assignee})" if task_draft.assignee else ""
                sprint_info = f" [Sprint ID: {task_draft.sprint_id}]" if task_draft.sprint_id else ""
                reply_messages.append(f"   └─ 🔨 Task: {task_ticket.key} - {task_draft.summary}{assignee_str}{sprint_info}")

            self._send_and_log(channel_id, "\n".join(reply_messages), "ticket_created")
        else:
            # Real ticket creation
            try:
                reply_messages = [f"📎 **為 {parent_story_key} 補建 Task 成功**"]
                
                for task_draft in plan.tasks:
                    task_ticket = self.jira_service.create_ticket(task_draft, config.JIRA_PROJECT_KEY, caller_account_id)
                    try:
                        self.jira_service.link_tickets(task_ticket.key, parent_story_key, "Blocks")
                        link_status = "(已連結 - Blocks)"
                    except Exception as le:
                        logger.warning(f"連結失敗: {le}")
                        link_status = "(連結失敗)"
                    reply_messages.append(
                        f"   └─ 🔨 **Task**: [{task_ticket.key}]({task_ticket.link}) {link_status}"
                    )

                self._send_and_log(channel_id, "\n".join(reply_messages), "ticket_created")
                
                # Success: Clear history for this session
                self._clear_session_state(channel_id)

            except AmbiguousUserError as aue:
                self._send_and_log(channel_id, aue.format_options(), "clarification")
            except ValueError as ve:
                logger.error(f"輸入資料錯誤: {ve}")
                self._send_and_log(channel_id, f"❌ 無法建立票券: {ve}", "error")
            except Exception as e:
                logger.error(f"建立 Task 時發生錯誤: {e}")
                self._send_and_log(channel_id, "❌ 補建 Task 失敗，請檢查系統日誌或稍後再試。", "error")
