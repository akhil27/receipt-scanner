import base64
import json
import os
from datetime import date, datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from PIL import Image

from db import (
    delete_receipt,
    get_analytics_summary,
    get_receipt,
    get_receipts,
    init_db,
    save_receipt,
    update_receipt,
)
from models import CATEGORIES, Receipt, ReceiptItem
from nim_client import extract_receipt

# Configure Streamlit page
st.set_page_config(
    page_title="Receipt Scanner",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
    }
    .stAlert {
        border-radius: 8px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Ensure DB is initialized
init_db()
RECEIPTS_DIR = "receipts"
os.makedirs(RECEIPTS_DIR, exist_ok=True)

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/receipt-terminal.png", width=64)
    st.title("Receipt Scanner")
    st.caption("Powered by NVIDIA NIM Vision LLM")

    st.markdown("---")
    st.subheader("⚙️ Settings")
    current_key = os.environ.get("NVIDIA_API_KEY", "")
    current_model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")

    api_key_input = st.text_input(
        "NVIDIA API Key",
        value=current_key if current_key and not current_key.startswith("your-") else "",
        type="password",
        help="Enter your NVIDIA API Key from build.nvidia.com",
    )
    if api_key_input:
        os.environ["NVIDIA_API_KEY"] = api_key_input

    model_input = st.text_input(
        "NVIDIA Model",
        value=current_model,
        help="e.g. meta/llama-3.2-11b-vision-instruct, meta/llama-3.2-90b-vision-instruct",
    )
    if model_input:
        os.environ["NVIDIA_MODEL"] = model_input

    st.markdown("---")
    st.subheader("🧪 Quick Test Data")
    if st.button("➕ Load 5 Sample Receipts"):
        sample_receipts = [
            Receipt(
                merchant="Walmart",
                date=date.today().isoformat(),
                total=47.85,
                subtotal=44.30,
                tax=3.55,
                items=[
                    ReceiptItem(name="Organic Whole Milk 1 Gal", price=4.48, category="Groceries"),
                    ReceiptItem(name="Boneless Chicken Breast 2.5lb", price=11.98, category="Groceries"),
                    ReceiptItem(name="Paper Towels 6pk", price=12.44, category="Household"),
                    ReceiptItem(name="Tide Laundry Detergent", price=15.40, category="Household"),
                ],
                needs_review=False,
            ),
            Receipt(
                merchant="Target",
                date=(date.today() - timedelta(days=2)).isoformat(),
                total=89.20,
                subtotal=82.59,
                tax=6.61,
                items=[
                    ReceiptItem(name="USB-C Charging Cable 6ft", price=19.99, category="Electronics"),
                    ReceiptItem(name="Wireless Mouse", price=29.99, category="Electronics"),
                    ReceiptItem(name="Shampoo & Conditioner Set", price=14.99, category="Health"),
                    ReceiptItem(name="Snack Protein Bars 8ct", price=17.62, category="Food"),
                ],
                needs_review=False,
            ),
            Receipt(
                merchant="Costco",
                date=(date.today() - timedelta(days=5)).isoformat(),
                total=156.40,
                subtotal=145.00,
                tax=11.40,
                items=[
                    ReceiptItem(name="Kirkland Signature Coffee Beans 2.5lb", price=16.99, category="Groceries"),
                    ReceiptItem(name="Salmon Fillet Fresh Wild", price=32.50, category="Groceries"),
                    ReceiptItem(name="Bath Tissue 30pk", price=22.99, category="Household"),
                    ReceiptItem(name="Red Wine Cabernet 6pk", price=54.99, category="Alcohol"),
                    ReceiptItem(name="Cashews Roasted 2.5lb", price=17.53, category="Food"),
                ],
                needs_review=False,
            ),
            Receipt(
                merchant="Amazon",
                date=(date.today() - timedelta(days=7)).isoformat(),
                total=34.99,
                subtotal=32.39,
                tax=2.60,
                items=[
                    ReceiptItem(name="Ergonomic Desk Wrist Rest", price=18.99, category="Electronics"),
                    ReceiptItem(name="Multi-Plug Power Strip Outlet", price=13.40, category="Electronics"),
                ],
                needs_review=False,
            ),
            Receipt(
                merchant="Starbucks",
                date=(date.today() - timedelta(days=1)).isoformat(),
                total=14.25,
                subtotal=13.15,
                tax=1.10,
                items=[
                    ReceiptItem(name="Iced Caramel Macchiato Venti", price=6.45, category="Restaurant"),
                    ReceiptItem(name="Bacon Gouda Egg Sandwich", price=5.75, category="Restaurant"),
                    ReceiptItem(name="Butter Croissant", price=0.95, category="Food"),
                ],
                needs_review=False,
            ),
        ]
        for s in sample_receipts:
            save_receipt(s)
        st.success("Loaded 5 sample receipts!")
        st.rerun()

# Main UI
st.markdown('<div class="main-header">🧾 Receipt Scanner & Expense Tracker</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Automated extraction and expense analytics powered by NVIDIA NIM Vision LLM</div>',
    unsafe_allow_html=True,
)

# Tabs
tab_upload, tab_dashboard, tab_receipts = st.tabs(["📤 Upload Receipt", "📊 Analytics Dashboard", "📋 Receipts Vault & Edit"])

# TAB 1: UPLOAD
with tab_upload:
    st.subheader("Upload Receipt Image")
    col1, col2 = st.columns([1, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Choose a receipt image (JPG, PNG, WEBP)",
            type=["jpg", "jpeg", "png", "webp"],
            help="Take a photo or upload a scanned image of your receipt",
        )

        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Receipt Preview", use_container_width=True)

            if st.button("🚀 Process & Extract Receipt", type="primary"):
                with st.spinner("Extracting receipt data with NVIDIA NIM Vision LLM..."):
                    # Save file locally
                    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
                    unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}"
                    save_path = os.path.join(RECEIPTS_DIR, unique_filename)
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    # Extract
                    parsed = extract_receipt(save_path)
                    receipt_id = save_receipt(parsed)

                if parsed.needs_review:
                    st.warning("⚠️ Receipt extracted, but arithmetic validation failed or API key was missing. Flagged for review.")
                else:
                    st.success(f"✅ Successfully scanned receipt from **{parsed.merchant}** (ID #{receipt_id})!")

                st.session_state["last_receipt_id"] = receipt_id
                st.rerun()

    with col2:
        st.subheader("Extraction Result")
        last_id = st.session_state.get("last_receipt_id")
        if last_id:
            latest = get_receipt(last_id)
            if latest:
                st.markdown(f"### Store: **{latest['merchant']}**")
                st.markdown(f"**Date:** {latest['date']} | **Total:** `${latest['total']:.2f}`")
                if latest.get("subtotal") is not None:
                    st.markdown(f"**Subtotal:** `${latest['subtotal']:.2f}` | **Tax:** `${(latest.get('tax') or 0.0):.2f}`")

                if latest["needs_review"]:
                    st.error("⚠️ Status: Needs Review (Please verify the fields in 'Receipts Vault')")
                else:
                    st.success("✅ Status: Validated")

                st.markdown("#### Items Extracted:")
                items = latest.get("items", [])
                if items:
                    df_items = pd.DataFrame(items)
                    st.dataframe(df_items, use_container_width=True)
                else:
                    st.info("No individual line items parsed.")
        else:
            st.info("Upload a receipt on the left to view parsed information here.")

# TAB 2: ANALYTICS DASHBOARD
with tab_dashboard:
    st.subheader("Spending Analytics & Insights")

    # Date range filters
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("From Date", value=date.today() - timedelta(days=30))
    with col_d2:
        end_date = st.date_input("To Date", value=date.today())

    summary = get_analytics_summary(
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
    )

    # Metric cards
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Spend", f"${summary['total_spend']:,.2f}")
    with m2:
        st.metric("Total Receipts", f"{summary['receipt_count']}")
    with m3:
        avg_spend = round(summary["total_spend"] / summary["receipt_count"], 2) if summary["receipt_count"] > 0 else 0.0
        st.metric("Average / Receipt", f"${avg_spend:,.2f}")
    with m4:
        st.metric("Flagged for Review", f"{summary['needs_review_count']}")

    st.markdown("---")

    # Charts
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.markdown("#### 🛍️ Spend by Category")
        cat_data = summary.get("by_category", {})
        if cat_data:
            df_cat = pd.DataFrame(
                [{"Category": k, "Spend ($)": v} for k, v in cat_data.items() if v > 0]
            ).sort_values(by="Spend ($)", ascending=False)
            st.bar_chart(df_cat.set_index("Category"))
        else:
            st.info("No categorized spending data in selected date range.")

    with chart_col2:
        st.markdown("#### 🏢 Spend by Merchant")
        merchant_data = summary.get("by_merchant", {})
        if merchant_data:
            df_merch = pd.DataFrame(
                [{"Merchant": k, "Spend ($)": v} for k, v in merchant_data.items() if v > 0]
            ).sort_values(by="Spend ($)", ascending=False)
            st.bar_chart(df_merch.set_index("Merchant"))
        else:
            st.info("No merchant spending data in selected date range.")

    st.markdown("#### 📅 Spend Over Time (Daily)")
    daily_data = summary.get("by_day", {})
    if daily_data:
        df_daily = pd.DataFrame(
            [{"Date": k, "Spend ($)": v} for k, v in sorted(daily_data.items())]
        )
        st.line_chart(df_daily.set_index("Date"))
    else:
        st.info("No daily spending data recorded in this range.")

# TAB 3: RECEIPTS VAULT & MANUAL CORRECTION
with tab_receipts:
    st.subheader("Manage & Manually Edit Receipts")
    receipts_list = get_receipts()

    if not receipts_list:
        st.info("No receipts saved yet. Upload a receipt or click 'Load 5 Sample Receipts' in the sidebar.")
    else:
        # Search and filter
        search_query = st.text_input("🔍 Search receipts by merchant name...", "")
        filtered_receipts = [
            r for r in receipts_list if search_query.lower() in (r["merchant"] or "").lower()
        ]

        st.caption(f"Showing {len(filtered_receipts)} of {len(receipts_list)} receipts")

        for r in filtered_receipts:
            badge = "⚠️ Needs Review" if r["needs_review"] else "✅ Validated"
            with st.expander(f"🧾 #{r['id']} | **{r['merchant']}** — ${r['total']:.2f} ({r['date']}) — {badge}"):
                c1, c2 = st.columns([1, 2])

                with c1:
                    if r.get("image_path") and os.path.exists(r["image_path"]):
                        st.image(r["image_path"], caption="Uploaded Receipt Image", use_container_width=True)
                    else:
                        st.info("No receipt image file available.")

                with c2:
                    with st.form(key=f"edit_form_{r['id']}"):
                        st.markdown("##### ✏️ Edit Receipt Details")
                        f_merchant = st.text_input("Merchant", value=r["merchant"] or "")
                        f_date = st.text_input("Date (YYYY-MM-DD)", value=r["date"] or "")
                        f_col1, f_col2, f_col3 = st.columns(3)
                        with f_col1:
                            f_total = st.number_input("Total ($)", value=float(r["total"] or 0.0), step=0.01)
                        with f_col2:
                            f_subtotal = st.number_input("Subtotal ($)", value=float(r["subtotal"] or 0.0), step=0.01)
                        with f_col3:
                            f_tax = st.number_input("Tax ($)", value=float(r["tax"] or 0.0), step=0.01)

                        f_review = st.checkbox("Flagged for Review", value=r["needs_review"])

                        st.markdown("##### Line Items")
                        items = r.get("items", [])
                        new_items = []
                        for i, item in enumerate(items):
                            it_c1, it_c2, it_c3 = st.columns([3, 1, 2])
                            with it_c1:
                                it_name = st.text_input(f"Item #{i+1} Name", value=item.get("name", ""), key=f"it_name_{r['id']}_{i}")
                            with it_c2:
                                it_price = st.number_input(f"Price ($)", value=float(item.get("price", 0.0)), step=0.01, key=f"it_price_{r['id']}_{i}")
                            with it_c3:
                                current_cat = item.get("category", "Other")
                                cat_idx = CATEGORIES.index(current_cat) if current_cat in CATEGORIES else CATEGORIES.index("Other")
                                it_cat = st.selectbox(f"Category", CATEGORIES, index=cat_idx, key=f"it_cat_{r['id']}_{i}")
                            new_items.append({"name": it_name, "price": it_price, "category": it_cat})

                        col_btn1, col_btn2 = st.columns([1, 1])
                        with col_btn1:
                            submitted = st.form_submit_button("💾 Save Changes", type="primary")
                        with col_btn2:
                            deleted = st.form_submit_button("🗑️ Delete Receipt")

                        if submitted:
                            update_receipt(
                                r["id"],
                                {
                                    "merchant": f_merchant,
                                    "date": f_date,
                                    "total": f_total,
                                    "subtotal": f_subtotal,
                                    "tax": f_tax,
                                    "items": new_items,
                                    "needs_review": f_review,
                                },
                            )
                            st.success(f"Saved changes to receipt #{r['id']}!")
                            st.rerun()

                        if deleted:
                            delete_receipt(r["id"])
                            st.warning(f"Deleted receipt #{r['id']}.")
                            st.rerun()
