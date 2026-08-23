import json
import os
import sqlite3
import tempfile
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
from main import app
import main
from models import CATEGORIES, Receipt, ReceiptInDB, ReceiptItem, ReceiptUpdate
from nim_client import clean_json_response, normalize_merchant, validate_totals


# =====================================================================
# 1. SCHEMA VALIDATION TESTS
# =====================================================================

def test_models_validation_valid():
    """Verify valid models can be instantiated with expected default values."""
    item = ReceiptItem(name="Milk", price=3.99, category="Groceries")
    assert item.name == "Milk"
    assert item.price == 3.99
    assert item.category == "Groceries"

    # Default category should be 'Other'
    default_cat_item = ReceiptItem(name="Mystery Box", price=9.99)
    assert default_cat_item.category == "Other"

    receipt = Receipt(
        merchant="Walmart Supercenter",
        date="2026-08-23",
        total=15.00,
        subtotal=14.00,
        tax=1.00,
        items=[item],
        needs_review=False,
    )
    assert receipt.merchant == "Walmart Supercenter"
    assert len(receipt.items) == 1
    assert receipt.needs_review is False
    assert receipt.image_path is None


def test_models_validation_missing_required_fields():
    """Verify validation errors when mandatory fields are omitted."""
    # Missing merchant
    with pytest.raises(ValidationError):
        Receipt(date="2026-08-23", total=10.0)

    # Missing date
    with pytest.raises(ValidationError):
        Receipt(merchant="Target", total=10.0)

    # Missing total
    with pytest.raises(ValidationError):
        Receipt(merchant="Target", date="2026-08-23")

    # Item missing price
    with pytest.raises(ValidationError):
        ReceiptItem(name="Apples")

    # Item missing name
    with pytest.raises(ValidationError):
        ReceiptItem(price=4.50)


def test_models_validation_invalid_types():
    """Verify validation errors when invalid data types are supplied."""
    with pytest.raises(ValidationError):
        Receipt(merchant="Target", date="2026-08-23", total="not-a-number")

    with pytest.raises(ValidationError):
        Receipt(merchant="Target", date="2026-08-23", total=10.0, items="not-a-list")

    with pytest.raises(ValidationError):
        ReceiptItem(name="Item", price="invalid-price")


def test_models_receipt_indb_and_update():
    """Verify ReceiptInDB and ReceiptUpdate models."""
    db_receipt = ReceiptInDB(
        id=1,
        merchant="Costco",
        date="2026-08-23",
        total=50.00,
        created_at="2026-08-23 12:00:00",
    )
    assert db_receipt.id == 1
    assert db_receipt.created_at == "2026-08-23 12:00:00"

    # ReceiptUpdate with partial fields
    update_data = ReceiptUpdate(merchant="Costco Wholesale", total=55.00)
    dumped = update_data.model_dump(exclude_unset=True)
    assert dumped == {"merchant": "Costco Wholesale", "total": 55.00}
    assert "date" not in dumped


# =====================================================================
# 2. MERCHANT NORMALIZATION TESTS
# =====================================================================

def test_merchant_normalization_case_and_whitespace():
    """Verify case-insensitivity, leading/trailing whitespace, and internal spacing."""
    assert normalize_merchant("wal-mart") == "Walmart"
    assert normalize_merchant("  WAL-MART  ") == "Walmart"
    assert normalize_merchant("Walmart Supercenter") == "Walmart"
    assert normalize_merchant("WALMART.COM") == "Walmart"
    assert normalize_merchant("\n\t amzn mktp us \t\n") == "Amazon"
    assert normalize_merchant("Amazon.com") == "Amazon"
    assert normalize_merchant("AMZN") == "Amazon"
    assert normalize_merchant(" TARGET STORES ") == "Target"
    assert normalize_merchant("target.com") == "Target"
    assert normalize_merchant("costco wholesale corp") == "Costco"
    assert normalize_merchant("sams club store") == "Sam's Club"
    assert normalize_merchant("sam's club") == "Sam's Club"
    assert normalize_merchant("TRADER JOES") == "Trader Joe's"
    assert normalize_merchant("whole foods market") == "Whole Foods"
    assert normalize_merchant("mcdonald's") == "McDonald's"
    assert normalize_merchant("STARBUCKS COFFEE") == "Starbucks"
    assert normalize_merchant("home depot") == "The Home Depot"
    assert normalize_merchant("cvs pharmacy") == "CVS"
    assert normalize_merchant("Walgreens") == "Walgreens"
    assert normalize_merchant("Best Buy") == "Best Buy"


def test_merchant_normalization_unseen_and_accents():
    """Verify unknown merchants and accented characters are preserved properly with whitespace stripped."""
    assert normalize_merchant("Unique Local Bakery") == "Unique Local Bakery"
    assert normalize_merchant("  CafÃ© de Paris  ") == "CafÃ© de Paris"
    assert normalize_merchant("TaquerÃ­a El Pastor") == "TaquerÃ­a El Pastor"
    assert normalize_merchant("BÃ¤ckerei Schmidt") == "BÃ¤ckerei Schmidt"
    assert normalize_merchant("") == ""


# =====================================================================
# 3. ARITHMETIC VALIDATION TESTS
# =====================================================================

def test_arithmetic_validation_exact_and_tolerances():
    """Verify arithmetic validation with exact match, tolerances (0.02, 0.05), and mismatches."""
    # Exact match: subtotal(10.00) + tax(1.00) == total(11.00), sum(items) == 10.00
    valid_exact = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=11.00,
        subtotal=10.00,
        tax=1.00,
        items=[
            ReceiptItem(name="Item 1", price=6.00, category="Groceries"),
            ReceiptItem(name="Item 2", price=4.00, category="Household"),
        ],
    )
    assert validate_totals(valid_exact) is True

    # Total tolerance within 0.02 (e.g. subtotal 10.00 + tax 0.00 vs total 10.02)
    receipt_tol_pass = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=10.02,
        subtotal=10.00,
        tax=0.00,
        items=[ReceiptItem(name="Item 1", price=10.00, category="Groceries")],
    )
    assert validate_totals(receipt_tol_pass) is True

    # Total tolerance exceeds 0.02 (diff 0.03) -> Fail
    receipt_tol_fail = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=10.03,
        subtotal=10.00,
        tax=0.00,
        items=[ReceiptItem(name="Item 1", price=10.00, category="Groceries")],
    )
    assert validate_totals(receipt_tol_fail) is False

    # Subtotal items sum tolerance within 0.05 (e.g. sum(items)=10.04 vs subtotal 10.00)
    receipt_item_tol_pass = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=10.00,
        subtotal=10.00,
        tax=0.00,
        items=[ReceiptItem(name="Item 1", price=10.04, category="Groceries")],
    )
    assert validate_totals(receipt_item_tol_pass) is True

    # Subtotal items sum tolerance exceeds 0.05 (diff 0.06) -> Fail
    receipt_item_tol_fail = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=10.00,
        subtotal=10.00,
        tax=0.00,
        items=[ReceiptItem(name="Item 1", price=10.06, category="Groceries")],
    )
    assert validate_totals(receipt_item_tol_fail) is False


def test_arithmetic_validation_edge_cases():
    """Verify zero totals, missing subtotal/tax, negative refund totals."""
    # Missing subtotal or tax should not fail validation
    no_subtotal = Receipt(merchant="Target", date="2026-08-23", total=10.00, subtotal=None, tax=1.00)
    assert validate_totals(no_subtotal) is True

    no_tax = Receipt(merchant="Target", date="2026-08-23", total=10.00, subtotal=10.00, tax=None)
    assert validate_totals(no_tax) is True

    # Zero total
    zero_receipt = Receipt(merchant="Free Sample", date="2026-08-23", total=0.0, subtotal=0.0, tax=0.0, items=[])
    assert validate_totals(zero_receipt) is True

    # Negative total / refund
    refund_receipt = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=-15.00,
        subtotal=-14.00,
        tax=-1.00,
        items=[ReceiptItem(name="Returned Shirt", price=-14.00, category="Other")],
    )
    assert validate_totals(refund_receipt) is True


# =====================================================================
# 4. JSON PARSING RESILIENCE TESTS
# =====================================================================

def test_clean_json_response_fences_and_noise():
    """Verify parsing markdown fences, pre/post text noise, and think tags."""
    # Markdown fence with language identifier
    raw_md = '```json\n{"merchant": "Target", "date": "2026-08-23", "total": 20.00, "items": []}\n```'
    cleaned = clean_json_response(raw_md)
    parsed = json.loads(cleaned)
    assert parsed["merchant"] == "Target"
    assert parsed["total"] == 20.00

    # Markdown fence without language
    raw_plain_fence = '```\n{"merchant": "Walmart", "date": "2026-08-23", "total": 12.50}\n```'
    cleaned2 = clean_json_response(raw_plain_fence)
    assert json.loads(cleaned2)["merchant"] == "Walmart"

    # Conversational text wrapping JSON
    raw_conversational = 'Here is the extracted receipt data:\n{"merchant": "CVS", "date": "2026-08-23", "total": 8.99}\nHope this helps!'
    cleaned3 = clean_json_response(raw_conversational)
    assert json.loads(cleaned3)["merchant"] == "CVS"

    # Reasoning model <think> tags
    raw_think = '<think>Let me examine the receipt carefully...\nStore: Starbucks\nTotal: 5.50</think>\n```json\n{"merchant": "Starbucks", "date": "2026-08-23", "total": 5.50}\n```'
    cleaned4 = clean_json_response(raw_think)
    assert json.loads(cleaned4)["merchant"] == "Starbucks"
    assert json.loads(cleaned4)["total"] == 5.50


# =====================================================================
# 5. SQLITE CRUD AND EDGE CASE TESTS
# =====================================================================

def test_sqlite_crud_and_analytics_edge_cases():
    """Verify database CRUD, empty table handling, non-existent ID deletion, large item sets, and SQL injection safety."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db = tmp.name

    try:
        init_db(test_db)

        # 1. Empty database queries
        assert get_receipts(db_path=test_db) == []
        assert get_receipt(999, db_path=test_db) is None
        assert delete_receipt(999, db_path=test_db) is False

        empty_summary = get_analytics_summary(db_path=test_db)
        assert empty_summary["total_spend"] == 0.0
        assert empty_summary["receipt_count"] == 0
        assert empty_summary["needs_review_count"] == 0
        assert empty_summary["by_merchant"] == {}
        assert empty_summary["by_category"] == {}
        assert empty_summary["by_day"] == {}

        # 2. Large item set receipt (100 items)
        large_items = [
            ReceiptItem(name=f"Item {i}", price=1.50, category=CATEGORIES[i % len(CATEGORIES)])
            for i in range(100)
        ]
        large_receipt = Receipt(
            merchant="Costco Wholesale",
            date="2026-08-20",
            total=150.00,
            subtotal=150.00,
            tax=0.00,
            items=large_items,
            needs_review=False,
        )
        r_id = save_receipt(large_receipt, db_path=test_db)
        assert r_id > 0

        fetched = get_receipt(r_id, db_path=test_db)
        assert fetched is not None
        assert len(fetched["items"]) == 100
        assert fetched["total"] == 150.00

        # 3. Partial update with no-op fields
        updated_noop = update_receipt(r_id, {}, db_path=test_db)
        assert updated_noop["merchant"] == "Costco Wholesale"

        # Update fields
        updated = update_receipt(
            r_id,
            {"merchant": "Costco", "total": 160.00, "needs_review": True},
            db_path=test_db,
        )
        assert updated["merchant"] == "Costco"
        assert updated["total"] == 160.00
        assert updated["needs_review"] is True

        # 4. Update non-existent receipt
        assert update_receipt(9999, {"merchant": "Ghost"}, db_path=test_db) is None

        # 5. SQL injection safety in date filters
        # If vulnerable to injection, '1'='1' would return records; parameterized query treats it as a string >= '2099...' and returns 0.
        sqli_summary = get_analytics_summary(
            start_date="2099-01-01' OR '1'='1",
            end_date="2099-12-31' OR '1'='1",
            db_path=test_db,
        )
        assert sqli_summary["receipt_count"] == 0

        # Valid date filter matching receipt
        valid_summary = get_analytics_summary(
            start_date="2026-08-01",
            end_date="2026-08-31",
            db_path=test_db,
        )
        assert valid_summary["receipt_count"] == 1
        assert valid_summary["total_spend"] == 160.00

        # 6. Delete existing receipt & non-existent delete
        assert delete_receipt(r_id, db_path=test_db) is True
        assert get_receipt(r_id, db_path=test_db) is None
        assert delete_receipt(r_id, db_path=test_db) is False

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


# =====================================================================
# 6. FASTAPI API INTEGRATION TESTS
# =====================================================================

def test_fastapi_endpoints_and_validation():
    """Verify FastAPI routes, status codes, invalid payloads, filters, and CORS headers."""
    client = TestClient(app)

    # 1. Root info endpoint
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"

    # 2. CORS headers
    cors_resp = client.options(
        "/receipts",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert cors_resp.status_code in (200, 204)
    assert "access-control-allow-origin" in cors_resp.headers

    # 3. Upload invalid file extension (e.g. .exe) -> 400 Bad Request
    invalid_file_resp = client.post(
        "/receipts",
        files={"file": ("malicious_script.exe", b"binary content", "application/octet-stream")},
    )
    assert invalid_file_resp.status_code == 400
    assert "Unsupported file type" in invalid_file_resp.json()["detail"]

    # 4. Upload valid image
    dummy_image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    upload_resp = client.post(
        "/receipts",
        files={"file": ("receipt_test.png", dummy_image, "image/png")},
    )
    assert upload_resp.status_code == 201
    created_id = upload_resp.json()["id"]

    # 5. GET single receipt & 404 for missing
    get_resp = client.get(f"/receipts/{created_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created_id

    missing_get = client.get("/receipts/999999")
    assert missing_get.status_code == 404

    # 6. PATCH valid update
    patch_resp = client.patch(
        f"/receipts/{created_id}",
        json={
            "merchant": "Whole Foods Market",
            "total": 35.75,
            "subtotal": 32.50,
            "tax": 3.25,
            "items": [
                {"name": "Organic Almond Milk", "price": 4.50, "category": "Groceries"},
                {"name": "Avocados 4pk", "price": 5.00, "category": "Groceries"},
            ],
            "needs_review": False,
        },
    )
    assert patch_resp.status_code == 200
    updated_body = patch_resp.json()
    assert updated_body["merchant"] == "Whole Foods Market"
    assert updated_body["total"] == 35.75
    assert updated_body["needs_review"] is False
    assert len(updated_body["items"]) == 2

    # 7. PATCH invalid payload (invalid type for total) -> 422 Unprocessable Entity
    bad_patch = client.patch(f"/receipts/{created_id}", json={"total": "not-a-float"})
    assert bad_patch.status_code == 422

    # 8. PATCH non-existent receipt -> 404
    missing_patch = client.patch("/receipts/999999", json={"merchant": "Nowhere"})
    assert missing_patch.status_code == 404

    # 9. List receipts with query filters
    list_all = client.get("/receipts")
    assert list_all.status_code == 200
    assert len(list_all.json()) >= 1

    # Filter by merchant
    filtered_merch = client.get("/receipts?merchant=Whole+Foods")
    assert filtered_merch.status_code == 200
    assert all("whole foods" in r["merchant"].lower() for r in filtered_merch.json())

    # Filter by needs_review=false
    filtered_review = client.get("/receipts?needs_review=false")
    assert filtered_review.status_code == 200
    assert all(r["needs_review"] is False for r in filtered_review.json())

    # 10. Analytics summary with date boundaries
    analytics_resp = client.get("/analytics/summary?start=2020-01-01&end=2030-12-31")
    assert analytics_resp.status_code == 200
    analytics_data = analytics_resp.json()
    assert analytics_data["total_spend"] >= 35.75
    assert "Groceries" in analytics_data["by_category"]

    # 11. DELETE receipt & 404 on missing delete
    del_resp = client.delete(f"/receipts/{created_id}")
    assert del_resp.status_code == 204

    missing_del = client.delete("/receipts/999999")
    assert missing_del.status_code == 404


# =====================================================================
# 7. DUPLICATE DETECTION TESTS
# =====================================================================

def test_db_migration_preserves_legacy_data(tmp_path):
    """Verify init_db adds image_hash/possible_duplicate columns to a pre-existing v1 table without data loss."""
    test_db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(test_db)
    conn.execute("""
        CREATE TABLE receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merchant TEXT,
            date TEXT,
            total REAL,
            subtotal REAL,
            tax REAL,
            items_json TEXT,
            needs_review INTEGER,
            image_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute(
        "INSERT INTO receipts (merchant, date, total, subtotal, tax, items_json, needs_review, image_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("Legacy Mart", "2025-12-01", 10.0, 9.0, 1.0, "[]", 0, None),
    )
    conn.commit()
    conn.close()

    init_db(test_db)
    recs = get_receipts(db_path=test_db)
    assert len(recs) == 1
    assert recs[0]["merchant"] == "Legacy Mart"
    assert recs[0]["total"] == 10.0
    assert recs[0]["image_hash"] is None
    assert recs[0]["possible_duplicate"] is False


def test_image_hash_lookup(tmp_path):
    """Verify exact-hash lookup finds the right receipt and returns None for unknown/empty hashes."""
    test_db = str(tmp_path / "hash.db")
    init_db(test_db)

    receipt = Receipt(
        merchant="Target",
        date="2026-08-23",
        total=20.00,
        subtotal=19.00,
        tax=1.00,
        items=[ReceiptItem(name="Sponge", price=19.00, category="Household")],
        image_hash="abc123hash",
    )
    rid = save_receipt(receipt, db_path=test_db)

    hit = get_receipt_by_image_hash("abc123hash", db_path=test_db)
    assert hit is not None
    assert hit["id"] == rid
    assert get_receipt_by_image_hash("different-hash", db_path=test_db) is None
    assert get_receipt_by_image_hash(None, db_path=test_db) is None
    assert get_receipt_by_image_hash("", db_path=test_db) is None


def test_fingerprint_match_tolerance(tmp_path):
    """Verify fingerprint matching: normalized merchant + exact date + total within 0.02 tolerance."""
    test_db = str(tmp_path / "fp.db")
    init_db(test_db)

    receipt = Receipt(
        merchant="Walmart Supercenter",
        date="2026-08-23",
        total=50.00,
        subtotal=49.00,
        tax=1.00,
        items=[ReceiptItem(name="Goods", price=49.00, category="Groceries")],
        image_hash="hash-original",
    )
    save_receipt(receipt, db_path=test_db)

    # Match: variant merchant string normalizes identically
    assert find_fingerprint_match("wal-mart", "2026-08-23", 50.00, db_path=test_db) is not None
    # Match: exact normalized name, total within 0.02 tolerance
    assert find_fingerprint_match("Walmart", "2026-08-23", 50.02, db_path=test_db) is not None
    # No match: total outside tolerance (0.03 diff)
    assert find_fingerprint_match("Walmart", "2026-08-23", 50.03, db_path=test_db) is None
    # No match: different date
    assert find_fingerprint_match("Walmart", "2026-08-24", 50.00, db_path=test_db) is None
    # No match: different merchant
    assert find_fingerprint_match("Target", "2026-08-23", 50.00, db_path=test_db) is None


def test_duplicate_detection_api(monkeypatch, tmp_path):
    """Verify API behavior: same image -> 409 hard reject; same fingerprint different image -> flagged;
    different merchant/date/total -> no flag."""
    test_db = str(tmp_path / "dup.db")
    init_db(test_db)

    monkeypatch.setattr(main, "get_receipt_by_image_hash",
                        lambda h: get_receipt_by_image_hash(h, db_path=test_db))
    monkeypatch.setattr(main, "find_fingerprint_match",
                        lambda m, d, t: find_fingerprint_match(m, d, t, db_path=test_db))
    monkeypatch.setattr(main, "save_receipt", lambda r: save_receipt(r, db_path=test_db))
    monkeypatch.setattr(main, "get_receipt", lambda i: get_receipt(i, db_path=test_db))

    base_receipt = Receipt(
        merchant="Walmart Supercenter",
        date="2026-01-15",
        total=25.00,
        subtotal=24.00,
        tax=1.00,
        items=[ReceiptItem(name="Bananas", price=24.00, category="Groceries")],
    )
    current = {"receipt": base_receipt}

    def fake_extract(path, **kwargs):
        r = current["receipt"].model_copy(deep=True)
        r.image_path = path
        return r

    monkeypatch.setattr(main, "extract_receipt", fake_extract)

    client = TestClient(app)
    img_a = b"\x89PNG-fake-image-bytes-A"
    img_b = b"\x89PNG-fake-image-bytes-B"
    img_c = b"\x89PNG-fake-image-bytes-C"

    # 1. First upload succeeds, no duplicate flag, hash stored
    r1 = client.post("/receipts", files={"file": ("a.png", img_a, "image/png")})
    assert r1.status_code == 201
    body1 = r1.json()
    first_id = body1["id"]
    assert body1["possible_duplicate"] is False
    import hashlib as _hashlib
    assert body1["image_hash"] == _hashlib.sha256(img_a).hexdigest()

    # 2. Same exact image again -> hard reject with clear message, nothing saved
    r2 = client.post("/receipts", files={"file": ("a-again.png", img_a, "image/png")})
    assert r2.status_code == 409
    assert "already uploaded" in r2.json()["detail"]
    assert str(first_id) in r2.json()["detail"]
    assert client.get(f"/receipts/{first_id}").status_code == 200  # original untouched

    # 3. Different image, same merchant/date/total -> saved but flagged possible_duplicate
    r3 = client.post("/receipts", files={"file": ("b.png", img_b, "image/png")})
    assert r3.status_code == 201
    body3 = r3.json()
    assert body3["possible_duplicate"] is True
    assert body3["image_hash"] != body1["image_hash"]

    # 4. Different image AND different totals (same store/date) -> not flagged
    current["receipt"] = base_receipt.model_copy(update={"total": 99.00, "subtotal": 98.00})
    current["receipt"].items = [ReceiptItem(name="Bananas", price=98.00, category="Groceries")]
    r4 = client.post("/receipts", files={"file": ("c.png", img_c, "image/png")})
    assert r4.status_code == 201
    body4 = r4.json()
    assert body4["possible_duplicate"] is False

    # Cleanup temp images written by the endpoint into receipts/
    for f in (body1.get("image_path"), body3.get("image_path"), body4.get("image_path")):
        if f and os.path.exists(f):
            os.remove(f)


# =====================================================================
# 8. PDF UPLOAD TESTS
# =====================================================================

def test_pdf_first_page_rendered_to_png(tmp_path):
    """Verify a real PDF has its first page rendered to a PNG for the vision call."""
    import pymupdf

    pdf_path = str(tmp_path / "real.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((40, 60), "ACME GROCERY", fontsize=14)
    page.insert_text((40, 90), "TOTAL 16.36", fontsize=12)
    doc.save(pdf_path)
    doc.close()

    from nim_client import _prepare_image
    send_path, mime = _prepare_image(pdf_path)

    try:
        assert mime == "image/png"
        assert send_path != pdf_path
        assert send_path.endswith(".png")
        assert os.path.exists(send_path) and os.path.getsize(send_path) > 0
        with pymupdf.open(send_path) as check:
            assert check.page_count == 1
    finally:
        if os.path.exists(send_path):
            os.remove(send_path)
