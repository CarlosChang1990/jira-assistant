from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from models.ticket import TicketDraft, TicketPlan
import config
import logging
import datetime

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        if config.GOOGLE_API_KEY:
            self.llm = ChatGoogleGenerativeAI(
                google_api_key=config.GOOGLE_API_KEY, model="gemini-2.5-flash", temperature=0
            )
        else:
            self.llm = None
            logger.warning("缺少 Google API Key")

        self.parser = PydanticOutputParser(pydantic_object=TicketDraft)

    def _format_history(self, history: list) -> str:
        if not history:
            return ""
        s = "---對話歷史開始---\n"
        for msg in history:
            role_name = "User" if msg["role"] == "user" else "Assistant"
            s += f"{role_name}: {msg['content']}\n"
        s += "---對話歷史結束---\n"
        return s

    def parse_intent(
        self, user_message: str, history: list = None, intent_type: str = "feature", resolved_bu: dict = None, resolved_system: str = None
    ) -> Optional[TicketPlan]:
        """
        將使用者訊息解析為結構化的 TicketPlan (包含 Story 和 Tasks)。

        Args:
            intent_type: "feature" or "bug"
            resolved_bu: 已解析的 BU component, e.g. {'name': '短租(SR)', 'prefix': 'SR'}
            resolved_system: 已解析的 System Prefix, e.g. "WP"
        """
        if not self.llm:
            return None

        # 當前情境 (相對日期的當前時間)
        # 包含星期幾，幫助 LLM 正確計算相對日期（如「這禮拜五」）
        now_dt = datetime.datetime.now()
        weekday_map = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        weekday = weekday_map[now_dt.weekday()]
        now = f"{now_dt.strftime('%Y-%m-%d')} 星期{weekday} {now_dt.strftime('%H:%M:%S')}"

        history_str = self._format_history(history)
        full_input = f"{history_str}\n當前使用者訊息:\n{user_message}"

        # 更新 Parser 以支援 TicketPlan (巢狀結構)
        self.parser = PydanticOutputParser(pydantic_object=TicketPlan)

        # Build BU context string
        if resolved_bu:
            bu_context = f"**BU 已確認為: {resolved_bu['name']}** (前綴: {resolved_bu['prefix']})\n請使用此 BU 產生 Summary 和 Components。"
        else:
            bu_context = "BU 尚未確認，請從對話歷史中推斷。"

        # Build System context string
        if resolved_system:
             system_context = f"**System Prefix 已確認為: {resolved_system}**\n請將 `system_prefixes` 設為 `['{resolved_system}']`。"
        else:
             system_context = "System Prefix 尚未確認，若對話中有明確提到系統前綴(如 WP, OPS)，請填入；否則留空。"

        if intent_type == "bug":
            # Bug 票 Prompt - 單張 Bug，無 Story
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        f"""你是一個 Jira 助理，負責解析 Bug 票資訊。

{bu_context}
{system_context}

**Bug 票規則**：
- 不需要 Story，只需要一張 Bug 類型的票
- Type: `Bug`
- Summary: `[{{{{BU_PREFIX}}}}-{{{{ROLE}}}}] {{{{錯誤描述}}}}` (必須包含職能)
- Components: `[{{{{BU_COMPONENT}}}}, {{{{ROLE}}}}]` (必須包含職能)

### 職能對照表
- **後端**: `BE`
- **前端**: `FE`
- **App**: `APP`

### Assignee 解析規則 (重要!)
- 如果使用者說「給我」、「我來」、「我自己」 → `assignee: "me"`
- 如果使用者說「給 John」、「John 處理」 → `assignee: "John"`

### 輸出格式範例
有職能時:
```json
{{{{
  "story": null,
  "tasks": [
    {{{{
      "summary": "[SR-BE] 排車表資料錯誤",
      "issuetype": "Bug",
      "assignee": "me",
      "components": ["短租(SR)", "BE"],
      "system_prefixes": ["{resolved_system if resolved_system else 'WP'}"],
      "expected_release_date": "2026-01-15"
    }}}}
  ]
}}}}
```

現在時間: {{current_time}}
**請參考對話歷史來補全資訊 (BU, 職能, 系統, 日期, 負責人)。**

{{format_instructions}}
""",
                    ),
                    ("human", "{text}"),
                ]
            )
        elif intent_type == "operational":
            # Operational 票 Prompt - 單張 Operational Task，無 Story
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        f"""你是一個 Jira 助理，負責解析維運票 (Operational Task) 資訊。

{bu_context}

**維運票規則**：
- 不需要 Story，只需要一張 Operational Task 類型的票
- Type: `Operational Task`
- Summary: `[{{{{BU_PREFIX}}}}-BE] {{{{維運任務描述}}}}` (強制為 BE)
- Components: `[{{{{BU_COMPONENT}}}}, BE]` (強制為 BE)

### Assignee 解析規則 (重要!)
- 如果使用者說「給我」、「我來」、「我自己」 → `assignee: "me"`
- 如果使用者說「給 John」、「John 處理」 → `assignee: "John"`

### 輸出格式範例
有職能時:
```json
{{{{
  "story": null,
  "tasks": [
    {{{{
      "summary": "[SR-BE] 資料庫調整",
      "issuetype": "Operational Task",
      "assignee": "me",
      "components": ["短租(SR)", "BE"]
    }}}}
  ]
}}}}
```

現在時間: {{current_time}}
**請參考對話歷史來補全資訊 (BU, 負責人)。維運票不需要上版日期與系統。**

{{format_instructions}}
""",
                    ),
                    ("human", "{text}"),
                ]
            )
        else:
            # Feature 票 Prompt - 原有邏輯
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是一個協助專案經理 (Product Manager) 的 Jira 助理。 "
                        "你的目標是從使用者的自然語言需求中提取票券資訊，並依照公司複雜的業務規則進行拆票與分類。\n"
                        "**請參考上方的對話歷史 (Context) 來補全當前訊息中遺漏的資訊 (如 BU, 系統, 日期)。**\n"
                        "現在時間: {current_time}\n"
                        "\n"
                        "### 1. 職能 Component (Role)\n"
                        "\n"
                        "### 1. 職能 Component (Role)\n"
                        "以下 Component 屬於執行端職能，**只會出現在 Type='Feature Task' 的票上**，且通常這代表需要拆分出子任務：\n"
                        "- `APP`: App 前端\n"
                        "- `BE`: 後端 (Backend)\n"
                        "- `FE`: Web 前端 (Frontend)\n"
                        "- `UX`: 設計與體驗\n"
                        "\n"
                        "### 2. 業務單位 Component (BU)\n"
                        f"{bu_context}\n"
                        "**注意**：`APP`, `BE`, `FE`, `UX` 是職能 Component，不能單獨作為 Story 的唯一 Component，**Story 必須隸屬於 BU**。\n"
                        "\n"
                        "### 3. 開票策略 (重要)\n"
                        "當使用者描述一個需求時，請判斷是否涉及特定的職能 (如後端、前端)。\n"
                        "**規則 A: 主要票券 (Story)**\n"
                        "- Type: `Story`\n"
                        "- Summary: `[{{BU_PREFIX}}] {{User_Summary}}`\n"
                        "- Components: `[{{BU_COMPONENT}}]` (只能放 BU)\n"
                        "  - ❌ 錯誤: `[APP] 字體太小` (因為 APP 不是 BU)\n"
                        "  - ✅ 正確: `[AR] 字體太小` (假如是機接的 APP 需求)\n"
                        "\n"
                        "**規則 B: 職能票券 (Feature Task)**\n"
                        "- 如果使用者提到需要「後端」、「App」等，請為每個職能建立一張額外的 Task。\n"
                        "- Type: `Feature Task`\n"
                        "- Summary: `[{{BU_PREFIX}}-{{ROLE_PREFIX}}] {{User_Summary}}`\n"
                        "- Components: `[{{BU_COMPONENT}}, {{ROLE_COMPONENT}}]` (BU + Role)\n"
                        "\n"
                        "### 範例\n"
                        '使用者: "幫我開一張短租的票，排車表異常，需要後端處理"\n'
                        "輸出:\n"
                        '  Story: Summary="[SR] 排車表異常", Components=["短租(SR)"]\n'
                        "  Tasks: [\n"
                        '    {{{{ Summary="[SR-BE] 排車表異常", Components=["短租(SR)", "BE"], Type="Feature Task" }}}}\n'
                        "  ]\n"
                        "- Expected Release Date (預計上版日): YYYY-MM-DD (若使用者有提到上版時間，如「今天上版」、「明天」)。**不要填 due_date**。\n"
                        f"{system_context}\\n"
                        "  - **只需要填在 Story 上**，Task 不需要。\n"
                        "- Assignee (經辦人): \n"
                        "  - **重要**: 如果使用者說「給我」、「我來」、「我自己」，請填入 `me`。\n"
                        '  - 若使用者指定人名 (如: "後端給 John"), 請填入該名字。\n'
                        "\n"
                        "**規則 C: 人員指派與數量**\n"
                        "- Story: **預設 assignee 是 `me`** (開票者)，除非使用者特別指定其他人。\n"
                        "- Feature Task (子單): **必須**確認是誰負責。若使用者沒說，請留空，後續我會反問。\n"
                        "  - 如果使用者說「設計給我」，則設計 Task 的 assignee 是 `me`。\n"
                        '- **數量偵測**: 若使用者說 "2張前端", "兩張設計"，請產生對應數量的 Task 物件。\n'
                        "\n"
                        "### 範例\n"
                        '使用者: "幫我開一張短租的票... 需要兩張前端 (Allen, Grey) 和一張後端 (John)"\n'
                        "輸出:\n"
                        "  Story: ...\n"
                        "  Tasks: [\n"
                        '    {{{{ Summary="[SR-FE] ...", Components=["短租(SR)", "FE"], Assignee="Allen" ... }}}},\n'
                        '    {{{{ Summary="[SR-FE] ...", Components=["短租(SR)", "FE"], Assignee="Grey" ... }}}},\n'
                        '    {{{{ Summary="[SR-BE] ...", Components=["短租(SR)", "BE"], Assignee="John" ... }}}}\n'
                        "  ]\n"
                        "\n"
                        "{format_instructions}\n"
                        "若無明確職能需求，Tasks 列表可為空。若使用者只是問問題，回傳 null。",
                    ),
                    ("human", "{text}"),
                ]
            )

        chain = prompt | self.llm | self.parser

        try:
            plan = chain.invoke(
                {
                    "text": full_input,  # Use full input with history
                    "current_time": now,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )
            # Set intent_type on the plan
            if plan:
                plan.intent_type = intent_type
            return plan
        except Exception as e:
            logger.error(f"Error parsing intent: {e}")
            return None

    def parse_add_task_intent(
        self, user_message: str, history: list = None, story_info: dict = None, bu_prefix: str = None
    ) -> Optional[TicketPlan]:
        """
        解析「為既有 Story 補建 Task」的請求。

        Args:
            user_message: 使用者訊息
            history: 對話歷史
            story_info: 從 Jira 取得的 Story 資訊 (key, summary, components 等)
            bu_prefix: BU 前綴 (來自 component description，例如 "SR")

        Returns:
            TicketPlan with parent_story_key set, story=None, tasks=list
        """
        if not self.llm:
            return None

        history_str = self._format_history(history)
        full_input = f"{history_str}\n當前使用者訊息:\n{user_message}"

        # Extract story key from message
        story_key = self._extract_story_key(user_message)
        if history:
            for msg in history:
                if msg.get("role") == "user" and not story_key:
                    story_key = self._extract_story_key(msg.get("content", ""))

        # Build context from story_info
        story_context = ""
        if story_info:
            story_context = f"""
**既有 Story 資訊**:
- Key: {story_info.get('key', 'N/A')}
- Summary: {story_info.get('summary', 'N/A')}
- Components: {story_info.get('components', [])}
- Sprint ID: {story_info.get('sprint_id', 'None')}

請根據此 Story 建立對應的 Task，繼承 Story 的 BU Component。
"""
        else:
            story_context = f"**Story Key**: {story_key or '(未提供)'}"

        # Get BU component name (for setting components on task)
        bu_component = ""
        if story_info and story_info.get('components'):
            for comp in story_info['components']:
                if comp not in ['BE', 'FE', 'APP', 'UX']:
                    bu_component = comp
                    break
        
        # Use provided bu_prefix, fallback to component name if not provided
        prefix_to_use = bu_prefix or bu_component or "BU"

        self.parser = PydanticOutputParser(pydantic_object=TicketPlan)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"""你是一個 Jira 助理，負責解析「為既有 Story 補建 Task」的請求。

{story_context}

**規則**：
1. **不需要建立 Story**，只需要建立 Task (Feature Task 類型)
2. Task 必須指定負責人 (Assignee)，可以是「我/me」或指定人名
3. Task 的 Summary: **直接使用 Story 的 Summary**，只把前綴 `[{prefix_to_use}]` 替換成 `[{prefix_to_use}-{{{{ROLE}}}}]`
4. Task 的 Components: `[{bu_component or 'BU_Component'}, {{{{ROLE}}}}]`
5. **重要：每個 Task 是獨立的！如果使用者說「兩張前端分別給 A 和 B」，需要建立兩張獨立的 Task**

### 職能對照表
- **後端/BE**: `BE`
- **前端/FE**: `FE`
- **App/APP**: `APP`
- **設計/UX**: `UX`

### Assignee 解析規則
- 「給我」「我來」「我自己」→ `assignee: "me"`
- 「給 John」「John 處理」→ `assignee: "John"`

### 範例 1：單張 Task
假設 Story Summary 是: `[{prefix_to_use}] 新增人工排車訂單警示功能`

如果使用者說「加 BE task 給 Grey」，則輸出:
```json
{{{{
  "story": null,
  "tasks": [
    {{{{
      "summary": "[{prefix_to_use}-BE] 新增人工排車訂單警示功能",
      "issuetype": "Feature Task",
      "assignee": "Grey",
      "components": ["{bu_component or 'BU_Component'}", "BE"]
    }}}}
  ],
  "intent_type": "add_task",
  "parent_story_key": "{story_key or 'PROJ-1234'}"
}}}}
```

### 範例 2：多張 Task（相同職能不同負責人）
如果使用者說「一張前端給 Allen，再一張前端給 Rex，一張 App 給 Sambow，一張後端給 Jim」，則輸出 **4 張獨立的 Task**:
```json
{{{{
  "story": null,
  "tasks": [
    {{{{
      "summary": "[{prefix_to_use}-FE] 新增人工排車訂單警示功能",
      "issuetype": "Feature Task",
      "assignee": "Allen",
      "components": ["{bu_component or 'BU_Component'}", "FE"]
    }}}},
    {{{{
      "summary": "[{prefix_to_use}-FE] 新增人工排車訂單警示功能",
      "issuetype": "Feature Task",
      "assignee": "Rex",
      "components": ["{bu_component or 'BU_Component'}", "FE"]
    }}}},
    {{{{
      "summary": "[{prefix_to_use}-APP] 新增人工排車訂單警示功能",
      "issuetype": "Feature Task",
      "assignee": "Sambow",
      "components": ["{bu_component or 'BU_Component'}", "APP"]
    }}}},
    {{{{
      "summary": "[{prefix_to_use}-BE] 新增人工排車訂單警示功能",
      "issuetype": "Feature Task",
      "assignee": "Jim",
      "components": ["{bu_component or 'BU_Component'}", "BE"]
    }}}}
  ],
  "intent_type": "add_task",
  "parent_story_key": "{story_key or 'PROJ-1234'}"
}}}}
```

{{format_instructions}}
""",
                ),
                ("human", "{text}"),
            ]
        )

        try:
            chain = prompt | self.llm | self.parser
            plan = chain.invoke(
                {
                    "text": full_input,
                    "format_instructions": self.parser.get_format_instructions(),
                }
            )
            if plan:
                plan.intent_type = "add_task"
                plan.parent_story_key = story_key
            return plan
        except Exception as e:
            logger.error(f"Error parsing add_task intent: {e}")
            return None

    def _extract_story_key(self, text: str) -> Optional[str]:
        """
        從文字中提取 Jira Story Key (如 PROJ-1234) 或從 URL 中提取。
        
        Returns:
            Story key (e.g., 'PROJ-1234') 或 None
        """
        import re
        
        # Pattern 1: Direct key format (PROJ-1234)
        key_pattern = re.compile(r'\b([A-Z][A-Z0-9]+-\d+)\b')
        
        # Pattern 2: URL format (https://jira.xxx.com/browse/PROJ-1234)
        url_pattern = re.compile(r'browse/([A-Z][A-Z0-9]+-\d+)')
        
        # Try URL first (more specific)
        url_match = url_pattern.search(text)
        if url_match:
            return url_match.group(1)
        
        # Then try direct key
        key_match = key_pattern.search(text)
        if key_match:
            return key_match.group(1)
        
        return None

    def _detect_ticket_type_from_history(self, history: list, current_message: str) -> dict:
        """
        Pre-detect ticket type from conversation history using two-level keyword matching.
        
        Returns: dict with:
            - 'type': 'add_task', 'bug', 'feature', 'operational', 'unknown', or 'conflict'
            - 'conflict_types': list of conflicting types (only when type='conflict')
            - 'declaration_matches': dict of {type: [matched_keywords]} for debugging
        
        Priority:
        1. Add-task intent (補建 Task) - highest priority
        2. Declaration keywords (Level 1): 使用者明確指定票券類型，如「功能」「bug」
        3. Content keywords (Level 2): 描述內容中出現的詞，如「錯誤」「異常」
        
        Rules:
        - Declaration keywords always override Content keywords
        - If multiple Declaration keywords conflict → return 'conflict' for user to choose
        - Content keywords are only used when no Declaration keywords match
        """
        # Combine all user messages
        all_text = current_message.lower()
        original_text = current_message  # Keep original case for key extraction
        if history:
            for msg in history:
                if msg.get("role") == "user":
                    all_text += " " + msg.get("content", "").lower()
                    original_text += " " + msg.get("content", "")

        # 0. Check for add-task intent (highest priority)
        add_task_keywords = [
            "補建", "增補", "新增任務", "加開task", "補task", "補開", 
            "補 task", "加 task", "補建task", "增加task", "增加 task",
            "加task", "新增task", "新增 task", "加開 task",
            "補一張", "補一個", "補張", "補個", "幫我補"
        ]
        add_task_pattern_keywords = ["增加", "新增", "加", "補"]
        task_indicator = "task" in all_text
        
        has_add_task_intent = any(kw in all_text for kw in add_task_keywords)
        if not has_add_task_intent and task_indicator:
            has_add_task_intent = any(kw in all_text for kw in add_task_pattern_keywords)
        
        story_key = self._extract_story_key(original_text)
        
        if has_add_task_intent and story_key:
            return {"type": "add_task", "conflict_types": [], "declaration_matches": {}}

        # ========================================
        # Two-Level Keyword System
        # ========================================
        
        # Level 1: Declaration keywords - 使用者用來「指定票券類型」的詞
        # These are words that NAME the ticket type (meta-level)
        DECLARATION_KEYWORDS = {
            "feature": ["功能", "功能票", "需求", "feature", "新功能", "story", "開發"],
            "bug": ["bug", "bug票", "bug單", "開bug"],
            "operational": ["維運", "維運票", "op票", "operational", "開維運"]
        }
        
        # Level 2: Content keywords - 出現在描述中，暗示問題性質的詞
        # These are words that DESCRIBE the issue (content-level)
        CONTENT_KEYWORDS = {
            "bug": ["錯誤", "壞掉", "異常", "修復", "修正", "失敗", "問題"]
            # Note: Feature doesn't need content keywords - if no declaration, it's unknown
        }
        
        # Step 1: Find all declaration matches
        declaration_matches = {}
        for intent_type, keywords in DECLARATION_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in all_text]
            if matched:
                declaration_matches[intent_type] = matched
        
        # Step 2: Find all content matches
        content_matches = {}
        for intent_type, keywords in CONTENT_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in all_text]
            if matched:
                content_matches[intent_type] = matched
        
        # Step 3: Decision logic
        result = {
            "type": "unknown",
            "conflict_types": [],
            "declaration_matches": declaration_matches
        }
        
        if len(declaration_matches) == 1:
            # Only one declaration type → use it (ignore content keywords)
            result["type"] = list(declaration_matches.keys())[0]
            logger.debug(f"[DETECT] Single declaration match: {result['type']} (keywords: {declaration_matches})")
        
        elif len(declaration_matches) > 1:
            # Multiple declaration types conflict → ask user
            result["type"] = "conflict"
            result["conflict_types"] = list(declaration_matches.keys())
            logger.debug(f"[DETECT] Declaration conflict: {result['conflict_types']} (keywords: {declaration_matches})")
        
        elif len(content_matches) >= 1:
            # No declaration, only content → use content (lower priority)
            if len(content_matches) > 1:
                # Multiple content types conflict → also ask user
                result["type"] = "conflict"
                result["conflict_types"] = list(content_matches.keys())
                logger.debug(f"[DETECT] Content conflict: {result['conflict_types']} (keywords: {content_matches})")
            else:
                # Single content type → use it
                result["type"] = list(content_matches.keys())[0]
                logger.debug(f"[DETECT] Content-based inference: {result['type']} (keywords: {content_matches})")
        
        else:
            # No matches at all
            result["type"] = "unknown"
            logger.debug("[DETECT] No keywords matched, returning unknown")
        
        return result

    def needs_clarification(self, user_message: str, history: list = None, known_prefixes: list = None) -> dict:
        """
        判斷使用者的需求是否需要進一步澄清。

        Returns:
            dict: {'needs_clarification': bool, 'missing_fields': list[str]}
        """
        if not self.llm:
            return {"needs_clarification": False, "missing_fields": []}

        # Pre-detect ticket type using code (more reliable than LLM)
        detection_result = self._detect_ticket_type_from_history(history, user_message)
        detected_type = detection_result.get("type", "unknown")
        conflict_types = detection_result.get("conflict_types", [])
        logger.debug(f"[PRE-DETECT TICKET TYPE] {detection_result}")

        # Handle conflict - return early so bot_logic can ask user
        if detected_type == "conflict":
            return {
                "needs_clarification": True,
                "missing_fields": ["Ticket Type"],
                "intent_type": "conflict",
                "conflict_types": conflict_types,
                "declaration_matches": detection_result.get("declaration_matches", {}),
            }

        # Special handling for add_task mode - use code-based checking instead of LLM
        if detected_type == "add_task":
            # For add_task, we need: Story Key + Role + Assignee
            story_key = self._extract_story_key(user_message)
            if history:
                for msg in history:
                    if msg.get("role") == "user" and not story_key:
                        story_key = self._extract_story_key(msg.get("content", ""))
            
            missing_fields = []
            
            # Combine all text for checking
            all_text = user_message.lower()
            if history:
                for msg in history:
                    if msg.get("role") == "user":
                        all_text += " " + msg.get("content", "").lower()
            
            # Check for Story Key
            if not story_key:
                missing_fields.append("Story Key")
            
            # Check for Role (BE/FE/APP/UX)
            role_keywords = ["be", "後端", "後端", "fe", "前端", "app", "ux", "設計"]
            has_role = any(kw in all_text for kw in role_keywords)
            if not has_role:
                missing_fields.append("Role")
            
            # Check for Assignee
            assignee_keywords = ["給我", "我來", "我自己", "給 ", "給", "負責"]
            has_assignee = any(kw in all_text for kw in assignee_keywords)
            # Also check for name patterns like "Grey", "John" after "給"
            if not has_assignee:
                missing_fields.append("Assignee")
            
            needs = len(missing_fields) > 0
            return {
                "needs_clarification": needs,
                "missing_fields": missing_fields,
                "intent_type": "add_task",
                "story_key": story_key,
            }

        # Format history
        # History
        history_str = self._format_history(history)
        full_input = f"{history_str}\n當前使用者訊息:\n{user_message}"
        logger.debug(f"[CLARIFICATION INPUT]\n{full_input}")

        valid_prefixes_str = ", ".join(known_prefixes) if known_prefixes else "(未知, 請檢查是否有明確系統代號)"

        # Use simple structured output to force checklist compliance

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """你是一個 Jira 助理。請根據**整個對話歷史**判斷是否已收集到開票所需的資訊。

---
## ⚠️ 最重要的規則

1. **必須從整個對話歷史中提取資訊**，不只是最後一句話
2. **條件必填欄位**：除非使用者明確說「不急」、「未定」、「不需要」，否則仍視為缺少
3. **已經提過的欄位不要再問**
4. **負責人 (Assignee) 判斷**：
   - 「給我」、「票給我」、「我來處理」→ Assignee = me ✅
   - 「給 John」、「John 處理」→ Assignee = John ✅

---
## 第一步：判斷票券類型

從對話歷史中尋找以下關鍵字：
- **Feature**: 「功能」、「功能票」、「需求」、「feature」、「新功能」、「開發」
- **Bug**: 「bug」、「bug票」、「bug單」、「開bug」、「錯誤」、「壞掉」、「異常」、「修復」、「修正」
- **Operational**: 「維運」、「維運票」、「op票」、「operational」、「開維運」
- **Unknown**: 完全沒有上述關鍵字

---
## 第二步：檢查欄位 (依票券類型)

### Feature 票
| 欄位 | 類別 | 說明 |
|------|------|------|
| Ticket Type | 必填 | 必須明確是 Feature |
| BU | 必填 | 業務單位 |
| Summary | 必填 | 功能描述 |
| Task Breakdown | 條件必填 | 需要哪些職能 (BE/FE/APP/UX)？除非使用者說「不用」「自己處理」 |
| Release Date | 條件必填 | 除非說「不急」「未定」「沒有期限」 |
| System | 條件必填 | 若有 Release Date 則需要；若「不急」則可略 |

### Bug 票
| 欄位 | 類別 | 說明 |
|------|------|------|
| Ticket Type | 必填 | 必須明確是 Bug |
| BU | 必填 | 業務單位 |
| Role | 必填 | 職能 (BE/FE/APP) |
| Summary | 必填 | 錯誤描述 |
| Assignee | 必填 | 負責修復的人 |
| Release Date | 條件必填 | 除非說「不急」「未定」 |
| System | 條件必填 | 若有 Release Date 則需要 |

### Operational 票 (維運票)
| 欄位 | 類別 | 說明 |
|------|------|------|
| Ticket Type | 必填 | 必須明確是 Operational (維運) |
| BU | 必填 | 業務單位 |
| Summary | 必填 | 維運任務描述 |
| Assignee | 必填 | 負責執行的人 |

---
## 條件必填規則

**Task Breakdown** (僅 Feature 票):
- ✅ OK: 使用者說「不用」「不需要」「自己處理」「只開 Story」
- ✅ OK: 使用者提供職能如「BE」「後端」「前端 + App」
- ❌ Missing: 完全沒提到是否需要職能子單

**Release Date**:
- ✅ OK: 使用者說「不急」「未定」「沒有deadline」「先不指定日期」
- ✅ OK: 使用者提供具體日期如「明天」「1/15」「下週」
- ❌ Missing: 完全沒提到上版時間

**System** (系統別):
- ✅ OK: Release Date 為「不急」時，System 自動視為 OK
- ✅ OK: 使用者提到系統如「WP」「NGS」「CMS」
- ❌ Missing: 有 Release Date 但沒提 System

---
## 輸出 JSON

```json
{{
  "intent_type": "feature" 或 "bug" 或 "operational" 或 "unknown",
  "missing_fields": ["列出所有缺少的必填和條件必填欄位"],
  "is_clear": true 或 false
}}
```

---
## 範例

### 範例 1: 剛開始對話
User: 幫我開一張短租票

分析:
- Ticket Type: Unknown (只說「開票」，不知道是 Feature 還是 Bug) ❌
- BU: 短租 ✅
- Summary: 未提及 ❌
- Release Date: 未提及 ❌

```json
{{
  "intent_type": "unknown",
  "missing_fields": ["Ticket Type", "Summary", "Release Date"],
  "is_clear": false
}}
```

### 範例 2: 完整的 Feature 請求
User: 幫我開一張短租的功能票，排車表要新增欄位，WP系統，明天要上版

分析:
- Ticket Type: Feature ✅
- BU: 短租 ✅
- Summary: 排車表要新增欄位 ✅
- Release Date: 明天 ✅
- System: WP ✅

```json
{{
  "intent_type": "feature",
  "missing_fields": [],
  "is_clear": true
}}
```

### 範例 3: 明確說不急
User: 短租功能票，排車表新增欄位，不急

分析:
- Ticket Type: Feature ✅
- BU: 短租 ✅
- Summary: 排車表新增欄位 ✅
- Release Date: 「不急」(明確 opt-out) ✅
- System: 因為「不急」，自動 OK ✅

```json
{{
  "intent_type": "feature",
  "missing_fields": [],
  "is_clear": true
}}
```

### 範例 4: 多輪對話 (重要！)
對話歷史:
  User: 短租的bug票，車籍查詢錯誤，今天要上
  Assistant: 請問這是 功能 還是 Bug？
  User: bug

分析 (必須從整個歷史提取):
- Ticket Type: Bug (User 說了「bug」) ✅
- BU: 短租 (從歷史: 「短租的bug票」) ✅
- Summary: 車籍查詢錯誤 (從歷史) ✅
- Release Date: 今天 (從歷史: 「今天要上」) ✅
- Role: 未提及 ❌
- Assignee: 未提及 ❌
- System: 未提及 ❌

```json
{{
  "intent_type": "bug",
  "missing_fields": ["Role", "Assignee", "System"],
  "is_clear": false
}}
```

**開始分析**：
""",
                ),
                ("human", "{text}"),
            ]
        )

        try:
            chain = prompt | self.llm
            response = chain.invoke({"text": full_input, "valid_prefixes_str": valid_prefixes_str})
            content = response.content.strip()
            # Clean up JSON if LLM wraps it in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import json

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Fallback for single quotes which LLMs sometimes use
                import ast

                try:
                    data = ast.literal_eval(content)
                except Exception:
                    # If both fail, raise the original JSON error or log it
                    logger.warning(f"Failed to parse JSON with both json and ast. Content: {content}")
                    raise

            logger.debug(f"needs_clarification JSON: {data}")

            missing = data.get("missing_fields", [])
            is_clear = data.get("is_clear", True)
            intent_type = data.get("intent_type", "feature")  # Default to feature

            # Override with code-detected type if LLM got it wrong
            if detected_type != "unknown":
                intent_type = detected_type
                # Also remove Ticket Type from missing fields if we detected it
                missing = [f for f in missing if f != "Ticket Type"]

            needs = (not is_clear) or bool(missing)
            return {"needs_clarification": needs, "missing_fields": missing, "intent_type": intent_type}

        except Exception as e:
            logger.error(f"Error checking clarification: {e}")
            # Fallback to conservative True
            return {"needs_clarification": True, "missing_fields": []}

    def get_clarification_question(
        self, user_message: str, history: list = None, known_prefixes: list = None, missing_fields: list = None
    ) -> str:
        """
        生成澄清問題。
        """
        if not self.llm:
            return "需求不夠清晰，請再描述一次。"

        history_str = self._format_history(history)
        full_input = f"{history_str}\n當前使用者訊息:\n{user_message}"

        prefix_str = ", ".join(known_prefixes) if known_prefixes else "我們好像沒有已知的系統前綴，能請您提供嗎？"

        # Build prompt based on missing_fields
        missing_fields = missing_fields or []
        
        # Composite field descriptions (for combined questions)
        composite_descriptions = {
            "TaskPlan": "任務規劃 - 這張票需要拆給其他職能處理嗎？如需要，請提供職能及負責人（例如：BE 給 John, FE 給 Mary）；如不需要請說「不用」",
            "ReleasePlan": "上版規劃 - 請問預計什麼時候上版、上哪個系統？（例如：0115 上 WP）；如不急請說「不急」",
        }
        
        # Single field descriptions
        field_descriptions = {
            "Ticket Type": "票券類型 (功能/需求、Bug/錯誤、還是 維運/Operational？ 請列出這三種供選擇)",
            "BU": "業務單位 (短租, 長租, 機接, 訂閱, 會員, 中台...)",
            "Role": "職能 (BE/FE/APP/UX)",
            "Task Breakdown": "需要哪些職能處理？(例如: BE/FE/APP/UX，或回答「不用」)",
            "Assignee": "負責人 (是誰要負責這張票？例如：給我、給 John)",
            "Release Date": "預計上版日期",
            "System": "系統前綴 (請提供系統代號，例如: WP, OPS, NGS...)",
            "Summary": "內容描述",
            "Story Key": "Story 票號 (請提供既有 Story 的 Key，例如: PROJ-1234 或 Jira 連結)",
        }
        
        # Process missing_fields: combine related fields into composite fields
        processed_fields = []
        fields_to_skip = set()
        
        # Check for TaskPlan composite (Task Breakdown + Assignee)
        if "Task Breakdown" in missing_fields and "Assignee" in missing_fields:
            processed_fields.append("TaskPlan")
            fields_to_skip.add("Task Breakdown")
            fields_to_skip.add("Assignee")
        
        # Check for ReleasePlan composite (Release Date + System)
        if "Release Date" in missing_fields and "System" in missing_fields:
            processed_fields.append("ReleasePlan")
            fields_to_skip.add("Release Date")
            fields_to_skip.add("System")
        
        # Add remaining single fields
        for field in missing_fields:
            if field not in fields_to_skip:
                processed_fields.append(field)
        
        # Build display string for prompt
        missing_str = ", ".join(processed_fields) if processed_fields else "(未知)"
        
        # Build field explanation for processed fields
        field_explanation_lines = []
        for field in processed_fields:
            if field in composite_descriptions:
                field_explanation_lines.append(f"- {field}: {composite_descriptions[field]}")
            elif field in field_descriptions:
                field_explanation_lines.append(f"- {field}: {field_descriptions[field]}")
        
        field_explanation = "\n".join(field_explanation_lines) if field_explanation_lines else "(無需說明)"

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"""你是一個 Jira 助理。使用者的需求不夠清晰，無法開票。

**⚠️ 你的唯一任務：詢問以下缺少的資訊**
`{missing_str}`

**嚴格規則**：
1. **只能**詢問上面列出的欄位，**絕對禁止**詢問其他欄位。
2. **絕不要**詢問使用者「您的角色是什麼」，而是問「請問這張票是給哪個職能 (Role)？例如 BE/FE/APP？」
3. 語氣親切，一次問完所有缺少欄位。

**以下是需要詢問的欄位說明** (只問這些):
{field_explanation}

""",
                ),
                ("human", "{{text}}"),
            ]
        )

        try:
            response = self.llm.invoke(prompt.format_messages(text=full_input, prefix_list=prefix_str))
            return response.content
        except Exception as e:
            logger.error(f"Error generating clarification: {e}")
            return "請問您可以提供更多關於這個票券的細節嗎？"

    def parse_sprint_assignment(self, user_input: str, tickets: list, sprints: list) -> dict:
        """
        Use LLM to parse user's Sprint assignment for multiple tickets.

        Args:
            user_input: User's response like "全部當前sprint" or "Story放129, Task放130"
            tickets: List of ticket info dicts [{'type': 'Story', 'summary': '...'}, ...]
            sprints: List of sprint dicts [{'id': 123, 'name': 'Sprint 129', 'state': 'active'}, ...]

        Returns:
            dict mapping ticket index to sprint_id, e.g. {0: 2060, 1: 2060, 2: 2061}
        """
        if not self.llm:
            return {}

        # Build ticket list for prompt
        ticket_list = "\n".join([f"  {i}. [{t['type']}] {t['summary']}" for i, t in enumerate(tickets)])

        # Build sprint list for prompt
        sprint_list = "\n".join(
            [f"  {i+1}. {s['name']} (id: {s['id']}, state: {s['state']})" for i, s in enumerate(sprints)]
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """你是一個 Sprint 分配助理。根據使用者的回覆，判斷每張票應該放到哪個 Sprint。

**可用的票券列表**:
{ticket_list}

**可用的 Sprint 列表**:
  0. Backlog (不指定 Sprint)
{sprint_list}

**解析規則**:
1. 如果使用者說「全部」、「都」、「所有」+ Sprint，則所有票放同一個 Sprint
2. 如果使用者說「當前」、「active」、「現在的」，對應第一個 (active) Sprint
3. 如果使用者說「下個」、「next」，對應第二個 Sprint
4. 如果使用者指定數字如「1」、「Sprint 129」，找到對應的 Sprint
5. 如果使用者分別指定，如「Story 放 129，Task 放 130」，則分別設定
6. 如果使用者說「不要sprint」、「放backlog」、「不指定」、「0」，則 value 為 null

**輸出格式** (必須是有效的 JSON):
回傳一個 JSON 物件，key 是票的索引 (0-based)，value 是 Sprint ID 或 null (表示 Backlog)。
範例: {{"0": 2060, "1": 2060, "2": 2061}}
範例 (Backlog): {{"0": null, "1": null, "2": null}}

只輸出 JSON，不要其他文字。""",
                ),
                ("human", "{user_input}"),
            ]
        )

        try:
            response = self.llm.invoke(
                prompt.format_messages(ticket_list=ticket_list, sprint_list=sprint_list, user_input=user_input)
            )

            # Parse JSON response
            import json
            import re

            content = response.content.strip()
            # Extract JSON from response (may be wrapped in markdown)
            json_match = re.search(r"\{[^}]+\}", content)
            if json_match:
                result = json.loads(json_match.group())
                # Convert string keys to int
                return {int(k): v for k, v in result.items()}
            else:
                logger.warning(f"Could not parse Sprint assignment JSON: {content}")
                return {}

        except Exception as e:
            logger.error(f"Error parsing sprint assignment: {e}")
            return {}
