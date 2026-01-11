# YNAB CSV Importer

A local web application for importing OP Bank CSV exports into YNAB (You Need A Budget) with intelligent rule-based categorization.

## Features

- **CSV Upload**: Drag-and-drop interface for uploading OP Bank CSV exports
- **Automatic Categorization**: Rule-based system that auto-categorizes transactions
- **Interactive Review**: Review and manually categorize uncertain transactions
- **Rule Management**: Create, edit, and delete categorization rules
- **YNAB Integration**: Direct import to YNAB via their API
- **Duplicate Detection**: Automatic deduplication using YNAB's import_id system

## Prerequisites

- Python 3.10+
- YNAB account with API access
- OP Bank CSV export file

## Setup

### 1. Install Dependencies

```bash
cd ynab-importer
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure YNAB API Access

1. Go to [YNAB Developer Settings](https://app.ynab.com/settings/developer)
2. Create a new "Personal Access Token"
3. Copy your token

Edit `config.json`:

```json
{
  "ynab_api_token": "your-token-here",
  "budget_id": "your-budget-id-here"
}
```

**Finding your Budget ID:**
- Open YNAB in your browser
- Navigate to your budget
- The URL will be: `https://app.ynab.com/BUDGET_ID_HERE/budget`

### 3. Run the Application

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## Usage

### Importing Transactions

1. Export transactions from OP online banking as CSV
2. Go to http://localhost:8000
3. Drop the CSV file in the upload zone
4. Review auto-categorized transactions (green checkmarks)
5. Manually categorize uncertain transactions (amber dropdowns)
6. Click "Import to YNAB"

### Creating Rules

Rules automate categorization for future imports. Go to **Rules** in the navigation.

**Rule Conditions** (all specified conditions must match):

| Condition | Description | Example |
|-----------|-------------|---------|
| Payee Exact | Exact payee name match | `PRISMA SELLO` |
| Payee Contains | Payee name contains text | `PRISMA` |
| Payee Regex | Regular expression match | `S-MARKET.*` |
| Memo Contains | Memo/message contains text | `LAINA` |
| Amount Exact | Exact amount match | `-892.00` |
| Amount Range | Amount within range | `-1000` to `-800` |

**Tips:**
- Higher priority numbers are checked first
- Use "contains" for flexibility with chain stores
- Use exact amounts for recurring fixed payments (rent, loans)

### Example Rules

**Groceries at any Prisma store:**
```
Name: Prisma Groceries
Payee Contains: PRISMA
Category: Groceries
Priority: 10
```

**Monthly loan payment:**
```
Name: Housing Loan
Payee Contains: OP ASUNTOLAINA
Amount Exact: -892.00
Category: Loan Payment
Priority: 20
```

## Architecture

```
ynab-importer/
├── app/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration management
│   ├── database.py       # SQLite database setup
│   ├── models.py         # SQLAlchemy models
│   ├── parsers/
│   │   └── op_bank.py    # OP Bank CSV parser
│   ├── rules/
│   │   └── engine.py     # Categorization rules engine
│   ├── ynab/
│   │   └── client.py     # YNAB API client
│   ├── routers/
│   │   ├── upload.py     # CSV upload endpoints
│   │   ├── transactions.py # Import endpoints
│   │   └── rules.py      # Rules CRUD endpoints
│   └── templates/        # Jinja2 HTML templates
├── config.json           # YNAB credentials (not committed)
├── requirements.txt
└── README.md
```

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: HTMX + Tailwind CSS
- **Database**: SQLite (via SQLAlchemy)
- **Templates**: Jinja2

## Security Notes

- This application is designed for **local use only**
- Keep your `config.json` private (it's in `.gitignore`)
- The YNAB API token has full access to your budget data
- Consider adding authentication if deploying to a server

## Troubleshooting

**"No accounts found in budget"**
- Verify your `budget_id` in `config.json` is correct
- Make sure the budget has at least one open account

**CSV parsing errors**
- Ensure the CSV is exported from OP Bank (Finnish format)
- Check that the file encoding is UTF-8

**Duplicate transactions not detected**
- YNAB uses `import_id` for deduplication
- Re-importing the same CSV should skip already-imported transactions

## License

MIT
