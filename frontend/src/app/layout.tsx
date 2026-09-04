import './globals.css';
import React from 'react';

export const metadata = {
  title: 'Razorpay - Resolution Console',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header style={{ padding: 'var(--spacing-md) var(--spacing-lg)', borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface)' }}>
          <h1 style={{ fontSize: '1.25rem', margin: 0, fontWeight: 600 }}>Resolution Console</h1>
        </header>
        <main style={{ padding: 'var(--spacing-lg)', maxWidth: '1400px', margin: '0 auto' }}>
          {children}
        </main>
      </body>
    </html>
  );
}
