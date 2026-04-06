import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path to find config and services
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import config
from services.jira_service import JiraService

class TestUserMapping(unittest.TestCase):

    def test_config_loading(self):
        print("\n--- Testing Config Loading ---")
        # Verify 'me' is loaded
        me_id = config.get_my_account_id()
        print(f"Me ID: {me_id}")
        self.assertIsNotNone(me_id)
        
        # Verify 'jenny'
        jenny_ids = config.get_account_ids_by_nickname('jenny')
        print(f"Jenny IDs: {jenny_ids}")
        self.assertTrue(len(jenny_ids) >= 1)

    @patch('services.jira_service.config.get_account_ids_by_nickname')
    def test_ambiguity_exception(self, mock_get_ids):
        print("\n--- Testing Ambiguity Handling ---")
        # Mock returning two IDs
        mock_get_ids.return_value = ["id1", "id2"]
        
        service = JiraService()
        # Mock jira client to avoid real calls
        service.jira = MagicMock()
        
        with self.assertRaises(ValueError) as cm:
            service.find_user("ambiguous_nick")
        
        print(f"Caught expected error: {cm.exception}")
        self.assertIn("Ambiguous user nickname", str(cm.exception))

    @patch('services.jira_service.config.get_account_ids_by_nickname')
    def test_single_match(self, mock_get_ids):
        print("\n--- Testing Single Match ---")
        # Mock returning one ID
        mock_get_ids.return_value = ["id1"]
        
        service = JiraService()
        service.jira = MagicMock()
        
        # Mock jira.user() return
        mock_user = MagicMock()
        mock_user.accountId = "id1"
        mock_user.displayName = "Test User"
        service.jira.user.return_value = mock_user
        
        user = service.find_user("valid_nick")
        
        print(f"Found user: {user.displayName}")
        service.jira.user.assert_called_with("id1")
        self.assertEqual(user.accountId, "id1")

if __name__ == '__main__':
    unittest.main()
