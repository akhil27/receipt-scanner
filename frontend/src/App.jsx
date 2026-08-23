import { useEffect, useState } from "react";
import UploadPanel from "./components/UploadPanel.jsx";
import AnalyticsDashboard from "./components/AnalyticsDashboard.jsx";
import ReceiptVault from "./components/ReceiptVault.jsx";
import ApiKeyModal from "./components/ApiKeyModal.jsx";

const API_KEY_STORAGE = "receipt_scanner_api_key";

const VIEWS = [
  { id: "upload", label: "Upload", hash: "#/upload" },
  { id: "dashboard", label: "Dashboard", hash: "#/dashboard" },
  { id: "vault", label: "Vault", hash: "#/vault" },
];

function viewFromHash() {
  const h = window.location.hash.replace(/^#\/?/, "");
  return VIEWS.some((v) => v.id === h) ? h : "upload";
}

function Icon({ name }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };
  if (name === "upload")
    return (
      <svg {...common}>
        <path d="M12 16V4m0 0l-4 4m4-4l4 4" />
        <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
      </svg>
    );
  if (name === "dashboard")
    return (
      <svg {...common}>
        <path d="M4 19h16" />
        <path d="M7 15v-4m5 4V7m5 8v-6" />
      </svg>
    );
  return (
    <svg {...common}>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M9 4v4h6V4M4 12h16" />
    </svg>
  );
}

export default function App() {
  const [view, setView] = useState(viewFromHash);
  const [dataVersion, setDataVersion] = useState(0);
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(API_KEY_STORAGE) || "");
  const [keyModalOpen, setKeyModalOpen] = useState(false);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const saveApiKey = (key) => {
    if (key) localStorage.setItem(API_KEY_STORAGE, key);
    else localStorage.removeItem(API_KEY_STORAGE);
    setApiKey(key);
  };

  const go = (v) => {
    window.location.hash = `#/${v.id}`;
    setView(v.id);
  };

  const bumpData = () => setDataVersion((n) => n + 1);

  return (
    <div className="app">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ✓
          </span>
          <div>
            <span className="brand-name">Receipt Scanner</span>
            <span className="brand-sub">Expense ledger</span>
          </div>
        </div>
        <nav className="rail-nav" aria-label="Main navigation">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              className={`rail-link${view === v.id ? " active" : ""}`}
              onClick={() => go(v)}
              aria-current={view === v.id ? "page" : undefined}
            >
              <Icon name={v.id} />
              {v.label}
            </button>
          ))}
        </nav>
        <div className="rail-foot">
          <button className="key-btn" onClick={() => setKeyModalOpen(true)}>
            <span className={`key-dot${apiKey ? " set" : ""}`} aria-hidden />
            {apiKey ? "API key saved" : "Set API key"}
          </button>
        </div>
      </aside>

      <main className="content">
        {view === "upload" && <UploadPanel apiKey={apiKey} onSaved={bumpData} />}
        {view === "dashboard" && <AnalyticsDashboard dataVersion={dataVersion} />}
        {view === "vault" && <ReceiptVault dataVersion={dataVersion} onChanged={bumpData} />}
      </main>

      {keyModalOpen && (
        <ApiKeyModal apiKey={apiKey} onSave={saveApiKey} onClose={() => setKeyModalOpen(false)} />
      )}
    </div>
  );
}
