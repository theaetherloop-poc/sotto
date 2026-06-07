import { useEffect, useMemo, useState } from 'react';
import { RoomEvent } from 'livekit-client';
import { useRoomContext } from '@livekit/components-react';

const textDecoder = new TextDecoder();

export type SottoTranscriptSpeaker = 'doctor' | 'patient';

export type SottoTranscriptLine = {
  id: string;
  speaker: SottoTranscriptSpeaker;
  text: string;
  /** ISO timestamp string from the agent */
  timestamp: string;
};

const MAX_LINES_DEFAULT = 200;

function parsePayload(payload: Uint8Array): SottoTranscriptLine | null {
  try {
    const message = JSON.parse(textDecoder.decode(payload));
    if (!message || message.type !== 'sotto_transcript' || typeof message.data !== 'object') {
      return null;
    }
    const data = message.data as Record<string, unknown>;
    const speaker =
      data.speaker === 'doctor' ? 'doctor' : data.speaker === 'patient' ? 'patient' : null;
    const text = typeof data.text === 'string' ? data.text : '';
    if (!speaker || !text) {
      return null;
    }
    const timestamp =
      typeof data.timestamp === 'string' ? data.timestamp : new Date().toISOString();
    return {
      id: `${timestamp}-${speaker}-${text.slice(0, 16)}`,
      speaker,
      text,
      timestamp,
    };
  } catch (error) {
    console.warn('Failed to parse sotto_transcript payload', error);
    return null;
  }
}

/**
 * Subscribes to the Sotto agent's `sotto_transcript` data messages and returns the live,
 * speaker-labeled consult transcript in chronological order. The agent publishes one message per
 * finalized STT turn (reliable, JSON->bytes).
 *
 * Must be used within a RoomContext (provided by `AgentSessionProvider`/`SessionProvider`).
 */
export function useSottoTranscript(maxLines = MAX_LINES_DEFAULT) {
  const room = useRoomContext();
  const [lines, setLines] = useState<SottoTranscriptLine[]>([]);

  useEffect(() => {
    if (!room) return;

    const handleData = (payload: Uint8Array) => {
      const parsed = parsePayload(payload);
      if (!parsed) return;
      setLines((prev) => {
        if (prev.some((l) => l.id === parsed.id)) return prev;
        const next = [...prev, parsed];
        return maxLines > 0 && next.length > maxLines ? next.slice(-maxLines) : next;
      });
    };

    room.on(RoomEvent.DataReceived, handleData);
    return () => {
      room.off(RoomEvent.DataReceived, handleData);
    };
  }, [room, maxLines]);

  return useMemo(() => lines, [lines]);
}
