"""
Router for Rule Suggestions

Provides endpoints for analyzing YNAB transactions and suggesting
categorization rules based on historical patterns.
"""

from datetime import date, timedelta
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import Optional, List

from app.database import get_db
from app.models import Rule
from app.ynab import YNABClient
from app.rules.analyzer import PatternAnalyzer


class SuggestionItem(BaseModel):
    payee_name: str
    category_id: str
    category_name: str
    direction: str


class BulkCreateRequest(BaseModel):
    suggestions: List[SuggestionItem]

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def suggestions_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Render the suggestions page with filters."""
    # Default date: 6 months ago
    default_since = (date.today() - timedelta(days=180)).isoformat()
    
    # Get accounts for filter dropdown
    ynab_client = YNABClient()
    accounts = await ynab_client.get_accounts()
    
    return templates.TemplateResponse(
        "suggestions.html",
        {
            "request": request,
            "default_since": default_since,
            "accounts": accounts,
        },
    )


@router.get("/analyze", response_class=HTMLResponse)
async def analyze_transactions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    since_date: Optional[str] = Query(None),
    threshold: float = Query(98.0, ge=50.0, le=100.0),
    min_transactions: int = Query(3, ge=1, le=100),
    account_id: Optional[str] = Query(None),
):
    """
    Analyze YNAB transactions and return rule suggestions.
    
    This is an HTMX endpoint that returns a partial HTML response.
    Filters out suggestions that already have existing rules.
    """
    # Fetch transactions from YNAB
    ynab_client = YNABClient()
    
    try:
        transactions = await ynab_client.get_transactions(
            since_date=since_date,
            account_id=account_id if account_id else None,
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/suggestions_error.html",
            {
                "request": request,
                "error": str(e),
            },
        )
    
    if not transactions:
        return templates.TemplateResponse(
            "partials/suggestions_empty.html",
            {
                "request": request,
                "message": "No transactions found for the selected period.",
            },
        )
    
    # Analyze patterns
    analyzer = PatternAnalyzer(
        threshold=threshold,
        min_transactions=min_transactions,
    )
    suggestions = analyzer.analyze(transactions)
    
    # Fetch existing rules to filter out already-covered payees
    existing_rules_result = await db.execute(
        select(Rule).where(Rule.is_active == True)
    )
    existing_rules = existing_rules_result.scalars().all()
    
    # Build sets of covered payees (exact and contains)
    exact_payees = {r.payee_exact.upper() for r in existing_rules if r.payee_exact}
    contains_payees = {r.payee_contains.upper() for r in existing_rules if r.payee_contains}
    
    # Filter out suggestions that already have rules
    def has_existing_rule(suggestion):
        payee_upper = suggestion.payee_name.upper()
        # Check exact match
        if payee_upper in exact_payees:
            return True
        # Check if any contains pattern matches
        for pattern in contains_payees:
            if pattern in payee_upper:
                return True
        return False
    
    filtered_suggestions = [s for s in suggestions if not has_existing_rule(s)]
    
    # Get categories for the create rule modal
    categories = await ynab_client.get_categories()
    
    return templates.TemplateResponse(
        "partials/suggestions_results.html",
        {
            "request": request,
            "suggestions": [s.to_dict() for s in filtered_suggestions],
            "total_transactions": len(transactions),
            "categories": categories,
        },
    )


@router.post("/create-rule", response_class=HTMLResponse)
async def create_rule_from_suggestion(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payee_name: str = Form(...),
    category_id: str = Form(...),
    category_name: str = Form(...),
    direction: str = Form(...),  # "incoming" or "outgoing"
    rule_type: str = Form("exact"),  # "exact" or "contains"
    priority: int = Form(10),
):
    """
    Create a new rule from a suggestion.
    
    Returns a success message partial for HTMX swap.
    """
    from sqlalchemy import select, and_, or_
    
    # Build direction label for rule name
    direction_label = "Income" if direction == "incoming" else "Expense"
    direction_suffix = f" ({direction_label})"
    
    # Check if similar rule already exists for this payee+direction
    # We check by looking at amount constraints too
    existing_query = select(Rule).where(
        Rule.is_active == True,
        or_(
            Rule.payee_exact == payee_name,
            Rule.payee_contains == payee_name,
        )
    )
    
    # Add direction-specific check
    if direction == "incoming":
        existing_query = existing_query.where(
            or_(
                Rule.amount_min >= 0,
                and_(Rule.amount_min.is_(None), Rule.amount_max.is_(None))
            )
        )
    else:
        existing_query = existing_query.where(
            or_(
                Rule.amount_max < 0,
                and_(Rule.amount_min.is_(None), Rule.amount_max.is_(None))
            )
        )
    
    existing = await db.execute(existing_query)
    existing_rule = existing.scalar_one_or_none()
    
    if existing_rule:
        return templates.TemplateResponse(
            "partials/suggestion_created.html",
            {
                "request": request,
                "success": False,
                "message": f"A rule for '{payee_name}' ({direction_label.lower()}) already exists.",
                "payee_name": payee_name,
                "direction": direction,
            },
        )
    
    # Create the rule based on type and direction
    # Use amount constraints to differentiate incoming vs outgoing
    if direction == "incoming":
        amount_min = 0.0  # Positive or zero amounts
        amount_max = None
    else:
        amount_min = None
        amount_max = -0.01  # Negative amounts only
    
    if rule_type == "exact":
        rule = Rule(
            name=f"Auto: {payee_name[:35]}{direction_suffix}",
            priority=priority,
            payee_exact=payee_name,
            amount_min=amount_min,
            amount_max=amount_max,
            category_id=category_id,
            category_name=category_name,
        )
    else:
        # Use contains for flexibility
        rule = Rule(
            name=f"Auto: {payee_name[:30]}...{direction_suffix}",
            priority=priority,
            payee_contains=payee_name,
            amount_min=amount_min,
            amount_max=amount_max,
            category_id=category_id,
            category_name=category_name,
        )
    
    db.add(rule)
    await db.commit()
    
    return templates.TemplateResponse(
        "partials/suggestion_created.html",
        {
            "request": request,
            "success": True,
            "message": f"Rule created for '{payee_name}' ({direction_label.lower()})",
            "payee_name": payee_name,
            "direction": direction,
            "rule_id": rule.id,
        },
    )


@router.post("/bulk-create")
async def bulk_create_rules(
    request: BulkCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk create rules from multiple suggestions.
    
    Returns JSON with count of created and skipped rules.
    """
    created_count = 0
    skipped_count = 0
    
    for suggestion in request.suggestions:
        payee_name = suggestion.payee_name
        direction = suggestion.direction
        direction_label = "Income" if direction == "incoming" else "Expense"
        
        # Check if rule already exists
        existing = await db.execute(
            select(Rule).where(
                Rule.is_active == True,
                or_(
                    Rule.payee_exact == payee_name,
                    Rule.payee_contains == payee_name,
                )
            )
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            continue
        
        # Set amount constraints based on direction
        if direction == "incoming":
            amount_min = 0.0
            amount_max = None
        else:
            amount_min = None
            amount_max = -0.01
        
        # Create rule with exact match
        rule = Rule(
            name=f"Auto: {payee_name[:35]} ({direction_label})",
            priority=10,
            payee_exact=payee_name,
            amount_min=amount_min,
            amount_max=amount_max,
            category_id=suggestion.category_id,
            category_name=suggestion.category_name,
        )
        db.add(rule)
        created_count += 1
    
    await db.commit()
    
    return JSONResponse({
        "created": created_count,
        "skipped": skipped_count,
    })
