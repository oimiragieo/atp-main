import { useEffect, useState } from 'react';

const AGG_URL = process.env.NEXT_PUBLIC_AGGREGATOR_URL || 'http://localhost:8081';

export default function AdminDashboard() {
  const [summary, setSummary] = useState(null);
  const [clusterStats, setClusterStats] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchAll() {
      try {
        const [s, cs, ms] = await Promise.all([
          fetch(`${AGG_URL}/summary`).then(r => r.json()),
          fetch(`${AGG_URL}/cluster_stats`).then(r => r.json()),
          fetch(`${AGG_URL}/model_status`).then(r => r.json()),
        ]);
        setSummary(s);
        setClusterStats(cs);
        setModelStatus(ms);
      } catch (e) {
        setError(String(e));
      }
    }
    fetchAll();
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: 'system-ui, sans-serif' }}>
      <h1>ATP Monitoring (Aggregator)</h1>
      <p style={{ color: '#666' }}>Source: {AGG_URL}</p>
      {error && <div style={{ color: 'crimson' }}>Error: {error}</div>}

      <section style={{ marginTop: 24 }}>
        <h2>Routers Summary</h2>
        {!summary && <div>Loading summary…</div>}
        {summary && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {Object.entries(summary.routers || {}).map(([router, data]) => (
              <div key={router} style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12 }}>
                <h3 style={{ marginTop: 0 }}>{router}</h3>
                <div>Version: {data?.version?.service_version || 'n/a'}</div>
                <div>
                  State: {data?.state_health?.status || 'unknown'} ({data?.state_health?.backend || 'n/a'})
                </div>
                {(data?.errors || []).length > 0 && (
                  <div style={{ color: '#c77' }}>Errors: {data.errors.join('; ')}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section style={{ marginTop: 24 }}>
        <h2>Cluster Stats</h2>
        {!clusterStats && <div>Loading cluster stats…</div>}
        {clusterStats && (
          <div>
            {Object.keys(clusterStats.errors || {}).length > 0 && (
              <div style={{ color: '#c77' }}>Errors: {JSON.stringify(clusterStats.errors)}</div>
            )}
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={th}>Router</th>
                  <th style={th}>Cluster</th>
                  <th style={th}>Model</th>
                  <th style={th}>Calls</th>
                </tr>
              </thead>
              <tbody>
                {(clusterStats.stats || []).map((row, i) => (
                  <tr key={i}>
                    <td style={td}>{row.router}</td>
                    <td style={td}>{row.cluster}</td>
                    <td style={td}>{row.model}</td>
                    <td style={td}>{row.calls}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section style={{ marginTop: 24 }}>
        <h2>Model Status</h2>
        {!modelStatus && <div>Loading model status…</div>}
        {modelStatus && (
          <div>
            <div style={{ marginBottom: 8 }}>
              Promotions: {modelStatus.promotions} | Demotions: {modelStatus.demotions}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={th}>Router</th>
                  <th style={th}>Model</th>
                  <th style={th}>Status</th>
                  <th style={th}>Capabilities</th>
                  <th style={th}>Safety</th>
                </tr>
              </thead>
              <tbody>
                {(modelStatus.models || []).map((row, i) => (
                  <tr key={i}>
                    <td style={td}>{row.router}</td>
                    <td style={td}>{row.model}</td>
                    <td style={td}>{row.status}</td>
                    <td style={td}>{(row.capabilities || []).join(', ')}</td>
                    <td style={td}>{row.safety_grade || 'n/a'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

const th = { textAlign: 'left', borderBottom: '1px solid #eee', padding: '8px 6px' };
const td = { borderBottom: '1px solid #f3f3f3', padding: '8px 6px' };
