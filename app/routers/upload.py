from fastapi import APIRouter, UploadFile, Request, Depends
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.parsers import OPBankParser
from app.rules import RulesEngine
from app.ynab import YNABClient

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.post("")
async def upload_csv(
    request: Request,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    """Handle CSV file upload and parse transactions."""
    # Read file content
    content = await file.read()
    text = content.decode("utf-8")
    
    # Parse transactions
    parser = OPBankParser()
    transactions = parser.parse(text)
    
    # Apply categorization rules
    rules_engine = RulesEngine(db)
    categorized = await rules_engine.categorize_transactions(transactions)
    
    # Get YNAB categories for dropdown
    ynab_client = YNABClient()
    categories = await ynab_client.get_categories()
    
    # Count stats
    auto_categorized = sum(1 for t in categorized if t.get("category_id"))
    needs_review = len(categorized) - auto_categorized
    
    return templates.TemplateResponse(
        "partials/transaction_table.html",
        {
            "request": request,
            "transactions": categorized,
            "categories": categories,
            "stats": {
                "total": len(categorized),
                "auto_categorized": auto_categorized,
                "needs_review": needs_review,
            },
        },
    )
