import { Check, ClipboardList, Package, X } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError, api, type CaseChange, type CaseDetail, messageFor, type Session,
  type User, useResource, writeHeaders,
} from "./api";
import { Badge, ErrorBox, formatDate, formatTime, Lines, signalLabels, statusLabels } from "./ui";

const shipmentLabels = { label_created: "Label created", in_transit: "In transit", delivered: "Delivered" };
const eventLabels: Record<string, string> = {
  detected: "Exception detected", evidence_updated: "Evidence updated", reopened: "Reopened",
  assign: "Assignment changed", acknowledge: "Acknowledged", resolve: "Resolved",
};

export function CaseDialog({ caseId, session, revision, onClose, onExpired, onChange }: {
  caseId: number;
  session: Session;
  revision: number;
  onClose: () => void;
  onExpired: () => void;
  onChange: () => void;
}) {
  const element = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [reason, setReason] = useState("");
  const { data: item, setData: setItem, error: readError, loading } = useResource<CaseDetail>(
    `/exceptions/${caseId}`, revision, onExpired,
  );
  const operators = useResource<User[]>("/operators", 0, onExpired);

  useEffect(() => {
    const dialog = element.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  async function update(change: Omit<CaseChange, "version">) {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<CaseDetail>(`/exceptions/${caseId}`, {
        method: "PATCH",
        headers: writeHeaders(session, "application/json"),
        body: JSON.stringify({ ...change, version: item.version }),
      });
      setItem(updated);
      if (change.action === "resolve") {
        setReason("");
        setResolving(false);
      }
      onChange();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) onExpired();
      else {
        setError(messageFor(failure));
        if (failure instanceof ApiError && failure.status === 409) onChange();
      }
    } finally {
      setBusy(false);
    }
  }

  function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reason.trim().length < 3) {
      setError("Enter at least three characters for the resolution.");
      return;
    }
    void update({ action: "resolve", reason: reason.trim() });
  }

  const editable = item?.status !== "resolved" && session.user.role === "operator";
  return <dialog ref={element} className="drawer" aria-labelledby="case-heading"
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <div className="drawer-header">
      <div><small className="muted">Exception details</small>
        <h2 id="case-heading">{item ? `${item.order_number} · Line ${item.line_number}` : "Purchase order"}</h2>
      </div>
      <button autoFocus className="icon-button" type="button" aria-label="Close details" onClick={onClose}>
        <X size={21} aria-hidden="true" />
      </button>
    </div>
    <div className="drawer-body" aria-busy={loading}>
      {readError && <ErrorBox>{readError} <button className="text-button" onClick={onChange}>Retry</button></ErrorBox>}
      {!item && loading && <p role="status" className="muted">Loading shipment evidence…</p>}
      {item && <>
        <div className="drawer-intro">
          <h3>{item.description}</h3>
          <p>{item.supplier} · {item.sku}</p>
          <div className="badge-line">
            <Badge tone={item.severity}>{item.severity}</Badge>
            <Badge tone={item.status}>{statusLabels[item.status]}</Badge>
            <Badge>{signalLabels[item.signal]}</Badge>
          </div>
        </div>
        <dl className="detail-grid">
          <div><dt>Promised</dt><dd>{formatDate(item.promise_date)}</dd></div>
          <div><dt>Delivered</dt><dd><Lines delivered={item.delivered_quantity} ordered={item.ordered_quantity} /></dd></div>
        </dl>
        <section className="drawer-section" aria-labelledby="workflow-heading">
          <h3 id="workflow-heading">Workflow</h3>
          {error && <ErrorBox>{error}</ErrorBox>}
          {editable ? <>
            {operators.error && <ErrorBox>{operators.error}</ErrorBox>}
            <label className="field">Owner
              <select value={item.assigned_to_id ?? ""} disabled={busy || operators.loading}
                onChange={(event) => void update({ action: "assign", assigned_to_id: Number(event.target.value) })}>
                <option value="" disabled>Unassigned</option>
                {operators.data?.map((operator) => <option value={operator.id} key={operator.id}>{operator.name}</option>)}
              </select>
            </label>
            <div className="workflow-actions">
              {item.status === "open" && <button type="button" className="button secondary" disabled={busy}
                onClick={() => void update({ action: "acknowledge" })}>Acknowledge</button>}
              {!resolving && <button type="button" className="button primary" disabled={busy}
                onClick={() => setResolving(true)}><Check size={17} aria-hidden="true" />Resolve</button>}
            </div>
            {resolving && <form className="resolve-form" onSubmit={resolve}>
              <label className="field">Resolution reason
                <textarea required minLength={3} maxLength={500} rows={3} value={reason}
                  onChange={(event) => setReason(event.target.value)} />
              </label>
              <div className="workflow-actions">
                <button type="button" className="button secondary" disabled={busy}
                  onClick={() => { setResolving(false); setError(""); }}>Cancel</button>
                <button type="submit" className="button primary" disabled={busy}>Confirm resolution</button>
              </div>
            </form>}
          </> : <p className="muted">Owner · {item.assigned_to_name ?? "Unassigned"}</p>}
        </section>
        <section className="drawer-section" aria-labelledby="shipments-heading">
          <h3 id="shipments-heading"><Package size={18} aria-hidden="true" />Shipment evidence</h3>
          {item.shipments.length === 0 ? <p className="muted">No carrier records for this order line.</p>
            : <ul className="evidence-list">
              {item.shipments.map((shipment) => <li key={shipment.shipment_id}>
                <div><strong>{shipment.shipment_id}</strong><small>{shipment.carrier} · {formatTime(shipment.updated_at)}</small></div>
                <div><strong>{shipment.quantity} units</strong><small>{shipmentLabels[shipment.status]}</small></div>
              </li>)}
            </ul>}
        </section>
        <section className="drawer-section" aria-labelledby="activity-heading">
          <h3 id="activity-heading"><ClipboardList size={18} aria-hidden="true" />Activity</h3>
          <ol className="timeline">
            {item.events.map((event) => <li key={event.id}>
              <strong>{eventLabels[event.action] ?? event.action}</strong>
              <small>{event.actor_name ?? "Reconciliation"} · {formatTime(event.created_at)}</small>
              <p>{event.note}</p>
            </li>)}
          </ol>
        </section>
      </>}
    </div>
  </dialog>;
}
