import hashlib
import os
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db import (
    delete_receipt,
    find_fingerprint_match,
    get_analytics_summary,
    get_receipt,
    get_receipt_by_image_hash,
    get_receipts,
    init_db,
    save_receipt,
    update_receipt,
)
from models import Receipt, ReceiptInDB, ReceiptUpdate
from nim_client import extract_receipt

# Create directories
RECEIPTS_DIR = "receipts"
os.makedirs(RECEIPTS_DIR, exist_ok=True)

# Initialize Database
init_db()

app = FastAPI(
    title="Receipt Scanner API",
    description="Scan receipts, extract line items, and track spending",
    version="1.1.0",
)

# CORS middleware for local frontend/dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded receipt images
app.mount("/images", StaticFiles(directory=RECEIPTS_DIR), name="images")


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Receipt Scanner API",
        "endpoints": {
            "upload_receipt": "POST /receipts",
            "list_receipts": "GET /receipts",
            "get_receipt": "GET /receipts/{id}",
            "update_receipt": "PATCH /receipts/{id}",
            "delete_receipt": "DELETE /receipts/{id}",
            "analytics_summary": "GET /analytics/summary",
        },
    }


@app.post("/receipts", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    file: UploadFile = File(...),
):
    """Accept an uploaded receipt image or PDF, extract data with the vision LLM, validate and save to SQLite."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Generate safe unique filename
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".pdf"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Please upload JPG, PNG, WEBP, or PDF.",
        )

    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    saved_path = os.path.join(RECEIPTS_DIR, unique_filename)

    contents = await file.read()
    with open(saved_path, "wb") as buffer:
        buffer.write(contents)

    # Certain duplicate check: exact same image bytes uploaded before
    image_hash = hashlib.sha256(contents).hexdigest()
    existing = get_receipt_by_image_hash(image_hash)
    if existing:
        os.remove(saved_path)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This exact image was already uploaded on {existing['date']} as receipt #{existing['id']}",
        )

    # Call vision LLM extraction
    parsed_receipt = extract_receipt(saved_path)
    parsed_receipt.image_hash = image_hash

    # Probable duplicate check: same merchant/date/total, different image
    if find_fingerprint_match(parsed_receipt.merchant, parsed_receipt.date, parsed_receipt.total):
        parsed_receipt.possible_duplicate = True

    # Save to SQLite
    receipt_id = save_receipt(parsed_receipt)
    saved_data = get_receipt(receipt_id)

    return saved_data


@app.get("/receipts", response_model=List[dict])
def list_receipts(
    needs_review: Optional[bool] = Query(None),
    merchant: Optional[str] = Query(None),
):
    """List all receipts, optionally filtering by needs_review or merchant."""
    receipts = get_receipts()
    if needs_review is not None:
        receipts = [r for r in receipts if r["needs_review"] == needs_review]
    if merchant:
        receipts = [r for r in receipts if merchant.lower() in (r["merchant"] or "").lower()]
    return receipts


@app.get("/receipts/{receipt_id}", response_model=dict)
def read_receipt(receipt_id: int):
    """Get single receipt details by ID."""
    receipt = get_receipt(receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@app.patch("/receipts/{receipt_id}", response_model=dict)
def patch_receipt(receipt_id: int, update: ReceiptUpdate):
    """Manually update or correct receipt fields (merchant, date, total, items, needs_review)."""
    update_dict = update.model_dump(exclude_unset=True)
    updated = update_receipt(receipt_id, update_dict)
    if not updated:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return updated


@app.delete("/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_receipt(receipt_id: int):
    """Delete a receipt record."""
    deleted = delete_receipt(receipt_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return None


@app.get("/analytics/summary")
def get_analytics(
    start: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
):
    """Get aggregate spending analytics, categorized totals, and daily spend for given date range."""
    return get_analytics_summary(start_date=start, end_date=end)
