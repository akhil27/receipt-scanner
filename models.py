from typing import List, Optional
from pydantic import BaseModel, Field


CATEGORIES = [
    "Food",
    "Groceries",
    "Restaurant",
    "Alcohol",
    "Household",
    "Electronics",
    "Health",
    "Transportation",
    "Entertainment",
    "Other",
]


class ReceiptItem(BaseModel):
    name: str
    price: float
    category: str = "Other"


class Receipt(BaseModel):
    merchant: str
    date: str
    total: float
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    items: List[ReceiptItem] = Field(default_factory=list)
    needs_review: bool = False
    possible_duplicate: bool = False
    image_path: Optional[str] = None
    image_hash: Optional[str] = None


class ReceiptUpdate(BaseModel):
    merchant: Optional[str] = None
    date: Optional[str] = None
    total: Optional[float] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    items: Optional[List[ReceiptItem]] = None
    needs_review: Optional[bool] = None


class ReceiptInDB(Receipt):
    id: int
    created_at: Optional[str] = None
