"""
Pattern Analyzer for Rule Suggestions

Analyzes existing YNAB transactions to identify patterns and suggest
categorization rules based on payee/category consistency.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal


@dataclass
class RuleSuggestion:
    """A suggested rule based on transaction patterns."""
    payee_name: str
    category_id: str
    category_name: str
    direction: Literal["incoming", "outgoing"]  # income vs expense
    confidence: float  # Percentage of transactions with this category (0-100)
    transaction_count: int
    total_for_payee: int
    sample_transactions: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "payee_name": self.payee_name,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "direction": self.direction,
            "confidence": round(self.confidence, 1),
            "transaction_count": self.transaction_count,
            "total_for_payee": self.total_for_payee,
            "sample_transactions": self.sample_transactions[:5],  # Limit samples
        }


class PatternAnalyzer:
    """
    Analyzes transaction patterns to suggest categorization rules.
    
    Looks for payees where a high percentage of transactions share
    the same category, indicating a good candidate for auto-categorization.
    Analyzes incoming and outgoing transactions separately.
    """
    
    def __init__(
        self,
        threshold: float = 98.0,
        min_transactions: int = 3,
    ):
        """
        Initialize the analyzer.
        
        Args:
            threshold: Minimum percentage of transactions that must share
                      a category to suggest a rule (0-100)
            min_transactions: Minimum number of transactions required for
                            a payee to be considered for suggestions
        """
        self.threshold = threshold
        self.min_transactions = min_transactions
    
    def _get_direction(self, amount: float) -> Literal["incoming", "outgoing"]:
        """Determine if transaction is incoming (positive) or outgoing (negative)."""
        return "incoming" if amount >= 0 else "outgoing"
    
    def analyze(self, transactions: List[Dict[str, Any]]) -> List[RuleSuggestion]:
        """
        Analyze transactions and return rule suggestions.
        
        Separates incoming and outgoing transactions for each payee,
        as they often have different categories.
        
        Args:
            transactions: List of transaction dicts from YNAB API with:
                - payee_name: string
                - category_id: string (may be None for uncategorized)
                - category_name: string
                - amount: float (positive = income, negative = expense)
                - date, memo, etc.
        
        Returns:
            List of RuleSuggestion objects, sorted by confidence (highest first)
        """
        # Group transactions by (payee, direction)
        # Key: (payee_name, direction)
        grouped: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        
        for txn in transactions:
            payee = (txn.get("payee_name") or "").strip()
            if not payee:
                continue
            # Skip transfers (they start with "Transfer :")
            if payee.startswith("Transfer :"):
                continue
            
            amount = txn.get("amount", 0)
            direction = self._get_direction(amount)
            grouped[(payee, direction)].append(txn)
        
        # Analyze each (payee, direction) group's category distribution
        suggestions = []
        
        for (payee, direction), txns in grouped.items():
            # Skip if not enough transactions
            if len(txns) < self.min_transactions:
                continue
            
            # Count categories for this payee+direction
            category_counts: Dict[str, Dict[str, Any]] = defaultdict(
                lambda: {"count": 0, "name": "", "transactions": []}
            )
            
            for txn in txns:
                cat_id = txn.get("category_id")
                if not cat_id:
                    # Count uncategorized separately
                    cat_id = "__uncategorized__"
                
                category_counts[cat_id]["count"] += 1
                category_counts[cat_id]["name"] = txn.get("category_name") or "Uncategorized"
                category_counts[cat_id]["transactions"].append(txn)
            
            # Find the dominant category
            total_count = len(txns)
            for cat_id, cat_data in category_counts.items():
                # Skip uncategorized as a suggestion
                if cat_id == "__uncategorized__":
                    continue
                
                count = cat_data["count"]
                confidence = (count / total_count) * 100
                
                # Only suggest if above threshold
                if confidence >= self.threshold:
                    suggestion = RuleSuggestion(
                        payee_name=payee,
                        category_id=cat_id,
                        category_name=cat_data["name"],
                        direction=direction,
                        confidence=confidence,
                        transaction_count=count,
                        total_for_payee=total_count,
                        sample_transactions=cat_data["transactions"][:5],
                    )
                    suggestions.append(suggestion)
        
        # Sort by confidence (highest first), then by transaction count
        suggestions.sort(key=lambda s: (-s.confidence, -s.transaction_count))
        
        return suggestions
    
    def get_payee_summary(
        self, 
        transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Get a summary of all payees and their category distribution.
        
        Useful for debugging or showing all payees regardless of threshold.
        
        Returns:
            List of dicts with payee info and category breakdown
        """
        # Group by (payee, direction)
        grouped: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        
        for txn in transactions:
            payee = (txn.get("payee_name") or "").strip()
            if not payee or payee.startswith("Transfer :"):
                continue
            
            amount = txn.get("amount", 0)
            direction = self._get_direction(amount)
            grouped[(payee, direction)].append(txn)
        
        summaries = []
        
        for (payee, direction), txns in grouped.items():
            if len(txns) < self.min_transactions:
                continue
            
            # Count categories
            category_counts: Dict[str, int] = defaultdict(int)
            category_names: Dict[str, str] = {}
            
            for txn in txns:
                cat_id = txn.get("category_id") or "__uncategorized__"
                category_counts[cat_id] += 1
                category_names[cat_id] = txn.get("category_name") or "Uncategorized"
            
            # Build category breakdown
            total = len(txns)
            categories = [
                {
                    "id": cat_id,
                    "name": category_names[cat_id],
                    "count": count,
                    "percentage": round((count / total) * 100, 1),
                }
                for cat_id, count in sorted(
                    category_counts.items(), 
                    key=lambda x: -x[1]
                )
            ]
            
            summaries.append({
                "payee": payee,
                "direction": direction,
                "total_transactions": total,
                "categories": categories,
                "dominant_category": categories[0] if categories else None,
            })
        
        # Sort by transaction count
        summaries.sort(key=lambda s: -s["total_transactions"])
        
        return summaries
