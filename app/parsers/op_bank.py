"""
OP Bank CSV Parser

Parses CSV files exported from OP (Osuuspankki) online banking.
Finnish locale: semicolon separators, DD.MM.YYYY dates, comma as decimal separator.

Expected CSV columns (Finnish):
- Kirjauspäivä (Booking date)
- Arvopäivä (Value date)  
- Määrä (Amount)
- Laji (Type)
- Selitys (Explanation)
- Saaja/Maksaja (Payee/Payer)
- Saajan tilinumero (Payee account number)
- Viite (Reference)
- Viesti (Message)
- Arkistointitunnus (Archive ID)
"""

import csv
import re
import hashlib
from datetime import datetime
from io import StringIO
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Transaction:
    """Parsed transaction from CSV."""
    date: str  # ISO format YYYY-MM-DD
    payee: str
    amount: float
    memo: Optional[str]
    import_id: str  # Unique ID for YNAB deduplication
    
    # Original data for reference
    original_date: str
    original_amount: str
    reference: Optional[str]
    archive_id: Optional[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date,
            "payee": self.payee,
            "amount": self.amount,
            "amount_milliunits": int(self.amount * 1000),
            "memo": self.memo,
            "import_id": self.import_id,
            "original_date": self.original_date,
            "original_amount": self.original_amount,
            "reference": self.reference,
            "archive_id": self.archive_id,
        }


class OPBankParser:
    """Parser for OP Bank CSV exports."""
    
    # Column name mappings (Finnish -> English)
    COLUMN_MAPPINGS = {
        "kirjauspäivä": "booking_date",
        "arvopäivä": "value_date",
        "määrä": "amount",
        "laji": "type",
        "selitys": "explanation",
        "saaja/maksaja": "payee",
        "saajan tilinumero": "payee_account",
        "viite": "reference",
        "viesti": "message",
        "arkistointitunnus": "archive_id",
    }
    
    def parse(self, csv_content: str) -> List[Transaction]:
        """
        Parse CSV content and return list of transactions.
        
        Args:
            csv_content: Raw CSV file content as string
            
        Returns:
            List of Transaction objects
        """
        transactions = []
        
        # Detect delimiter (OP uses semicolon, but let's be safe)
        delimiter = self._detect_delimiter(csv_content)
        
        # Parse CSV
        reader = csv.DictReader(
            StringIO(csv_content),
            delimiter=delimiter,
        )
        
        # Normalize column names
        if reader.fieldnames:
            reader.fieldnames = [
                self._normalize_column(col) for col in reader.fieldnames
            ]
        
        for row in reader:
            try:
                txn = self._parse_row(row)
                if txn:
                    transactions.append(txn)
            except Exception as e:
                # Log error but continue parsing
                print(f"Error parsing row: {row}, error: {e}")
                continue
        
        return transactions
    
    def _detect_delimiter(self, content: str) -> str:
        """Detect CSV delimiter by counting occurrences in first line."""
        first_line = content.split("\n")[0]
        semicolons = first_line.count(";")
        commas = first_line.count(",")
        return ";" if semicolons > commas else ","
    
    def _normalize_column(self, column: str) -> str:
        """Normalize column name to lowercase and map to English."""
        normalized = column.lower().strip()
        return self.COLUMN_MAPPINGS.get(normalized, normalized)
    
    def _parse_row(self, row: dict) -> Optional[Transaction]:
        """Parse a single CSV row into a Transaction."""
        # Get date (prefer booking date)
        date_str = row.get("booking_date") or row.get("value_date", "")
        if not date_str:
            return None
        
        # Parse Finnish date format (DD.MM.YYYY)
        date = self._parse_finnish_date(date_str)
        if not date:
            return None
        
        # Get amount (Finnish format: comma as decimal separator)
        amount_str = row.get("amount", "0")
        amount = self._parse_finnish_amount(amount_str)
        
        # Get payee
        payee = row.get("payee", "").strip()
        if not payee:
            payee = row.get("explanation", "Unknown").strip()
        
        # Build memo from available fields
        memo_parts = []
        if row.get("explanation"):
            memo_parts.append(row["explanation"].strip())
        if row.get("message"):
            memo_parts.append(row["message"].strip())
        memo = " | ".join(filter(None, memo_parts)) or None
        
        # Generate unique import ID for YNAB deduplication
        import_id = self._generate_import_id(
            date, payee, amount, row.get("archive_id")
        )
        
        return Transaction(
            date=date,
            payee=payee,
            amount=amount,
            memo=memo,
            import_id=import_id,
            original_date=date_str,
            original_amount=amount_str,
            reference=row.get("reference"),
            archive_id=row.get("archive_id"),
        )
    
    def _parse_finnish_date(self, date_str: str) -> Optional[str]:
        """
        Parse Finnish date format (DD.MM.YYYY) to ISO format (YYYY-MM-DD).
        """
        date_str = date_str.strip()
        
        # Try DD.MM.YYYY format
        match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if match:
            day, month, year = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return None
        
        # Try ISO format (already correct)
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
        if match:
            return date_str
        
        return None
    
    def _parse_finnish_amount(self, amount_str: str) -> float:
        """
        Parse Finnish number format (comma as decimal separator).
        Also handles negative amounts indicated by minus sign.
        """
        if not amount_str:
            return 0.0
        
        # Clean the string
        amount_str = amount_str.strip()
        
        # Remove any thousand separators (space or period in Finnish)
        amount_str = amount_str.replace(" ", "").replace("\u00a0", "")
        
        # Check if there are both comma and period
        # In Finnish: period is thousand separator, comma is decimal
        if "," in amount_str and "." in amount_str:
            # Remove thousand separators (periods)
            amount_str = amount_str.replace(".", "")
        
        # Replace comma with period for decimal
        amount_str = amount_str.replace(",", ".")
        
        try:
            return float(amount_str)
        except ValueError:
            return 0.0
    
    def _generate_import_id(
        self, 
        date: str, 
        payee: str, 
        amount: float, 
        archive_id: Optional[str]
    ) -> str:
        """
        Generate unique import ID for YNAB deduplication.
        
        YNAB uses import_id to prevent duplicate imports.
        Format: YNAB:{amount_milliunits}:{date}:{occurrence}
        
        We'll use a hash to make it truly unique.
        """
        # If we have an archive ID from the bank, use it
        if archive_id:
            return f"OP:{archive_id}"
        
        # Otherwise, create a hash-based ID
        unique_str = f"{date}:{payee}:{amount}"
        hash_suffix = hashlib.md5(unique_str.encode()).hexdigest()[:8]
        return f"YNAB:{int(amount * 1000)}:{date}:{hash_suffix}"
