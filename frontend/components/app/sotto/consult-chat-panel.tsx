'use client';

import * as React from 'react';
import { useState } from 'react';
import { type AgentState, type ReceivedMessage, useChat } from '@livekit/components-react';
import { AgentChatTranscript } from '@/components/agents-ui/agent-chat-transcript';

interface ConsultChatPanelProps {
  messages: ReceivedMessage[];
  agentState?: AgentState;
  onClose: () => void;
}

/**
 * White chat side panel for the doctor consult view. Reuses LiveKit's `useChat` to send text
 * messages and the existing transcript renderer, styled to match the mockup rather than the dark
 * floating control bar.
 */
export function ConsultChatPanel({ messages, agentState, onClose }: ConsultChatPanelProps) {
  const { send } = useChat();
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);

  const submit = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    try {
      setSending(true);
      await send(text);
      setDraft('');
    } catch (err) {
      console.error('Failed to send chat message', err);
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 14,
        right: 14,
        bottom: 14,
        zIndex: 80,
        width: 320,
        maxWidth: 'calc(100vw - 28px)',
        background: '#fff',
        border: '0.5px solid #E5E7EB',
        borderRadius: 12,
        boxShadow: '0 8px 30px rgba(16,24,40,0.12)',
        display: 'flex',
        flexDirection: 'column',
        color: '#1B2430',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 12px',
          borderBottom: '0.5px solid #F0F1F3',
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 500, color: '#6B7280' }}>
          <i className="ti ti-message" /> Chat
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close chat"
          style={{ border: 'none', background: 'transparent', color: '#6B7280', cursor: 'pointer' }}
        >
          <i className="ti ti-x" />
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '6px 4px' }}>
        <AgentChatTranscript agentState={agentState} messages={messages} />
      </div>

      <div style={{ display: 'flex', gap: 7, padding: 10, borderTop: '0.5px solid #F0F1F3' }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Type a note…"
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
          onClick={submit}
          disabled={sending || draft.trim().length === 0}
          style={{
            flexShrink: 0,
            border: 'none',
            background: '#185FA5',
            color: '#fff',
            borderRadius: 8,
            padding: '6px 12px',
            fontSize: 12,
            fontWeight: 500,
            cursor: sending || draft.trim().length === 0 ? 'default' : 'pointer',
            opacity: sending || draft.trim().length === 0 ? 0.55 : 1,
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}
