"""
Mattermost Bot - Uses shared BotLogicMixin for ticket creation workflow.
"""

import logging
from mattermostautodriver import Driver
from collections import defaultdict
import config
import json

from services.jira_service import JiraService
from services.llm_service import LLMService
from services.bot_logic import BotLogicMixin

logger = logging.getLogger(__name__)


class MattermostBot(BotLogicMixin):
    """Mattermost bot using shared BotLogicMixin."""

    def __init__(self, dry_run=False):
        self.driver = Driver(
            {
                "url": config.MATTERMOST_URL,
                "token": config.MATTERMOST_TOKEN,
                "scheme": config.MATTERMOST_SCHEME,
                "port": config.MATTERMOST_PORT,
                "debug": False,
            }
        )
        self.bot_user_id = None

        # Services
        self.jira_service = JiraService()
        self.llm_service = LLMService()

        # Conversation History: {channel_id: [{"role": "user"/"assistant", "content": "..."}]}
        self.history = defaultdict(list)

        # Initialize shared bot logic state
        self.__init_bot_logic__()

        # Dry run mode
        self.dry_run = dry_run
        if self.dry_run:
            print("⚠️  Running in DRY RUN mode: No tickets will be created.")
            self._setup_dry_run()

    def start(self):
        """啟動機器人監聽。"""
        self.driver.login()
        self.bot_user_id = self.driver.users.get_user(user_id="me")["id"]
        print(f"機器人已啟動。 ID: {self.bot_user_id}")
        self.driver.init_websocket(self._websocket_handler)

    async def _websocket_handler(self, event):
        """處理傳入的 WebSocket 事件。"""
        if isinstance(event, str):
            try:
                event = json.loads(event)
            except json.JSONDecodeError:
                return

        if "event" in event and event["event"] == "posted":
            data = event.get("data", {})
            post_str = data.get("post", "{}")
            try:
                post = json.loads(post_str)
            except (json.JSONDecodeError, TypeError):
                return

            # 避免自我回覆
            mm_user_id = post.get("user_id")
            if mm_user_id == self.bot_user_id:
                return

            message = post.get("message", "")
            channel_id = post.get("channel_id")

            # Only respond to Direct Messages (1-on-1 DM), ignore group channels
            try:
                channel_info = self.driver.channels.get_channel(channel_id)
                channel_type = channel_info.get("type", "")
                if channel_type != "D":  # D = Direct Message
                    return  # Ignore non-DM messages
            except Exception as e:
                logger.warning(f"Failed to get channel info: {e}")
                return  # Conservatively ignore if we can't determine channel type

            # Get user nickname for logging
            user_nickname = self._get_user_nickname(mm_user_id)

            # Resolve Mattermost user to Jira Account ID
            caller_account_id = self._resolve_jira_account_id(mm_user_id)

            # Use shared handle_message from BotLogicMixin
            self.handle_message(message, channel_id, caller_account_id=caller_account_id, user_nickname=user_nickname)

    def _get_user_nickname(self, mm_user_id: str) -> str:
        """
        Get a user's display name for logging.
        Priority: nickname > first_name > username
        """
        try:
            mm_user = self.driver.users.get_user(user_id=mm_user_id)
            nickname = mm_user.get("nickname", "").strip()
            if nickname:
                return nickname
            first_name = mm_user.get("first_name", "").strip()
            if first_name:
                return first_name
            return mm_user.get("username", "UnknownUser")
        except Exception:
            return "UnknownUser"

    def _resolve_jira_account_id(self, mm_user_id: str) -> str:
        """
        Resolve a Mattermost user ID to a Jira Account ID.

        Priority:
        1. Look up username in users.json
        2. Look up email prefix in users.json
        3. Search Jira directly by email (fallback)
        """
        try:
            mm_user = self.driver.users.get_user(user_id=mm_user_id)
            username = mm_user.get("username", "")
            email = mm_user.get("email", "")

            # 1. Try username in users.json
            candidate_ids = config.get_account_ids_by_nickname(username)
            if len(candidate_ids) == 1:
                return candidate_ids[0]

            # 2. Try email prefix in users.json (e.g., john from john@example.com)
            if email:
                email_prefix = email.split("@")[0]
                candidate_ids = config.get_account_ids_by_nickname(email_prefix)
                if len(candidate_ids) == 1:
                    return candidate_ids[0]

            # 3. Fallback: Search Jira directly by email
            if email and self.jira_service.jira:
                try:
                    jira_users = self.jira_service.jira.search_users(query=email)
                    if jira_users:
                        jira_user = jira_users[0]
                        print(f"[Info] Resolved '{username}' via Jira email search: {jira_user.accountId}")
                        return jira_user.accountId
                except Exception as je:
                    print(f"[Warning] Jira email search failed: {je}")

            print(f"[Warning] Could not resolve Mattermost user '{username}' (email: {email}) to Jira Account ID")
        except Exception as e:
            print(f"[Error] Failed to resolve Mattermost user: {e}")

        return None

    def send_message(self, channel_id, message):
        """發送訊息到頻道。"""
        import os
        # Add local dev marker if running locally
        if os.getenv("LOCAL_DEV", "false").lower() == "true":
            message = f"🏠 **[LOCAL]** {message}"
        
        # Update history
        self.history[channel_id].append({"role": "assistant", "content": message})

        self.driver.posts.create_post({"channel_id": channel_id, "message": message})

    def _mock_link_tickets(self, source, target, link_type="Relates"):
        """Not used in production/real run, but used in Dry Run."""
        pass

    def _setup_dry_run(self):
        """Mock state-changing methods for dry run mode."""
        from unittest.mock import MagicMock
        
        print("🛠️ Setting up Dry Run Mocks for MattermostBot...")
        
        # 1. Ticket Creation: Mock the Service method
        self.jira_service.create_ticket = MagicMock(side_effect=self._mock_create_ticket)

        # 2. Link Tickets: Mock the Service method
        self.jira_service.link_tickets = MagicMock(side_effect=self._mock_link_tickets_dry)

        # 3. Version Creation: Mock the UNDERLYING Jira Client method
        if self.jira_service.jira:
            self.jira_service.jira.create_version = MagicMock(side_effect=self._mock_create_version)
        else:
            print("Warning: Jira client not initialized. check your .env")

    def _mock_create_ticket(self, draft, project_key, caller_account_id=None):
        """Mock ticket creation for dry run."""
        from unittest.mock import MagicMock
        import random

        rand_id = random.randint(1000, 9999)
        key = f"DRY-{rand_id}"

        print(f"\n[Dry Run] Would CREATE TICKET (Key: {key}):")
        print(f"  Summary: {draft.summary}")
        
        # Return a mock object that mimics a jira.resources.Issue
        m = MagicMock()
        m.key = key
        m.link = f"http://dry-run/{key}"
        # We need to ensure accessing attributes doesn't fail
        m.fields.summary = draft.summary
        return m

    def _mock_create_version(self, project, name, releaseDate=None, description=None):
        """Mock version creation for dry run."""
        from unittest.mock import MagicMock
        print(f"\n[Dry Run] Would CREATE VERSION: {name} (Date: {releaseDate})")
        m = MagicMock(id="99999")
        m.name = name
        return m

    def _mock_link_tickets_dry(self, source, target, link_type="Relates"):
        """Mock ticket linking for dry run."""
        print(f"\n[Dry Run] Would LINK TICKETS: {source} -> {link_type} -> {target}")
