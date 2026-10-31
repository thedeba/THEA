import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "thea_scan_face";
const MAX_SIDE = 640;
const MAX_DATA_URL_LENGTH = 900_000;

const ScanContext = createContext(null);

function readStoredScan() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.src === "string" && parsed.src.startsWith("data:")) {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}

export function ScanProvider({ children }) {
  const [scan, setScanState] = useState(readStoredScan);

  const setScan = useCallback((next) => {
    setScanState(next);
    try {
      if (next) {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } else {
        window.sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      /* storage can be unavailable; the in-memory scan still works */
    }
  }, []);

  const clearScan = useCallback(() => setScan(null), [setScan]);

  useEffect(() => {
    const handleLogout = () => clearScan();
    window.addEventListener("thea:logout", handleLogout);
    window.addEventListener("thea:unauthorized", handleLogout);
    return () => {
      window.removeEventListener("thea:logout", handleLogout);
      window.removeEventListener("thea:unauthorized", handleLogout);
    };
  }, [clearScan]);

  const value = useMemo(
    () => ({ scan, setScan, clearScan }),
    [scan, setScan, clearScan],
  );

  return <ScanContext.Provider value={value}>{children}</ScanContext.Provider>;
}

export function useScan() {
  const context = useContext(ScanContext);
  if (!context) throw new Error("useScan must be used inside ScanProvider");
  return context;
}

export async function fileToScanImage(file) {
  const source = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

  if (typeof source !== "string" || !source.startsWith("data:")) {
    throw new Error("Could not read that image");
  }

  const image = await new Promise((resolve, reject) => {
    const element = new Image();
    element.onload = () => resolve(element);
    element.onerror = () => reject(new Error("Could not decode that image"));
    element.src = source;
  });

  const scale = Math.min(1, MAX_SIDE / Math.max(image.width, image.height));
  if (scale === 1 && source.length <= MAX_DATA_URL_LENGTH) {
    return source;
  }

  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.width * scale));
  canvas.height = Math.max(1, Math.round(image.height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Could not process that image");
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85);
}
