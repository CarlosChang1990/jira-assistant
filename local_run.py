import sys
import os
import argparse
import json
from unittest.mock import MagicMock
from collections import defaultdict

import logging

# Configure logging
logger = logging.getLogger(__name__)

# Local modules
import config
from services.jira_service import JiraService
from services.llm_service import LLMService
from services.bot_logic import BotLogicMixin


import subprocess
import time
import atexit

class CloudRunManager:
    """Helper to manage Cloud Run service scaling."""
    def __init__(self):
        self.service_name = config.CLOUD_RUN_SERVICE_NAME
        self.region = config.CLOUD_RUN_REGION
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.original_min = None
        self.original_max = None

    def validate_config(self):
        if not self.service_name or not self.region:
            print("❌ Error: CLOUD_RUN_SERVICE_NAME and CLOUD_RUN_REGION must be set in .env")
            return False
        if not self.project_id:
            print("❌ Error: GCP_PROJECT_ID must be set in .env")
            return False
        return True

    def get_cloud_bot_enabled(self):
        """Check if BOT_ENABLED is true in Cloud Run."""
        try:
            cmd = [
                "gcloud", "run", "services", "describe", self.service_name,
                "--region", self.region,
                "--format=json",
                "--project", self.project_id
            ]
            logger.debug(f"🔍 Checking current Cloud Run state for {self.service_name}...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            # Navigate schema: spec -> template -> spec -> containers[0] -> env
            containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            if not containers:
                logger.debug("⚠️ No containers found in spec")
                return True # Default to True if can't find
            
            env_vars = containers[0].get("env", [])
            logger.debug(f"🔍 Found env vars: {env_vars}")

            for var in env_vars:
                if var.get("name") == "BOT_ENABLED":
                    value = var.get("value", "true").lower()
                    logger.debug(f"🔍 Found BOT_ENABLED={value}")
                    return value == "true"
            
            # Default to true if not set
            logger.debug("⚠️ BOT_ENABLED not set, defaulting to True")
            return True
        except Exception as e:
            logger.error(f"⚠️ Failed to fetch Cloud Run config: {e}")
            # Assume it's enabled so we try to disable it to be safe
            return True

    def disable_bot(self):
        """Disable the bot via env var (BOT_ENABLED=false)."""
        if not self.get_cloud_bot_enabled():
            print("✅ Cloud bot is ALREADY disabled. Skipping deployment.")
            return True

        print("🔻 Disabling Cloud Run bot (BOT_ENABLED=false)...")
        return self._set_env_var("false")

    def restore(self):
        """Enable the bot via env var (BOT_ENABLED=true)."""
        print("🔄 Enabling Cloud Run bot (BOT_ENABLED=true)...")
        self._set_env_var("true")

    def _set_env_var(self, value):
        try:
            cmd = [
                "gcloud", "run", "services", "update", self.service_name,
                "--region", self.region,
                "--update-env-vars", f"BOT_ENABLED={value}",
                "--project", self.project_id,
                "--quiet"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            print("✅ Configuration updated.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to update service: {e}")
            return False

class VMManager:
    """Helper to manage GCE VM state."""
    def __init__(self):
        self.vm_name = "jira-bot-vm"
        self.zone = "us-central1-a"
        self.project_id = os.getenv("GCP_PROJECT_ID")

    def _vm_exists(self):
        """Check if the VM exists."""
        if not self.project_id:
            logger.warning("⚠️ GCP_PROJECT_ID not set, skipping VM check.")
            return False
            
        try:
            cmd = [
                "gcloud", "compute", "instances", "describe", self.vm_name,
                "--zone", self.zone,
                "--project", self.project_id,
                "--format=json"
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def stop_vm(self):
        """Stop the VM to prevent double processing."""
        if not self._vm_exists():
            print(f"ℹ️  VM '{self.vm_name}' not found. Skipping stop.")
            return

        print(f"🔻 Stopping VM '{self.vm_name}'...")
        try:
            cmd = [
                "gcloud", "compute", "instances", "stop", self.vm_name,
                "--zone", self.zone,
                "--project", self.project_id,
                "--quiet"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            print("✅ VM stopped.")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Failed to stop VM: {e}")

    def start_vm(self):
        """Start the VM (Restore)."""
        if not self._vm_exists():
            print(f"ℹ️  VM '{self.vm_name}' not found. Skipping start.")
            return

        print(f"🔄 Starting VM '{self.vm_name}'...")
        try:
            cmd = [
                "gcloud", "compute", "instances", "start", self.vm_name,
                "--zone", self.zone,
                "--project", self.project_id,
                "--quiet"
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            print("✅ VM started.")
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Failed to start VM: {e}")

class LocalBot(BotLogicMixin):
    """Local CLI bot for testing, using shared BotLogicMixin."""

    def __init__(self, dry_run=False):
        # Services
        self.jira_service = JiraService()
        self.llm_service = LLMService()

        # Conversation History
        self.history = defaultdict(list)

        # Initialize shared bot logic state
        self.__init_bot_logic__()

        self.dry_run = dry_run
        if self.dry_run:
            print("⚠️  DRY RUN MODE: 不會真的建立票券或版本，僅顯示操作。")
            self._setup_dry_run()

    def _setup_dry_run(self):
        """Mock state-changing methods for dry run mode."""
        # 1. Ticket Creation: Mock the Service method
        self.jira_service.create_ticket = MagicMock(side_effect=self._mock_create_ticket)

        # 2. Link Tickets: Mock the Service method
        self.jira_service.link_tickets = MagicMock(side_effect=self._mock_link_tickets)

        # 3. Version Creation: Mock the UNDERLYING Jira Client method
        if self.jira_service.jira:
            self.jira_service.jira.create_version = MagicMock(side_effect=self._mock_create_version)
        else:
            print("Warning: Jira client not initialized. check your .env")

    def _mock_create_ticket(self, draft, project_key, caller_account_id=None):
        """Mock ticket creation for dry run."""
        import random

        rand_id = random.randint(1000, 9999)
        key = f"DRY-{rand_id}"

        print(f"\n[Dry Run] Would CREATE TICKET (Key: {key}):")
        print(f"  Project: {project_key}")
        print(f"  Summary: {draft.summary}")
        print(f"  Type: {draft.issuetype}")
        print(f"  Components: {draft.components}")
        print(f"  Assignee: {draft.assignee if draft.assignee else 'Unassigned'}")
        print(f"  Fix Versions: {draft.fix_versions if draft.fix_versions else 'None'}")
        print(f"  Sprint ID: {draft.sprint_id if draft.sprint_id else 'None'}")

        return MagicMock(key=key, link=f"http://dry-run/{key}", summary=draft.summary)

    def _mock_create_version(self, project, name, releaseDate=None, description=None):
        """Mock version creation for dry run."""
        print(f"\n[Dry Run] Would CREATE VERSION:")
        print(f"  Project: {project}")
        print(f"  Name: {name}")
        print(f"  Date: {releaseDate}")
        m = MagicMock(id="99999")
        m.name = name
        return m

    def _mock_link_tickets(self, source, target, link_type="Relates"):
        """Mock ticket linking for dry run."""
        print(f"\n[Dry Run] Would LINK TICKETS:")
        print(f"  {source} -> {link_type} -> {target}")

    def send_message(self, channel_id, message):
        """Print message to console."""
        # Update history
        self.history[channel_id].append({"role": "assistant", "content": message})
        print(f"\n[Bot 🤖]: {message}\n")

    def _send_and_log(self, channel_id: str, message: str, msg_type: str = "reply"):
        """Send message and log it for debugging (LocalBot override)."""
        logger.debug("=" * 60)
        logger.debug(f"[Bot 回覆] ({msg_type}): {message[:200]}..." if len(message) > 200 else f"[Bot 回覆] ({msg_type}): {message}")
        logger.debug("=" * 60)
        self.send_message(channel_id, message)

    def run_cli(self):
        """Run interactive CLI mode."""
        print("=== Jira Assistant CLI Mode (Local Testing) ===")
        print("可以直接輸入對話測試機器人回應。輸入 'exit' 或 'quit' 離開。")
        print("===============================================")

        channel_id = "local_cli"

        while True:
            try:
                user_input = input("\n[You 👤]: ")
                if user_input.lower() in ["exit", "quit"]:
                    print("Bye!")
                    break

                self.handle_message(user_input, channel_id)

            except EOFError:
                print("\nBye!")
                break
            except KeyboardInterrupt:
                print("\nBye!")
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Jira Assistant locally")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode (no actual tickets created)")
    parser.add_argument("--real", action="store_true", help="Run the REAL Mattermost bot (Auto-enables Cloud Run takeover)")
    parser.add_argument("--restore", action="store_true", help="Restore Cloud Run bot (Re-enable BOT_ENABLED)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Managers
    cr_manager = CloudRunManager()
    vm_manager = VMManager()

    # 1. Restore Mode
    if args.restore:
        print("\n=== Restoring Cloud Services ===")
        # Restore Cloud Run
        if cr_manager.validate_config():
            cr_manager.restore()
        
        # Restore VM
        vm_manager.start_vm()
        
        sys.exit(0)

    # 2. Real Mode (Takeover)
    if args.real:
        print("\n=== Preparing Local Takeover ===")
        # Disable Cloud Run
        if cr_manager.validate_config():
            if cr_manager.disable_bot():
                print("⚠️  Cloud Run Bot disabled.")
            else:
                print("⚠️ Failed to disable Cloud Run bot. Proceeding anyway...")
        else:
            print("⚠️ Cloud Run config missing or invalid. Skipping Cloud Run check.")
            
        # Stop VM
        vm_manager.stop_vm()
        print("--------------------------------")
    
    try:
        if args.real:
            # Mark as local dev for message tagging
            os.environ["LOCAL_DEV"] = "true"
            from services.mattermost import MattermostBot
            print(f"🚀 Starting REAL Mattermost Bot (LOCAL DEV MODE{' + DRY RUN' if args.dry_run else ''})...")
            bot = MattermostBot(dry_run=args.dry_run)
            bot.start()
        else:
            bot = LocalBot(dry_run=args.dry_run)
            bot.run_cli()
    except KeyboardInterrupt:
        print("\nStopping...")
        # No auto-restore
    except Exception as e:
        print(f"Error: {e}")

