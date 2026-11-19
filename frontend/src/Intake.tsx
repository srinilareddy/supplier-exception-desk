import { ArrowRight, Download, FileSpreadsheet, RadioTower, RefreshCw, Upload } from "lucide-react";
import { type FormEvent, useState } from "react";
import { type Overview, type Run, useResource } from "./api";
import { Badge, ErrorBox, formatTime } from "./ui";

const sourceLabels = { orders: "Order CSV", carrier: "Carrier API" };
const statusLabels = { success: "Succeeded", partial: "Partial", failed: "Failed" };

function RunStatus({ run }: { run: Run | null | undefined }) {
  return run ? <Badge tone={run.status}>{statusLabels[run.status]}</Badge> : <Badge>Awaiting data</Badge>;
}

export function Intake({ overview, revision, canWrite, pending, submit, onExpired }: {
  overview: Overview | undefined;
  revision: number;
  canWrite: boolean;
  pending?: "orders" | "carrier";
  submit: (source: "orders" | "carrier", file?: File) => Promise<Run | undefined>;
  onExpired: () => void;
}) {
  const [file, setFile] = useState<File>();
  const [selectedRun, setSelectedRun] = useState<Run>();
  const [fileError, setFileError] = useState("");
  const runs = useResource<Run[]>("/runs", revision, onExpired);
  const current = selectedRun ?? runs.data?.[0];

  async function importOrders(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    if (file.size > 1_048_576) {
      setFileError("Choose a CSV file up to 1 MiB.");
      return;
    }
    setFileError("");
    const result = await submit("orders", file);
    if (result) setSelectedRun(result);
  }

  async function sync() {
    const result = await submit("carrier");
    if (result) setSelectedRun(result);
  }

  return <>
    <div className="source-grid">
      <section className="panel source-card" aria-labelledby="csv-heading">
        <div className="source-head">
          <span className="stat-icon stat-blue"><FileSpreadsheet size={21} aria-hidden="true" /></span>
          <div><h2 id="csv-heading">Order CSV</h2><p>Purchase order lines from your ERP export</p></div>
          <RunStatus run={overview?.latest_orders} />
        </div>
        <dl className="source-data"><dt>Last usable import</dt><dd>{formatTime(overview?.orders_last_available_at)}</dd></dl>
        {canWrite && <form onSubmit={importOrders} className="import-form">
          {fileError && <ErrorBox>{fileError}</ErrorBox>}
          <label className="field">Purchase order CSV
            <input type="file" accept=".csv,text/csv" onChange={(event) => {
              setFile(event.target.files?.[0]);
              setFileError("");
            }} />
          </label>
          <div className="workflow-actions">
            <button type="submit" className="button primary" disabled={!file || Boolean(pending)}>
              <Upload size={17} aria-hidden="true" />{pending === "orders" ? "Importing…" : "Upload order file"}
            </button>
            <a className="button secondary" href="/api/imports/orders/template">
              <Download size={17} aria-hidden="true" />CSV template
            </a>
          </div>
        </form>}
      </section>
      <section className="panel source-card" aria-labelledby="carrier-heading">
        <div className="source-head">
          <span className="stat-icon stat-green"><RadioTower size={21} aria-hidden="true" /></span>
          <div><h2 id="carrier-heading">Carrier API</h2><p>Shipment snapshots from the reference carrier</p></div>
          <RunStatus run={overview?.latest_carrier} />
        </div>
        <dl className="source-data"><dt>Last usable sync</dt><dd>{formatTime(overview?.carrier_last_available_at)}</dd></dl>
        {canWrite && <button className="button primary" disabled={Boolean(pending)} onClick={() => void sync()}>
          <RefreshCw size={17} aria-hidden="true" className={pending === "carrier" ? "spin" : ""} />
          {pending === "carrier" ? "Syncing…" : "Sync carrier"}
        </button>}
      </section>
    </div>
    <section className="panel" aria-labelledby="runs-heading">
      <div className="panel-heading"><h2 id="runs-heading">Recent runs</h2><small className="muted">Latest 20 runs</small></div>
      {runs.error ? <div className="panel-message"><ErrorBox>{runs.error}</ErrorBox></div>
        : runs.loading && !runs.data ? <p className="panel-message" role="status">Loading runs…</p>
          : runs.data?.length ? <div className="table-wrap"><table>
            <thead><tr>
              <th scope="col">Run</th><th scope="col">Source</th><th scope="col">Result</th>
              <th scope="col">Added</th><th scope="col">Updated</th><th scope="col">Unchanged</th>
              <th scope="col">Rejected</th><th scope="col">Started</th>
            </tr></thead><tbody>
              {runs.data.map((run) => <tr key={run.id} className={current?.id === run.id ? "selected-row" : ""}>
                <td><button className="order-link" onClick={() => setSelectedRun(run)}
                  aria-label={`Review run ${run.id}`}>#{run.id} <ArrowRight size={14} aria-hidden="true" /></button></td>
                <td>{sourceLabels[run.source]}</td><td><RunStatus run={run} /></td>
                <td>{run.added}</td><td>{run.updated}</td><td>{run.duplicates}</td><td>{run.rejected}</td>
                <td className="nowrap">{formatTime(run.created_at)}</td>
              </tr>)}
            </tbody>
          </table></div> : <p className="panel-message">No runs recorded.</p>}
      {current && <div className="run-details">
        <h3>Run #{current.id} · {sourceLabels[current.source]}</h3>
        {current.issues.length > 0 ? <ul>
          {current.issues.map((issue, index) => <li key={index}>
            {issue.row ? <strong>Row {issue.row} · </strong> : null}{issue.reason}
          </li>)}
        </ul> : <p className="muted">No validation issues.</p>}
        {current.rejected > current.issues.length && <small className="muted">
          Showing the first {current.issues.length} of {current.rejected} rejected rows.
        </small>}
      </div>}
    </section>
  </>;
}
