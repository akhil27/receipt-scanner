import { money } from "./format.js";

export default function ReceiptCard({ receipt, onOpen }) {
  const verified = !receipt.needs_review && !receipt.possible_duplicate;

  return (
    <button
      className="entry"
      onClick={() => onOpen(receipt)}
      aria-label={`Open receipt ${receipt.merchant}, ${money(receipt.total)}, ${receipt.date}`}
    >
      <div className="entry-head">
        {verified && (
          <span className="seal" title="Verified" aria-label="Verified entry">
            ✓
          </span>
        )}
        <span className="entry-id">#{receipt.id}</span>
        <h3 className="entry-store">{receipt.merchant}</h3>
        <span className="entry-total">{money(receipt.total)}</span>
      </div>

      <div className="entry-meta">
        <span>{receipt.date}</span>
        <span>{(receipt.items || []).length} items</span>
        <span>sub {money(receipt.subtotal)}</span>
        <span>tax {money(receipt.tax)}</span>
      </div>

      {(!verified || receipt.possible_duplicate) && (
        <div className="entry-badges">
          {receipt.needs_review && <span className="badge badge-review">Needs review</span>}
          {receipt.possible_duplicate && (
            <span className="badge badge-duplicate">Possible duplicate</span>
          )}
        </div>
      )}
    </button>
  );
}
