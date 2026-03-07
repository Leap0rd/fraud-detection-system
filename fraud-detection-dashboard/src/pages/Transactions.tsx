import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { format } from 'date-fns';

interface LogEntry {
  transaction_id: string;
  user_id?: string;
  amount?: number;
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

export default function Transactions() {
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
        amount: typeof x.amount === 'number' ? x.amount : undefined,
        timestamp: typeof x.timestamp === 'string' ? x.timestamp : (typeof x.Timestamp === 'string' ? x.Timestamp : undefined),
        is_anomaly: Boolean(x.is_anomaly),
        confirmed_legit: Boolean(x.confirmed_legit),
        reconstruction_error: typeof x.reconstruction_error === 'number' ? x.reconstruction_error : undefined,
        threshold: typeof x.threshold === 'number' ? x.threshold : undefined,
      }))
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

  const totals = useMemo(() => {
    const total = logs.length;
    const fraud = logs.filter((l) => l.is_anomaly).length;
    return { total, fraud, legit: total - fraud };
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
      <div className="panel-header">Transactions</div>
      <div className="panel-body" style={{ padding: 12 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 10, opacity: 0.95, fontWeight: 700 }}>
          <div>Total: {totals.total}</div>
          <div>Legit: {totals.legit}</div>
          <div>Fraud: {totals.fraud}</div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Transaction ID</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>User</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Status</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Date & Time</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Error</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Threshold</th>
                <th style={{ textAlign: 'left', opacity: 0.9 }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.transaction_id}>
                  <td>{l.transaction_id.substring(0, 8)}...</td>
                  <td>{l.user_id || 'N/A'}</td>
                  <td>
                    <span className={l.is_anomaly ? 'badge bad' : 'badge ok'}>
                      {l.is_anomaly ? (l.confirmed_legit ? 'Reviewed' : 'Fraud') : 'Legit'}
                    </span>
                  </td>
                  <td>{formatDate(l.timestamp)}</td>
                  <td>{typeof l.reconstruction_error === 'number' ? l.reconstruction_error.toFixed(6) : '—'}</td>
                  <td>{typeof l.threshold === 'number' ? l.threshold.toFixed(6) : '—'}</td>
                  <td>{typeof l.amount === 'number' ? `$${l.amount.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: 14, opacity: 0.85 }}>
                    No transactions found. Make sure Flask is running and you have sent at least one /predict request.
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
