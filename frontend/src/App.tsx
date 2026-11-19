import {
  Boxes, CalendarDays, ChevronRight, CircleCheck, CircleHelp, ClipboardList,
  Database, LogOut, RefreshCw, TriangleAlert, Upload,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
  ApiError, api, isRun, messageFor, type Overview, type Run, type Session,
  useResource, writeHeaders,
} from "./api";
import { CaseDialog } from "./CaseDialog";
import { Intake } from "./Intake";
import { Queue } from "./Queue";
import { Brand, ErrorBox, formatDate, formatNumber } from "./ui";

type Screen = "queue" | "intake";
type Notice = { text: string; error?: boolean };
type IntakeAction = "carrier" | "orders";

const currentScreen = (): Screen => window.location.hash === "#intake" ? "intake" : "queue";

function SignIn({ onLogin }: { onLogin: (value: Session) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      onLogin(await api<Session>("/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      }));
    } catch (failure) {
      setError(messageFor(failure));
    } finally {
      setPending(false);
    }
  }

  return <main className="signin">
    <form className="signin-panel" onSubmit={submit}>
      <Brand />
      <h1>Sign in</h1>
      <p className="muted">Access the shipment exception workspace.</p>
      {error && <ErrorBox>{error}</ErrorBox>}
      <label>Email<input type="email" autoComplete="username" value={email} required
        onChange={(event) => setEmail(event.target.value)} /></label>
      <label>Password<input type="password" autoComplete="current-password" value={password} required
        onChange={(event) => setPassword(event.target.value)} /></label>
      <button type="submit" className="button primary" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  </main>;
}

function Metrics({ overview }: { overview: Overview | undefined }) {
  const stats = [
    { label: "Active exceptions", count: overview?.active_cases, icon: ClipboardList, tone: "blue" },
    { label: "Critical", count: overview?.critical_cases, icon: TriangleAlert, tone: "red" },
    { label: "Suppliers affected", count: overview?.affected_suppliers, icon: Boxes, tone: "purple" },
    { label: "Resolved", count: overview?.resolved_cases, icon: CircleCheck, tone: "green" },
  ];
  return <div className="metrics" aria-label="Exception summary">
    {stats.map(({ label, count, icon: Icon, tone }) => <section className="stat-card" key={label}>
      <span className={`stat-icon stat-${tone}`}><Icon size={20} aria-hidden="true" /></span>
      <div><span className="stat-label">{label}</span>
        <strong>{count === undefined ? "—" : formatNumber(count)}</strong>
      </div>
    </section>)}
  </div>;
}

function Workspace({ session, onExpired }: { session: Session; onExpired: () => void }) {
  const [screen, setScreen] = useState<Screen>(currentScreen);
  const [revision, setRevision] = useState(0);
  const [selectedCase, setSelectedCase] = useState<number>();
  const [notice, setNotice] = useState<Notice>();
  const [pending, setPending] = useState<IntakeAction>();
  const overview = useResource<Overview>("/overview", revision, onExpired);
  const canWrite = session.user.role === "operator";
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    const listener = () => setScreen(currentScreen());
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);

  async function submitIntake(source: IntakeAction, file?: File): Promise<Run | undefined> {
    setNotice(undefined);
    setPending(source);
    try {
      const result = await api<Run>(source === "orders" ? "/imports/orders" : "/sync/carrier", {
        method: "POST",
        headers: writeHeaders(session, file ? "text/csv" : undefined),
        body: file,
      });
      setNotice({
        text: result.rejected
          ? `Run #${result.id} recorded ${result.rejected} rejected ${result.rejected === 1 ? "row" : "rows"}. Review Data intake for details.`
          : `Run #${result.id} completed. ${result.added} added, ${result.updated} updated, ${result.duplicates} unchanged.`,
        error: result.status === "failed",
      });
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onExpired();
      else if (error instanceof ApiError && isRun(error.payload)) {
        setNotice({ text: `Run #${error.payload.id}. ${error.payload.issues[0]?.reason ?? error.message}`, error: true });
        return error.payload;
      } else setNotice({ text: messageFor(error), error: true });
    } finally {
      setPending(undefined);
      refresh();
    }
  }

  async function logout() {
    try {
      await api<void>("/session", { method: "DELETE", headers: writeHeaders(session) });
      onExpired();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onExpired();
      else setNotice({ text: messageFor(error), error: true });
    }
  }

  const initials = session.user.name.split(" ").map((part) => part[0]).slice(0, 2).join("");
  return <div className="shell">
    <aside className="sidebar">
      <Brand />
      <nav aria-label="Workspace">
        <a className={screen === "queue" ? "selected" : ""} href="#queue"
          aria-current={screen === "queue" ? "page" : undefined}>
          <ClipboardList size={19} aria-hidden="true" />Exception queue
        </a>
        <a className={screen === "intake" ? "selected" : ""} href="#intake"
          aria-current={screen === "intake" ? "page" : undefined}>
          <Database size={19} aria-hidden="true" />Data intake
        </a>
      </nav>
      <div className="sidebar-bottom">
        <a href="/api/docs" target="_blank" rel="noreferrer" className="api-docs">
          <CircleHelp size={18} aria-hidden="true" />API documentation
        </a>
        <div className="account">
          <span className="avatar" aria-hidden="true">{initials}</span>
          <div><strong>{session.user.name}</strong><small>{canWrite ? "Operator" : "Read-only viewer"}</small></div>
          <button type="button" className="icon-button" aria-label="Sign out" onClick={() => void logout()}>
            <LogOut size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <span className="breadcrumbs">Operations <ChevronRight size={15} aria-hidden="true" />
          <strong>{screen === "queue" ? "Exception queue" : "Data intake"}</strong>
        </span>
        {overview.data && <span className="date-chip"><CalendarDays size={16} aria-hidden="true" />
          {formatDate(overview.data.as_of_date)}</span>}
      </header>
      <main className="content">
        <div className="page-heading">
          <div>
            <h1>{screen === "queue" ? "Shipment exceptions" : "Data intake"}</h1>
            <p>{screen === "queue"
              ? "Review late and short deliveries across your suppliers."
              : "Import purchase orders, refresh shipment evidence, and review source runs."}</p>
          </div>
          {screen === "queue" && canWrite && <div className="heading-actions">
            <a href="#intake" className="button secondary"><Upload size={17} aria-hidden="true" />Import CSV</a>
            <button type="button" className="button primary" disabled={Boolean(pending)}
              onClick={() => void submitIntake("carrier")}>
              <RefreshCw size={17} aria-hidden="true" className={pending === "carrier" ? "spin" : ""} />
              {pending === "carrier" ? "Syncing…" : "Sync carrier"}
            </button>
          </div>}
        </div>
        {overview.error && <ErrorBox>{overview.error} <button className="text-button" onClick={refresh}>Retry</button></ErrorBox>}
        {notice && (notice.error ? <ErrorBox>{notice.text}</ErrorBox> : <div className="notice" role="status">
          <CircleCheck size={17} aria-hidden="true" />{notice.text}
        </div>)}
        {screen === "queue" ? <>
          <Metrics overview={overview.data} />
          <Queue overview={overview.data} revision={revision} onExpired={onExpired}
            onSelect={setSelectedCase} onRefresh={refresh} />
        </> : <Intake overview={overview.data} canWrite={canWrite} revision={revision}
          onExpired={onExpired} pending={pending} submit={submitIntake} />}
      </main>
    </div>
    {selectedCase !== undefined && <CaseDialog caseId={selectedCase} session={session}
      revision={revision} onClose={() => setSelectedCase(undefined)} onExpired={onExpired} onChange={refresh} />}
  </div>;
}

export function App() {
  const [session, setSession] = useState<Session | null>();
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const expire = useCallback(() => setSession(null), []);
  useEffect(() => {
    const controller = new AbortController();
    api<Session>("/session", { signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) setSession(value); })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiError && failure.status === 401) setSession(null);
        else setError(messageFor(failure));
      });
    return () => controller.abort();
  }, [retry]);
  if (session === undefined) return <main className="signin"><div className="signin-panel">
    <Brand />
    {error ? <><ErrorBox>{error}</ErrorBox><button className="button secondary"
      onClick={() => { setError(""); setRetry((value) => value + 1); }}>Retry</button></>
      : <p role="status">Opening workspace…</p>}
  </div></main>;
  if (session === null) return <SignIn onLogin={setSession} />;
  return <Workspace key={session.user.id} session={session} onExpired={expire} />;
}
