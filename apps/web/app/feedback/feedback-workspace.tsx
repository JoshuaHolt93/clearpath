"use client";

import { feedbackViewSchema, type FeedbackView } from "@clearpath/validation";
import { MessageSquareText } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import shell from "../workspace-shell.module.css";
import styles from "./feedback.module.css";

async function responseMessage(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { message?: string } | null;
  return body?.message || fallback;
}

export function FeedbackWorkspace() {
  const [data, setData] = useState<FeedbackView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/feedback", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load feedback options."));
      const parsed = feedbackViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Feedback data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load feedback options.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const brokenFeatures = values.getAll("broken_features").map((value) => String(value));
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          reason: String(values.get("reason") ?? ""),
          featureExpectationReason: String(values.get("feature_expectation_reason") ?? "").trim() || null,
          brokenFeatures,
          description: String(values.get("description") ?? "").trim() || null,
          notifyWhenAddressed: values.get("notify_when_addressed") === "1",
        }),
      });
      const body = (await response.json().catch(() => null)) as { message?: string } | null;
      if (!response.ok) throw new Error(body?.message || "We could not save your feedback.");
      setStatus(body?.message || "Thanks for the feedback.");
      form.reset();
      setReason("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "We could not save your feedback.");
    } finally {
      setBusy(false);
    }
  };

  const content = (
    <div className={`${shell.page} ${styles.layout}`}>
      <header className={shell.pageHeader}>
        <div className={styles.headerHeading}>
          <MessageSquareText size={20} aria-hidden="true" />
          <div>
          <p className={shell.eyebrow}>Product Feedback</p><h1>Share Feedback</h1>
          <p>Tell us what is working, what is not, and what would make ClearPath more useful.</p>
          </div>
        </div>
      </header>

      {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      {status ? <p role="status" className={styles.status}>{status}</p> : null}
      {!data && !error ? <p className={styles.loading}>Loading feedback form...</p> : null}

      {data ? (
        <form className={styles.form} onSubmit={(event) => void submit(event)}>
          <fieldset disabled={busy}>
            <legend>Reason</legend>
            <div className={styles.choiceGrid}>
              {data.options.reasons.map(([value, label]) => (
                <label key={value} className={styles.choice}>
                  <input type="radio" name="reason" value={value} required checked={reason === value} onChange={() => setReason(value)} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {reason === "feature_expectations" ? (
            <fieldset disabled={busy}>
              <legend>What missed expectations?</legend>
              <div className={styles.choiceGrid}>
                {data.options.featureExpectationReasons.map(([value, label]) => (
                  <label key={value} className={styles.choice}>
                    <input type="radio" name="feature_expectation_reason" value={value} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}

          {reason === "broken" ? (
            <fieldset disabled={busy}>
              <legend>Which features were not working?</legend>
              <div className={styles.choiceGrid}>
                {data.options.brokenFeatures.map(([value, label]) => (
                  <label key={value} className={styles.choice}>
                    <input type="checkbox" name="broken_features" value={value} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}

          <label className={styles.checkboxRow}>
            <input type="checkbox" name="notify_when_addressed" value="1" disabled={busy} />
            <span>Notify me if this is fixed or addressed.</span>
          </label>

          <label className={styles.textField}>Optional Description
            <textarea name="description" rows={5} disabled={busy} placeholder="Tell us what happened, what you expected, or what would make ClearPath more useful." />
          </label>

          <button type="submit" disabled={busy}>Send Feedback</button>
        </form>
      ) : null}
    </div>
  );

  return <AuthenticatedPageFrame session={data?.session}>{content}</AuthenticatedPageFrame>;
}
