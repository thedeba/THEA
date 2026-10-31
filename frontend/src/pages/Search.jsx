import { useEffect, useRef, useState } from "react";
import { api, mediaUrl } from "../api";
import { EmptyState, ErrorBanner, Spinner } from "../components/Feedback";
import Icon from "../components/Icons";
import { fileToScanImage, useScan } from "../scan";
import { formatDateTime } from "../utils";

export default function Search() {
  const { setScan, clearScan } = useScan();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [threshold, setThreshold] = useState(0.45);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const scanRequestRef = useRef(0);
  const { scan } = useScan();

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const chooseFile = async (event) => {
    const next = event.target.files?.[0] || null;
    setFile(next);
    scanRequestRef.current += 1;
    const requestId = scanRequestRef.current;
    if (!next) {
      clearScan();
      return;
    }
    try {
      const src = await fileToScanImage(next);
      if (scanRequestRef.current !== requestId) return;
      setScan({ src, name: next.name, created_ts: Date.now() });
    } catch {
      if (scanRequestRef.current === requestId) clearScan();
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!file) {
      setError("Choose a photo to search");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    const form = new FormData();
    form.append("file", file);
    form.append("threshold", String(threshold));
    try {
      const data = await api("/api/search/face", { method: "POST", body: form });
      setResult(data);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    scanRequestRef.current += 1;
    setFile(null);
    setResult(null);
    setError("");
    clearScan();
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Face lookup</p>
          <h1>Search footage</h1>
          <p className="muted">
            Upload a face and compare it against every stored alert snapshot.
          </p>
        </div>
      </div>

      <ErrorBanner message={error} />

      <div className="search-layout">
        <section className="panel search-panel">
          <div className="panel-header">
            <div>
              <h2>Query photo</h2>
              <p className="muted">One clear, front-facing face works best.</p>
            </div>
          </div>
          <form onSubmit={submit} className="stack">
            <button
              type="button"
              className={`upload-drop${preview ? " has-preview" : ""}`}
              onClick={() => inputRef.current?.click()}
            >
              {preview ? (
                <img src={preview} alt="Search preview" />
              ) : (
                <>
                  <Icon name="upload" size={26} />
                  <strong>Choose a photo</strong>
                  <span>JPEG or PNG, one face</span>
                </>
              )}
            </button>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="visually-hidden"
              onChange={chooseFile}
            />
            <label className="field">
              <span>
                Similarity threshold <strong>{threshold.toFixed(2)}</strong>
              </span>
              <input
                type="range"
                min="0.2"
                max="0.8"
                step="0.01"
                value={threshold}
                onChange={(event) => setThreshold(Number(event.target.value))}
              />
              <span className="field-hint">
                Lower values return more candidates; higher values are stricter.
              </span>
            </label>
            <div className="filter-actions">
              <button type="button" className="ghost-button" onClick={reset}>
                Clear
              </button>
              <button type="submit" className="primary-button" disabled={loading || !file}>
                <Icon name="search" size={16} />
                {loading ? "Searching..." : "Search faces"}
              </button>
            </div>
          </form>
          <p className="search-note">
            THEA stores confirmed alert snapshots and their embeddings. Continuous recordings are
            not kept, so searches run against the alert history.
          </p>
        </section>

        <section className="panel results-panel">
          <div className="panel-header">
            <div>
              <h2>Matches</h2>
              <p className="muted">
                {result ? `${result.count} result${result.count === 1 ? "" : "s"} above threshold` : "Results appear here"}
              </p>
            </div>
            {result?.query_face ? (
              <span className="badge badge-neutral">
                Face detected · {Math.round(result.query_face.detection_score * 100)}%
              </span>
            ) : null}
          </div>

          {loading ? (
            <div className="center-pad">
              <Spinner label="Comparing embeddings" />
            </div>
          ) : !result ? (
            <EmptyState
              title="No search yet"
              message="Upload a photo to look for matching alert snapshots."
            />
          ) : result.results.length === 0 ? (
            <EmptyState
              title="No matches found"
              message="Try lowering the similarity threshold or using a clearer photo."
            />
          ) : (
            <div className="result-grid">
              {result.results.map((item) => (
                <article className="result-card" key={item.id}>
                  <div className="result-image">
                    {item.snapshot_url ? (
                      <img src={mediaUrl(item.snapshot_url)} alt={item.person_name} loading="lazy" />
                    ) : (
                      <span className="thumb-empty" />
                    )}
                    <span className="similarity-pill">
                      {Math.round(item.similarity * 100)}% similar
                    </span>
                  </div>
                  <div className="result-body">
                    <strong>{item.person_name}</strong>
                    <span className="muted">
                      {item.camera_name} · {formatDateTime(item.created_at)}
                    </span>
                    <span className="muted small-text">
                      Match confidence at capture: {item.confidence_percent}%
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
