import { motion } from "motion/react";
import { BrandMark } from "./BrandMark";

export function Header({
  projectName,
  suspended,
  killError,
  userName,
  userEmail,
  avatarUrl,
  signingOut,
  authError,
  canControl,
  role,
  onSignOut,
  onToggleSuspend,
}: {
  projectName: string;
  suspended: boolean;
  killError: string | null;
  userName: string;
  userEmail: string;
  avatarUrl: string | null;
  signingOut: boolean;
  authError: string | null;
  canControl: boolean;
  role: string | null;
  onSignOut: () => void;
  onToggleSuspend: () => void;
}) {
  const initial = (userName || userEmail).trim().charAt(0).toUpperCase() || "?";

  return (
    <header className="panel header" data-suspended={suspended}>
      <div className="brand">
        <BrandMark className="mark" size={20} suspended={suspended} />
        <span className="wordmark">JUNOGUARD</span>
      </div>

      <div className="brand-rule" />
      <span className="project">{projectName}</span>

      <div className="status" data-suspended={suspended}>
        <motion.span
          className="dot"
          animate={{ scale: 1 }}
          initial={false}
          transition={{ type: "spring", bounce: 0, duration: 0.3 }}
        />
        {suspended ? "SUSPENDED" : "ACTIVE"}
      </div>

      <div className="spacer" />

      {killError || authError ? (
        <span className="kill-error" role="alert" title={killError ?? authError ?? undefined}>
          {killError ?? authError}
        </span>
      ) : null}

      <div className="account" title={`${userName} · ${userEmail}`}>
        {avatarUrl ? (
          <img className="account-avatar" src={avatarUrl} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="account-avatar account-initial" aria-hidden="true">{initial}</span>
        )}
        <span className="account-copy">
          <strong>{userName}</strong>
          <small>{userEmail}</small>
        </span>
      </div>

      <button className="sign-out" type="button" onClick={onSignOut} disabled={signingOut}>
        {signingOut ? "SIGNING OUT…" : "SIGN OUT"}
      </button>

      <button
        type="button"
        className="kill"
        data-suspended={suspended}
        onClick={onToggleSuspend}
        aria-pressed={suspended}
        disabled={!canControl}
        title={
          canControl
            ? undefined
            : suspended
              ? `Resuming a project is owner-only${role ? ` — this account is ${role}` : ""}.`
              : `Suspending a project needs the operator role${role ? ` — this account is ${role}` : ""}.`
        }
      >
        {suspended ? "RESET" : "SUSPEND"}
      </button>
    </header>
  );
}
