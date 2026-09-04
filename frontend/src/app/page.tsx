"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Badge } from '@/components/Badge';
import { RiskIndicator } from '@/components/RiskIndicator';
import { getCases } from '@/api/cases';
import { CaseListItem } from '@/api/types';
import styles from './page.module.css';

export default function QueuePage() {
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterState, setFilterState] = useState('REVIEW');

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await getCases();
        setCases(data);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to load cases');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filteredCases = cases.filter(c => filterState === 'ALL' || c.state === filterState);

  return (
    <div>
      <div className={styles.header}>
        <h2>Failed Refund Queue</h2>
        <select 
          value={filterState} 
          onChange={(e) => setFilterState(e.target.value)}
          className={styles.filter}
        >
          <option value="ALL">All Cases</option>
          <option value="REVIEW">Needs Review</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>
      </div>

      {error ? (
        <div className={styles.errorState}>
          <p>{error}</p>
          <button onClick={() => window.location.reload()} className={styles.retryBtn}>Retry</button>
        </div>
      ) : loading ? (
        <div className={styles.loadingState}>
          {/* Skeleton rows */}
          {[1,2,3].map(i => <div key={i} className={styles.skeletonRow} />)}
        </div>
      ) : filteredCases.length === 0 ? (
        <div className={styles.emptyState}>
          No open cases — every failed refund is either resolved or on track automatically.
        </div>
      ) : (
        <div className={styles.tableContainer}>
          <table>
            <thead>
              <tr>
                <th>Case ID</th>
                <th>Amount</th>
                <th>Failure Type</th>
                <th>Risk</th>
                <th>Evidence Coverage</th>
                <th>Decision</th>
                <th>Status</th>
                <th>Age</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map(c => (
                <tr key={c.case_id} className={styles.row}>
                  <td>
                    <Link href={`/cases/${c.case_id}`} className={styles.caseIdLink}>
                      {c.case_id.substring(0, 8)}...
                    </Link>
                  </td>
                  <td className={styles.amount}>₹{(c.amount / 100).toLocaleString('en-IN')}</td>
                  <td><Badge status={c.failure_type} /></td>
                  <td><RiskIndicator score={c.risk_score} /></td>
                  <td>
                    <div className={styles.coverageDot} style={{ opacity: (c.evidence_coverage || 0) / 100 }} />
                  </td>
                  <td>{c.decision ? <Badge status={c.decision} /> : '—'}</td>
                  <td><Badge status={c.state} /></td>
                  <td className={styles.age}>
                    {Math.round((Date.now() - new Date(c.created_at).getTime()) / 3600000)}h ago
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
