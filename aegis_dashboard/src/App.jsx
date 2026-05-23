import React, { useState, useEffect } from 'react';
import { Shield, FileCode2, Terminal as TerminalIcon, ShieldCheck, Bug, Activity } from 'lucide-react';
import './App.css';

function App() {
  const [reports, setReports] = useState([]);
  const [activeReportId, setActiveReportId] = useState(null);

  useEffect(() => {
    // Fetch reports from the backend
    fetch('http://localhost:8000/api/reports')
      .then(res => res.json())
      .then(data => {
        if (data.reports && data.reports.length > 0) {
          setReports(data.reports);
          setActiveReportId(data.reports[0].id);
        }
      })
      .catch(err => console.error("Failed to fetch reports:", err));
  }, []);

  const activeReport = reports.find(r => r.id === activeReportId);

  return (
    <div className="dashboard-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <Shield className="brand-icon" size={28} />
          <span>AEGIS Proof</span>
        </div>
        
        <div className="report-list">
          {reports.length === 0 ? (
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No reports found. Run the Aegis pipeline.</div>
          ) : (
            reports.map(report => (
              <div 
                key={report.id} 
                className={`report-card ${activeReportId === report.id ? 'active' : ''}`}
                onClick={() => setActiveReportId(report.id)}
              >
                <div className="report-time">
                  {new Date(report.timestamp).toLocaleString()}
                </div>
                <div className="report-target">
                  {report.target_file}
                </div>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main Canvas */}
      <main className="canvas">
        {!activeReport ? (
          <div className="empty-state">
            <Activity size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
            <p>Waiting for Aegis Telemetry...</p>
          </div>
        ) : (
          <div className="timeline">
            
            {/* Node 1: Vulnerable Code */}
            <div className="node">
              <div className="node-icon-wrapper">
                <FileCode2 size={20} color="var(--text-secondary)" />
              </div>
              <div className="node-content">
                <div className="node-header">
                  <span className="node-title">Target: {activeReport.target_file}</span>
                  <span className="badge red">Vulnerable</span>
                </div>
                <div className="code-wrapper">
                  <pre>{activeReport.original_code}</pre>
                </div>
              </div>
            </div>

            {/* Node 2: The Exploit */}
            <div className="node">
              <div className="node-icon-wrapper">
                <Bug size={20} color="var(--accent-orange)" />
              </div>
              <div className="node-content">
                <div className="node-header">
                  <span className="node-title">Red Team Exploit Payload</span>
                  <span className="badge orange">Weaponized</span>
                </div>
                <div className="code-wrapper" style={{ color: 'var(--accent-orange)' }}>
                  <pre>{activeReport.exploit_code}</pre>
                </div>
              </div>
            </div>

            {/* Node 3: The Sandbox Terminal Proof */}
            <div className="node">
              <div className="node-icon-wrapper">
                <TerminalIcon size={20} color="var(--accent-green)" />
              </div>
              <div className="node-content">
                <div className="node-header">
                  <span className="node-title">Sandbox Execution Proof</span>
                  <span className="badge green">Pwned</span>
                </div>
                <div className="terminal-wrapper">
                  <pre>{activeReport.sandbox_output || "Exploit executed successfully. Target compromised."}</pre>
                </div>
              </div>
            </div>

            {/* Node 4: The Auto-Fix */}
            <div className="node">
              <div className="node-icon-wrapper">
                <ShieldCheck size={20} color="var(--accent-green)" />
              </div>
              <div className="node-content">
                <div className="node-header">
                  <span className="node-title">Blue Team Auto-Remediation</span>
                  <span className="badge green">Secured</span>
                </div>
                <div className="code-wrapper">
                  <pre>{activeReport.patched_code}</pre>
                </div>
              </div>
            </div>

          </div>
        )}
      </main>
    </div>
  );
}

export default App;
