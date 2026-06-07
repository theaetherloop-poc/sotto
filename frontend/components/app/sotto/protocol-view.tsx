'use client';

import * as React from 'react';
import { useMemo, useState } from 'react';
import { OTHER_FOCUS_AREAS, PRIORITIZED_FOCUS_AREAS, SUPPLEMENTS } from '@/lib/sotto-protocol';

interface ProtocolViewProps {
  onBack: () => void;
}

/**
 * Protocol view (Screen 2): prioritized focus areas + the suggested-supplement table, rendered
 * from the static mock protocol. The Add checkboxes update an "N of M selected" count; there is
 * no approve/finalize action — this is a suggestion the doctor curates.
 */
export function ProtocolView({ onBack }: ProtocolViewProps) {
  const [checked, setChecked] = useState<boolean[]>(() => SUPPLEMENTS.map((s) => s.defaultChecked));
  const selectedCount = useMemo(() => checked.filter(Boolean).length, [checked]);

  return (
    <div
      style={{
        background: '#fff',
        border: '0.5px solid #E5E7EB',
        borderRadius: 12,
        padding: '14px 16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 6,
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              border: '0.5px solid #E5E7EB',
              background: '#fff',
              borderRadius: 8,
              padding: '5px 10px',
              fontSize: 12,
              color: '#6B7280',
              cursor: 'pointer',
            }}
          >
            <i className="ti ti-arrow-left" /> Consult
          </button>
          <span style={{ fontSize: 17, fontWeight: 500 }}>Suggested protocol</span>
        </div>
        <span style={{ fontSize: 11, color: '#6B7280' }}>
          Sotto&apos;s suggestion from the consult — the doctor decides what to use
        </span>
      </div>

      <div style={{ fontSize: 13, color: '#6B7280', fontWeight: 500, margin: '8px 0 9px' }}>
        Prioritized focus areas
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
        {PRIORITIZED_FOCUS_AREAS.map((fa) => (
          <div key={fa.rank} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <span
              style={{
                flex: '0 0 22px',
                height: 22,
                borderRadius: '50%',
                background: '#EF9F27',
                color: '#412402',
                fontSize: 12,
                fontWeight: 500,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {fa.rank}
            </span>
            <div>
              <div style={{ fontWeight: 500, fontSize: 14 }}>{fa.name}</div>
              <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.5 }}>{fa.why}</div>
            </div>
          </div>
        ))}
        <div style={{ fontSize: 12, color: '#6B7280', paddingLeft: 32 }}>
          Other:{' '}
          {OTHER_FOCUS_AREAS.map((fa, i) => (
            <React.Fragment key={fa.rank}>
              {i > 0 && ' · '}
              <span style={{ color: '#1B2430' }}>{fa.rank}</span> {fa.name}
            </React.Fragment>
          ))}
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 6,
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <span style={{ fontSize: 13, color: '#6B7280', fontWeight: 500 }}>
          Suggested supplements
        </span>
        <span style={{ fontSize: 11, color: '#854F0B' }}>
          <i className="ti ti-star" /> Priority = supports a top-3 focus area
        </span>
      </div>

      <div style={{ border: '0.5px solid #E5E7EB', borderRadius: 12, overflow: 'hidden' }}>
        <table
          style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' }}
        >
          <thead>
            <tr>
              <th style={thStyle(7)}>Add</th>
              <th style={thStyle(20)}>Supplement</th>
              <th style={thStyle(12)}>Dosage</th>
              <th style={thStyle(14)}>Frequency</th>
              <th style={thStyle(17)}>Focus area</th>
              <th style={thStyle(30)}>Why</th>
            </tr>
          </thead>
          <tbody>
            {SUPPLEMENTS.map((s, i) => (
              <tr key={s.name}>
                <td style={tdStyle}>
                  <input
                    type="checkbox"
                    checked={checked[i]}
                    onChange={(e) =>
                      setChecked((prev) => {
                        const next = [...prev];
                        next[i] = e.target.checked;
                        return next;
                      })
                    }
                    style={{ width: 16, height: 16, accentColor: '#185FA5', cursor: 'pointer' }}
                  />
                </td>
                <td style={tdStyle}>
                  <span style={{ fontWeight: 500, color: '#185FA5' }}>{s.name}</span>{' '}
                  {s.priority && (
                    <span
                      style={{
                        background: '#EF9F27',
                        color: '#412402',
                        borderRadius: 20,
                        fontSize: 10,
                        padding: '1px 6px',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <i className="ti ti-star" /> Priority
                    </span>
                  )}
                </td>
                <td style={tdStyle}>{s.dosage}</td>
                <td style={tdStyle}>{s.frequency}</td>
                <td style={tdStyle}>{s.focusArea}</td>
                <td style={{ ...tdStyle, color: '#4B5563' }}>{s.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 10 }}>
        <span style={{ fontSize: 12, color: '#6B7280' }}>
          <i className="ti ti-clipboard-check" /> {selectedCount} of {SUPPLEMENTS.length} selected
          to include
        </span>
      </div>
    </div>
  );
}

function thStyle(widthPct: number): React.CSSProperties {
  return {
    width: `${widthPct}%`,
    padding: '8px 10px',
    fontWeight: 500,
    color: '#6B7280',
    textAlign: 'left',
    background: '#F5F6F8',
  };
}

const tdStyle: React.CSSProperties = {
  padding: '8px 10px',
  verticalAlign: 'top',
  borderTop: '0.5px solid #F0F1F3',
};
