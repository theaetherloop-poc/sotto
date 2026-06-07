'use client';

import * as React from 'react';
import { Track } from 'livekit-client';
import { useTrackToggle } from '@livekit/components-react';
import { DEMO_PATIENT_LABEL } from '@/lib/sotto-demo';

interface SottoTopBarProps {
  /** Green status dot is lit while the session/agent is connected. */
  connected: boolean;
  /** Opens the protocol view. */
  onGenerateProtocol: () => void;
  /** Ends/leaves the consult. */
  onEndCall: () => void;
  /** Whether the text-chat overlay is open. */
  chatOpen: boolean;
  /** Toggles the text-chat overlay. */
  onToggleChat: () => void;
}

/**
 * Consult-view top bar (Screen 1 of the mockup): status pill + patient label + the live mic toggle,
 * chat toggle, Generate-protocol, and End-consult controls. The mic toggle reuses LiveKit's
 * `useTrackToggle`, so it publishes/unpublishes the doctor's microphone exactly like the original
 * control bar did.
 *
 * The Auto/Manual segmented control is intentionally non-functional this pass — it renders to match
 * the mockup but is not yet wired to the agent.
 */
export function SottoTopBar({
  connected,
  onGenerateProtocol,
  onEndCall,
  chatOpen,
  onToggleChat,
}: SottoTopBarProps) {
  const mic = useTrackToggle({ source: Track.Source.Microphone });

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: '#fff',
        border: '0.5px solid #E5E7EB',
        borderRadius: 10,
        padding: '9px 12px',
        gap: 10,
        flexWrap: 'wrap',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
        <span
          aria-hidden
          style={{
            width: 9,
            height: 9,
            borderRadius: '50%',
            background: connected ? '#2E8B57' : '#9CA3AF',
            display: 'inline-block',
          }}
        />
        <span style={{ fontWeight: 500 }}>Sotto</span>
        <span style={{ color: '#6B7280' }}>{connected ? 'listening' : 'connecting…'}</span>
      </div>

      <div style={{ fontSize: 12 }}>
        <span style={{ fontWeight: 500 }}>{DEMO_PATIENT_LABEL.split(' · ')[0]}</span>{' '}
        <span style={{ color: '#6B7280' }}>
          · {DEMO_PATIENT_LABEL.split(' · ').slice(1).join(' · ')}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        {/* Auto / Manual toggle — visual-only */}
        <span
          style={{
            display: 'inline-flex',
            border: '0.5px solid #E5E7EB',
            borderRadius: 8,
            overflow: 'hidden',
            fontSize: 11,
          }}
        >
          <span
            style={{ padding: '4px 8px', background: '#E8F1FB', color: '#185FA5', fontWeight: 500 }}
          >
            Auto
          </span>
          <span style={{ padding: '4px 8px', color: '#6B7280' }}>Manual</span>
        </span>

        {/* Microphone toggle — publishes/unpublishes the doctor's mic */}
        <button
          type="button"
          onClick={() => mic.toggle()}
          disabled={mic.pending}
          aria-label={mic.enabled ? 'Mute microphone' : 'Unmute microphone'}
          title={mic.enabled ? 'Mute microphone' : 'Unmute microphone'}
          style={{
            border: mic.enabled ? '0.5px solid #E5E7EB' : '0.5px solid #F0C9C2',
            background: mic.enabled ? '#fff' : '#FBEAE6',
            color: mic.enabled ? '#1B2430' : '#B42318',
            borderRadius: 8,
            padding: '4px 9px',
            fontSize: 12,
            cursor: mic.pending ? 'default' : 'pointer',
            opacity: mic.pending ? 0.6 : 1,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          <i className={`ti ti-${mic.enabled ? 'microphone' : 'microphone-off'}`} />
          {mic.enabled ? 'Mic on' : 'Muted'}
        </button>

        {/* Text-chat toggle */}
        <button
          type="button"
          onClick={onToggleChat}
          aria-label="Toggle chat"
          title="Toggle chat"
          style={{
            border: '0.5px solid #E5E7EB',
            background: chatOpen ? '#E8F1FB' : '#fff',
            color: chatOpen ? '#185FA5' : '#6B7280',
            borderRadius: 8,
            padding: '4px 8px',
            cursor: 'pointer',
          }}
        >
          <i className="ti ti-message" />
        </button>

        <button
          type="button"
          onClick={onGenerateProtocol}
          style={{
            border: '0.5px solid #185FA5',
            background: '#185FA5',
            color: '#fff',
            borderRadius: 8,
            padding: '5px 10px',
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Generate protocol
        </button>

        {/* End consult */}
        <button
          type="button"
          onClick={onEndCall}
          style={{
            border: '0.5px solid #F0C9C2',
            background: '#FBEAE6',
            color: '#B42318',
            borderRadius: 8,
            padding: '5px 10px',
            fontSize: 12,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          End consult
        </button>
      </div>
    </div>
  );
}
