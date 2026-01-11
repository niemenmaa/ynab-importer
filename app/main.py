from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.database import init_db
from app.routers import upload, transactions, rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="YNAB CSV Importer",
    description="Import bank CSV files into YNAB with intelligent categorization",
    version="1.0.0",
    lifespan=lifespan,
)

# Templates
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Include routers
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
app.include_router(rules.router, prefix="/rules", tags=["Rules"])


@app.get("/")
async def index(request: Request):
    """Main page with CSV upload."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
