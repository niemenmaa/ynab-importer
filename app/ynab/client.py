"""
YNAB API Client

Wrapper around the YNAB API for fetching categories and creating transactions.
"""

import httpx
from typing import List, Dict, Any, Optional
from app.config import get_settings


class YNABClient:
    """Client for interacting with the YNAB API."""
    
    BASE_URL = "https://api.ynab.com/v1"
    
    def __init__(self):
        settings = get_settings()
        self.api_token = settings.ynab_api_token
        self.budget_id = settings.budget_id
        self._categories_cache: Optional[List[Dict]] = None
        self._accounts_cache: Optional[List[Dict]] = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an API request to YNAB."""
        url = f"{self.BASE_URL}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                json=data,
                timeout=30.0,
            )
            
            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                raise YNABAPIError(
                    status_code=response.status_code,
                    message=error_data.get("error", {}).get("detail", "Unknown error"),
                )
            
            return response.json()
    
    async def get_budgets(self) -> List[Dict[str, Any]]:
        """Get list of all budgets."""
        response = await self._request("GET", "/budgets")
        return response.get("data", {}).get("budgets", [])
    
    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get list of accounts for the configured budget."""
        if self._accounts_cache is not None:
            return self._accounts_cache
        
        if not self.budget_id:
            return []
        
        response = await self._request("GET", f"/budgets/{self.budget_id}/accounts")
        accounts = response.get("data", {}).get("accounts", [])
        
        # Filter to only open accounts
        self._accounts_cache = [
            acc for acc in accounts 
            if not acc.get("closed", False) and not acc.get("deleted", False)
        ]
        return self._accounts_cache
    
    async def get_categories(self) -> List[Dict[str, Any]]:
        """
        Get list of categories for the configured budget.
        
        Returns flattened list of categories with group info.
        """
        if self._categories_cache is not None:
            return self._categories_cache
        
        if not self.budget_id:
            return []
        
        response = await self._request("GET", f"/budgets/{self.budget_id}/categories")
        category_groups = response.get("data", {}).get("category_groups", [])
        
        # Flatten categories with group info
        categories = []
        for group in category_groups:
            # Skip internal categories
            if group.get("hidden", False) or group.get("deleted", False):
                continue
            if group.get("name") in ["Internal Master Category", "Credit Card Payments"]:
                continue
            
            group_name = group.get("name", "")
            
            for cat in group.get("categories", []):
                if cat.get("hidden", False) or cat.get("deleted", False):
                    continue
                
                categories.append({
                    "id": cat.get("id"),
                    "name": cat.get("name"),
                    "group_name": group_name,
                    "display_name": f"{group_name}: {cat.get('name')}",
                    "budgeted": cat.get("budgeted", 0),
                    "activity": cat.get("activity", 0),
                    "balance": cat.get("balance", 0),
                })
        
        self._categories_cache = categories
        return categories
    
    async def create_transactions(
        self, 
        transactions: List[Dict[str, Any]],
        account_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create transactions in YNAB.
        
        Args:
            transactions: List of transaction dicts with:
                - date: YYYY-MM-DD
                - amount: in milliunits (e.g., -45670 for -$45.67)
                - payee_name: string
                - category_id: YNAB category UUID
                - memo: optional string
                - import_id: unique ID for deduplication
            account_id: Account to add transactions to (uses first account if not specified)
        
        Returns:
            YNAB API response with created/duplicate transaction info.
        """
        if not self.budget_id:
            raise YNABAPIError(0, "Budget ID not configured")
        
        # Get account if not specified
        if not account_id:
            accounts = await self.get_accounts()
            if not accounts:
                raise YNABAPIError(0, "No accounts found in budget")
            # Use first non-tracking account
            account_id = accounts[0]["id"]
        
        # Format transactions for YNAB API
        formatted_transactions = []
        for txn in transactions:
            formatted = {
                "account_id": account_id,
                "date": txn.get("date"),
                "amount": txn.get("amount_milliunits") or int(txn.get("amount", 0) * 1000),
                "payee_name": txn.get("payee"),
                "memo": txn.get("memo", "")[:200] if txn.get("memo") else None,
                "cleared": "cleared",
                "approved": True,
            }
            
            # Add category if specified
            if txn.get("category_id"):
                formatted["category_id"] = txn["category_id"]
            
            # Add import_id for deduplication
            if txn.get("import_id"):
                formatted["import_id"] = txn["import_id"]
            
            formatted_transactions.append(formatted)
        
        # Send to YNAB
        response = await self._request(
            "POST",
            f"/budgets/{self.budget_id}/transactions",
            {"transactions": formatted_transactions},
        )
        
        data = response.get("data", {})
        
        return {
            "created": len(data.get("transaction_ids", [])),
            "duplicates": len(data.get("duplicate_import_ids", [])),
            "transactions": data.get("transactions", []),
            "duplicate_import_ids": data.get("duplicate_import_ids", []),
        }
    
    async def get_payees(self) -> List[Dict[str, Any]]:
        """Get list of payees for the configured budget."""
        if not self.budget_id:
            return []
        
        response = await self._request("GET", f"/budgets/{self.budget_id}/payees")
        payees = response.get("data", {}).get("payees", [])
        
        return [
            {"id": p["id"], "name": p["name"]}
            for p in payees
            if not p.get("deleted", False)
        ]
    
    async def get_transactions(
        self,
        since_date: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get list of transactions for the configured budget.
        
        Args:
            since_date: If specified, only transactions on or after this date 
                       will be included. Format: YYYY-MM-DD
            account_id: If specified, only transactions for this account
        
        Returns:
            List of transaction dicts with payee, category, amount, date, etc.
        """
        if not self.budget_id:
            return []
        
        # Build endpoint with optional query params
        if account_id:
            endpoint = f"/budgets/{self.budget_id}/accounts/{account_id}/transactions"
        else:
            endpoint = f"/budgets/{self.budget_id}/transactions"
        
        if since_date:
            endpoint += f"?since_date={since_date}"
        
        response = await self._request("GET", endpoint)
        transactions = response.get("data", {}).get("transactions", [])
        
        # Filter out deleted transactions and format response
        result = []
        for txn in transactions:
            if txn.get("deleted", False):
                continue
            
            result.append({
                "id": txn.get("id"),
                "date": txn.get("date"),
                "amount": txn.get("amount", 0) / 1000,  # Convert milliunits to units
                "amount_milliunits": txn.get("amount", 0),
                "payee_id": txn.get("payee_id"),
                "payee_name": txn.get("payee_name") or "",
                "category_id": txn.get("category_id"),
                "category_name": txn.get("category_name") or "",
                "memo": txn.get("memo") or "",
                "account_id": txn.get("account_id"),
                "account_name": txn.get("account_name") or "",
                "cleared": txn.get("cleared"),
                "approved": txn.get("approved", False),
            })
        
        return result


class YNABAPIError(Exception):
    """Exception raised for YNAB API errors."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"YNAB API Error ({status_code}): {message}")
