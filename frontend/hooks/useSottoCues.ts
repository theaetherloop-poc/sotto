import { useEffect, useMemo, useState } from 'react';
import { RoomEvent } from 'livekit-client';
import { useRoomContext } from '@livekit/components-react';

const textDecoder = new TextDecoder();

export type SottoCueType = 'suggested_question' | 'patient_context' | 'protocol_direction';

export type SottoCue = {
  id: string;
  type: SottoCueType;
  content: string;
  rationale: string;
  triggeredBySpeaker: string;
  transcriptSnippet: string;
  /** ISO timestamp string from the agent */
  triggeredAt: string;
};

const MAX_CUES_DEFAULT = 20;
const VALID_TYPES = new Set<SottoCueType>([
  'suggested_question',
  'patient_context',
  'protocol_direction',
]);

function parsePayload(payload: Uint8Array): SottoCue | null {
  try {
    const message = JSON.parse(textDecoder.decode(payload));
    if (!message || message.type !== 'sotto_cue' || typeof message.data !== 'object') {
      return null;
    }
    const data = message.data as Record<string, unknown>;
    const type = data.type as SottoCueType;
    if (!VALID_TYPES.has(type)) {
      return null;
    }
    const content = typeof data.content === 'string' ? data.content : '';
    if (!content) {
      return null;
    }
    return {
      id: typeof data.id === 'string' ? data.id : `${Date.now()}-${content.slice(0, 12)}`,
      type,
      content,
      rationale: typeof data.rationale === 'string' ? data.rationale : '',
      triggeredBySpeaker:
        typeof data.triggered_by_speaker === 'string' ? data.triggered_by_speaker : '',
      transcriptSnippet: typeof data.transcript_snippet === 'string' ? data.transcript_snippet : '',
      triggeredAt:
        typeof data.triggered_at === 'string' ? data.triggered_at : new Date().toISOString(),
    };
  } catch (error) {
    console.warn('Failed to parse sotto_cue payload', error);
    return null;
  }
}

/**
 * Subscribes to the Sotto agent's `sotto_cue` data messages and returns the most recent cue
 * cards. The agent publishes these (reliable, JSON->bytes) whenever its cue engine decides to
 * surface context to the practitioner.
 *
 * Must be used within a RoomContext (provided by `AgentSessionProvider`/`SessionProvider`).
 */
export function useSottoCues(maxCues = MAX_CUES_DEFAULT) {
  const room = useRoomContext();
  const [cues, setCues] = useState<SottoCue[]>([]);

  useEffect(() => {
    if (!room) return;

    const handleData = (payload: Uint8Array) => {
      const parsed = parsePayload(payload);
      if (!parsed) return;
      setCues((prev) => {
        if (prev.some((c) => c.id === parsed.id)) return prev;
        const next = [...prev, parsed];
        return maxCues > 0 && next.length > maxCues ? next.slice(-maxCues) : next;
      });
    };

    room.on(RoomEvent.DataReceived, handleData);
    return () => {
      room.off(RoomEvent.DataReceived, handleData);
    };
  }, [room, maxCues]);

  return useMemo(() => cues, [cues]);
}
