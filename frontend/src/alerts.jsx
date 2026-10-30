import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, clearToken, mediaUrl, wsUrl } from "./api";
import { formatTime } from "./utils";

const AlertContext = createContext(null);
const SOUND_KEY = "thea_sound_enabled";
const POPUPS_KEY = "thea_popups_enabled";
let audioContext = null;
let lastWarningAt = 0;

function getAudioContext() {
  if (!audioContext) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return null;
    audioContext = new AudioContext();
  }
  return audioContext;
}

function scheduleWarning(context) {
  const now = context.currentTime;
  const pulses = [
    { start: 0, frequency: 880, duration: 0.16 },
    { start: 0.2, frequency: 880, duration: 0.16 },
    { start: 0.4, frequency: 1175, duration: 0.34 },
  ];
  pulses.forEach((pulse) => {
    const start = now + pulse.start;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "triangle";
    oscillator.frequency.setValueAtTime(pulse.frequency, start);
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.2, start + 0.015);
    gain.gain.setValueAtTime(0.2, start + pulse.duration * 0.7);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + pulse.duration);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(start);
    oscillator.stop(start + pulse.duration);
  });
}

function playWarningSound() {
  const timestamp = Date.now();
  if (timestamp - lastWarningAt < 1000) return;
  lastWarningAt = timestamp;
  const context = getAudioContext();
  if (!context) return;
  if (context.state === "suspended") {
    context
      .resume()
      .then(() => scheduleWarning(context))
      .catch(() => {});
    return;
  }
  scheduleWarning(context);
}

function mergeAlerts(previous, incoming) {
  const map = new Map(previous.map((item) => [item.id, item]));
  incoming.forEach((item) => map.set(item.id, item));
  return Array.from(map.values())
    .sort((a, b) => b.created_ts - a.created_ts)
    .slice(0, 100);
}

export function AlertProvider({ children }) {
  const [recentAlerts, setRecentAlerts] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [connected, setConnected] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(
    () => localStorage.getItem(SOUND_KEY) !== "false",
  );
  const [popupsEnabled, setPopupsEnabled] = useState(
    () => localStorage.getItem(POPUPS_KEY) !== "false",
  );
  const soundRef = useRef(soundEnabled);
  const popupsRef = useRef(popupsEnabled);

  useEffect(() => {
    soundRef.current = soundEnabled;
    localStorage.setItem(SOUND_KEY, String(soundEnabled));
  }, [soundEnabled]);

  useEffect(() => {
    popupsRef.current = popupsEnabled;
    localStorage.setItem(POPUPS_KEY, String(popupsEnabled));
  }, [popupsEnabled]);

  useEffect(() => {
    const resume = () => {
      const context = getAudioContext();
      if (context && context.state === "suspended") context.resume().catch(() => {});
    };
    window.addEventListener("pointerdown", resume, { once: true });
    return () => window.removeEventListener("pointerdown", resume);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api("/api/alerts?limit=20")
      .then((data) => {
        if (!cancelled) setRecentAlerts((previous) => mergeAlerts(previous, data.items));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let socket = null;
    let stopped = false;
    let retry = 0;
    let reconnectTimer = null;
    let pingTimer = null;

    const handleAlert = (alert) => {
      setRecentAlerts((previous) => mergeAlerts(previous, [alert]));
      if (soundRef.current) playWarningSound();
      if (!popupsRef.current) return;
      const toast = { ...alert, toastKey: `${alert.id}-${Date.now()}` };
      setToasts((previous) => [toast, ...previous].slice(0, 4));
      window.setTimeout(() => {
        setToasts((previous) => previous.filter((item) => item.toastKey !== toast.toastKey));
      }, 9000);
    };

    const connect = () => {
      if (stopped) return;
      try {
        socket = new WebSocket(wsUrl());
      } catch {
        return;
      }
      socket.onopen = () => {
        retry = 0;
        setConnected(true);
        pingTimer = window.setInterval(() => {
          if (socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
        }, 20000);
      };
      socket.onmessage = (event) => {
        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        if (payload.type === "alert") handleAlert(payload);
        if (payload.type === "connected") setConnected(true);
      };
      socket.onclose = (event) => {
        setConnected(false);
        if (pingTimer) window.clearInterval(pingTimer);
        if (stopped) return;
        if (event.code === 4401) {
          clearToken();
          window.dispatchEvent(new Event("thea:unauthorized"));
          return;
        }
        const delay = Math.min(10000, 1000 * 2 ** Math.min(retry, 4));
        retry += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (pingTimer) window.clearInterval(pingTimer);
      socket?.close();
    };
  }, []);

  const dismissToast = useCallback((toastKey) => {
    setToasts((previous) => previous.filter((item) => item.toastKey !== toastKey));
  }, []);

  const toggleSound = useCallback(() => setSoundEnabled((value) => !value), []);
  const togglePopups = useCallback(() => setPopupsEnabled((value) => !value), []);

  const value = useMemo(
    () => ({
      recentAlerts,
      connected,
      soundEnabled,
      popupsEnabled,
      toggleSound,
      togglePopups,
    }),
    [recentAlerts, connected, soundEnabled, popupsEnabled, toggleSound, togglePopups],
  );

  return (
    <AlertContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((toast) => (
          <article className="alert-toast" key={toast.toastKey}>
            <div className="alert-toast-image">
              {toast.snapshot_url ? (
                <img src={mediaUrl(toast.snapshot_url)} alt={toast.person_name} />
              ) : null}
            </div>
            <div className="alert-toast-body">
              <div className="alert-toast-heading">
                <span className="live-dot" />
                <strong>{toast.person_name}</strong>
                <span className="match-pill">{toast.confidence_percent}%</span>
              </div>
              <p>
                {toast.camera_name} · {formatTime(toast.created_at)}
              </p>
              <div className="alert-toast-actions">
                <Link to="/alerts" onClick={() => dismissToast(toast.toastKey)}>
                  Open history
                </Link>
                <button type="button" onClick={() => dismissToast(toast.toastKey)}>
                  Dismiss
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </AlertContext.Provider>
  );
}

export function useAlerts() {
  const context = useContext(AlertContext);
  if (!context) throw new Error("useAlerts must be used inside AlertProvider");
  return context;
}
