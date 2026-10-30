import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../api";
import { useAlerts } from "../alerts";
import { EmptyState, ErrorBanner, PageLoader } from "../components/Feedback";
import Icon from "../components/Icons";
import Modal from "../components/Modal";
import { readRefreshSeconds, readStreamMode } from "../preferences";
import {
  formatClock,
  formatDate,
  formatTime,
  formatUptime,
  liveUptime,
  shortId,
} from "../utils";

function currentFullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

const SIGNAL_BARS = [32, 58, 44, 82, 66, 96, 54, 74, 48, 88, 62, 38, 70, 52];
const HERO_TITLE_WORDS = ["Security", "overview"];

function HeroMotion({ onlineCount, monitoring, engineReady, coverage }) {
  const activeBlips = Math.min(6, Math.max(0, onlineCount));
  return (
    <div className={`hero-motion${monitoring ? " live" : " paused"}`} aria-hidden="true">
      <div className="motion-topline">
        <span>Sector scan</span>
        <span>{monitoring ? "Live" : "Standby"}</span>
      </div>
      <div className="motion-radar">
        <span className="radar-ring ring-1" />
        <span className="radar-ring ring-2" />
        <span className="radar-ring ring-3" />
        <span className="radar-cross cross-x" />
        <span className="radar-cross cross-y" />
        <span className="radar-sweep" />
        <span className="radar-orbit"><span /></span>
        <span className="radar-core">
          <Icon name="shield" size={18} />
        </span>
        {Array.from({ length: 6 }, (_, index) => (
          <span
            key={index}
            className={`radar-blip blip-${index}${index < activeBlips ? " is-on" : ""}`}
            style={{ animationDelay: `${index * 0.37}s` }}
          />
        ))}
      </div>
      <div className="motion-signal">
        {SIGNAL_BARS.map((height, index) => (
          <span
            key={index}
            style={{ height: `${height}%`, animationDelay: `${index * 0.07}s` }}
          />
        ))}
      </div>
      <div className="motion-footer">
        <span>{Math.round(coverage * 100)}% coverage</span>
        <span>{engineReady ? "Core ready" : "Core warmup"}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { recentAlerts, connected, soundEnabled, popupsEnabled } = useAlerts();
  const [cameras, setCameras] = useState([]);
  const [health, setHealth] = useState(null);
  const [paths, setPaths] = useState([]);
  const [controls, setControls] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [reloading, setReloading] = useState(false);
  const [reconnectingId, setReconnectingId] = useState(null);
  const [streamNonce, setStreamNonce] = useState(0);
  const [refreshSeconds] = useState(() => readRefreshSeconds());
  const [streamMode] = useState(() => readStreamMode());
  const [focusId, setFocusId] = useState(null);
  const [focusFullscreen, setFocusFullscreen] = useState(false);
  const focusFeedRef = useRef(null);
  const [clock, setClock] = useState(() => new Date());

  const load = useCallback(async () => {
    const [cameraData, healthData, pathData, controlData] = await Promise.all([
      api("/api/cameras"),
      api("/api/health"),
      api("/api/alerts/paths?since_hours=24&limit=5"),
      api("/api/controls"),
    ]);
    setCameras(cameraData);
    setHealth(healthData);
    setPaths(pathData);
    setControls(controlData);
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    load()
      .catch((exc) => {
        if (active) setError(exc.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load]);

  useEffect(() => {
    let active = true;
    const timer = window.setInterval(() => {
      Promise.all([api("/api/cameras"), api("/api/health"), api("/api/controls")])
        .then(([cameraData, healthData, controlData]) => {
          if (!active) return;
          setCameras(cameraData);
          setHealth(healthData);
          setControls(controlData);
          if (streamMode === "snapshot") setStreamNonce((value) => value + 1);
        })
        .catch(() => {});
    }, refreshSeconds * 1000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refreshSeconds, streamMode]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      api("/api/alerts/paths?since_hours=24&limit=5")
        .then(setPaths)
        .catch(() => {});
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!focusId) return undefined;
    const node = focusFeedRef.current;
    const handleFullscreen = () => setFocusFullscreen(currentFullscreenElement() === node);
    document.addEventListener("fullscreenchange", handleFullscreen);
    document.addEventListener("webkitfullscreenchange", handleFullscreen);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreen);
      document.removeEventListener("webkitfullscreenchange", handleFullscreen);
      setFocusFullscreen(false);
      if (node && currentFullscreenElement() === node) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        exit?.call(document)?.catch?.(() => {});
      }
    };
  }, [focusId]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(""), 4500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const reloadCameras = async () => {
    setReloading(true);
    setActionError("");
    try {
      const data = await api("/api/cameras/reload", { method: "POST" });
      setCameras(data);
      setStreamNonce((value) => value + 1);
      setNotice("Camera configuration reloaded");
    } catch (exc) {
      setActionError(exc.message);
    } finally {
      setReloading(false);
    }
  };

  const reconnectCamera = async (cameraId) => {
    setReconnectingId(cameraId);
    setActionError("");
    try {
      const data = await api(`/api/cameras/${cameraId}/reconnect`, { method: "POST" });
      setCameras(data);
      setStreamNonce((value) => value + 1);
      setNotice(`Reconnecting ${cameraId}`);
    } catch (exc) {
      setActionError(exc.message);
    } finally {
      setReconnectingId(null);
    }
  };

  const toggleFocusFullscreen = async () => {
    const node = focusFeedRef.current;
    if (!node) return;
    try {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      const request = node.requestFullscreen || node.webkitRequestFullscreen;
      if (currentFullscreenElement() === node) {
        await exit.call(document);
      } else {
        await request.call(node);
      }
    } catch (exc) {
      setActionError(exc.message || "Fullscreen is not available in this browser.");
    }
  };

  const refreshStreams = () => {
    setStreamNonce((value) => value + 1);
    load().catch((exc) => setActionError(exc.message));
  };

  const monitoring = controls?.monitoring_enabled ?? health?.monitoring_enabled ?? true;
  const threshold = controls?.match_threshold ?? health?.match_threshold ?? 0.45;
  const engine = health?.face_engine;
  const engineReady = Boolean(engine?.ready);
  const engineText = engine?.backend === "mock" ? "Mock" : engineReady ? "InsightFace" : "Loading";
  const visibleCameras = cameras.filter((camera) => camera.configured !== false);
  const configError = cameras.find((camera) => camera.configured === false)?.last_error;
  const onlineCount = health?.cameras_online ?? visibleCameras.filter((camera) => camera.online).length;
  const totalCameras = health?.cameras ?? visibleCameras.length;
  const watchlistCount = health?.watchlist_people ?? 0;
  const coverage = totalCameras > 0 ? onlineCount / totalCameras : 0;
  const postureScore = Math.round(
    ((engineReady ? 0.3 : 0) +
      coverage * 0.3 +
      (watchlistCount > 0 ? 0.2 : 0) +
      (monitoring ? 0.2 : 0)) *
      100,
  );
  const postureLabel =
    postureScore >= 90
      ? "FORTIFIED"
      : postureScore >= 70
        ? "STABLE"
        : postureScore >= 45
          ? "DEGRADED"
          : "CRITICAL";
  const totalFrames = visibleCameras.reduce((sum, camera) => sum + camera.frames_processed, 0);
  const totalFaces = visibleCameras.reduce((sum, camera) => sum + camera.faces_detected, 0);
  const liveAlerts = recentAlerts.slice(0, 8);
  const focusCamera = visibleCameras.find((camera) => camera.id === focusId) || null;

  if (loading) return <PageLoader label="Initializing command center" />;

  return (
    <div className="page dashboard-page">
      <section className="command-hero">
        <div className="command-hero-main">
          <p className="eyebrow">THEA // COMMAND CENTER</p>
          <h1 className="hero-title" aria-label="Security overview">
            {HERO_TITLE_WORDS.map((word, wordIndex) => (
              <span className="hero-word" key={word}>
                {Array.from(word).map((letter, letterIndex) => (
                  <span
                    className="hero-letter"
                    key={`${word}-${letterIndex}`}
                    style={{ "--i": wordIndex * 10 + letterIndex }}
                  >
                    {letter}
                  </span>
                ))}
              </span>
            ))}
            <span className="hud-cursor" aria-hidden="true" />
          </h1>
          <p className="muted">
            Live camera health, recent matches and cross-camera trails.
          </p>
          <div className="hud-chip-row">
            <span className={`hud-chip ${onlineCount === totalCameras && totalCameras > 0 ? "ok" : "warn"}`}>
              <span className={`status-dot ${onlineCount === totalCameras && totalCameras > 0 ? "online" : "warn"}`} />
              {onlineCount}/{totalCameras} cameras
            </span>
            <span className={`hud-chip ${engineReady ? "ok" : "warn"}`}>
              <span className={`status-dot ${engineReady ? "online" : "warn"}`} />
              {engineText} engine
            </span>
            <span className={`hud-chip ${monitoring ? "ok" : "warn"}`}>
              <span className={`status-dot ${monitoring ? "online" : "warn"}`} />
              {monitoring ? "Monitoring live" : "Monitoring paused"}
            </span>
            <span className={`hud-chip ${connected ? "ok" : "warn"}`}>
              <span className={`status-dot ${connected ? "online" : "warn"}`} />
              {connected ? "Alert link online" : "Alert link offline"}
            </span>
          </div>
        </div>

        <HeroMotion
          onlineCount={onlineCount}
          monitoring={monitoring}
          engineReady={engineReady}
          coverage={coverage}
        />

        <div className="command-clock">
          <span className="hud-label">LOCAL TIME</span>
          <strong>{formatClock(clock)}</strong>
          <span>{formatDate(clock)}</span>
          <span className="uptime-line">UPTIME {formatUptime(liveUptime(health?.started_at, health?.uptime_seconds ?? 0, clock))}</span>
        </div>

        <div className="command-hero-actions">
          <Link className="hud-action hud-action-primary" to="/watchlist">
            <Icon name="plus" size={16} />
            Add person
          </Link>
          <Link className="hud-action" to="/search">
            <Icon name="crosshair" size={16} />
            Face search
          </Link>
          <Link className="hud-action" to="/alerts">
            <Icon name="alerts" size={16} />
            Alert log
          </Link>
          <button type="button" className="hud-action" onClick={refreshStreams}>
            <Icon name="refresh" size={16} />
            Refresh
          </button>
          <button
            type="button"
            className="hud-action"
            onClick={reloadCameras}
            disabled={reloading}
          >
            <Icon name="camera" size={16} />
            {reloading ? "Reloading" : "Reload cameras"}
          </button>
        </div>
      </section>

      <ErrorBanner message={error} onRetry={load} />
      <ErrorBanner message={configError} onRetry={reloadCameras} />
      <ErrorBanner message={actionError} onRetry={refreshStreams} />
      {notice ? <div className="notice-banner">{notice}</div> : null}

      <div className="command-grid">
        <section className="panel camera-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Vision grid</p>
              <h2>Live cameras</h2>
              <p className="muted">Sampled frames with face boxes drawn by the backend.</p>
            </div>
            <div className="camera-panel-status">
              <span className="mono">{totalFrames.toLocaleString()} frames</span>
              <span className="mono">{totalFaces.toLocaleString()} faces</span>
            </div>
          </div>

          {visibleCameras.length === 0 ? (
            <EmptyState
              title="No cameras configured"
              message="Add RTSP URLs to config/cameras.yaml, then use Reload cameras."
              action={
                <button type="button" className="primary-button" onClick={reloadCameras}>
                  Reload cameras
                </button>
              }
            />
          ) : (
            <div className="camera-grid command-camera-grid">
              {visibleCameras.map((camera) => {
                const path =
                  streamMode === "live"
                    ? `/api/cameras/${camera.id}/stream`
                    : `/api/cameras/${camera.id}/snapshot`;
                const source = `${mediaUrl(path)}&v=${streamNonce}`;
                const density =
                  camera.frames_processed > 0
                    ? Math.min(1, (camera.faces_detected / camera.frames_processed) * 3)
                    : 0;
                return (
                  <article
                    className={`camera-card hud-camera-card${camera.online ? "" : " offline"}`}
                    key={camera.id}
                  >
                    <div className="camera-frame">
                      <img
                        key={`${camera.id}-${streamNonce}-${streamMode}`}
                        src={source}
                        alt={`Live feed from ${camera.name}`}
                      />
                      <div className="camera-overlay">
                        <span
                          className={`badge ${
                            camera.online
                              ? "badge-live"
                              : camera.enabled
                                ? "badge-offline"
                                : "badge-neutral"
                          }`}
                        >
                          {camera.online ? "Live" : camera.enabled ? "Offline" : "Disabled"}
                        </span>
                        <span className="feed-mode">
                          {streamMode === "live" ? "CONTINUOUS" : "SNAPSHOT"}
                        </span>
                        {camera.location ? (
                          <span className="camera-location">{camera.location}</span>
                        ) : null}
                      </div>
                      <div className="camera-controls">
                        <button
                          type="button"
                          onClick={() => setFocusId(camera.id)}
                          title="Focus camera"
                        >
                          <Icon name="maximize" size={14} />
                          Focus
                        </button>
                        <a
                          href={mediaUrl(`/api/cameras/${camera.id}/snapshot`)}
                          target="_blank"
                          rel="noreferrer"
                          title="Open snapshot"
                        >
                          <Icon name="camera" size={14} />
                          Snap
                        </a>
                        <button
                          type="button"
                          onClick={() => reconnectCamera(camera.id)}
                          disabled={reconnectingId === camera.id}
                          title="Reconnect camera"
                        >
                          <Icon name="refresh" size={14} />
                          {reconnectingId === camera.id ? "..." : "Reconnect"}
                        </button>
                      </div>
                    </div>
                    <div className="camera-info">
                      <div className="camera-title-row">
                        <div>
                          <h3>{camera.name}</h3>
                          <p className="muted">
                            {camera.location || "Unassigned zone"}
                            {camera.width && camera.height
                              ? ` · ${camera.width}×${camera.height}`
                              : ""}
                            {camera.preview_fps
                              ? ` · ${Math.round(camera.preview_fps)} fps preview`
                              : ""}
                          </p>
                        </div>
                        <span className="mono uptime-chip">
                          {formatUptime(liveUptime(camera.started_at, camera.uptime_seconds, clock))}
                        </span>
                      </div>
                      <div className="telemetry-grid">
                        <div>
                          <span>AI FPS</span>
                          <strong>{camera.target_fps}</strong>
                        </div>
                        <div>
                          <span>Frames</span>
                          <strong>{camera.frames_processed.toLocaleString()}</strong>
                        </div>
                        <div>
                          <span>Faces</span>
                          <strong>{camera.faces_detected.toLocaleString()}</strong>
                        </div>
                        <div>
                          <span>Alerts</span>
                          <strong>{camera.alerts_created}</strong>
                        </div>
                      </div>
                      <div className="hud-meter camera-meter">
                        <span style={{ width: `${Math.round(density * 100)}%` }} />
                      </div>
                    </div>
                    {camera.last_error ? <p className="camera-error">{camera.last_error}</p> : null}
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <aside className="command-side">
          <section className="panel posture-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Readiness</p>
                <h2>Security posture</h2>
              </div>
              <span className="mono">{postureScore}%</span>
            </div>
            <div className="posture-body">
              <div
                className="posture-ring"
                style={{
                  background: `conic-gradient(var(--accent) ${postureScore * 3.6}deg, rgba(255,255,255,0.06) 0deg)`,
                }}
              >
                <div className="posture-ring-inner">
                  <strong>{postureScore}</strong>
                  <span>SCORE</span>
                </div>
              </div>
              <div className="posture-facts">
                <div>
                  <span>Coverage</span>
                  <strong>{Math.round(coverage * 100)}%</strong>
                </div>
                <div>
                  <span>Engine</span>
                  <strong>{engineReady ? "READY" : "WARMING"}</strong>
                </div>
                <div>
                  <span>Watchlist</span>
                  <strong>{watchlistCount} ID</strong>
                </div>
                <div>
                  <span>Detection</span>
                  <strong>{monitoring ? "LIVE" : "PAUSED"}</strong>
                </div>
              </div>
            </div>
            <p className={`posture-label posture-${postureLabel.toLowerCase()}`}>
              {postureLabel} // {monitoring ? "system armed" : "system in standby"}
            </p>
          </section>

          <section className="panel vitals-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Telemetry</p>
                <h2>System vitals</h2>
              </div>
              <Icon name="activity" size={18} />
            </div>
            <ul className="vital-list">
              <li>
                <span>Alert socket</span>
                <strong className={connected ? "vital-ok" : "vital-warn"}>
                  {connected ? "ONLINE" : "RETRYING"}
                </strong>
              </li>
              <li>
                <span>Search index</span>
                <strong>{health?.watchlist_index ?? "—"}</strong>
              </li>
              <li>
                <span>Threshold</span>
                <strong>{Math.round(threshold * 100)}%</strong>
              </li>
              <li>
                <span>Confirm frames</span>
                <strong>{controls?.consecutive_frames ?? "—"}</strong>
              </li>
              <li>
                <span>Uptime</span>
                <strong>{formatUptime(liveUptime(health?.started_at, health?.uptime_seconds ?? 0, clock))}</strong>
              </li>
              <li>
                <span>Sound / popups</span>
                <strong>
                  {soundEnabled ? "ON" : "OFF"} / {popupsEnabled ? "ON" : "OFF"}
                </strong>
              </li>
            </ul>
          </section>
        </aside>
      </div>

      <div className="two-column">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Signal feed</p>
              <h2>Recent alerts</h2>
              <p className="muted">Updates live over WebSocket.</p>
            </div>
            <Link className="text-link" to="/alerts">
              View history
            </Link>
          </div>
          {liveAlerts.length === 0 ? (
            <EmptyState
              title="No alerts yet"
              message="Confirmed watchlist matches will appear here in real time."
            />
          ) : (
            <ul className="alert-feed">
              {liveAlerts.map((alert) => (
                <li key={alert.id}>
                  <Link to="/alerts" className="alert-feed-item">
                    <span className="feed-thumb">
                      {alert.snapshot_url ? (
                        <img src={mediaUrl(alert.snapshot_url)} alt={alert.person_name} />
                      ) : null}
                    </span>
                    <span className="feed-main">
                      <span className="feed-title">
                        <strong>{alert.person_name}</strong>
                        <span className="match-pill">{alert.confidence_percent}%</span>
                      </span>
                      <span className="muted">
                        {alert.camera_name} · {formatTime(alert.created_at)}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Cross-camera</p>
              <h2>Movement trails</h2>
              <p className="muted">Same person seen on multiple cameras within two minutes.</p>
            </div>
          </div>
          {paths.length === 0 ? (
            <EmptyState
              title="No cross-camera trails"
              message="Trails appear when a matched person moves between cameras in a short window."
            />
          ) : (
            <ul className="trail-list">
              {paths.map((path) => (
                <li key={path.path_id} className="trail-item">
                  <span className="trail-icon">
                    <Icon name="trail" size={17} />
                  </span>
                  <div>
                    <div className="trail-title">
                      <strong>{path.person_name || "Unknown"}</strong>
                      <span className="muted">
                        {path.event_count} events · {shortId(path.path_id)}
                      </span>
                    </div>
                    <p className="trail-cameras">{path.cameras.join("  →  ")}</p>
                    <span className="muted small-text">
                      {formatTime(path.start_ts)} – {formatTime(path.end_ts)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {focusCamera ? (
        <Modal
          title={`${focusCamera.name} · focused feed`}
          onClose={() => setFocusId(null)}
          wide
          footer={
            <div className="modal-actions">
              <button type="button" className="ghost-button" onClick={() => setFocusId(null)}>
                Close
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => reconnectCamera(focusCamera.id)}
                disabled={reconnectingId === focusCamera.id}
              >
                <Icon name="refresh" size={16} />
                {reconnectingId === focusCamera.id ? "Reconnecting..." : "Reconnect camera"}
              </button>
            </div>
          }
        >
          <div className="focus-feed" ref={focusFeedRef}>
            <img
              src={`${mediaUrl(
                streamMode === "live"
                  ? `/api/cameras/${focusCamera.id}/stream`
                  : `/api/cameras/${focusCamera.id}/snapshot`,
              )}&v=${streamNonce}`}
              alt={`Focused feed from ${focusCamera.name}`}
              onDoubleClick={toggleFocusFullscreen}
            />
            <button
              type="button"
              className="focus-fullscreen-button"
              onClick={toggleFocusFullscreen}
              aria-label={focusFullscreen ? "Exit fullscreen" : "View feed fullscreen"}
            >
              <Icon name={focusFullscreen ? "minimize" : "maximize"} size={16} />
              <span>{focusFullscreen ? "Exit fullscreen" : "Fullscreen"}</span>
            </button>
          </div>
          <div className="focus-telemetry">
            <div>
              <span>Status</span>
              <strong>{focusCamera.online ? "LIVE" : "OFFLINE"}</strong>
            </div>
            <div>
              <span>Location</span>
              <strong>{focusCamera.location || "Unassigned"}</strong>
            </div>
            <div>
              <span>Resolution</span>
              <strong>
                {focusCamera.width && focusCamera.height
                  ? `${focusCamera.width}×${focusCamera.height}`
                  : "AUTO"}
              </strong>
            </div>
            <div>
              <span>Uptime</span>
              <strong>{formatUptime(liveUptime(focusCamera.started_at, focusCamera.uptime_seconds, clock))}</strong>
            </div>
            <div>
              <span>Frames</span>
              <strong>{focusCamera.frames_processed.toLocaleString()}</strong>
            </div>
            <div>
              <span>Faces / alerts</span>
              <strong>
                {focusCamera.faces_detected} / {focusCamera.alerts_created}
              </strong>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
