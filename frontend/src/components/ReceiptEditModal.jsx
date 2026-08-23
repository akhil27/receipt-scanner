import { useEffect, useState } from "react";
import { updateReceipt, deleteReceipt } from "../api/client.js";
import { money } from "./format.js";

const CATEGORIES = [
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
];

export default function ReceiptEditModal({ receipt, onClose, onChanged }) {
  const [form, setForm] = useState(() => ({
    merchant: receipt.merchant || "",
    date: receipt.date || "",
    total: receipt.total ?? 0,
    subtotal: receipt.subtotal ?? 0,
    tax: receipt.tax ?? 0,
    needs_review: !!receipt.needs_review,
    items: (receipt.items || []).map((it) => ({ ...it })),
  }));
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const setItem = (i, k, v) =>
    setForm((f) => ({
      ...f,
      items: f.items.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)),
    }));

  const addItem = () =>
    setForm((f) => ({
      ...f,
      items: [...f.items, { name: "", price: 0, category: "Other" }],
    }));

  const removeItem = (i) =>
    setForm((f) => ({ ...f, items: f.items.filter((_, idx) => idx !== i) }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateReceipt(receipt.id, {
        merchant: form.merchant,
        date: form.date,
        total: Number(form.total),
        subtotal: form.subtotal === null ? null : Number(form.subtotal),
        tax: form.tax === null ? null : Number(form.tax),
        items: form.items.map((it) => ({
          name: it.name,
          price: Number(it.price),
          category: it.category,
        })),
        needs_review: form.needs_review,
      });
      setSavedFlash(true);
      setTimeout(() => {
        onChanged();
        onClose();
      }, 500);
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      return;
    }
    setSaving(true);
    try {
      await deleteReceipt(receipt.id);
      onChanged();
      onClose();
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  };

  const verified = !receipt.needs_review && !receipt.possible_duplicate;

  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Edit receipt ${receipt.merchant}`}>
        <div className="modal-head">
          {verified && (
            <span className="seal seal-lg" title="Verified" aria-hidden>
              ✓
            </span>
          )}
          <h2 className="modal-title">Edit entry #{receipt.id}</h2>
          <button className="close-x" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
          {receipt.needs_review && <span className="badge badge-review">Needs review</span>}
          {receipt.possible_duplicate && (
            <span className="badge badge-duplicate">
              Possible duplicate — different photo, same store/date/total
            </span>
          )}
          {verified && (
            <span style={{ fontSize: 13.5, color: "var(--text-muted)" }}>
              Arithmetic checks out and no duplicate was found.
            </span>
          )}
        </div>

        <div className="form-grid">
          <div className="field">
            <label htmlFor="f-merchant">Merchant</label>
            <input
              id="f-merchant"
              value={form.merchant}
              onChange={(e) => setField("merchant", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="f-date">Date</label>
            <input
              id="f-date"
              className="mono"
              value={form.date}
              onChange={(e) => setField("date", e.target.value)}
              placeholder="YYYY-MM-DD"
            />
          </div>
        </div>

        <div className="trio" style={{ marginBottom: 14 }}>
          <div className="field">
            <label htmlFor="f-total">Total</label>
            <input
              id="f-total"
              className="mono"
              type="number"
              step="0.01"
              value={form.total}
              onChange={(e) => setField("total", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="f-subtotal">Subtotal</label>
            <input
              id="f-subtotal"
              className="mono"
              type="number"
              step="0.01"
              value={form.subtotal}
              onChange={(e) => setField("subtotal", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="f-tax">Tax</label>
            <input
              id="f-tax"
              className="mono"
              type="number"
              step="0.01"
              value={form.tax}
              onChange={(e) => setField("tax", e.target.value)}
            />
          </div>
        </div>

        <div className="field" style={{ marginBottom: 8 }}>
          <label htmlFor="f-review">Review flag</label>
          <select
            id="f-review"
            value={form.needs_review ? "yes" : "no"}
            onChange={(e) => setField("needs_review", e.target.value === "yes")}
          >
            <option value="no">Arithmetic verified</option>
            <option value="yes">Flagged for review</option>
          </select>
        </div>

        <p className="section-label" style={{ marginTop: 18 }}>
          Line items ({form.items.length}) · sum {money(form.items.reduce((a, i) => a + Number(i.price || 0), 0))}
        </p>

        <div className="item-editor">
          {form.items.map((it, i) => (
            <div key={i} className="item-edit-row">
              <input
                aria-label={`Item ${i + 1} name`}
                value={it.name}
                onChange={(e) => setItem(i, "name", e.target.value)}
                placeholder="Item name"
              />
              <input
                aria-label={`Item ${i + 1} price`}
                className="mono"
                type="number"
                step="0.01"
                value={it.price}
                onChange={(e) => setItem(i, "price", e.target.value)}
              />
              <select
                aria-label={`Item ${i + 1} category`}
                value={CATEGORIES.includes(it.category) ? it.category : "Other"}
                onChange={(e) => setItem(i, "category", e.target.value)}
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button className="remove-item" onClick={() => removeItem(i)} aria-label={`Remove item ${i + 1}`}>
                ✕
              </button>
            </div>
          ))}
          <button className="add-item" onClick={addItem}>
            + Add item
          </button>
        </div>

        {error && (
          <div className="error-note" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        <div className="modal-actions">
          <button className="btn btn-danger" onClick={remove} disabled={saving}>
            {confirmingDelete ? "Confirm delete" : "Delete receipt"}
          </button>
          <div className="group">
            {savedFlash && <span className="save-flash">Saved ✓</span>}
            <button className="btn btn-ghost" onClick={onClose} disabled={saving}>
              Discard changes
            </button>
            <button className="btn btn-gold" onClick={save} disabled={saving}>
              Save changes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
