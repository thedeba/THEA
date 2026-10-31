import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, mediaUrl } from "../api";
import { useAlerts } from "../alerts";
import { EmptyState, ErrorBanner, PageLoader } from "../components/Feedback";
import Icon from "../components/Icons";
import Modal from "../components/Modal";
import { readRefreshSeconds, readStreamMode } from "../preferences";
import { useScan } from "../scan";
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

function HeroMotion({ onlineCount, monitoring, engineReady, coverage, scan }) {
  const activeBlips = Math.min(6, Math.max(0, onlineCount));
  const scanLabel = scan
    ? scan.name || "Query face"
    : monitoring
      ? "Live"
      : "Standby";
  return (
    <div className={`hero-motion${monitoring ? " live" : " paused"}`} aria-hidden="true">
      <div className="motion-topline">
        <span>Sector scan</span>
        <span className={scan ? "radar-scan-name" : undefined}>{scanLabel}</span>
      </div>
      <div className="motion-radar">
        <span className="radar-ring ring-1" />
        <span className="radar-ring ring-2" />
        <span className="radar-ring ring-3" />
        <span className="radar-cross cross-x" />
        <span className="radar-cross cross-y" />
        <span className="radar-ticks" />
        <span className="radar-pulse pulse-a" />
        <span className="radar-pulse pulse-b" />
        <span className="radar-sweep" />
        <span className="radar-scanline" />
        <span className="radar-orbit orbit-a"><span /></span>
        <span className="radar-orbit orbit-b"><span /></span>
        {scan ? (
          <span
            key={scan.created_ts || scan.src}
            className="radar-face is-query"
          >
            <img
              src={scan.src}
              alt={scan.name || "Face search query"}
            />
            <span className="radar-face-scan" />
          </span>
        ) : (
          <span className="radar-core">
            <Icon name="shield" size={18} />
          </span>
        )}
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
        <span>LOCK {activeBlips}</span>
        <span>{engineReady ? "Core ready" : "Core warmup"}</span>
      </div>
    </div>
  );
}

function useLiveSeries(value, maxPoints = 32) {
  const [series, setSeries] = useState(() => [value, value]);
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeries((previous) => [...previous, latest.current].slice(-maxPoints));
    }, 2600);
    return () => window.clearInterval(timer);
  }, [maxPoints]);
  return series;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function sparklinePaths(values, max, width = 100, height = 40) {
  if (values.length === 0) return { line: "", area: "" };
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - clamp(value / max, 0, 1) * height;
    return [x, y];
  });
  const line = points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");
  return { line, area: `${line} L${width},${height} L0,${height} Z` };
}

function LiveSparkline({ values, max = 100, tone = "accent" }) {
  const { line, area } = sparklinePaths(values, max);
  const lastValue = values[values.length - 1] ?? 0;
  const lastY = 40 - clamp(lastValue / max, 0, 1) * 40;
  return (
    <svg
      className={`live-sparkline ${tone}`}
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      role="img"
      aria-label="Live readiness trend"
    >
      <defs>
        <linearGradient id={`spark-fill-${tone}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.4" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="spark-area" d={area} fill={`url(#spark-fill-${tone})`} />
      <path className="spark-line" d={line} vectorEffect="non-scaling-stroke" />
      <circle className="spark-dot" cx="100" cy={lastY} r="1.6" />
    </svg>
  );
}

function LiveBars({ values, max = 1 }) {
  return (
    <div className="live-bars" role="img" aria-label="Live camera coverage">
      {values.map((value, index) => (
        <span
          key={index}
          className={index === values.length - 1 ? "is-live" : ""}
          style={{ height: `${Math.max(6, clamp(value / max, 0, 1) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function ReadinessPanel({
  postureScore,
  postureLabel,
  coverage,
  engineReady,
  watchlistCount,
  monitoring,
}) {
  const scoreHistory = useLiveSeries(postureScore, 36);
  const coverageHistory = useLiveSeries(coverage, 24);

  return (
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

      <div className="posture-graphs">
        <div className="posture-graph">
          <div className="posture-graph-head">
            <span>Readiness trend</span>
            <strong className="mono">{postureScore}%</strong>
          </div>
          <LiveSparkline values={scoreHistory} max={100} />
        </div>
        <div className="posture-graph">
          <div className="posture-graph-head">
            <span>Camera coverage</span>
            <strong className="mono">{Math.round(coverage * 100)}%</strong>
          </div>
          <LiveBars values={coverageHistory} max={1} />
        </div>
      </div>
    </section>
  );
}

function FaceAnalysisPanel({ faces, connected }) {
  const [pinnedId, setPinnedId] = useState(null);
  const pinned = pinnedId ? faces.find((face) => face.id === pinnedId) : null;
  const selected = pinned || faces[0] || null;
  const confidence = selected
    ? selected.known
      ? selected.match_percent ?? 0
      : Math.round((selected.detection_score ?? 0) * 100)
    : 0;

  useEffect(() => {
    if (pinnedId && !faces.some((face) => face.id === pinnedId)) {
      setPinnedId(null);
    }
  }, [faces, pinnedId]);

  return (
    <section className="panel face-analysis-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Live biometrics</p>
          <h2>Face analysis</h2>
        </div>
        <span className={`badge ${connected ? "badge-live" : "badge-offline"}`}>
          {connected ? "Live" : "Offline"}
        </span>
      </div>

      <div className={`face-viewport${selected ? " has-face" : ""}`}>
        {selected ? (
          <>
            <img
              key={selected.id}
              className="face-zoom"
              src={mediaUrl(selected.thumbnail_url)}
              alt={selected.person_name || "Detected face"}
            />
            <span className="face-scanline" aria-hidden="true" />
            <span className="face-reticle" aria-hidden="true" />
            <span className={`face-status ${selected.known ? "is-known" : "is-unknown"}`}>
              {selected.known ? "MATCH" : "UNKNOWN"}
            </span>
            <span className="face-camera">{selected.camera_name}</span>
          </>
        ) : (
          <div className="face-empty">
            <span className="face-empty-ring" />
            <Icon name="crosshair" size={26} />
            <p>Waiting for a face</p>
            <span className="muted">The next detected face will appear here.</span>
          </div>
        )}
      </div>

      {selected ? (
        <>
          <div className="face-identity">
            <div>
              <span className="hud-label">Identity</span>
              <strong>{selected.known ? selected.person_name : "Unknown face"}</strong>
              {!selected.known && selected.person_name ? (
                <span className="control-meta">
                  Closest match: {selected.person_name} · {selected.match_percent}%
                </span>
              ) : (
                <span className="control-meta">
                  {selected.known ? "Confirmed watchlist match" : "Not on watchlist"}
                </span>
              )}
            </div>
            <span className="face-track mono">
              T{String(selected.track_id).padStart(2, "0")}
            </span>
          </div>

          <div className="face-confidence">
            <div className="face-confidence-head">
              <span>{selected.known ? "Match confidence" : "Detection score"}</span>
              <strong>{confidence}%</strong>
            </div>
            <div className="face-confidence-bar">
              <span style={{ width: `${confidence}%` }} />
            </div>
          </div>

          <div className="face-metrics">
            <div>
              <span>Camera</span>
              <strong>{selected.camera_name}</strong>
            </div>
            <div>
              <span>Detected</span>
              <strong>{formatTime(selected.created_at)}</strong>
            </div>
            <div>
              <span>Face box</span>
              <strong>
                {selected.width}×{selected.height}
              </strong>
            </div>
            <div>
              <span>Detector</span>
              <strong>{Math.round((selected.detection_score ?? 0) * 100)}%</strong>
            </div>
          </div>
        </>
      ) : null}

      {faces.length > 0 ? (
        <div className="face-history-wrap">
          <div className="face-history-head">
            <span className="hud-label">Recent faces</span>
            {pinnedId ? (
              <button
                type="button"
                className="face-live-button"
                onClick={() => setPinnedId(null)}
              >
                <span className="status-dot online" />
                Follow live
              </button>
            ) : (
              <span className="face-live-tag">
                <span className="status-dot online" />
                Live
              </span>
            )}
          </div>
          <div className="face-history">
            {faces.slice(0, 8).map((face) => (
              <button
                type="button"
                key={face.id}
                className={`face-thumb${selected?.id === face.id ? " active" : ""}${
                  face.known ? " known" : ""
                }`}
                onClick={() => setPinnedId(face.id)}
                title={`${face.known ? face.person_name : "Unknown"} · ${face.camera_name}`}
              >
                <img src={mediaUrl(face.thumbnail_url)} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function Dashboard() {
  const { recentAlerts, recentFaces, connected, soundEnabled, popupsEnabled, clearAlerts } =
    useAlerts();
  const { scan } = useScan();
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
  const [adminBusy, setAdminBusy] = useState(false);
  const [thresholdDraft, setThresholdDraft] = useState(0.45);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const thresholdDirtyRef = useRef(false);
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
    if (controls && !thresholdDirtyRef.current) {
      setThresholdDraft(controls.match_threshold);
    }
  }, [controls]);

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

  const patchControls = async (patch, message) => {
    setAdminBusy(true);
    setActionError("");
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
      setActionError(exc.message);
    } finally {
      setAdminBusy(false);
    }
  };

  const toggleMonitoring = () => {
    const next = !monitoring;
    patchControls(
      { monitoring_enabled: next },
      next ? "Monitoring resumed" : "Monitoring paused",
    );
  };

  const clearHistory = async () => {
    setClearing(true);
    setActionError("");
    try {
      const result = await api("/api/alerts", { method: "DELETE" });
      clearAlerts();
      setPaths([]);
      setConfirmClear(false);
      setNotice(
        `${result.deleted} alerts cleared${
          result.snapshots_removed ? ` · ${result.snapshots_removed} snapshots removed` : ""
        }`,
      );
      await load();
    } catch (exc) {
      setActionError(exc.message);
    } finally {
      setClearing(false);
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
        <div className="hero-ambient" aria-hidden="true">
          <span className="ambient-orb orb-a" />
          <span className="ambient-orb orb-b" />
          <span className="ambient-ring ring-a" />
          <span className="ambient-ring ring-b" />
          <span className="ambient-scan" />
          {Array.from({ length: 14 }, (_, index) => (
            <span
              key={index}
              className="ambient-particle"
              style={{
                "--x": `${(index * 37 + 7) % 100}%`,
                "--y": `${(index * 53 + 11) % 100}%`,
                "--delay": `${(index * 0.73).toFixed(2)}s`,
                "--duration": `${7 + (index % 5) * 2}s`,
                "--size": `${2 + (index % 3)}px`,
              }}
            />
          ))}
        </div>
        <div className="hero-frame" aria-hidden="true">
          <span className="frame-corner tl" />
          <span className="frame-corner tr" />
          <span className="frame-corner bl" />
          <span className="frame-corner br" />
        </div>

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
          scan={scan}
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
          <FaceAnalysisPanel faces={recentFaces} connected={connected} />

          <section className="panel signal-feed-panel">
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

          <ReadinessPanel
            postureScore={postureScore}
            postureLabel={postureLabel}
            coverage={coverage}
            engineReady={engineReady}
            watchlistCount={watchlistCount}
            monitoring={monitoring}
          />

          <section className="panel admin-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Administrator</p>
                <h2>Admin controls</h2>
              </div>
              <span className="badge badge-neutral">Admin</span>
            </div>

            <div className="admin-actions">
              <button
                type="button"
                className={`admin-action ${monitoring ? "is-on" : "is-off"}`}
                onClick={toggleMonitoring}
                disabled={adminBusy}
              >
                <span className="control-icon">
                  <Icon name={monitoring ? "pause" : "play"} size={16} />
                </span>
                <span className="admin-action-copy">
                  <strong>{monitoring ? "Pause monitoring" : "Resume monitoring"}</strong>
                  <span className="control-meta">Face matching on every camera</span>
                </span>
              </button>

              <button
                type="button"
                className="admin-action"
                onClick={reloadCameras}
                disabled={reloading}
              >
                <span className="control-icon">
                  <Icon name="camera" size={16} />
                </span>
                <span className="admin-action-copy">
                  <strong>{reloading ? "Reloading cameras" : "Reload cameras"}</strong>
                  <span className="control-meta">Re-read config/cameras.yaml</span>
                </span>
              </button>

              <button
                type="button"
                className="admin-action danger"
                onClick={() => setConfirmClear(true)}
                disabled={clearing || (health?.alerts ?? 0) === 0}
              >
                <span className="control-icon danger">
                  <Icon name="trash" size={16} />
                </span>
                <span className="admin-action-copy">
                  <strong>Clear alert history</strong>
                  <span className="control-meta">{health?.alerts ?? 0} alerts stored</span>
                </span>
              </button>

              <Link to="/settings" className="admin-action">
                <span className="control-icon">
                  <Icon name="sliders" size={16} />
                </span>
                <span className="admin-action-copy">
                  <strong>Open settings</strong>
                  <span className="control-meta">Engines, feeds and notifications</span>
                </span>
              </Link>
            </div>

            <div className="admin-threshold">
              <div className="admin-threshold-head">
                <span className="hud-label">Match threshold</span>
                <strong>{Math.round(thresholdDraft * 100)}%</strong>
              </div>
              <input
                type="range"
                min="0.2"
                max="0.9"
                step="0.01"
                value={thresholdDraft}
                className="hud-range"
                onChange={(event) => {
                  setThresholdDraft(Number(event.target.value));
                  thresholdDirtyRef.current = true;
                }}
                aria-label="Match threshold"
              />
              <div className="admin-threshold-actions">
                <span className="control-meta">Live {Math.round(threshold * 100)}%</span>
                <button
                  type="button"
                  className="ghost-button small"
                  onClick={() =>
                    patchControls(
                      { match_threshold: Number(thresholdDraft) },
                      `Threshold set to ${Math.round(thresholdDraft * 100)}%`,
                    )
                  }
                  disabled={adminBusy || Math.abs(thresholdDraft - threshold) < 0.005}
                >
                  Apply
                </button>
              </div>
            </div>
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

      <section className="panel cross-camera-panel">
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

      {confirmClear ? (
        <Modal
          title="Clear alert history"
          onClose={() => {
            if (!clearing) setConfirmClear(false);
          }}
          footer={
            <div className="modal-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => setConfirmClear(false)}
                disabled={clearing}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={clearHistory}
                disabled={clearing}
              >
                <Icon name="trash" size={16} />
                {clearing ? "Clearing..." : "Clear everything"}
              </button>
            </div>
          }
        >
          <p>
            This permanently deletes <strong>{health?.alerts ?? 0} alerts</strong> and their stored
            snapshots. Watchlist people and camera configuration are not affected.
          </p>
          <p className="muted">This action cannot be undone.</p>
        </Modal>
      ) : null}

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
