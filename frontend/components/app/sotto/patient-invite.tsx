'use client';

import * as React from 'react';
import { useEffect, useRef, useState } from 'react';
import { useRemoteParticipants } from '@livekit/components-react';

interface PatientInviteProps {
  url: string;
}

/**
 * Patient join link with presence-aware auto-collapse. While no patient is connected the link is
 * shown prominently; once a participant whose identity starts with `patient-` joins (matching the
 * agent's `speaker_for` prefix convention) it collapses to a small "Invite patient" button that
 * opens a popover with the copyable URL.
 */
export function PatientInvite({ url }: PatientInviteProps) {
  const participants = useRemoteParticipants();
  const patientPresent = participants.some((p) => p.identity?.startsWith('patient-'));

  const [copied, setCopied] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be blocked; the input below still lets the user copy manually.
    }
  };

  useEffect(() => {
    if (!popoverOpen) return;
    const onClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [popoverOpen]);

  const linkRow = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <input
        readOnly
        value={url}
        onFocus={(e) => e.currentTarget.select()}
        style={{
          flex: 1,
          minWidth: 0,
          border: '0.5px solid #E5E7EB',
          borderRadius: 8,
          padding: '6px 9px',
          fontSize: 12,
          color: '#1B2430',
          background: '#F5F6F8',
        }}
      />
      <button
        type="button"
        onClick={copy}
        style={{
          flexShrink: 0,
          border: 'none',
          background: '#185FA5',
          color: '#fff',
          borderRadius: 8,
          padding: '6px 12px',
          fontSize: 12,
          fontWeight: 500,
          cursor: 'pointer',
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );

  if (!patientPresent) {
    return (
      <div
        style={{
          background: '#fff',
          border: '0.5px solid #E5E7EB',
          borderRadius: 12,
          padding: '12px 14px',
        }}
      >
        <div
          style={{
            fontSize: 11,
            color: '#185FA5',
            fontWeight: 500,
            marginBottom: 6,
            display: 'flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          <i className="ti ti-link" /> Patient join link
        </div>
        {linkRow}
        <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 6 }}>
          Send this to the patient to join the consult.
        </div>
      </div>
    );
  }

  return (
    <div ref={popoverRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => setPopoverOpen((v) => !v)}
        style={{
          border: '0.5px solid #E5E7EB',
          background: '#fff',
          borderRadius: 8,
          padding: '5px 11px',
          fontSize: 12,
          color: '#1B2430',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
        }}
      >
        <i className="ti ti-user-plus" /> Invite patient
      </button>
      {popoverOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            zIndex: 70,
            width: 320,
            maxWidth: '80vw',
            background: '#fff',
            border: '0.5px solid #E5E7EB',
            borderRadius: 12,
            padding: '12px 14px',
            boxShadow: '0 8px 24px rgba(16,24,40,0.12)',
          }}
        >
          <div style={{ fontSize: 11, color: '#185FA5', fontWeight: 500, marginBottom: 6 }}>
            Patient join link
          </div>
          {linkRow}
        </div>
      )}
    </div>
  );
}
