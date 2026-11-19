import { CircleAlert, PackageCheck } from "lucide-react";
import type { ReactNode } from "react";

const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
});
const localTime = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
});

export const formatDate = (value: string) => shortDate.format(new Date(value));
export const formatTime = (value: string | null | undefined) =>
  value ? localTime.format(new Date(value)) : "No usable run";
export const formatNumber = (value: number) => value.toLocaleString("en-US");
export const signalLabels = {
  overdue: "Overdue",
  short_shipment: "Short shipment",
  cleared: "Delivery cleared",
} as const;
export const statusLabels = { open: "Open", acknowledged: "Acknowledged", resolved: "Resolved" } as const;

export function Brand() {
  return <div className="brand">
    <span className="brand-icon"><PackageCheck size={22} aria-hidden="true" /></span>
    <span><strong>Supplier Desk</strong><small>Procurement workspace</small></span>
  </div>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}><span aria-hidden="true" />{children}</span>;
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="error-box" role="alert"><CircleAlert size={17} aria-hidden="true" />{children}</div>;
}

export function Lines({ delivered, ordered }: { delivered: number; ordered: number }) {
  return <div className="units">
    <span><strong>{formatNumber(delivered)}</strong> / {formatNumber(ordered)}</span>
    <progress aria-label="Delivered units" value={Math.min(delivered, ordered)} max={ordered} />
  </div>;
}
