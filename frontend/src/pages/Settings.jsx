import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAlerts } from "../alerts";
import { ErrorBanner, PageLoader } from "../components/Feedback";
import Icon from "../components/Icons";
import {
  REFRESH_OPTIONS,
  readRefreshSeconds,
  readStreamMode,
  saveRefreshSeconds,
  saveStreamMode,
} from "../preferences";

export default function Settings() {
  const { soundEnabled, popupsEnabled, toggleSound, togglePopups } = useAlerts();
  const [controls, setControls] = useState(null);
  const [engines, setEngines] = useState(null);
  const [engineDraft, setEngineDraft] = useState("");
  const [engineBusy, setEngineBusy] = useState(false);
  const [thresholdDraft, setThresholdDraft] = useState(0.45);
  const thresholdDirtyRef = useRef(false);
  const [refreshSeconds, setRefreshSeconds] = useState(() => readRefreshSeconds());
  const [streamMode, setStreamMode] = useState(() => readStreamMode());
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [data, engineData] = await Promise.all([
      api("/api/controls"),
      api("/api/face-engines"),
    ]);
    setControls(data);
    setEngines(engineData);
    setEngineDraft(engineData.active_id);
    if (!thresholdDirtyRef.current) setThresholdDraft(data.match_threshold);
  }, []);

  useEffect(() => {
    load().catch((exc) => setError(exc.message));
  }, [load]);

  useEffect(() => {
    saveRefreshSeconds(refreshSeconds);
  }, [refreshSeconds]);

  useEffect(() => {
    saveStreamMode(streamMode);
  }, [streamMode]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(""), 4500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const selectEngine = async () => {
    if (!engines || engineDraft === engines.active_id) return;
    setEngineBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api(`/api/face-engines/${engineDraft}/select`, {
        method: "POST",
      });
      setEngines((current) => ({
        ...current,
        active_id: result.active_id,
        status: result.status,
      }));
      setNotice(result.message);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setEngineBusy(false);
    }
  };

  const patchControls = async (patch, message) => {
    setBusy(true);
    setError("");
    try {
      const next = await api("/api/controls", {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setControls(next);
      if ("match_threshold" in patch) {
        setThresholdDraft(next.match_threshold);
        thresholdDirtyRef.current = false;
      }
      if (message) setNotice(message);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  };

  if (!controls) {
    return (
      <div className="page settings-page">
        <header className="page-header">
          <div>
            <p className="eyebrow">Configuration</p>
            <h1>Settings</h1>
            <p className="muted">Detection, telemetry, feed and notification preferences.</p>
          </div>
        </header>
        <ErrorBanner message={error} onRetry={load} />
        {error ? null : <PageLoader label="Loading settings" />}
      </div>
    );
  }

  const monitoring = controls.monitoring_enabled;
  const threshold = controls.match_threshold;

  return (
    <div className="page settings-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Configuration</p>
          <h1>Settings</h1>
          <p className="muted">Detection, telemetry, feed and notification preferences.</p>
        </div>
      </header>

      <ErrorBanner message={error} onRetry={load} />
      {notice ? <div className="notice-banner">{notice}</div> : null}

      <div className="settings-stack">
        {engines ? (
          <section className="panel control-deck engine-deck">
            <div className="panel-header control-heading">
              <div>
                <p className="eyebrow">AI core</p>
                <h2>Face engine</h2>
                <p className="muted">
                  Choose the model used for detection, embeddings and watchlist matching.
                </p>
              </div>
              <span
                className={`badge ${
                  engines.status?.switching
                    ? "badge-neutral"
                    : engines.status?.ready
                      ? "badge-live"
                      : "badge-offline"
                }`}
              >
                {engines.status?.switching
                  ? "Switching"
                  : engines.status?.ready
                    ? "Engine ready"
                    : "Engine loading"}
              </span>
            </div>

            <div className="engine-grid" role="radiogroup" aria-label="Face engine">
              {engines.engines.map((engine) => {
                const active = engine.id === engines.active_id;
                const selected = engine.id === engineDraft;
                return (
                  <button
                    key={engine.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    className={`engine-option${selected ? " selected" : ""}${
                      active ? " active" : ""
                    }`}
                    onClick={() => setEngineDraft(engine.id)}
                    disabled={engineBusy}
                  >
                    <span className="engine-radio" aria-hidden="true" />
                    <span className="engine-copy">
                      <span className="engine-title">
                        <strong>{engine.label}</strong>
                        {engine.recommended ? (
                          <span className="engine-pill">Recommended</span>
                        ) : null}
                        {active ? <span className="engine-pill active">Active</span> : null}
                      </span>
                      <span className="control-meta">{engine.description}</span>
                      <span className="engine-meta">
                        {engine.tag} · {engine.cached ? "Cached locally" : "Downloads on first use"}
                        {engine.development ? " · Development only" : ""}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="engine-footer">
              <div className="engine-status">
                <span className="hud-label">Active engine</span>
                <strong>
                  {engines.engines.find((engine) => engine.id === engines.active_id)?.label ||
                    engines.active_id}
                </strong>
                <span className="control-meta">
                  {engines.status?.error
                    ? engines.status.error
                    : `${engines.status?.backend || "loading"} · ${
                        engines.status?.ready ? "ready" : "initializing"
                      }`}
                </span>
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={selectEngine}
                disabled={engineBusy || engineDraft === engines.active_id}
              >
                {engineBusy
                  ? "Switching engine…"
                  : engineDraft === engines.active_id
                    ? "Current engine"
                    : "Activate engine"}
              </button>
            </div>
            <p className="engine-note">
              Switching loads the selected model and re-indexes saved watchlist photos. Historical
              alerts keep the engine used when they were captured.
            </p>
          </section>
        ) : null}

        <section className="panel control-deck">
          <div className="panel-header control-heading">
            <div>
              <p className="eyebrow">Detection</p>
              <h2>Face matching</h2>
              <p className="muted">Pause detection or tune how closely faces must match.</p>
            </div>
            <span className={`badge ${monitoring ? "badge-live" : "badge-offline"}`}>
              {monitoring ? "Detection active" : "Detection paused"}
            </span>
          </div>

          <div className="control-grid">
            <article className={`control-tile ${monitoring ? "is-on" : "is-off"}`}>
              <span className="control-icon">
                <Icon name="shield" size={18} />
              </span>
              <div className="control-copy">
                <span className="hud-label">Detection engine</span>
                <strong>{monitoring ? "Monitoring live" : "Monitoring paused"}</strong>
                <span className="control-meta">Pause face matching across every camera feed.</span>
              </div>
              <button
                type="button"
                className={`switch${monitoring ? " on" : ""}`}
                onClick={() =>
                  patchControls(
                    { monitoring_enabled: !monitoring },
                    monitoring ? "Monitoring paused" : "Monitoring resumed",
                  )
                }
                disabled={busy}
                aria-label={monitoring ? "Pause monitoring" : "Resume monitoring"}
                aria-pressed={monitoring}
              >
                <span />
              </button>
            </article>

            <article className="control-tile control-tile-wide">
              <div className="control-copy">
                <span className="hud-label">Match sensitivity</span>
                <strong>{Math.round(thresholdDraft * 100)}%</strong>
                <span className="control-meta">
                  {thresholdDraft >= threshold + 0.005
                    ? "Stricter than live"
                    : thresholdDraft <= threshold - 0.005
                      ? "Looser than live"
                      : "Matches live threshold"}
                </span>
              </div>
              <input
                type="range"
                min="0.2"
                max="0.9"
                step="0.01"
                value={thresholdDraft}
                onChange={(event) => {
                  setThresholdDraft(Number(event.target.value));
                  thresholdDirtyRef.current = true;
                }}
                className="hud-range"
              />
              <div className="range-scale">
                <span>Broad</span>
                <span>Strict</span>
              </div>
              <button
                type="button"
                className="ghost-button small"
                onClick={() =>
                  patchControls(
                    { match_threshold: Number(thresholdDraft) },
                    `Threshold set to ${Math.round(thresholdDraft * 100)}%`,
                  )
                }
                disabled={busy || Math.abs(thresholdDraft - threshold) < 0.005}
              >
                Apply
              </button>
            </article>
          </div>
        </section>

        <section className="panel control-deck">
          <div className="panel-header control-heading">
            <div>
              <p className="eyebrow">Telemetry</p>
              <h2>Feeds and refresh</h2>
              <p className="muted">Control dashboard polling and how camera frames are displayed.</p>
            </div>
          </div>

          <div className="control-grid">
            <article className="control-tile">
              <span className="control-icon">
                <Icon name="clock" size={18} />
              </span>
              <div className="control-copy">
                <span className="hud-label">Telemetry refresh</span>
                <strong>{refreshSeconds}s</strong>
                <span className="control-meta">Camera and health polling interval.</span>
              </div>
              <select
                value={refreshSeconds}
                onChange={(event) => setRefreshSeconds(Number(event.target.value))}
                className="hud-select"
                aria-label="Telemetry refresh interval"
              >
                {REFRESH_OPTIONS.map((seconds) => (
                  <option key={seconds} value={seconds}>
                    {seconds} sec
                  </option>
                ))}
              </select>
            </article>

            <article className="control-tile">
              <span className="control-icon">
                <Icon name="layers" size={18} />
              </span>
              <div className="control-copy">
                <span className="hud-label">Feed mode</span>
                <strong>{streamMode === "live" ? "Continuous" : "Snapshot"}</strong>
                <span className="control-meta">Snapshot mode saves bandwidth.</span>
              </div>
              <div className="segmented">
                <button
                  type="button"
                  className={streamMode === "live" ? "active" : ""}
                  onClick={() => setStreamMode("live")}
                >
                  Live
                </button>
                <button
                  type="button"
                  className={streamMode === "snapshot" ? "active" : ""}
                  onClick={() => setStreamMode("snapshot")}
                >
                  Snap
                </button>
              </div>
            </article>
          </div>
        </section>

        <section className="panel control-deck">
          <div className="panel-header control-heading">
            <div>
              <p className="eyebrow">Notifications</p>
              <h2>Alert behavior</h2>
              <p className="muted">Choose how confirmed matches reach you.</p>
            </div>
          </div>

          <div className="control-grid">
            <article className={`control-tile ${soundEnabled ? "is-on" : "is-off"}`}>
              <span className="control-icon">
                <Icon name={soundEnabled ? "volume" : "muted"} size={18} />
              </span>
              <div className="control-copy">
                <span className="hud-label">Warning alarm</span>
                <strong>{soundEnabled ? "Armed" : "Muted"}</strong>
                <span className="control-meta">
                  Plays a warning siren when a watchlist match is confirmed.
                </span>
              </div>
              <button
                type="button"
                className={`switch${soundEnabled ? " on" : ""}`}
                onClick={toggleSound}
                aria-label={soundEnabled ? "Mute warning alarm" : "Enable warning alarm"}
                aria-pressed={soundEnabled}
              >
                <span />
              </button>
            </article>

            <article className={`control-tile ${popupsEnabled ? "is-on" : "is-off"}`}>
              <span className="control-icon">
                <Icon name={popupsEnabled ? "zap" : "pause"} size={18} />
              </span>
              <div className="control-copy">
                <span className="hud-label">Alert popups</span>
                <strong>{popupsEnabled ? "Enabled" : "Paused"}</strong>
                <span className="control-meta">Toast notifications for new matches.</span>
              </div>
              <button
                type="button"
                className={`switch${popupsEnabled ? " on" : ""}`}
                onClick={togglePopups}
                aria-label={popupsEnabled ? "Pause alert popups" : "Enable alert popups"}
                aria-pressed={popupsEnabled}
              >
                <span />
              </button>
            </article>
          </div>
        </section>
      </div>
    </div>
  );
}
