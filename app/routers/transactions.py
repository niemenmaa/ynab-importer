from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import List
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ynab import YNABClient

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


class TransactionImport(BaseModel):
    date: str
    payee: str
    amount: int  # In milliunits (YNAB format)
    memo: str | None = None
    category_id: str


@router.post("/import")
async def import_transactions(
    request: Request,
    transactions: str = Form(...),  # JSON string of transactions
):
    """Import categorized transactions to YNAB."""
    import json
    
    # Parse transactions from form
    txn_list = json.loads(transactions)
    
    # Send to YNAB
    ynab_client = YNABClient()
    result = await ynab_client.create_transactions(txn_list)
    
    return templates.TemplateResponse(
        "partials/import_result.html",
        {
            "request": request,
            "result": result,
        },
    )


@router.post("/{index}/category")
async def update_transaction_category(
    request: Request,
    index: int,
    category_id: str = Form(...),
    category_name: str = Form(...),
):
    """Update a single transaction's category (HTMX endpoint)."""
    return HTMLResponse(
        f'<span class="text-green-600">✓ {category_name}</span>'
    )
