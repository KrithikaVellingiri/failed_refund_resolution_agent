import React from 'react';
import styles from './Badge.module.css';

interface BadgeProps {
  status: string;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ status, className = '' }) => {
  let colorClass = styles.neutral;

  const s = status.toUpperCase();
  if (['APPROVE', 'APPROVED'].includes(s)) colorClass = styles.green;
  else if (['REVIEW'].includes(s)) colorClass = styles.amber;
  else if (['REJECT', 'REJECTED'].includes(s)) colorClass = styles.red;
  else if (['PAYOUT_SUCCESS', 'RESOLVED'].includes(s)) colorClass = styles.slateGreen;
  else if (['DUPLICATE_GUARD_TRIGGERED'].includes(s)) colorClass = styles.violet;
  else if (['PAYOUT_FAILED', 'CASE_EXPIRED'].includes(s)) colorClass = styles.grayRed;
  else if (['TYPE_1_TECHNICAL'].includes(s)) colorClass = styles.slateLight;
  else if (['TYPE_2_DESTINATION_UNAVAILABLE'].includes(s)) colorClass = styles.amber;

  return (
    <span className={`${styles.badge} ${colorClass} ${className}`}>
      {status}
    </span>
  );
};
