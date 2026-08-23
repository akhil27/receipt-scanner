import { useEffect, useState } from "react";

export default function ApiKeyModal({ apiKey, onSave, onClose }) {
  const [value, setValue] = useState(apiKey);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label="API key settings" style={{ width: "min(480px, 100%)" }}>
        <div className="modal-head">
          <h2 className="modal-title">API key</h2>
          <button className="close-x" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="view-lede" style={{ marginBottom: 18 }}>
          Receipt extraction runs through a vision model that needs an API key.
          Paste your own key and it stays on this device — it is sent only with
          your upload requests, never stored on the server.
        </p>

        <div className="field" style={{ marginBottom: 20 }}>
          <label htmlFor="f-apikey">Key</label>
          <input
            id="f-apikey"
            type="password"
            autoComplete="off"
            placeholder="Paste your API key"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </div>

        <div className="modal-actions">
          <button className="btn btn-danger" onClick={() => { setValue(""); onSave(""); onClose(); }}>
            Clear key
          </button>
          <button
            className="btn btn-gold"
            onClick={() => {
              onSave(value.trim());
              onClose();
            }}
          >
            Save key
          </button>
        </div>
      </div>
    </div>
  );
}
