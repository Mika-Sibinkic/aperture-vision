"use client";

import { useEffect } from "react";

export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    const controller = new AbortController();
    window.addEventListener(
      "load",
      () => {
        navigator.serviceWorker
          .register("/sw.js", { scope: "/" })
          .catch(() => {
            // Silent. PWA works fine without SW, just no offline.
          });
      },
      { once: true, signal: controller.signal }
    );
    return () => controller.abort();
  }, []);
  return null;
}
