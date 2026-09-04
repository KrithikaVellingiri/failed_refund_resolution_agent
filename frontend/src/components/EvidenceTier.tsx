import React from 'react';
import styles from './EvidenceTier.module.css';

interface EvidenceTierProps {
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  children: React.ReactNode;
}

export const EvidenceTier: React.FC<EvidenceTierProps> = ({ severity, children }) => {
  let tierClass = styles.weak;
  if (severity === 'HIGH') tierClass = styles.strong;
  else if (severity === 'MEDIUM') tierClass = styles.moderate;

  return (
    <div className={`${styles.container} ${tierClass}`}>
      {severity === 'LOW' && <div className={styles.caption}>Weak signal — not proof</div>}
      <div className={styles.content}>{children}</div>
    </div>
  );
};
