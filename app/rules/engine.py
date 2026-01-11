"""
Rules Engine for Transaction Categorization

Evaluates categorization rules against transactions in priority order.
First matching rule wins.
"""

import re
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Rule
from app.parsers.op_bank import Transaction


class RulesEngine:
    """Engine for evaluating categorization rules against transactions."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._rules_cache: Optional[List[Rule]] = None
    
    async def get_rules(self) -> List[Rule]:
        """Get all active rules, ordered by priority (highest first)."""
        if self._rules_cache is None:
            result = await self.db.execute(
                select(Rule)
                .where(Rule.is_active == True)
                .order_by(Rule.priority.desc())
            )
            self._rules_cache = list(result.scalars().all())
        return self._rules_cache
    
    async def categorize_transactions(
        self, 
        transactions: List[Transaction]
    ) -> List[Dict[str, Any]]:
        """
        Apply categorization rules to a list of transactions.
        
        Returns list of transaction dicts with added category info.
        """
        rules = await self.get_rules()
        result = []
        
        for txn in transactions:
            txn_dict = txn.to_dict()
            
            # Try to find a matching rule
            matched_rule = self._find_matching_rule(txn, rules)
            
            if matched_rule:
                txn_dict["category_id"] = matched_rule.category_id
                txn_dict["category_name"] = matched_rule.category_name
                txn_dict["matched_rule_id"] = matched_rule.id
                txn_dict["matched_rule_name"] = matched_rule.name
                txn_dict["auto_categorized"] = True
            else:
                txn_dict["category_id"] = None
                txn_dict["category_name"] = None
                txn_dict["matched_rule_id"] = None
                txn_dict["matched_rule_name"] = None
                txn_dict["auto_categorized"] = False
            
            result.append(txn_dict)
        
        return result
    
    def _find_matching_rule(
        self, 
        txn: Transaction, 
        rules: List[Rule]
    ) -> Optional[Rule]:
        """
        Find the first rule that matches the transaction.
        
        Rules are already sorted by priority, so first match wins.
        """
        for rule in rules:
            if self._rule_matches(rule, txn):
                return rule
        return None
    
    def _rule_matches(self, rule: Rule, txn: Transaction) -> bool:
        """
        Check if a rule matches a transaction.
        
        All non-null conditions in the rule must match (AND logic).
        """
        # Payee exact match
        if rule.payee_exact is not None:
            if txn.payee.upper() != rule.payee_exact.upper():
                return False
        
        # Payee contains
        if rule.payee_contains is not None:
            if rule.payee_contains.upper() not in txn.payee.upper():
                return False
        
        # Payee regex
        if rule.payee_regex is not None:
            try:
                if not re.search(rule.payee_regex, txn.payee, re.IGNORECASE):
                    return False
            except re.error:
                # Invalid regex, skip this condition
                pass
        
        # Memo contains
        if rule.memo_contains is not None and txn.memo:
            if rule.memo_contains.upper() not in txn.memo.upper():
                return False
        elif rule.memo_contains is not None and not txn.memo:
            # Rule requires memo but transaction has none
            return False
        
        # Memo regex
        if rule.memo_regex is not None and txn.memo:
            try:
                if not re.search(rule.memo_regex, txn.memo, re.IGNORECASE):
                    return False
            except re.error:
                pass
        elif rule.memo_regex is not None and not txn.memo:
            return False
        
        # Amount exact match (with small tolerance for float comparison)
        if rule.amount_exact is not None:
            if abs(txn.amount - rule.amount_exact) > 0.01:
                return False
        
        # Amount range
        if rule.amount_min is not None:
            if txn.amount < rule.amount_min:
                return False
        
        if rule.amount_max is not None:
            if txn.amount > rule.amount_max:
                return False
        
        # All conditions passed
        return True
    
    async def suggest_rule(
        self, 
        txn: Transaction, 
        category_id: str, 
        category_name: str
    ) -> Dict[str, Any]:
        """
        Suggest a rule based on a transaction and chosen category.
        
        Returns a rule suggestion dict that can be used to create a new rule.
        """
        # Start with payee-based rule as the most common case
        suggestion = {
            "name": f"Rule for {txn.payee[:30]}",
            "priority": 10,
            "category_id": category_id,
            "category_name": category_name,
        }
        
        # If payee is specific enough, use exact match
        if len(txn.payee) <= 30 and " " not in txn.payee:
            suggestion["payee_exact"] = txn.payee
        else:
            # Use contains for longer/complex payees
            # Try to extract the main identifier
            words = txn.payee.split()
            if words:
                # Use first meaningful word (skip common prefixes)
                main_word = words[0]
                for word in words:
                    if len(word) > 3 and word.upper() not in ["OY", "AB", "OYJ"]:
                        main_word = word
                        break
                suggestion["payee_contains"] = main_word
        
        # If amount is a round number, it might be recurring
        if txn.amount == int(txn.amount):
            suggestion["amount_exact"] = txn.amount
        
        return suggestion
