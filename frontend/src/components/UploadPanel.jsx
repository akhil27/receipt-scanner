import { useEffect, useRef, useState } from "react";
import { uploadReceipt } from "../api/client.js";

const STAGES = ["Uploading", "Extracting", "Validating", "Checking duplicates", "Complete"];

function money(n) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n ?? 0);
}

export default function UploadPanel({ apiKey, onSaved }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [stageIdx, setStageIdx] = useState(-1);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (preview) URL.revokeObjectURL(preview);
  }, []);

  const pickFile = (f) => {
    if (!f) return;
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError(null);
    setStageIdx(-1);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    pickFile(e.dataTransfer.files && e.dataTransfer.files[0]);
  };

  const startPipeline = async () => {
    if (!file) return;
    setError(null);
    setResult(null);
    setStageIdx(0);

    timerRef.current = setInterval(() => {
      setStageIdx((i) => Math.min(i + 1, STAGES.length - 2));
    }, 1100);

    try {
      const saved = await uploadReceipt(file, apiKey);
      clearInterval(timerRef.current);
      setStageIdx(STAGES.length - 1);
      setResult(saved);
      onSaved();
    } catch (e) {
      clearInterval(timerRef.current);
      setStageIdx(-1);
      setError(e.message || "Extraction failed");
    }
  };

  const reset = () => {
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
    setResult(null);
    setError(null);
    setStageIdx(-1);
  };

  const busy = stageIdx >= 0 && !result;

  return (
    <section>
      <h1 className="view-title">Upload a receipt</h1>
      <p className="view-lede">
        Drop in a photo or PDF of any receipt. Extraction pulls the store, date,
        line items and totals, and arithmetic is checked before it enters the ledger.
      </p>

      {!file && (
        <div
          className={`dropzone${dragging ? " dragover" : ""}`}
          role="button"
          tabIndex={0}
          aria-label="Choose or drop a receipt image"
          onClick={() => inputRef.current && inputRef.current.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current && inputRef.current.click();
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <div className="dropzone-icon" aria-hidden>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4" />
              <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
            </svg>
          </div>
          <p className="dropzone-title">Drop your receipt here</p>
          <p className="dropzone-hint">JPG, PNG, WEBP or PDF — a clear photo works best</p>
          <input
            ref={inputRef}
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.pdf"
            hidden
            onChange={(e) => pickFile(e.target.files && e.target.files[0])}
          />
        </div>
      )}

      {file && (
        <div className="preview-wrap">
          <div>
            <div className="preview-frame">
              {file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf") ? (
                <iframe src={preview} title={`Preview of ${file.name}`} className="pdf-preview" />
              ) : (
                <img src={preview} alt={`Preview of ${file.name}`} />
              )}
            </div>
            {!apiKey && (
              <div className="error-note" style={{ marginTop: 14 }}>
                No API key saved yet — set one from the left rail, or extraction will fall back to
                the server key if it has one.
              </div>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn btn-gold" onClick={startPipeline} disabled={busy}>
                {busy ? "Reading receipt…" : "Upload receipt"}
              </button>
              {!busy && (
                <button className="btn btn-ghost" onClick={reset}>
                  Choose another
                </button>
              )}
            </div>
            {error && (
              <div className="error-note" role="alert">
                {error}
              </div>
            )}
          </div>

          <div>
            <ol className="stage-list" aria-live="polite">
              {STAGES.map((label, i) => {
                let state = "";
                if (stageIdx > i) state = "done";
                else if (stageIdx === i) state = "active";
                return (
                  <li key={label} className={`stage ${state}`}>
                    <span className="stage-dot" aria-hidden />
                    {label}
                    {state === "done" ? " ✓" : ""}
                  </li>
                );
              })}
            </ol>

            {result && (
              <article className="result-card">
                <div className="result-head">
                  <h2 className="result-store">{result.merchant}</h2>
                  <span className="result-total">{money(result.total)}</span>
                </div>
                <p className="result-meta">
                  {result.date} · #{result.id} · subtotal {money(result.subtotal)} · tax{" "}
                  {money(result.tax)}
                </p>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
                  {result.needs_review ? (
                    <span className="badge badge-review">Needs review</span>
                  ) : (
                    <>
                      <span className="seal" title="Validated" aria-label="Validated">
                        ✓
                      </span>
                      <span style={{ fontSize: 13, color: "var(--text-muted)", alignSelf: "center" }}>
                        Arithmetic checks out — sealed into the ledger.
                      </span>
                    </>
                  )}
                  {result.possible_duplicate && (
                    <span className="badge badge-duplicate">Possible duplicate</span>
                  )}
                </div>

                {(result.items || []).length > 0 && (
                  <table className="items-table">
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th>Category</th>
                        <th className="num">Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.items.map((it, idx) => (
                        <tr key={idx}>
                          <td>{it.name}</td>
                          <td>
                            <span className="cat-tag">{it.category}</span>
                          </td>
                          <td className="num">{money(it.price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                <div style={{ marginTop: 18 }}>
                  <button
                    className="link-btn"
                    onClick={() => (window.location.hash = "#/vault")}
                  >
                    Open the vault to review this entry →
                  </button>
                </div>
              </article>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
