"use client";

import {
  settingsViewSchema,
  householdInviteCreateResultSchema,
  type SettingsView,
} from "@clearpath/validation";
import { KeyRound, RefreshCw, Send, ShieldCheck, Trash2, UserMinus, Users } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./settings.module.css";

async function responseMessage(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { message?: string } | null;
  return body?.message || fallback;
}

export function SettingsWorkspace() {
  const [data, setData] = useState<SettingsView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [fallbackInviteUrl, setFallbackInviteUrl] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/settings", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load settings."));
      const parsed = settingsViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Settings data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load settings.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const runAction = async (payload: Record<string, unknown>, fallback: string, { reload = true }: { reload?: boolean } = {}) => {
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const response = await fetch("/api/settings/account", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await response.json().catch(() => null)) as { message?: string } | null;
      if (!response.ok) throw new Error(body?.message || fallback);
      setStatus(body?.message || "Saved.");
      if (reload) await load();
      return true;
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : fallback);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const submitPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const changed = await runAction(
      {
        action: "password",
        currentPassword: String(values.get("current_password") ?? ""),
        newPassword: String(values.get("new_password") ?? ""),
        confirmPassword: String(values.get("confirm_password") ?? ""),
      },
      "We could not update the password.",
      { reload: false },
    );
    if (changed) form.reset();
  };

  const submitHousehold = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await runAction({ action: "household", householdName: String(values.get("household_name") ?? "") }, "We could not update the household.");
  };

  const submitMfaPreference = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await runAction({ action: "mfa_preferences", mfaPreferredMethod: String(values.get("mfa_preferred_method") ?? "totp") }, "We could not update MFA preferences.");
  };

  const acknowledgeEthics = async () => {
    await runAction({ action: "ethics" }, "We could not record the acknowledgement.");
  };

  const submitDelete = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const deleted = await runAction(
      {
        action: "account_delete",
        currentPassword: String(values.get("delete_current_password") ?? ""),
        confirmation: String(values.get("delete_confirmation") ?? ""),
      },
      "We could not delete the account.",
      { reload: false },
    );
    if (deleted) window.location.assign("/login");
  };

  const submitInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setStatus("");
    setError("");
    setFallbackInviteUrl(null);
    try {
      const response = await fetch("/api/settings/invites", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ inviteEmail: String(values.get("invite_email") ?? ""), inviteRole: String(values.get("invite_role") ?? "editor") }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error((body as { message?: string } | null)?.message || "We could not create that invite.");
      const parsed = householdInviteCreateResultSchema.safeParse(body);
      if (parsed.success && !parsed.data.emailSent && parsed.data.fallbackInviteUrl) {
        setFallbackInviteUrl(parsed.data.fallbackInviteUrl);
        setStatus("Household invite created, but email delivery is unavailable. Share the fallback invite link below.");
      } else {
        setStatus(`Household invite sent to ${parsed.success ? parsed.data.invite.email : "the invitee"}.`);
      }
      form.reset();
      await load();
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : "We could not create that invite.");
    } finally {
      setBusy(false);
    }
  };

  const changeMemberRole = async (memberId: number, role: string) => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/settings/members/${memberId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ memberRole: role }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not update that member."));
      setStatus("Shared access permission updated.");
      await load();
    } catch (roleError) {
      setError(roleError instanceof Error ? roleError.message : "We could not update that member.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (url: string, success: string, fallback: string) => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(url, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseMessage(response, fallback));
      setStatus(success);
      await load();
    } catch (revokeError) {
      setError(revokeError instanceof Error ? revokeError.message : fallback);
    } finally {
      setBusy(false);
    }
  };

  const isPrimary = Boolean(data?.session.primaryAccountHolder);
  const activeMembers = (data?.householdMembers ?? []).filter((member) => member.status !== "revoked");

  const content = (
      <div className={styles.layout}>
        <header className={styles.header}>
          <div>
            <h1>Settings</h1>
            <p>Manage the household profile, security, shared access, and account lifecycle.</p>
          </div>
          <button type="button" onClick={() => void load()} disabled={busy}><RefreshCw size={16} aria-hidden="true" />Refresh</button>
        </header>

        {error ? <p role="alert" className={styles.error}>{error}</p> : null}
        {status ? <p role="status" className={styles.status}>{status}</p> : null}
        {!data && !error ? <p className={styles.loading}>Loading settings...</p> : null}

        {data ? (
          <div className={styles.sections}>
            <section className={styles.panel} aria-labelledby="settings-household">
              <header><Users size={18} aria-hidden="true" /><h2 id="settings-household">Household</h2></header>
              <p className={styles.meta}>Signed in as {data.email}. Plan: {data.session.planDisplayName}.</p>
              {isPrimary ? (
                <form onSubmit={(event) => void submitHousehold(event)}>
                  <label>Household Name<input name="household_name" defaultValue={data.householdName ?? ""} disabled={busy} /></label>
                  <button type="submit" disabled={busy}>Save Household</button>
                </form>
              ) : (
                <p className={styles.meta}>Shared household access: the primary account holder manages household settings.</p>
              )}
            </section>

            {isPrimary ? (
              <section className={styles.panel} aria-labelledby="settings-security">
                <header><KeyRound size={18} aria-hidden="true" /><h2 id="settings-security">Security</h2></header>
                <form onSubmit={(event) => void submitPassword(event)}>
                  <div className={styles.formGrid}>
                    <label>Current Password<input name="current_password" type="password" autoComplete="current-password" disabled={busy} required /></label>
                    <label>New Password<input name="new_password" type="password" autoComplete="new-password" disabled={busy} required /></label>
                    <label>Confirm New Password<input name="confirm_password" type="password" autoComplete="new-password" disabled={busy} required /></label>
                  </div>
                  <button type="submit" disabled={busy}>Update Password</button>
                </form>
                <form onSubmit={(event) => void submitMfaPreference(event)} className={styles.mfaForm}>
                  <fieldset disabled={busy}>
                    <legend>Sign-In Verification</legend>
                    <label><input type="radio" name="mfa_preferred_method" value="totp" defaultChecked={data.mfaPreferredMethod !== "push"} />Authenticator codes</label>
                    <label><input type="radio" name="mfa_preferred_method" value="push" defaultChecked={data.mfaPreferredMethod === "push"} />Duo Push approval{data.pushMfa.available ? "" : " (not configured)"}</label>
                  </fieldset>
                  <button type="submit" disabled={busy}>Save MFA Preference</button>
                </form>
              </section>
            ) : null}

            <section className={styles.panel} aria-labelledby="settings-ethics">
              <header><ShieldCheck size={18} aria-hidden="true" /><h2 id="settings-ethics">Ethics, Terms, And Privacy</h2></header>
              {data.ethicsAcknowledgedAt ? (
                <p className={styles.meta}>Acknowledged version {data.ethicsPolicyVersion} on {new Date(data.ethicsAcknowledgedAt).toLocaleDateString("en-US")}.</p>
              ) : (
                <>
                  <p className={styles.meta}>The current policy version has not been acknowledged yet.</p>
                  <button type="button" onClick={() => void acknowledgeEthics()} disabled={busy}>Acknowledge Policy</button>
                </>
              )}
            </section>

            {isPrimary ? (
              <section className={styles.panel} aria-labelledby="settings-shared">
                <header><Send size={18} aria-hidden="true" /><h2 id="settings-shared">Shared Household Access</h2></header>
                <form onSubmit={(event) => void submitInvite(event)}>
                  <div className={styles.formGrid}>
                    <label>Invite Email<input name="invite_email" type="email" disabled={busy} required /></label>
                    <label>Permission<select name="invite_role" defaultValue="editor" disabled={busy}>
                      {Object.entries(data.householdRoleOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select></label>
                  </div>
                  <button type="submit" disabled={busy}>Send Invite</button>
                </form>
                {fallbackInviteUrl ? <p className={styles.fallback}>Fallback invite link: <code>{fallbackInviteUrl}</code></p> : null}

                <h3>Pending Invites</h3>
                {data.pendingHouseholdInvites.length === 0 ? <p className={styles.meta}>No pending invites.</p> : (
                  <ul className={styles.rows}>
                    {data.pendingHouseholdInvites.map((invite) => (
                      <li key={invite.id}>
                        <span>{invite.email} — {data.householdRoleOptions[invite.role] ?? invite.role}</span>
                        <button type="button" disabled={busy} onClick={() => void revoke(`/api/settings/invites/${invite.id}`, "Pending invite revoked.", "We could not revoke that invite.")}>
                          <Trash2 size={14} aria-hidden="true" />Revoke
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <h3>Household Members</h3>
                {activeMembers.length === 0 ? <p className={styles.meta}>No shared members yet.</p> : (
                  <ul className={styles.rows}>
                    {activeMembers.map((member) => (
                      <li key={member.id}>
                        <span>{member.displayName || member.email} ({member.email})</span>
                        <span className={styles.rowActions}>
                          <select aria-label={`Role for ${member.email}`} value={member.role ?? "editor"} disabled={busy} onChange={(event) => void changeMemberRole(member.id, event.target.value)}>
                            {Object.entries(data.householdRoleOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                          </select>
                          <button type="button" disabled={busy} onClick={() => void revoke(`/api/settings/members/${member.id}`, "Shared household access revoked.", "We could not revoke that member.")}>
                            <UserMinus size={14} aria-hidden="true" />Revoke
                          </button>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ) : null}

            {isPrimary ? (
              <section className={`${styles.panel} ${styles.danger}`} aria-labelledby="settings-delete">
                <header><Trash2 size={18} aria-hidden="true" /><h2 id="settings-delete">Delete Account</h2></header>
                {data.accountDeleteBillingBlocked ? (
                  <p className={styles.meta}>Cancel your active Stripe subscription first, then return here to delete the ClearPath account data.</p>
                ) : (
                  <form onSubmit={(event) => void submitDelete(event)}>
                    <p className={styles.meta}>This permanently deletes the household&apos;s app data. Type <strong>{data.accountDeleteConfirmation}</strong> to confirm.</p>
                    <div className={styles.formGrid}>
                      <label>Current Password<input name="delete_current_password" type="password" autoComplete="current-password" disabled={busy} required /></label>
                      <label>Confirmation Phrase<input name="delete_confirmation" disabled={busy} required /></label>
                    </div>
                    <button type="submit" disabled={busy}>Delete My Account</button>
                  </form>
                )}
              </section>
            ) : null}
          </div>
        ) : null}
      </div>
  );

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}
