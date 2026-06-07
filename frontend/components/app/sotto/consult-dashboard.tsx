'use client';

import * as React from 'react';
import { useState } from 'react';
import type { SottoCue } from '@/hooks/useSottoCues';
import { ContextRail } from './context-rail';
import { LoadedContextBar } from './loaded-context-bar';
import { PatientInvite } from './patient-invite';
import { ProtocolView } from './protocol-view';
import { SottoTopBar } from './sotto-top-bar';
import { TranscriptPane } from './transcript-pane';

interface SottoConsultDashboardProps {
  /** Live cue cards from `useSottoCues`. */
  cues: SottoCue[];
  /** Whether the session/agent is connected (drives the status pill). */
  connected: boolean;
  /** Shareable URL the patient uses to join (shown until the patient connects). */
  patientShareUrl?: string;
  /** Ends/leaves the consult. */
  onEndCall: () => void;
  /** Whether the text-chat overlay is open. */
  chatOpen: boolean;
  /** Toggles the text-chat overlay. */
  onToggleChat: () => void;
}

type View = 'consult' | 'protocol';

/**
 * Doctor-facing consult dashboard (mockup Screen 1 + Screen 2). Fills the screen and composes the
 * top bar (status + mic/chat/end controls), loaded-context chips, the patient invite, and the
 * transcript | cue-rail split. "Generate protocol" swaps to the static protocol view; "Back"
 * returns to the consult with transcript/cards intact.
 */
export function SottoConsultDashboard({
  cues,
  connected,
  patientShareUrl,
  onEndCall,
  chatOpen,
  onToggleChat,
}: SottoConsultDashboardProps) {
  const [view, setView] = useState<View>('consult');

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        background: '#F5F6F8',
        color: '#1B2430',
        overflowY: 'auto',
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 11,
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
      }}
    >
      <SottoTopBar
        connected={connected}
        onGenerateProtocol={() => setView('protocol')}
        onEndCall={onEndCall}
        chatOpen={chatOpen}
        onToggleChat={onToggleChat}
      />

      <div
        style={{
          fontSize: 10.5,
          color: '#854F0B',
          background: '#FCF3E3',
          border: '0.5px solid #F0DDB6',
          borderRadius: 8,
          padding: '4px 9px',
        }}
      >
        <i className="ti ti-alert-triangle" /> Sotto surfaces context and suggestions — not medical
        advice. The doctor decides.
      </div>

      {view === 'consult' ? (
        <>
          <LoadedContextBar />
          {patientShareUrl && <PatientInvite url={patientShareUrl} />}
          <div style={{ display: 'flex', gap: 11, flex: 1, minHeight: 360, alignItems: 'stretch' }}>
            <TranscriptPane />
            <ContextRail cues={cues} />
          </div>
        </>
      ) : (
        <ProtocolView onBack={() => setView('consult')} />
      )}
    </div>
  );
}
