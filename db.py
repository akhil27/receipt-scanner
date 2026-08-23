import json
import sqlite3
from typing import Any, Dict, List, Optional
from models import Receipt, ReceiptInDB, ReceiptItem

from contextlib import contextmanager

DB_PATH = "receipts.db"

# Same tolerance as arithmetic validation: total-vs-total fingerprint comparison
FINGERPRINT_TOTAL_TOLERANCE = 0.02


@contextmanager
def get_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after v1 to an existing table without losing data."""
    cursor = conn.execute("PRAGMA table_info(receipts)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "image_hash" not in columns:
        conn.execute("ALTER TABLE receipts ADD COLUMN image_hash TEXT")
    if "possible_duplicate" not in columns:
        conn.execute("ALTER TABLE receipts ADD COLUMN possible_duplicate INTEGER NOT NULL DEFAULT 0")


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize SQLite database with receipts table, migrating older schemas in place."""
    with get_db(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant TEXT,
                date TEXT,
                total REAL,
                subtotal REAL,
                tax REAL,
                items_json TEXT,
                needs_review INTEGER,
                image_path TEXT,
                image_hash TEXT,
                possible_duplicate INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        _migrate_schema(conn)
        conn.commit()



def save_receipt(receipt: Receipt, db_path: str = DB_PATH) -> int:
    """Save a receipt to SQLite database and return generated id."""
    items_json = json.dumps([item.model_dump() for item in receipt.items])
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO receipts (
                merchant, date, total, subtotal, tax, items_json, needs_review,
                image_path, image_hash, possible_duplicate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.merchant,
                receipt.date,
                receipt.total,
                receipt.subtotal,
                receipt.tax,
                items_json,
                1 if receipt.needs_review else 0,
                receipt.image_path,
                receipt.image_hash,
                1 if receipt.possible_duplicate else 0,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    items_raw = row["items_json"] or "[]"
    try:
        items = json.loads(items_raw)
    except Exception:
        items = []

    return {
        "id": row["id"],
        "merchant": row["merchant"],
        "date": row["date"],
        "total": row["total"],
        "subtotal": row["subtotal"],
        "tax": row["tax"],
        "items": items,
        "needs_review": bool(row["needs_review"]),
        "image_path": row["image_path"],
        "image_hash": row["image_hash"] if "image_hash" in row.keys() else None,
        "possible_duplicate": bool(row["possible_duplicate"]) if "possible_duplicate" in row.keys() else False,
        "created_at": row["created_at"],
    }


def get_receipts(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve all receipts sorted by date desc."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM receipts ORDER BY date DESC, id DESC")
        rows = cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


def get_receipt(receipt_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve a single receipt by ID."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_dict(row)


def get_receipt_by_image_hash(image_hash: Optional[str], db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Find a receipt previously uploaded with the exact same image bytes (SHA-256 match)."""
    if not image_hash:
        return None
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM receipts WHERE image_hash = ? LIMIT 1", (image_hash,))
        row = cursor.fetchone()
        if not row:
            return None
        return _row_to_dict(row)


def _merchant_fingerprint(name: str) -> str:
    """Normalize merchant for fingerprint comparison: use mapping, then lowercase for case-insensitive match."""
    from nim_client import normalize_merchant
    return normalize_merchant(name or "").lower()


def find_fingerprint_match(
    merchant: str,
    date_str: str,
    total: float,
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Find an existing receipt with the same normalized merchant, exact date,
    and total within the arithmetic-validation tolerance. Probable (not certain) duplicate."""
    target = _merchant_fingerprint(merchant)
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM receipts WHERE date = ?", (date_str,))
        rows = cursor.fetchall()

    for row in rows:
        candidate = _row_to_dict(row)
        same_merchant = _merchant_fingerprint(candidate.get("merchant") or "") == target
        # Round to cents first to avoid float representation drift (e.g. 0.020000000000003)
        diff = round(abs((candidate.get("total") or 0.0) - total), 2)
        if same_merchant and diff <= FINGERPRINT_TOTAL_TOLERANCE:
            return candidate
    return None


def update_receipt(receipt_id: int, update_data: Dict[str, Any], db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Update fields on an existing receipt."""
    existing = get_receipt(receipt_id, db_path=db_path)
    if not existing:
        return None

    fields = []
    values = []

    if "merchant" in update_data and update_data["merchant"] is not None:
        fields.append("merchant = ?")
        values.append(update_data["merchant"])

    if "date" in update_data and update_data["date"] is not None:
        fields.append("date = ?")
        values.append(update_data["date"])

    if "total" in update_data and update_data["total"] is not None:
        fields.append("total = ?")
        values.append(update_data["total"])

    if "subtotal" in update_data and update_data["subtotal"] is not None:
        fields.append("subtotal = ?")
        values.append(update_data["subtotal"])

    if "tax" in update_data and update_data["tax"] is not None:
        fields.append("tax = ?")
        values.append(update_data["tax"])

    if "items" in update_data and update_data["items"] is not None:
        items = update_data["items"]
        if isinstance(items, list) and len(items) > 0 and hasattr(items[0], "model_dump"):
            items_json = json.dumps([item.model_dump() for item in items])
        else:
            items_json = json.dumps(items)
        fields.append("items_json = ?")
        values.append(items_json)

    if "needs_review" in update_data and update_data["needs_review"] is not None:
        fields.append("needs_review = ?")
        values.append(1 if update_data["needs_review"] else 0)

    if not fields:
        return existing

    values.append(receipt_id)
    with get_db(db_path) as conn:
        conn.execute(
            f"UPDATE receipts SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()

    return get_receipt(receipt_id, db_path=db_path)


def delete_receipt(receipt_id: int, db_path: str = DB_PATH) -> bool:
    """Delete a receipt by ID."""
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_analytics_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """Calculate aggregate analytics for receipts in given date range using SQL and item breakdown."""
    init_db(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM receipts WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        receipts = [_row_to_dict(r) for r in rows]

    total_spend = sum(r["total"] for r in receipts)
    receipt_count = len(receipts)
    needs_review_count = sum(1 for r in receipts if r["needs_review"])

    # Spend by merchant
    merchant_spend: Dict[str, float] = {}
    for r in receipts:
        m = r["merchant"] or "Unknown"
        merchant_spend[m] = round(merchant_spend.get(m, 0.0) + r["total"], 2)

    # Spend by day
    daily_spend: Dict[str, float] = {}
    for r in receipts:
        d = r["date"] or "Unknown"
        daily_spend[d] = round(daily_spend.get(d, 0.0) + r["total"], 2)

    # Spend by category across all items
    category_spend: Dict[str, float] = {}
    uncategorized_amount = 0.0
    for r in receipts:
        items = r.get("items", [])
        if items:
            for item in items:
                cat = item.get("category") or "Other"
                p = float(item.get("price") or 0.0)
                category_spend[cat] = round(category_spend.get(cat, 0.0) + p, 2)
        else:
            # If no items extracted, assign total to 'Other'
            category_spend["Other"] = round(category_spend.get("Other", 0.0) + r["total"], 2)

    return {
        "total_spend": round(total_spend, 2),
        "receipt_count": receipt_count,
        "needs_review_count": needs_review_count,
        "by_merchant": merchant_spend,
        "by_category": category_spend,
        "by_day": daily_spend,
    }
