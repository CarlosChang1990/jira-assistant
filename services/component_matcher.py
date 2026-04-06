"""
Component Matcher - 從 Jira Component Name 提取關鍵字並比對使用者輸入
"""
import re
import logging
from typing import List, Optional, NamedTuple
from dataclasses import dataclass

import config

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """比對結果"""
    match_type: str  # 'single', 'multiple', 'none'
    components: List[dict]  # [{'name': '短租(SR)', 'prefix': 'SR'}]


class ComponentMatcher:
    """
    從 Jira Component Name 提取 tokens 並比對使用者輸入。
    
    Example:
        Component Name: "短租(SR)"
        Extracted Tokens: ["短租", "sr"]
    """
    
    def __init__(self, jira_service=None):
        self.jira_service = jira_service
        self.components = []  # [{'name': '短租(SR)', 'prefix': 'SR', 'tokens': ['短租', 'sr']}]
        self._cached = False
    
    def refresh_cache(self, project_key: str = None):
        """從 Jira 取得 BU Components，並提取 tokens"""
        if not self.jira_service or not self.jira_service.jira:
            logger.warning("JiraService not available, cannot refresh component cache")
            return
        
        project_key = project_key or config.JIRA_PROJECT_KEY
        
        try:
            jira_components = self.jira_service.jira.project_components(project_key)
            self.components = []
            
            excluded_names = {'APP', 'UX', 'FE', 'BE'}
            
            for comp in jira_components:
                name = comp.name
                if name.upper() in excluded_names:
                    continue

                description = getattr(comp, 'description', None)
                
                # 一律使用 description 作為 prefix (不再從 name 解析括號)
                if description and description.strip():
                    prefix = description.strip()
                else:
                    # Fallback: 如果沒有 description，用 name
                    prefix = name
                    logger.warning(f"Component '{name}' has no description, using name as prefix")
                
                # Tokens for matching: parse name into parts + description
                # e.g. "短租(SR)" -> ["短租", "sr"]
                # e.g. "基礎服務(IS)" -> ["基礎服務", "is"]
                tokens = []
                
                # Try to parse "Name(Prefix)" format
                name_match = re.match(r'^(.+?)\(([^)]+)\)$', name)
                if name_match:
                    # Add the Chinese/main part (e.g. "短租")
                    main_part = name_match.group(1).strip()
                    if main_part:
                        tokens.append(main_part.lower())
                    # Add the prefix part (e.g. "sr")
                    prefix_part = name_match.group(2).strip()
                    if prefix_part:
                        tokens.append(prefix_part.lower())
                else:
                    # No parentheses, use full name
                    tokens.append(name.lower())
                
                # Also add description if different from existing tokens
                if description and description.strip():
                    desc_lower = description.strip().lower()
                    if desc_lower not in tokens:
                        tokens.append(desc_lower)
                
                self.components.append({
                    'name': name,
                    'prefix': prefix,
                    'description': description,
                    'tokens': tokens,
                })
                logger.debug(f"Cached BU component: {name} -> prefix: {prefix}, tokens: {tokens}")
            
            self._cached = True
            logger.info(f"Cached {len(self.components)} BU components from Jira")
            
        except Exception as e:
            logger.error(f"Error refreshing component cache: {e}")
    
    def match(self, user_text: str) -> MatchResult:
        """
        比對使用者輸入中是否包含任何 BU component token。
        
        Returns:
            MatchResult with match_type: 'single', 'multiple', or 'none'
        """
        if not self._cached:
            logger.warning("Component cache not initialized, call refresh_cache() first")
            return MatchResult(match_type='none', components=[])
        
        user_text_lower = user_text.lower()
        matched = []
        
        # Tier 1: Exact Name Match (Highest Confidence)
        # Check if full component name exists in text (e.g. "財務(FN)")
        for comp in self.components:
            if comp['name'] in user_text:
                logger.info(f"[Tier 1 Match] Exact name found: {comp['name']}")
                return MatchResult(match_type='single', components=[comp])

        # Tier 2: Token Match with Word Boundary (High Confidence)
        # Use regex to ensure tokens are distinct words (e.g. "AR" matches "AR" but not "Cary")
        import re
        matched = []
        
        for comp in self.components:
            for token in comp['tokens']:
                # Detect if token is ASCII (English) or CJK
                # For English tokens, enforce word boundary
                if re.match(r'^[a-zA-Z0-9]+$', token):
                    # \b matches word boundary
                    # Escape token to handle special chars if any, though alnum usually safe
                    pattern = r'(?<![a-zA-Z0-9])' + re.escape(token) + r'(?![a-zA-Z0-9])'
                    if re.search(pattern, user_text, re.IGNORECASE):
                         matched.append(comp)
                         break
                else:
                    # For non-ASCII (Chinese), use simple substring match
                    if token in user_text_lower:
                        matched.append(comp)
                        break

        # Tier 3: Fallback (if needed, but for now Tier 2 covers most valid cases)
        # If we use strict Tier 2, we might miss some loose cases, but that's the point of the fix.
        
        # Deduplicate matched components
        seen = set()
        unique_matched = []
        for comp in matched:
            if comp['name'] not in seen:
                seen.add(comp['name'])
                unique_matched.append(comp)
        
        if len(unique_matched) == 0:
            return MatchResult(match_type='none', components=[])
        elif len(unique_matched) == 1:
            return MatchResult(match_type='single', components=unique_matched)
        else:
            return MatchResult(match_type='multiple', components=unique_matched)
    
    def get_all_bu_components(self) -> List[dict]:
        """取得所有 BU components (供 NoMatch 時列出選項)"""
        return self.components
    
    def format_options(self, components: List[dict] = None) -> str:
        """格式化 component 選項供使用者選擇"""
        if components is None:
            components = self.components
        
        lines = ["請選擇業務單位 (BU)："]
        for i, comp in enumerate(components, 1):
            lines.append(f"  {i}. {comp['name']}")
        return "\n".join(lines)
