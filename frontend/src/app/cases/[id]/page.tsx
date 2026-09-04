"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Badge } from '@/components/Badge';
import { SyntheticLabel } from '@/components/SyntheticLabel';
import { EvidenceTier } from '@/components/EvidenceTier';
import { RiskIndicator } from '@/components/RiskIndicator';
import { getCaseDetail } from '@/api/cases';
import { CaseDetail } from '@/api/types';
import styles from './page.module.css';

export default function CaseInvestigationPage() {
  const params = useParams();
  const caseId = params.id as string;
  
  const [data, setData] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Review state
  const [reviewAction, setReviewAction] = useState<'APPROVE' | 'REJECT' | 'REQUEST_MORE_INFO' | null>(null);
  const [reviewReason, setReviewReason] = useState('');

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const res = await getCaseDetail(caseId);
        setData(res);
        setError(null);
      } catch (err: any) {
        setError(err.message || 'Failed to load case detail');
      } finally {
        setLoading(false);
      }
    }
    if (caseId) load();
  }, [caseId]);

  if (error) {
    return (
      <div className={styles.errorState}>
        <p>{error}</p>
        <button onClick={() => window.location.reload()} className={styles.retryBtn}>Retry</button>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className={styles.loadingState}>
        <div className={styles.skeletonBox} style={{ height: '100px' }} />
        <div className={styles.skeletonBox} style={{ height: '300px' }} />
      </div>
    );
  }

  const isReview = data.state === 'REVIEW';
  const showReviewPanel = isReview;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <Link href="/" className={styles.backLink}>&larr; Back to Queue</Link>
        <div className={styles.headerInfo}>
          <h2 className={styles.title}>Case <span className={styles.monospace}>{data.case_id.substring(0,8)}</span></h2>
          <span className={styles.amount}>₹{(data.amount / 100).toLocaleString('en-IN')}</span>
          <Badge status={data.failure_type} />
          <Badge status={data.state} />
          <span className={styles.age}>{Math.round((Date.now() - new Date(data.created_at).getTime())/3600000)}h ago</span>
        </div>
      </div>

      <div className={styles.layout}>
        {/* LEFT COLUMN - 60% */}
        <div className={styles.leftCol}>
          
          <section className={styles.section}>
            <h3>A. Original Refund & Customer</h3>
            <div className={styles.card}>
              <div className={styles.grid2}>
                <div>
                  <label>Refund ID</label>
                  <p className={styles.monospace}>{data.refund.refund_id}</p>
                </div>
                <div>
                  <label>Payment ID</label>
                  <p className={styles.monospace}>{data.refund.payment_id}</p>
                </div>
                <div style={{ gridColumn: 'span 2' }}>
                  <label>Failure Reason</label>
                  <p>{data.refund.failure_reason}</p>
                </div>
                <div>
                  <label>Customer Name</label>
                  <p>{data.customer.name}</p>
                </div>
                <div>
                  <label>Customer Since</label>
                  <p>{new Date(data.customer.created_at).toLocaleDateString()}</p>
                </div>
              </div>
            </div>
          </section>

          <section className={styles.section}>
            <h3>B. Proposed Alternate Destination</h3>
            <div className={styles.card}>
              {data.proposed_destination ? (
                <>
                  <div className={styles.grid2}>
                    <div>
                      <label>Type</label>
                      <p><Badge status={data.proposed_destination.type} className={styles.typeBadge} /></p>
                    </div>
                    <div>
                      <label>Identifier</label>
                      <p className={styles.monospace}>{data.proposed_destination.identifier}</p>
                    </div>
                    <div>
                      <label>Holder Name</label>
                      <p>{data.proposed_destination.holder_name}</p>
                    </div>
                    <div>
                      <label>Prior Successful Uses</label>
                      <p>{data.proposed_destination.times_used}</p>
                    </div>
                  </div>
                  <div className={styles.ownershipCard}>
                    <strong>Ownership Signal: </strong>
                    <span className={data.risk_signals.ownership_signal.includes('MISMATCH') ? styles.textRed : ''}>
                      {data.risk_signals.ownership_signal.replace('_SYNTHETIC', '')}
                    </span>
                    <SyntheticLabel />
                  </div>
                </>
              ) : (
                <p className={styles.muted}>No alternate destination proposed yet.</p>
              )}
            </div>
          </section>

          <section className={styles.section}>
            <h3>C. Extracted Claims & Contradiction Results</h3>
            {data.extracted_claims.length === 0 ? (
              <div className={styles.emptyState}>Still investigating...</div>
            ) : (
              <table className={styles.claimsTable}>
                <thead>
                  <tr>
                    <th>Claim</th>
                    <th>Status</th>
                    <th>Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {data.extracted_claims.map((claim, idx) => (
                    <tr key={idx} className={claim.status === 'CONTRADICTED' ? styles.rowContradicted : ''}>
                      <td>
                        <div className={styles.claimText}>"{claim.claim_text}"</div>
                        <div className={styles.claimType}>{claim.claim_type}</div>
                      </td>
                      <td>
                        <span className={`${styles.statusLabel} ${styles[claim.status.toLowerCase()]}`}>
                          {claim.status}
                        </span>
                      </td>
                      <td><Badge status={claim.severity} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className={styles.section}>
            <h3>D. Risk Signals</h3>
            <div className={styles.riskCard}>
              <EvidenceTier severity="HIGH">
                <div className={styles.grid2}>
                  <div>
                    <label>Amount Matches</label>
                    <p>{data.risk_signals.amount_matches_original ? 'Yes' : 'No'}</p>
                  </div>
                  <div>
                    <label>Destination Age (Days)</label>
                    <p>{data.risk_signals.destination_age_days ?? 'N/A'}</p>
                  </div>
                  <div>
                    <label>Redirect Count (30d)</label>
                    <p>{data.risk_signals.redirect_count_30d ?? 'N/A'}</p>
                  </div>
                </div>
              </EvidenceTier>
              
              <EvidenceTier severity="MEDIUM">
                <div className={styles.aiFlagsBlock}>
                  <strong>AI-Flagged Language:</strong>
                  <div className={styles.chips}>
                    {data.risk_signals.message_risk_flags?.urgency_language && <span className={styles.chip}>Urgency Language</span>}
                    {data.risk_signals.message_risk_flags?.third_party_destination && <span className={styles.chip}>Third Party Dest</span>}
                    {data.risk_signals.message_risk_flags?.avoid_verified_channel && <span className={styles.chip}>Avoids Verified Channel</span>}
                    {data.risk_signals.message_risk_flags?.instruction_manipulation && <span className={styles.chip}>Instruction Manipulation</span>}
                    {!data.risk_signals.message_risk_flags || !Object.values(data.risk_signals.message_risk_flags).some(Boolean) ? <span className={styles.muted}>None</span> : null}
                  </div>
                </div>
              </EvidenceTier>

              <EvidenceTier severity="LOW">
                <div className={styles.weakSignalRow}>
                  <span>Name Similarity Score: {data.risk_signals.name_similarity_score ?? 'N/A'}</span>
                </div>
              </EvidenceTier>
            </div>
          </section>

          <section className={styles.section}>
            <h3>E. Evidence Coverage</h3>
            <div className={styles.coverageCallout}>
              {data.evidence_coverage && data.evidence_coverage < 50 ? (
                <p><strong>Routed to review:</strong> Insufficient evidence (coverage {data.evidence_coverage}%)</p>
              ) : (
                <p><strong>Routed to review:</strong> Elevated risk score</p>
              )}
            </div>
          </section>

          <section className={styles.section}>
            <h3>G. Audit Timeline</h3>
            <div className={styles.timeline}>
              {data.audit_events.map((evt, i) => (
                <div key={i} className={styles.timelineEvent}>
                  <div className={styles.timelineActor}>{evt.actor_type}</div>
                  <div className={styles.timelineContent}>
                    <strong>{evt.action}</strong> - {evt.reason}
                    <div className={styles.timelineTime}>{new Date(evt.created_at).toLocaleString()}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* RIGHT COLUMN - 40% Sticky */}
        <div className={styles.rightCol}>
          <div className={styles.stickyPanel}>
            <h3>F. Decision Summary</h3>
            <div className={styles.decisionBlock}>
              <div className={styles.decisionBadgeRow}>
                {data.decision ? <Badge status={data.decision} className={styles.largeBadge} /> : <Badge status="PENDING" className={styles.largeBadge} />}
                <RiskIndicator score={data.risk_signals?.name_similarity_score ? data.amount / 1000 : null} /> {/* Placeholder for score passing */}
              </div>
              
              {data.decision_reasons && data.decision_reasons.length > 0 && (
                <ul className={styles.reasonList}>
                  {data.decision_reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
            </div>

            {showReviewPanel && (
              <div className={styles.reviewPanel}>
                <h4>Human Review Action</h4>
                <div className={styles.reviewButtons}>
                  <button 
                    className={`${styles.btn} ${reviewAction === 'APPROVE' ? styles.btnApproveActive : styles.btnApprove}`}
                    onClick={() => setReviewAction('APPROVE')}
                  >Approve</button>
                  <button 
                    className={`${styles.btn} ${reviewAction === 'REJECT' ? styles.btnRejectActive : styles.btnReject}`}
                    onClick={() => setReviewAction('REJECT')}
                  >Reject</button>
                  <button 
                    className={`${styles.btn} ${reviewAction === 'REQUEST_MORE_INFO' ? styles.btnInfoActive : styles.btnInfo}`}
                    onClick={() => setReviewAction('REQUEST_MORE_INFO')}
                  >Req More Info</button>
                </div>
                
                <textarea 
                  className={styles.reasonInput} 
                  placeholder="Required: State your reason..."
                  value={reviewReason}
                  onChange={(e) => setReviewReason(e.target.value)}
                />

                {reviewAction === 'APPROVE' && (
                  <div className={styles.confirmBox}>
                    ⚠️ Double-check: Approving will initiate a payout of ₹{(data.amount / 100).toLocaleString('en-IN')} to {data.proposed_destination?.identifier}.
                  </div>
                )}
                
                <button 
                  className={styles.submitBtn} 
                  disabled={!reviewAction || !reviewReason.trim()}
                  onClick={() => alert('Review submitted! (UI mockup)')}
                >
                  Submit Decision
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
