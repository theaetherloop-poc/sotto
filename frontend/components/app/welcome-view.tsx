'use client';

import * as React from 'react';
import { useState } from 'react';
import { DEMO_PATIENT_LABEL } from '@/lib/sotto-demo';

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
  /** Shareable URL the patient uses to join (shown so the doctor can send it before joining). */
  patientShareUrl?: string;
}

/**
 * White, mockup-styled start screen (doctor-only — the patient joins via the shared meet.livekit.io
 * link, never this app). Surfaces the patient invite link up front so the doctor can send it before
 * entering the consult.
 */
export const WelcomeView = ({
  startButtonText,
  onStartCall,
  patientShareUrl,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!patientShareUrl) return;
    try {
      await navigator.clipboard.writeText(patientShareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be blocked; the input below still lets the user copy manually.
    }
  };

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed',
        inset: 0,
        background: '#F5F6F8',
        color: '#1B2430',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 460,
          background: '#fff',
          border: '0.5px solid #E5E7EB',
          borderRadius: 16,
          padding: '28px 26px',
          boxShadow: '0 8px 30px rgba(16,24,40,0.06)',
          textAlign: 'center',
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 20,
            fontWeight: 600,
          }}
        >
          <span
            aria-hidden
            style={{
              width: 30,
              height: 30,
              borderRadius: 9,
              background: '#185FA5',
              color: '#fff',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <i className="ti ti-wave-sine" />
          </span>
          Sotto
        </div>

        <p style={{ color: '#6B7280', fontSize: 13.5, lineHeight: 1.5, margin: '12px 0 0' }}>
          Ambient consult co-pilot. Sotto listens to the visit and surfaces context and suggestions
          — it never speaks and gives no medical advice.
        </p>

        <div
          style={{
            margin: '18px 0',
            padding: '10px 12px',
            background: '#F5F6F8',
            border: '0.5px solid #E5E7EB',
            borderRadius: 10,
            fontSize: 12.5,
            color: '#1B2430',
          }}
        >
          <span style={{ color: '#6B7280' }}>Next consult · </span>
          {DEMO_PATIENT_LABEL}
        </div>

        <button
          type="button"
          onClick={onStartCall}
          style={{
            width: '100%',
            border: 'none',
            background: '#185FA5',
            color: '#fff',
            borderRadius: 10,
            padding: '11px 0',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {startButtonText || 'Start consult'}
        </button>
        <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 7 }}>
          You&apos;ll be asked for microphone access.
        </div>

        {patientShareUrl && (
          <div
            style={{
              marginTop: 20,
              paddingTop: 16,
              borderTop: '0.5px solid #F0F1F3',
              textAlign: 'left',
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                readOnly
                value={patientShareUrl}
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
            <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 6 }}>
              Send this to the patient — they join from their own device.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
