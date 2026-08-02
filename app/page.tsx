"use client";

import { useCallback, useState } from "react";

type Phase = "idle" | "sending" | "success" | "error";

type DonationResult = {
  weight_lbs: number | null;
  weight_residual_est: number | null;
  item_type: string | null;
  confidence: number | null;
  charuco_detected: boolean;
  farmbrite_id: string | null;
  notes?: string | null;
};

export default function Home() {
  const [description, setDescription] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<DonationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const location =
    process.env.NEXT_PUBLIC_LOCATION_LABEL ?? "Cul2vate, Ellington Ag Center";

  const trigger = useCallback(async () => {
    setPhase("sending");
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/donate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: description.trim(),
          triggered_at: new Date().toISOString(),
          location
        })
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = (await res.json()) as DonationResult;
      setResult(data);
      setPhase("success");
      setDescription("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      setPhase("error");
    }
  }, [description, location]);

  const disabled = phase === "sending";

  return (
    <main>
      <div className="header">
        <div className="brand">APERTURE</div>
        <div className="loc">{location}</div>
      </div>

      <div className="card">
        <label htmlFor="note">Description (optional)</label>
        <textarea
          id="note"
          className="note"
          placeholder="e.g. frozen ground beef, mixed produce, canned goods…"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={disabled}
          autoCapitalize="sentences"
          autoCorrect="on"
          spellCheck
        />
      </div>

      <button className="trigger" onClick={trigger} disabled={disabled}>
        {phase === "sending" ? "Weighing…" : "Log Donation"}
      </button>

      <div className="card status" aria-live="polite">
        {phase === "idle" && (
          <div className="muted">
            Place the donation inside the taped zone, then press the green button.
          </div>
        )}

        {phase === "sending" && (
          <>
            <div className="row">
              <div className="spinner" />
              <div className="v">Weighing. One moment.</div>
            </div>
            <div className="muted">Usually about 4 to 10 seconds.</div>
          </>
        )}

        {phase === "success" && result && (
          <>
            <div className="headline ok">
              {result.weight_lbs !== null
                ? `${result.weight_lbs.toFixed(1)} lbs`
                : "Logged"}
            </div>
            <div className="row">
              <span className="k">Item</span>
              <span className="v">{result.item_type ?? "unspecified"}</span>
            </div>
            {result.farmbrite_id && (
              <div className="row">
                <span className="k">Farmbrite</span>
                <span className="v">#{result.farmbrite_id}</span>
              </div>
            )}
            {result.notes && <div className="muted">{result.notes}</div>}
          </>
        )}

        {phase === "error" && (
          <>
            <div className="headline err">Failed</div>
            <div className="muted">{error ?? "Unknown error."}</div>
            <div className="muted">Tap the button again to retry.</div>
          </>
        )}
      </div>

      <div className="footer">
        Null Systems. Tap outside the box to hide the keyboard.
      </div>
    </main>
  );
}
