import React from 'react';
import styles from './RiskIndicator.module.css';

interface RiskIndicatorProps {
  score: number | null;
}

export const RiskIndicator: React.FC<RiskIndicatorProps> = ({ score }) => {
  if (score === null || score === undefined) return <span>-</span>;
  
  let dotClass = styles.green;
  if (score >= 71) dotClass = styles.red;
  else if (score >= 31) dotClass = styles.amber;

  return (
    <div className={styles.container}>
      <span className={`${styles.dot} ${dotClass}`} />
      <span className={styles.score}>{score}</span>
    </div>
  );
};
