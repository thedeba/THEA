import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, mediaUrl } from "../api";
import { EmptyState, ErrorBanner, PageLoader, Spinner } from "../components/Feedback";
import Icon from "../components/Icons";
import Modal from "../components/Modal";
import { formatDateTime, shortId } from "../utils";

const PAGE_SIZE = 25;
const emptyFilters = { person: "", camera_id: "", date_from: "", date_to: "" };

function filtersFromParams(params) {
  return {
    person: params.get("person") || "",
    camera_id: params.get("camera_id") || "",
    date_from: params.get("date_from") || "",
    date_to: params.get("date_to") || "",
  };
}

export default function Alerts() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [form, setForm] = useState(() => filtersFromParams(searchParams));
  const [applied, setApplied] = useState(() => filtersFromParams(searchParams));
  const [cameras, setCameras] = useState([]);
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [trail, setTrail] = useState(null);
  const [trailLoading, setTrailLoading] = useState(false);
  const offset = Math.max(0, Number(searchParams.get("offset") || 0) || 0);

  useEffect(() => {
    api("/api/cameras")
      .then(setCameras)
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (applied.person) params.set("person", applied.person);
    if (applied.camera_id) params.set("camera_id", applied.camera_id);
    if (applied.date_from) params.set("date_from", applied.date_from);
    if (applied.date_to) params.set("date_to", applied.date_to);
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(offset));
    try {
      const result = await api(`/api/alerts?${params.toString()}`);
      setData(result);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }, [applied, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selected?.path_id) {
      setTrail(null);
      return undefined;
    }
    let active = true;
    setTrailLoading(true);
    api(`/api/alerts/paths/${selected.path_id}`)
      .then((items) => {
        if (active) setTrail(items);
      })
      .catch(() => {
        if (active) setTrail(null);
      })
      .finally(() => {
        if (active) setTrailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selected]);

  const applyFilters = (event) => {
    event.preventDefault();
    const next = new URLSearchParams();
    Object.entries(form).forEach(([key, value]) => {
      if (value) next.set(key, value);
    });
    setSearchParams(next);
    setApplied({ ...form });
  };

  const resetFilters = () => {
    setForm(emptyFilters);
    setApplied(emptyFilters);
    setSearchParams(new URLSearchParams());
  };

  const goToOffset = (nextOffset) => {
    const next = new URLSearchParams(searchParams);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    else next.delete("offset");
    setSearchParams(next);
  };

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Evidence log</p>
          <h1>Alert history</h1>
          <p className="muted">Every confirmed watchlist match, stored with its snapshot.</p>
        </div>
        <span className="badge badge-neutral">{data.total} alerts</span>
      </div>

      <form className="filter-bar" onSubmit={applyFilters}>
        <label className="field compact">
          <span>Person</span>
          <input
            type="text"
            value={form.person}
            placeholder="Search by name"
            onChange={(event) => setForm({ ...form, person: event.target.value })}
          />
        </label>
        <label className="field compact">
          <span>Camera</span>
          <select
            value={form.camera_id}
            onChange={(event) => setForm({ ...form, camera_id: event.target.value })}
          >
            <option value="">All cameras</option>
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field compact">
          <span>From</span>
          <input
            type="date"
            value={form.date_from}
            onChange={(event) => setForm({ ...form, date_from: event.target.value })}
          />
        </label>
        <label className="field compact">
          <span>To</span>
          <input
            type="date"
            value={form.date_to}
            onChange={(event) => setForm({ ...form, date_to: event.target.value })}
          />
        </label>
        <div className="filter-actions">
          <button type="button" className="ghost-button" onClick={resetFilters}>
            Reset
          </button>
          <button type="submit" className="primary-button">
            <Icon name="search" size={16} />
            Filter
          </button>
        </div>
      </form>

      <ErrorBanner message={error} onRetry={load} />

      {loading ? (
        <PageLoader label="Loading alerts" />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No matching alerts"
          message="Try widening the date range or clearing the filters."
        />
      ) : (
        <div className="table-card">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Snapshot</th>
                  <th>Person</th>
                  <th>Camera</th>
                  <th>Match</th>
                  <th>Time</th>
                  <th>Trail</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((alert) => (
                  <tr key={alert.id}>
                    <td>
                      <button
                        type="button"
                        className="thumb-button"
                        onClick={() => setSelected(alert)}
                        aria-label={`Open alert ${alert.id}`}
                      >
                        {alert.snapshot_url ? (
                          <img
                            src={mediaUrl(alert.snapshot_url)}
                            alt={alert.person_name}
                            loading="lazy"
                          />
                        ) : (
                          <span className="thumb-empty" />
                        )}
                      </button>
                    </td>
                    <td>
                      <strong>{alert.person_name}</strong>
                    </td>
                    <td>
                      <span>{alert.camera_name}</span>
                      <span className="cell-sub">{alert.camera_id}</span>
                    </td>
                    <td>
                      <span className="confidence-pill">{alert.confidence_percent}%</span>
                    </td>
                    <td>
                      <span>{formatDateTime(alert.created_at)}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="path-link"
                        onClick={() => setSelected(alert)}
                        title={alert.path_id}
                      >
                        <Icon name="trail" size={14} />
                        {shortId(alert.path_id)}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span className="muted">
              Page {currentPage} of {totalPages}
            </span>
            <div className="pagination-actions">
              <button
                type="button"
                className="ghost-button"
                disabled={offset === 0}
                onClick={() => goToOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="ghost-button"
                disabled={offset + PAGE_SIZE >= data.total}
                onClick={() => goToOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}

      {selected ? (
        <Modal
          title="Alert details"
          onClose={() => setSelected(null)}
          wide
          footer={
            <button type="button" className="primary-button" onClick={() => setSelected(null)}>
              Close
            </button>
          }
        >
          <div className="alert-detail">
            <div className="alert-detail-image">
              {selected.snapshot_url ? (
                <img src={mediaUrl(selected.snapshot_url)} alt={selected.person_name} />
              ) : (
                <span className="thumb-empty" />
              )}
            </div>
            <dl className="detail-list">
              <div>
                <dt>Person</dt>
                <dd>{selected.person_name}</dd>
              </div>
              <div>
                <dt>Camera</dt>
                <dd>
                  {selected.camera_name}
                  <span className="cell-sub">{selected.camera_id}</span>
                </dd>
              </div>
              <div>
                <dt>Match confidence</dt>
                <dd>{selected.confidence_percent}%</dd>
              </div>
              <div>
                <dt>Timestamp</dt>
                <dd>{formatDateTime(selected.created_at)}</dd>
              </div>
              <div>
                <dt>Trail ID</dt>
                <dd className="mono">{selected.path_id}</dd>
              </div>
            </dl>
          </div>

          {selected.path_id ? (
            <div className="trail-detail">
              <h3>Movement trail</h3>
              {trailLoading ? (
                <Spinner label="Loading trail" />
              ) : trail && trail.length > 1 ? (
                <ol className="trail-steps">
                  {trail.map((item) => (
                    <li key={item.id}>
                      <span className="trail-step-dot" />
                      <div>
                        <strong>{item.camera_name}</strong>
                        <span className="muted">{formatDateTime(item.created_at)}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted">
                  This alert is not linked to another camera yet. Cross-camera trails form when the
                  same person appears on a different camera within the configured time window.
                </p>
              )}
            </div>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}
