'use client';

import * as React from 'react';
import { LOADED_CONTEXT_CHIPS } from '@/lib/sotto-demo';

/**
 * Static "Loaded for this consult" chip row (Screen 1 of the mockup). Shows what Sotto already
 * has for this consult; populated from session context at start (static for the demo).
 */
export function LoadedContextBar() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
        flexWrap: 'wrap',
        fontSize: 11.5,
        color: '#6B7280',
      }}
    >
      <span style={{ fontWeight: 500 }}>Loaded for this consult</span>
      {LOADED_CONTEXT_CHIPS.map((chip) => (
        <span
          key={chip.label}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            background: '#fff',
            border: '0.5px solid #E5E7EB',
            borderRadius: 20,
            padding: '3px 10px',
          }}
        >
          <i className={`ti ti-${chip.icon}`} /> {chip.label}{' '}
          <i className="ti ti-circle-check" style={{ color: '#2E8B57' }} />
        </span>
      ))}
    </div>
  );
}
