import { ArrowRight, ChevronLeft, ChevronRight, Filter, Search } from "lucide-react";
import { useState } from "react";
import { type CasePage, type CaseSummary, type Overview, useResource } from "./api";
import { Badge, ErrorBox, formatDate, Lines, signalLabels, statusLabels } from "./ui";

const PAGE_SIZE = 20;

export function Queue({ overview, revision, onExpired, onSelect, onRefresh }: {
  overview: Overview | undefined;
  revision: number;
  onExpired: () => void;
  onSelect: (id: number) => void;
  onRefresh: () => void;
}) {
  const [q, setSearch] = useState("");
  const [supplier, setSupplier] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("active");
  const [offset, setOffset] = useState(0);
  const query = new URLSearchParams({ status, limit: String(PAGE_SIZE), offset: String(offset) });
  if (q.trim()) query.set("q", q.trim());
  if (severity) query.set("severity", severity);
  if (supplier) query.set("supplier", supplier);
  const page = useResource<CasePage>(`/exceptions?${query}`, revision, onExpired);
  const total = page.data?.total ?? 0;
  const filtering = Boolean(q || supplier || severity || status !== "active");

  function clearFilters() {
    setSearch("");
    setSupplier("");
    setSeverity("");
    setStatus("active");
    setOffset(0);
  }

  function selectItem(row: CaseSummary) {
    onSelect(row.id);
  }

  return <section className="panel queue" aria-labelledby="queue-heading">
    <div className="panel-heading">
      <div className="panel-title"><h2 id="queue-heading">Exception queue</h2><span className="count-pill">{page.data ? total : "—"}</span></div>
      <small className="muted">Sorted by priority and promise date</small>
    </div>
    <div className="filter-bar">
      <label className="search-input"><Search size={17} aria-hidden="true" />
        <input type="search" aria-label="Search exceptions" placeholder="Search orders, suppliers or SKUs" maxLength={80}
          value={q} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} />
      </label>
      <label className="select-filter"><span className="visually-hidden">Supplier</span>
        <select value={supplier} onChange={(event) => { setSupplier(event.target.value); setOffset(0); }}>
          <option value="">All suppliers</option>
          {overview?.suppliers.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
      <label className="select-filter"><span className="visually-hidden">Priority</span>
        <select value={severity} onChange={(event) => { setSeverity(event.target.value); setOffset(0); }}>
          <option value="">All priorities</option><option value="critical">Critical</option>
          <option value="high">High</option><option value="normal">Normal</option>
        </select>
      </label>
      <label className="select-filter"><span className="visually-hidden">Status</span>
        <select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}>
          <option value="active">Active</option><option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option>
          <option value="all">All statuses</option>
        </select>
      </label>
      {filtering && <button className="text-button" onClick={clearFilters}><Filter size={15} aria-hidden="true" />Reset</button>}
    </div>
    <div aria-busy={page.loading}>
      {page.error ? <div className="panel-message"><ErrorBox>{page.error}
        <button className="text-button" onClick={onRefresh}>Retry</button></ErrorBox></div>
        : !page.data ? <p className="panel-message" role="status">Loading exceptions…</p>
          : total === 0 ? <p className="panel-message">No exceptions match these filters.</p>
            : page.data.items.length === 0 ? <div className="panel-message">
              There are no more results. <button className="text-button" onClick={() => setOffset(0)}>First page</button>
            </div>
            : <div className="table-wrap"><table>
              <thead><tr>
                <th scope="col">Purchase order</th><th scope="col">Supplier</th><th scope="col">Promise date</th>
                <th scope="col">Delivered</th><th scope="col">Priority</th><th scope="col">Status</th>
                <th scope="col">Owner</th><th scope="col" aria-label="Open case" />
              </tr></thead>
              <tbody>
                {page.data.items.map((row) => <tr key={row.id}>
                  <td><button className="order-link" onClick={() => selectItem(row)}
                    aria-label={`Open ${row.order_number} line ${row.line_number}`}>
                    {row.order_number} <small>· {row.line_number}</small>
                  </button><span className="cell-secondary">{signalLabels[row.signal]}</span></td>
                  <td>{row.supplier}<span className="cell-secondary">{row.sku}</span></td>
                  <td className="nowrap">{formatDate(row.promise_date)}</td>
                  <td><Lines delivered={row.delivered_quantity} ordered={row.ordered_quantity} /></td>
                  <td><Badge tone={row.severity}>{row.severity}</Badge></td>
                  <td><Badge tone={row.status}>{statusLabels[row.status]}</Badge></td>
                  <td className={row.assigned_to_name ? "" : "muted"}>{row.assigned_to_name ?? "Unassigned"}</td>
                  <td><button className="icon-button row-arrow" onClick={() => selectItem(row)}
                    aria-label={`View evidence for ${row.order_number} line ${row.line_number}`}>
                    <ArrowRight size={18} aria-hidden="true" />
                  </button></td>
                </tr>)}
              </tbody>
            </table></div>}
    </div>
    {page.data && <footer className="table-footer">
      <span>{page.data.items.length ? `Showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`
        : `${total} ${total === 1 ? "exception" : "exceptions"}`}</span>
      <div className="pagination">
        <button className="icon-button" disabled={offset === 0 || page.loading} aria-label="Previous page"
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={19} aria-hidden="true" /></button>
        <button className="icon-button" disabled={offset + PAGE_SIZE >= total || page.loading} aria-label="Next page"
          onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={19} aria-hidden="true" /></button>
      </div>
    </footer>}
  </section>;
}
