'use client';

import * as React from 'react';
import type { SottoCue, SottoCueType } from '@/hooks/useSottoCues';

interface ContextRailProps {
  cues: SottoCue[];
}

const TYPE_META: Record<
  SottoCueType,
  { icon: string; label: string; accent: boolean; headerColor: string }
> = {
  suggested_question: {
    icon: 'help-circle',
    label: 'Suggested question',
    accent: true,
    headerColor: '#185FA5',
  },
  protocol_direction: {
    icon: 'route',
    label: 'Protocol direction',
    accent: true,
    headerColor: '#185FA5',
  },
  patient_context: {
    icon: 'user-heart',
    label: 'Patient context',
    accent: false,
    headerColor: '#6B7280',
  },
};

// Source-chip palette for the multi-row patient_context card (matches the mockup).
const ROW_SOURCE_STYLE: Record<string, { bg: string; color: string }> = {
  Labs: { bg: '#FBEAEA', color: '#A32D2D' },
  OURA: { bg: '#E6F4EC', color: '#0F6E56' },
};
const ROW_SOURCE_DEFAULT = { bg: '#F1EFE8', color: '#5F5E5A' };

function CueCard({ cue }: { cue: SottoCue }) {
  const meta = TYPE_META[cue.type];
  const label = cue.header ?? meta.label;
  const hasRows = !!cue.rows && cue.rows.length > 0;
  return (
    <div
      style={{
        background: '#fff',
        border: meta.accent ? '2px solid #85B7EB' : '0.5px solid #E5E7EB',
        borderRadius: 12,
        padding: '10px 12px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          fontSize: 11,
          color: meta.headerColor,
          fontWeight: 500,
          marginBottom: hasRows ? 6 : 5,
        }}
      >
        <i className={`ti ti-${meta.icon}`} style={{ marginRight: 5 }} />
        {label}
        {/* The multi-row patient_context card labels its source per row, so it omits the
            header-level source chip (per the mockup). */}
        {!hasRows && (
          <span
            style={{
              background: '#F1EFE8',
              color: '#5F5E5A',
              borderRadius: 6,
              padding: '1px 7px',
              fontSize: 11,
              marginLeft: 6,
            }}
          >
            {cue.source}
          </span>
        )}
      </div>

      {hasRows ? (
        cue.rows!.map((row, i) => {
          const chip = ROW_SOURCE_STYLE[row.source] ?? ROW_SOURCE_DEFAULT;
          return (
            <div
              key={`${row.heading}-${i}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '4px 0',
                borderBottom: i < cue.rows!.length - 1 ? '0.5px solid #F0F1F3' : undefined,
              }}
            >
              <div style={{ fontSize: 13 }}>
                <span style={{ fontWeight: 500 }}>{row.heading}</span>{' '}
                <span style={{ color: row.tone === 'red' ? '#B00020' : '#6B7280', fontSize: 11 }}>
                  {row.detail}
                </span>
              </div>
              <span
                style={{
                  fontSize: 10,
                  background: chip.bg,
                  color: chip.color,
                  borderRadius: 6,
                  padding: '1px 7px',
                }}
              >
                {row.source}
              </span>
            </div>
          );
        })
      ) : (
        <div style={{ fontSize: 13.5, lineHeight: 1.5, color: '#1B2430' }}>{cue.content}</div>
      )}

      {cue.rationale && (
        <div style={{ fontSize: 11, lineHeight: 1.45, color: '#6B7280', marginTop: 6 }}>
          {cue.rationale}
        </div>
      )}
    </div>
  );
}

/**
 * Context rail (right of Screen 1): renders the live cue cards (from `useSottoCues`) in the
 * mockup's typed-card styles. The "Suggest" button is visual-only this pass.
 */
export function ContextRail({ cues }: ContextRailProps) {
  // Newest first.
  const ordered = [...cues].reverse();
  const hasCards = ordered.length > 0;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 9, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11, color: '#6B7280', fontWeight: 500 }}>Live context</span>
        {hasCards && (
          <span
            style={{
              fontSize: 11,
              background: '#E8F1FB',
              color: '#185FA5',
              borderRadius: 20,
              padding: '1px 8px',
              fontWeight: 500,
            }}
          >
            new
          </span>
        )}
      </div>

      {!hasCards ? (
        <div
          style={{
            color: '#9CA3AF',
            fontSize: 13,
            textAlign: 'center',
            padding: '28px 0',
            border: '0.5px dashed #D7DAE0',
            borderRadius: 12,
          }}
        >
          Listening — nothing to surface yet
        </div>
      ) : (
        ordered.map((cue) => <CueCard key={cue.id} cue={cue} />)
      )}

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <button
          type="button"
          style={{
            border: '0.5px solid #E5E7EB',
            background: '#fff',
            borderRadius: 8,
            padding: '5px 11px',
            fontSize: 12,
            color: '#1B2430',
            cursor: 'pointer',
          }}
        >
          <i className="ti ti-bulb" /> Suggest
        </button>
        <span style={{ fontSize: 11, color: '#9CA3AF' }}>tap to pin · dismiss to clear</span>
      </div>
    </div>
  );
}
