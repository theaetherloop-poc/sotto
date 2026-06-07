'use client';

import * as React from 'react';
import { useEffect, useRef } from 'react';
import { useSottoTranscript } from '@/hooks/useSottoTranscript';
import { DEMO_PATIENT } from '@/lib/sotto-demo';

/**
 * Live, speaker-labeled transcript pane (left of Screen 1). Appends each final STT turn and
 * auto-scrolls to the bottom. Doctor lines are blue ("Dr."), patient lines green (first name).
 */
export function TranscriptPane() {
  const lines = useSottoTranscript();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <div
      style={{
        flex: '0 0 290px',
        background: '#fff',
        border: '0.5px solid #E5E7EB',
        borderRadius: 12,
        padding: 11,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
      }}
    >
      <div style={{ fontSize: 11, color: '#6B7280', fontWeight: 500, marginBottom: 8 }}>
        Transcript
      </div>
      <div
        ref={scrollRef}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 7,
          fontSize: 12,
          lineHeight: 1.45,
          overflowY: 'auto',
          flex: 1,
          minHeight: 0,
        }}
      >
        {lines.map((line) => {
          const isDoctor = line.speaker === 'doctor';
          return (
            <div key={line.id}>
              <span style={{ color: isDoctor ? '#185FA5' : '#2E8B57', fontWeight: 500 }}>
                {isDoctor ? 'Dr.' : DEMO_PATIENT.firstName}
              </span>{' '}
              {line.text}
            </div>
          );
        })}
        <div style={{ color: '#9CA3AF', fontSize: 11 }}>listening…</div>
      </div>
    </div>
  );
}
