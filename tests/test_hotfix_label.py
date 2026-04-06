"""
Tests for _is_hotfix_version() — determines if a version name represents
a non-routine release (Hotfix) based on the last version segment.

Version format examples:
  WP2.100.6(260303)      → patch=6 → Hotfix
  FNMD_26.0317.2(260401) → patch=2 → Hotfix
  FNMD_26.0317.1(260318) → patch=1 → Hotfix
  MD_26.0320.0(260320)   → patch=0 → Routine (not Hotfix)
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.bot_logic import BotLogicMixin


class TestIsHotfixVersion:
    """Test the _is_hotfix_version static method."""

    # --- Hotfix cases (patch != 0) ---

    def test_wp_patch_6(self):
        assert BotLogicMixin._is_hotfix_version("WP2.100.6(260303)") is True

    def test_fnmd_patch_2(self):
        assert BotLogicMixin._is_hotfix_version("FNMD_26.0317.2(260401)") is True

    def test_fnmd_patch_1(self):
        assert BotLogicMixin._is_hotfix_version("FNMD_26.0317.1(260318)") is True

    def test_wp_patch_5(self):
        assert BotLogicMixin._is_hotfix_version("WP2.97.5(260204)") is True

    def test_patch_10(self):
        assert BotLogicMixin._is_hotfix_version("SYS_1.2.10(261231)") is True

    # --- Routine cases (patch == 0) ---

    def test_md_patch_0(self):
        assert BotLogicMixin._is_hotfix_version("MD_26.0320.0(260320)") is False

    def test_wp_patch_0(self):
        assert BotLogicMixin._is_hotfix_version("WP2.100.0(260301)") is False

    def test_initial_version(self):
        assert BotLogicMixin._is_hotfix_version("WP 1.0.0(260101)") is False

    # --- Edge / fallback cases ---

    def test_no_date_suffix_hotfix(self):
        """Version without (YYMMDD) suffix — fallback regex should still work."""
        assert BotLogicMixin._is_hotfix_version("WP2.100.3") is True

    def test_no_date_suffix_routine(self):
        assert BotLogicMixin._is_hotfix_version("WP2.100.0") is False

    def test_unrecognized_format(self):
        """Completely unrecognized format should return False (safe default)."""
        assert BotLogicMixin._is_hotfix_version("some_random_string") is False


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
