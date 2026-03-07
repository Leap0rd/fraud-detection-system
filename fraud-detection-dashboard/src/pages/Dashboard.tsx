// src/pages/Dashboard.tsx
import { useState, useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  LineElement,
  PointElement,
  LineController,
  BarController,
} from 'chart.js';
import { Pie, Bar, Chart as ReactChart } from 'react-chartjs-2';
import { format } from 'date-fns';
import axios from 'axios';

// Register ChartJS components
ChartJS.register(
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  LineElement,
  PointElement,
  LineController,
  BarController
);

interface Transaction {
  transaction_id: string;
  user_id: string;
  amount: number;
  is_anomaly: boolean;
  confirmed_legit?: boolean;
  timestamp?: string;
  reconstruction_error?: number;
  threshold?: number;
  top_features?: Array<[string, number]>;
}

// Sample data for development/testing
const getSampleTransactions = (): Transaction[] => [
  {
    transaction_id: 'tx_' + Math.random().toString(36).substr(2, 9),
    user_id: 'user_' + Math.floor(Math.random() * 1000),
    amount: Math.floor(Math.random() * 1000) + 10,
    is_anomaly: Math.random() > 0.8,
    timestamp: new Date().toISOString(),
  },
  {
    transaction_id: 'tx_' + Math.random().toString(36).substr(2, 9),
    user_id: 'user_' + Math.floor(Math.random() * 1000),
    amount: Math.floor(Math.random() * 1000) + 10,
    is_anomaly: Math.random() > 0.8,
    timestamp: new Date(Date.now() - 3600000).toISOString(),
  },
];

const parseDate = (dateString?: string): Date | null => {
  if (!dateString) return null;

  // Browser-safe normalization:
  // - ISO strings already parse fine.
  // - Many browsers treat 'YYYY-MM-DD HH:mm:ss' as invalid.
  //   Convert it to 'YYYY-MM-DDTHH:mm:ss'.
  const normalized =
    dateString.includes('T') || !dateString.includes(' ') ? dateString : dateString.replace(' ', 'T');

  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
};

// Helper function to safely format dates
const formatDate = (dateString?: string): string => {
  const d = parseDate(dateString);
  if (!d) return 'N/A';
  try {
    return format(d, 'MMM d, yyyy HH:mm');
  } catch (error) {
    console.error('Error formatting date:', error);
    return 'N/A';
  }
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const getMonthLabel = (dateString?: string): string | null => {
  const d = parseDate(dateString);
  if (!d) return null;
  return MONTHS[d.getMonth()] ?? null;
};

export default function Dashboard() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const refreshInFlightRef = useRef(false);
  const [stats, setStats] = useState({
    total: 0,
    fraud: 0,
    legit: 0,
    fraudRate: 0,
  });

  const [selectedMonth, setSelectedMonth] = useState<string>('All');
  const [selectedStatus, setSelectedStatus] = useState<'All' | 'Legit' | 'Fraud'>('All');

  // Fetch stats
  const fetchStats = async () => {
    try {
      const response = await axios.get('http://localhost:5000/stats');
      const { total, fraud, legit } = response.data;
      setStats({
        total,
        fraud,
        legit,
        fraudRate: total > 0 ? Math.round((fraud / total) * 100) : 0,
      });
    } catch (error) {
      console.error('Error fetching stats:', error);
      // Set some default stats if API call fails
      const sampleTransactions = getSampleTransactions();
      setStats({
        total: sampleTransactions.length,
        fraud: sampleTransactions.filter(tx => tx.is_anomaly).length,
        legit: sampleTransactions.filter(tx => !tx.is_anomaly).length,
        fraudRate: sampleTransactions.length > 0 
          ? Math.round((sampleTransactions.filter(tx => tx.is_anomaly).length / sampleTransactions.length) * 100) 
          : 0,
      });
    }
  };

  // Fetch recent transactions
  const fetchRecentTransactions = async () => {
    try {
      const response = await axios.get('http://localhost:5000/logs');
      // Process and validate the response data
      const transactions = Array.isArray(response.data) ? response.data : [];
      const processed: Transaction[] = transactions
        .filter((tx: any) => tx && tx.transaction_id) // Ensure transaction has required fields
        .map((tx: any) => ({
          ...tx,
          amount:
            typeof tx.amount === 'number'
              ? tx.amount
              : typeof tx.Transaction_Amount === 'number'
                ? tx.Transaction_Amount
                : 0,
          is_anomaly: Boolean(tx.is_anomaly),
          confirmed_legit: Boolean(tx.confirmed_legit),
          timestamp: typeof tx.timestamp === 'string' ? tx.timestamp : (typeof tx.Timestamp === 'string' ? tx.Timestamp : undefined),
        }))
        .sort((a: any, b: any) => {
          const timeA = parseDate(a.timestamp)?.getTime() ?? 0;
          const timeB = parseDate(b.timestamp)?.getTime() ?? 0;
          return timeB - timeA;
        });

      const fallback = getSampleTransactions();
      const finalList = processed.length > 0 ? processed : fallback;
      setTransactions(finalList);
      setRecentTransactions(finalList.slice(0, 8));
    } catch (error) {
      console.error('Error fetching transactions:', error);
      // Fallback to sample data if API call fails
      const fallback = getSampleTransactions();
      setTransactions(fallback);
      setRecentTransactions(fallback.slice(0, 8));
    }
  };

  const refreshData = async (showSpinner: boolean) => {
    if (refreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    if (showSpinner) setLoading(true);
    try {
      await Promise.all([fetchStats(), fetchRecentTransactions()]);
    } finally {
      if (showSpinner) setLoading(false);
      refreshInFlightRef.current = false;
    }
  };

  const handleRefresh = async () => {
    await refreshData(true);
  };

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      await refreshData(true);
    };
    init();

    const pollMs = 2000;
    const id = window.setInterval(() => {
      if (cancelled) return;
      void refreshData(false);
    }, pollMs);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const filteredTransactions = transactions.filter((tx) => {
    const monthOk =
      selectedMonth === 'All' ? true : getMonthLabel(tx.timestamp) === selectedMonth;
    const statusOk =
      selectedStatus === 'All'
        ? true
        : selectedStatus === 'Fraud'
          ? tx.is_anomaly
          : !tx.is_anomaly;
    return monthOk && statusOk;
  });

  const kpiTotal = filteredTransactions.length;
  const kpiFraud = filteredTransactions.filter((t) => t.is_anomaly).length;
  const kpiLegit = kpiTotal - kpiFraud;
  const kpiRate = kpiTotal > 0 ? Math.round((kpiFraud / kpiTotal) * 100) : 0;
  const kpiUsers = new Set(filteredTransactions.map((t) => t.user_id).filter(Boolean)).size;
  const avgRisk = (() => {
    const vals = filteredTransactions
      .map((t) => (typeof t.reconstruction_error === 'number' ? t.reconstruction_error : null))
      .filter((v): v is number => v !== null);
    if (vals.length === 0) return null;
    const s = vals.reduce((a, b) => a + b, 0);
    return s / vals.length;
  })();

  // Donut
  const pieData = {
    labels: ['Legit', 'Fraud'],
    datasets: [
      {
        data: [kpiLegit, kpiFraud],
        backgroundColor: ['rgba(92, 234, 215, 0.9)', 'rgba(255, 86, 115, 0.9)'],
        borderColor: ['rgba(92, 234, 215, 0.35)', 'rgba(255, 86, 115, 0.35)'],
        borderWidth: 2,
      },
    ],
  };

  // Monthly totals + fraud trend
  const totalsByMonth = Array(12).fill(0);
  const fraudByMonth = Array(12).fill(0);
  for (const tx of transactions) {
    const d = parseDate(tx.timestamp);
    if (!d) continue;
    const m = d.getMonth();
    totalsByMonth[m] += 1;
    if (tx.is_anomaly) fraudByMonth[m] += 1;
  }

  const comboData = {
    labels: MONTHS,
    datasets: [
      {
        type: 'bar' as const,
        label: 'Total Transactions',
        data: totalsByMonth,
        backgroundColor: 'rgba(120, 158, 255, 0.7)',
        borderColor: 'rgba(120, 158, 255, 0.35)',
        borderWidth: 2,
      },
      {
        type: 'line' as const,
        label: 'Fraud Count',
        data: fraudByMonth,
        borderColor: 'rgba(92, 234, 215, 0.95)',
        backgroundColor: 'rgba(92, 234, 215, 0.10)',
        pointRadius: 3,
        tension: 0.35,
      },
    ],
  };

  // Status breakdown
  const confirmedLegit = filteredTransactions.filter((t) => Boolean(t.confirmed_legit)).length;
  const potentialFraud = filteredTransactions.filter((t) => t.is_anomaly && !t.confirmed_legit).length;

  const breakdownData = {
    labels: ['Legit', 'Potential Fraud', 'Confirmed Legit'],
    datasets: [
      {
        label: 'Count',
        data: [kpiLegit, potentialFraud, confirmedLegit],
        backgroundColor: [
          'rgba(92, 234, 215, 0.85)',
          'rgba(255, 86, 115, 0.85)',
          'rgba(255, 210, 107, 0.85)',
        ],
        borderColor: [
          'rgba(92, 234, 215, 0.35)',
          'rgba(255, 86, 115, 0.35)',
          'rgba(255, 210, 107, 0.35)',
        ],
        borderWidth: 2,
      },
    ],
  };

  // Hourly activity
  const totalsByHour = Array(24).fill(0);
  const fraudByHour = Array(24).fill(0);
  for (const tx of filteredTransactions) {
    const d = parseDate(tx.timestamp);
    if (!d) continue;
    const h = d.getHours();
    totalsByHour[h] += 1;
    if (tx.is_anomaly) fraudByHour[h] += 1;
  }

  const hourlyData = {
    labels: Array.from({ length: 24 }, (_, i) => `${i}`),
    datasets: [
      {
        label: 'Total',
        data: totalsByHour,
        backgroundColor: 'rgba(120, 158, 255, 0.7)',
        borderColor: 'rgba(120, 158, 255, 0.35)',
        borderWidth: 2,
      },
      {
        label: 'Fraud',
        data: fraudByHour,
        backgroundColor: 'rgba(255, 86, 115, 0.7)',
        borderColor: 'rgba(255, 86, 115, 0.35)',
        borderWidth: 2,
      },
    ],
  };

  const darkAxis: any = {
    ticks: { color: 'rgba(232, 236, 244, 0.85)' },
    grid: { color: 'rgba(255, 255, 255, 0.08)' },
  };

  const darkPlugins: any = {
    legend: { labels: { color: 'rgba(232, 236, 244, 0.9)', font: { weight: 700 } } },
    title: { display: false },
    tooltip: { enabled: true },
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220 }}>
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="dashboard">
      <div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
          <div className="kpi-row" style={{ flex: 1 }}>
            <div className="kpi">
              <div className="kpi-label">Total Transactions</div>
              <div className="kpi-value">{kpiTotal || stats.total}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Legit</div>
              <div className="kpi-value">{kpiLegit || stats.legit}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Fraud</div>
              <div className="kpi-value">{kpiFraud || stats.fraud}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Fraud Rate</div>
              <div className="kpi-value">{kpiRate}%</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Active Users</div>
              <div className="kpi-value">{kpiUsers}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Avg Risk Score</div>
              <div className="kpi-value">{avgRisk === null ? '—' : avgRisk.toFixed(4)}</div>
            </div>
          </div>

          <button type="button" className="btn primary" onClick={handleRefresh}>
            Refresh Data
          </button>
        </div>

        <div className="grid-panels">
          <div className="panel">
            <div className="panel-header">SUM of Transactions</div>
            <div className="panel-body">
              <div className="panel-chart">
                <Pie
                  data={pieData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '62%',
                    plugins: darkPlugins,
                  }}
                />
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">Total Transactions and Fraud Trend</div>
            <div className="panel-body">
              <div className="panel-chart">
                <ReactChart
                  type="bar"
                  data={comboData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: darkPlugins,
                    scales: {
                      x: darkAxis,
                      y: { ...darkAxis, beginAtZero: true },
                    },
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="grid-panels-bottom">
          <div className="panel">
            <div className="panel-header">SUM of Decisions</div>
            <div className="panel-body">
              <div className="panel-chart">
                <Bar
                  data={breakdownData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: darkPlugins,
                    scales: {
                      x: darkAxis,
                      y: { ...darkAxis, beginAtZero: true },
                    },
                  }}
                />
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">SUM of Hourly Activity</div>
            <div className="panel-body">
              <div className="panel-chart">
                <Bar
                  data={hourlyData}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: darkPlugins,
                    scales: {
                      x: darkAxis,
                      y: { ...darkAxis, beginAtZero: true },
                    },
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="panel" style={{ marginTop: 12 }}>
          <div className="panel-header">Latest Transactions</div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', opacity: 0.9 }}>Transaction ID</th>
                  <th style={{ textAlign: 'left', opacity: 0.9 }}>User</th>
                  <th style={{ textAlign: 'left', opacity: 0.9 }}>Status</th>
                  <th style={{ textAlign: 'left', opacity: 0.9 }}>Date & Time</th>
                </tr>
              </thead>
              <tbody>
                {recentTransactions.map((txn) => (
                  <tr key={txn.transaction_id}>
                    <td>{txn.transaction_id.substring(0, 8)}...</td>
                    <td>{txn.user_id || 'N/A'}</td>
                    <td>
                      <span className={txn.is_anomaly ? 'badge bad' : 'badge ok'}>
                        {txn.is_anomaly ? 'Fraud' : 'Legit'}
                      </span>
                    </td>
                    <td>{formatDate(txn.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <aside className="filters">
        <div className="panel">
          <div className="panel-header">Month</div>
          <div className="panel-body">
            <div className="filter-list">
              {['All', ...MONTHS].map((m) => (
                <button
                  key={m}
                  type="button"
                  className={m === selectedMonth ? 'filter-item active' : 'filter-item'}
                  onClick={() => setSelectedMonth(m)}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">Risk Type</div>
          <div className="panel-body">
            <div className="filter-list">
              {(['All', 'Legit', 'Fraud'] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={s === selectedStatus ? 'filter-item active' : 'filter-item'}
                  onClick={() => setSelectedStatus(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">Quick Stats</div>
          <div className="panel-body" style={{ fontSize: 13, lineHeight: 1.6, opacity: 0.95 }}>
            <div>Showing: <b>{filteredTransactions.length}</b> txns</div>
            <div>Filter month: <b>{selectedMonth}</b></div>
            <div>Risk type: <b>{selectedStatus}</b></div>
          </div>
        </div>
      </aside>
    </div>
  );
}