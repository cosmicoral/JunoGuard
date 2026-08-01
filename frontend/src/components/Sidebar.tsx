import { BrandLockup } from "./BrandMark";

export type DashboardSection = "overview" | "feed" | "incidents" | "controls";

const NAV_ITEMS: { id: DashboardSection; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "feed", label: "Live Feed" },
  { id: "incidents", label: "Incidents" },
  { id: "controls", label: "Controls" },
];

export function Sidebar({
  activeSection,
  suspended,
  userName,
  userEmail,
  avatarUrl,
  signingOut,
  authError,
  killError,
  canControl,
  role,
  onNavigate,
  onSignOut,
  onToggleSuspend,
}: {
  activeSection: DashboardSection;
  suspended: boolean;
  userName: string;
  userEmail: string;
  avatarUrl: string | null;
  signingOut: boolean;
  authError: string | null;
  killError: string | null;
  canControl: boolean;
  role: string | null;
  onNavigate: (section: DashboardSection) => void;
  onSignOut: () => void;
  onToggleSuspend: () => void;
}) {
  const initial = (userName || userEmail).trim().charAt(0).toUpperCase() || "?";
  const controlTitle = canControl
    ? undefined
    : suspended
      ? `Resetting a project is owner-only${role ? ` - this account is ${role}` : ""}.`
      : `Suspending a project needs the operator role${role ? ` - this account is ${role}` : ""}.`;

  return (
    <aside className="sidebar" data-suspended={suspended}>
      <div className="sidebar-brand">
        <BrandLockup className="sidebar-lockup" size={30} suspended={suspended} />
      </div>

      <nav className="sidebar-nav" aria-label="Dashboard sections">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="sidebar-nav-item"
            data-active={activeSection === item.id}
            onClick={() => onNavigate(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        {(killError || authError) && (
          <p className="sidebar-error" role="alert">
            {killError ?? authError}
          </p>
        )}

        <button
          type="button"
          className="kill sidebar-kill"
          data-suspended={suspended}
          onClick={onToggleSuspend}
          aria-pressed={suspended}
          disabled={!canControl}
          title={controlTitle}
        >
          {suspended ? "RESET" : "SUSPEND"}
        </button>

        <div className="sidebar-account" title={`${userName} · ${userEmail}`}>
          {avatarUrl ? (
            <img className="account-avatar" src={avatarUrl} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="account-avatar account-initial" aria-hidden="true">
              {initial}
            </span>
          )}
          <span className="account-copy">
            <strong>{userName}</strong>
            <small>{userEmail}</small>
          </span>
        </div>

        <button className="sign-out" type="button" onClick={onSignOut} disabled={signingOut}>
          {signingOut ? "SIGNING OUT..." : "SIGN OUT"}
        </button>
      </div>
    </aside>
  );
}
