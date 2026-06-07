'use client';

import { useEffect, useMemo, useState } from 'react';
import { DisconnectReason, RoomEvent } from 'livekit-client';
import { useSession } from '@livekit/components-react';
import { WarningIcon } from '@phosphor-icons/react/dist/ssr';
import type { AppConfig } from '@/app-config';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { ViewController } from '@/components/app/view-controller';
import { Toaster } from '@/components/ui/sonner';
import { useDebugMode } from '@/hooks/useDebug';
import { fetchPatientMeetUrl, getSottoTokenSource } from '@/lib/utils';

export type ConsultRole = 'doctor' | 'patient';

function resolveConsultParams(): { role: ConsultRole; room: string } {
  if (typeof window === 'undefined') {
    return { role: 'doctor', room: '' };
  }
  const params = new URLSearchParams(window.location.search);
  const role: ConsultRole = params.get('role') === 'patient' ? 'patient' : 'doctor';
  const room = params.get('room')?.trim() || `sotto-${Math.random().toString(36).slice(2, 8)}`;
  return { role, room };
}

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  // NOTE: useAgentErrors() is intentionally NOT used. It's a watchdog for conversational voice
  // agents — it force-ends the session when agent.state becomes 'failed' (i.e., the agent never
  // reaches a speaking/listening state within the connect timeout). Sotto is an ambient listener
  // that never speaks or reports a conversational state, so that watchdog would always trip and
  // kill the consult mid-conversation.

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  const [{ role, room }] = useState(resolveConsultParams);

  // Pin the (otherwise randomly generated) room into the URL on first load so reloads reuse the
  // same room — otherwise the doctor jumps to a fresh room on every reload while the patient link
  // already shared still points at the old one, leaving doctor and patient in separate rooms.
  useEffect(() => {
    if (typeof window === 'undefined' || !room) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('room')?.trim()) return;
    params.set('room', room);
    if (!params.get('role')) params.set('role', role);
    window.history.replaceState(null, '', `?${params.toString()}`);
  }, [room, role]);

  const tokenSource = useMemo(() => getSottoTokenSource(role, room), [role, room]);

  // No agentName: the Sotto agent uses automatic dispatch, so we don't wait for a named agent.
  const session = useSession(tokenSource);

  // Surface the disconnect reason in plain text (the raw event logs it as a collapsed object).
  useEffect(() => {
    const room = session.room;
    const onDisconnected = (reason?: DisconnectReason) => {
      console.warn(
        '[SOTTO] room disconnected — reason:',
        reason,
        reason != null ? DisconnectReason[reason] : '(none)'
      );
    };
    room.on(RoomEvent.Disconnected, onDisconnected);
    return () => {
      room.off(RoomEvent.Disconnected, onDisconnected);
    };
  }, [session.room]);

  // The patient joins via LiveKit's public hosted client (reachable from any device, HTTPS),
  // not the localhost dev frontend. Mint their token + meet URL once, doctor-side only.
  const [patientShareUrl, setPatientShareUrl] = useState('');
  useEffect(() => {
    if (role !== 'doctor' || !room) return;
    let cancelled = false;
    fetchPatientMeetUrl(room)
      .then((url) => {
        if (!cancelled) setPatientShareUrl(url);
      })
      .catch((err) => console.error('Failed to build patient join link', err));
    return () => {
      cancelled = true;
    };
  }, [role, room]);

  return (
    <AgentSessionProvider session={session}>
      <AppSetup />
      <main className="grid h-svh grid-cols-1 place-content-center">
        <ViewController appConfig={appConfig} role={role} patientShareUrl={patientShareUrl} />
      </main>
      <StartAudioButton label="Start Audio" />
      <Toaster
        icons={{
          warning: <WarningIcon weight="bold" />,
        }}
        position="top-center"
        className="toaster group"
        style={
          {
            '--normal-bg': 'var(--popover)',
            '--normal-text': 'var(--popover-foreground)',
            '--normal-border': 'var(--border)',
          } as React.CSSProperties
        }
      />
    </AgentSessionProvider>
  );
}
