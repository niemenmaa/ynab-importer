from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.models import Rule
from app.ynab import YNABClient

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def list_rules(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List all categorization rules."""
    result = await db.execute(
        select(Rule).where(Rule.is_active == True).order_by(Rule.priority.desc())
    )
    rules = result.scalars().all()
    
    # Get categories for dropdown
    ynab_client = YNABClient()
    categories = await ynab_client.get_categories()
    
    return templates.TemplateResponse(
        "rules.html",
        {
            "request": request,
            "rules": rules,
            "categories": categories,
        },
    )


@router.post("")
async def create_rule(
    request: Request,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    priority: int = Form(0),
    payee_exact: Optional[str] = Form(None),
    payee_contains: Optional[str] = Form(None),
    payee_regex: Optional[str] = Form(None),
    memo_contains: Optional[str] = Form(None),
    memo_regex: Optional[str] = Form(None),
    amount_exact: Optional[float] = Form(None),
    amount_min: Optional[float] = Form(None),
    amount_max: Optional[float] = Form(None),
    category_id: str = Form(...),
    category_name: str = Form(...),
):
    """Create a new categorization rule."""
    rule = Rule(
        name=name,
        priority=priority,
        payee_exact=payee_exact or None,
        payee_contains=payee_contains or None,
        payee_regex=payee_regex or None,
        memo_contains=memo_contains or None,
        memo_regex=memo_regex or None,
        amount_exact=amount_exact,
        amount_min=amount_min,
        amount_max=amount_max,
        category_id=category_id,
        category_name=category_name,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    
    return templates.TemplateResponse(
        "partials/rule_row.html",
        {
            "request": request,
            "rule": rule,
        },
    )


@router.delete("/{rule_id}")
async def delete_rule(
    request: Request,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a rule (soft delete by setting is_active=False)."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if rule:
        rule.is_active = False
        await db.commit()
    
    return ""


@router.put("/{rule_id}")
async def update_rule(
    request: Request,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    priority: int = Form(0),
    payee_exact: Optional[str] = Form(None),
    payee_contains: Optional[str] = Form(None),
    payee_regex: Optional[str] = Form(None),
    memo_contains: Optional[str] = Form(None),
    memo_regex: Optional[str] = Form(None),
    amount_exact: Optional[float] = Form(None),
    amount_min: Optional[float] = Form(None),
    amount_max: Optional[float] = Form(None),
    category_id: str = Form(...),
    category_name: str = Form(...),
):
    """Update an existing rule."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if rule:
        rule.name = name
        rule.priority = priority
        rule.payee_exact = payee_exact or None
        rule.payee_contains = payee_contains or None
        rule.payee_regex = payee_regex or None
        rule.memo_contains = memo_contains or None
        rule.memo_regex = memo_regex or None
        rule.amount_exact = amount_exact
        rule.amount_min = amount_min
        rule.amount_max = amount_max
        rule.category_id = category_id
        rule.category_name = category_name
        await db.commit()
        await db.refresh(rule)
    
    return templates.TemplateResponse(
        "partials/rule_row.html",
        {
            "request": request,
            "rule": rule,
        },
    )
