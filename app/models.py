from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Rule(Base):
    """Categorization rule for transactions."""
    __tablename__ = "rules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    
    # Match conditions (all non-null conditions must match)
    payee_exact = Column(String, nullable=True)
    payee_contains = Column(String, nullable=True)
    payee_regex = Column(String, nullable=True)
    memo_contains = Column(String, nullable=True)
    memo_regex = Column(String, nullable=True)
    amount_exact = Column(Float, nullable=True)
    amount_min = Column(Float, nullable=True)
    amount_max = Column(Float, nullable=True)
    
    # Action: which category to assign
    category_id = Column(String, nullable=False)  # YNAB category ID
    category_name = Column(String, nullable=False)  # For display purposes
    
    # Metadata
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Rule {self.id}: {self.name} -> {self.category_name}>"
