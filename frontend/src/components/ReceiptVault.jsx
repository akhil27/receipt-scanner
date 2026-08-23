import { useEffect, useMemo, useState } from "react";
import { getReceipts } from "../api/client.js";
import ReceiptCard from "./ReceiptCard.jsx";
import ReceiptEditModal from "./ReceiptEditModal.jsx";

const FILTERS = [
  { id: "all", label: "All entries" },
  { id: "review", label: "Needs review" },
  { id: "duplicates", label: "Possible duplicates" },
];

export default function ReceiptVault({ dataVersion, onChanged }) {
  const [receipts, setReceipts] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    getReceipts()
      .then(setReceipts)
      .catch((e) => setError(e.message));
  }, [dataVersion]);

  const visible = useMemo(() => {
    if (!receipts) return [];
    let list = receipts;
    if (filter === "review") list = list.filter((r) => r.needs_review);
    if (filter === "duplicates") list = list.filter((r) => r.possible_duplicate);
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (r) =>
          (r.merchant || "").toLowerCase().includes(q) ||
          (r.items || []).some((it) => (it.name || "").toLowerCase().includes(q))
      );
    }
    return list;
  }, [receipts, filter, query]);

  if (error)
    return (
      <section>
        <h1 className="view-title">Vault</h1>
        <div className="error-note">{error}</div>
      </section>
    );

  if (!receipts)
    return (
      <section>
        <h1 className="view-title">Vault</h1>
        <p className="empty-note">Unlocking the vault…</p>
      </section>
    );

  return (
    <section>
      <h1 className="view-title">The Vault</h1>
      <p className="view-lede">
        Every receipt on record. Open an entry to correct any field the scanner misread.
      </p>

      <div className="vault-toolbar">
        <input
          className="search-input"
          placeholder="Search by store or item…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search receipts"
        />
        {FILTERS.map((f) => (
          <button
            key={f.id}
            className={`chip${filter === f.id ? " on" : ""}`}
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
          >
            {f.label}
          </button>
        ))}
      </div>

      <p className="vault-count">
        Showing {visible.length} of {receipts.length} entries
      </p>

      {visible.length === 0 ? (
        <div className="empty-state">
          {receipts.length === 0 ? (
            <>
              <strong>The ledger is empty.</strong>
              Upload your first receipt and it will be recorded here.
              <div style={{ marginTop: 14 }}>
                <button className="link-btn" onClick={() => (window.location.hash = "#/upload")}>
                  Upload a receipt →
                </button>
              </div>
            </>
          ) : (
            <>
              <strong>No entries match.</strong>
              Try a different search or clear the filters.
            </>
          )}
        </div>
      ) : (
        <div className="entry-list">
          {visible.map((r) => (
            <ReceiptCard key={r.id} receipt={r} onOpen={setEditing} />
          ))}
        </div>
      )}

      {editing && (
        <ReceiptEditModal receipt={editing} onClose={() => setEditing(null)} onChanged={onChanged} />
      )}
    </section>
  );
}
