import sys
import logging
import argparse
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from services.mattermost import MattermostBot

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Simple handler for Cloud Run health checks."""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def log_message(self, format, *args):
        # Suppress logging to keep logs clean
        pass


def start_health_server():
    """Starts a background HTTP server for health checks."""
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check server listening on port {port}")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Jira Assistant Mattermost Bot")
    args = parser.parse_args()

    # Configure logging level
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.info("啟動 Jira 助理機器人...")

    # Start health check server in background
    threading.Thread(target=start_health_server, daemon=True).start()

    # Check feature flag for Cloud Run takeover
    bot_enabled = os.getenv("BOT_ENABLED", "true").lower() == "true"
    
    if not bot_enabled:
        logger.warning("⚠️ BOT_ENABLED is false. Bot is disabled (Health check only).")
        # Just keep the process alive for health checks
        while True:
            import time
            time.sleep(3600)
        return

    try:
        bot = MattermostBot()
        bot.start()
    except KeyboardInterrupt:
        logger.info("使用者停止了機器人。")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
