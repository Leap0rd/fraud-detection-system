import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { format } from 'date-fns';

interface LogEntry {
  transaction_id: string;
  user_id?: string;
  timestamp?: string;
  is_anomaly: boolean;
  confirmed_legit?: boolean;
  reconstruction_error?: number;
  threshold?: number;
}

const parseDate = (dateString?: string): Date | null => {
  if (!dateString) return null;
  const normalized =
    dateString.includes('T') || !dateString.includes(' ') ? dateString : dateString.replace(' ', 'T');
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
};

const formatDate = (dateString?: string): string => {
  const d = parseDate(dateString);
  if (!d) return 'N/A';
  try {
    return format(d, 'MMM d, yyyy HH:mm');
  } catch {
    return 'N/A';
  }
};

const getSeverity = (error?: number, threshold?: number): 'Low' | 'Medium' | 'High' => {
  if (typeof error !== 'number' || typeof threshold !== 'number' || threshold <= 0) return 'Low';
  const ratio = error / threshold;
  if (ratio >= 1.5) return 'High';
  if (ratio >= 1.15) return 'Medium';
  return 'Low';
};

export default function Alerts() {
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const refreshInFlightRef = useRef(false);

  const fetchLogs = async () => {
    const res = await axios.get('http://localhost:5000/logs');
    const rows = Array.isArray(res.data) ? (res.data as any[]) : [];
    const processed: LogEntry[] = rows
      .filter((x) => x && x.transaction_id)
      .map((x) => ({
        transaction_id: String(x.transaction_id),
        user_id: typeof x.user_id === 'string' ? x.user_id : undefined,
        timestamp: typeof x.timestamp === 'string' ? x.timestamp : (typeof x.Timestamp === 'string' ? x.Timestamp : undefined),
        is_anomaly: Boolean(x.is_anomaly),
        confirmed_legit: Boolean(x.confirmed_legit),
        reconstruction_error: typeof x.reconstruction_error === 'number' ? x.reconstruction_error : undefined,
        threshold: typeof x.threshold === 'number' ? x.threshold : undefined,
      }))
      .filter((x) => x.is_anomaly)
      .sort((a, b) => (parseDate(b.timestamp)?.getTime() ?? 0) - (parseDate(a.timestamp)?.getTime() ?? 0));
    setLogs(processed);
  };

  const refresh = async (showSpinner: boolean) => {
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    if (showSpinner) setLoading(true);
    try {
      await fetchLogs();
    } catch (e) {
      console.error('Failed to fetch logs', e);
      setLogs([]);
    } finally {
      if (showSpinner) setLoading(false);
      refreshInFlightRef.current = false;
    }
  };

  useEffect(() => {
    let cancelled = false;
    void refresh(true);

    const pollMs = 2000;
    const id = window.setInterval(() => {
      if (cancelled) return;
      void refresh(false);
    }, pollMs);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const counts = useMemo(() => {
    const total = logs.length;
    const reviewed = logs.filter((l) => Boolean(l.confirmed_legit)).length;
    return { total, reviewed, open: total - reviewed };
  }, [logs]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220 }}>
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">Alerts</div>
      <div className="panel-body" style={{ padding: 12 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 10, opacity: 0.95, fontWeight: 700 }}>
          <div>Total Alerts: {counts.total}</div>
          <div>Open: {counts.open}</div>
          <div>Reviewed: {counts.reviewed}</div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Transaction ID</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>User</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Severity</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Date & Time</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Status</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Error / Threshold</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => {
                const sev = getSeverity(l.reconstruction_error, l.threshold);
                const sevStyle: React.CSSProperties =
                  sev === 'High'
                    ? { background: 'rgba(255, 86, 115, 0.16)', borderColor: 'rgba(255, 86, 115, 0.45)' }
                    : sev === 'Medium'
                      ? { background: 'rgba(255, 210, 107, 0.16)', borderColor: 'rgba(255, 210, 107, 0.45)' }
                      : { background: 'rgba(92, 234, 215, 0.12)', borderColor: 'rgba(92, 234, 215, 0.35)' };

                return (
                  <tr key={l.transaction_id}>
                    <td>{l.transaction_id.substring(0, 8)}...</td>
                    <td>{l.user_id || 'N/A'}</td>
                    <td>
                      <span className="badge" style={sevStyle}>
                        {sev}
                      </span>
                    </td>
                    <td>{formatDate(l.timestamp)}</td>
                    <td>
                      <span className={l.confirmed_legit ? 'badge ok' : 'badge bad'}>
                        {l.confirmed_legit ? 'Reviewed Legit' : 'Fraud'}
                      </span>
                    </td>
                    <td>
                      {typeof l.reconstruction_error === 'number' ? l.reconstruction_error.toFixed(6) : '—'}
                      {' / '}
                      {typeof l.threshold === 'number' ? l.threshold.toFixed(6) : '—'}
                    </td>
                  </tr>
                );
              })}

              {logs.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 14, opacity: 0.85 }}>
                    No fraud alerts found yet. Trigger a fraud (is_anomaly=true) by sending a suspicious transaction to /predict.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
