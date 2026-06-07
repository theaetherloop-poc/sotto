import * as React from 'react';
import type { SottoCue, SottoCueType } from '@/hooks/useSottoCues';
import { cn } from '@/lib/shadcn/utils';

interface SottoCuePanelProps extends React.HTMLAttributes<HTMLDivElement> {
  cues: SottoCue[];
  hidden?: boolean;
}

const TYPE_META: Record<SottoCueType, { label: string; dot: string; ring: string }> = {
  suggested_question: {
    label: 'Suggested Next Question',
    dot: 'bg-sky-500',
    ring: 'border-sky-500/30',
  },
  patient_context: {
    label: 'Patient Context',
    dot: 'bg-emerald-500',
    ring: 'border-emerald-500/30',
  },
  protocol_direction: {
    label: 'Protocol Direction',
    dot: 'bg-fuchsia-500',
    ring: 'border-fuchsia-500/30',
  },
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function SottoCuePanel({ cues, hidden = false, className, ...props }: SottoCuePanelProps) {
  if (hidden) {
    return null;
  }

  // Newest first.
  const ordered = [...cues].reverse();

  return (
    <div className={cn('space-y-3', className)} {...props}>
      <h3 className="text-muted-foreground text-sm font-medium tracking-wide uppercase">
        Sotto Cues
      </h3>
      {ordered.length === 0 ? (
        <p className="text-muted-foreground text-sm italic">
          Listening… cues will appear here as the consult unfolds.
        </p>
      ) : (
        <div className="space-y-2">
          {ordered.map((cue) => {
            const meta = TYPE_META[cue.type];
            return (
              <div
                key={cue.id}
                className={cn(
                  'bg-card text-card-foreground rounded-lg border p-3 shadow-sm',
                  meta.ring
                )}
              >
                <div className="flex items-center gap-2">
                  <span className={cn('h-2 w-2 rounded-full', meta.dot)} aria-hidden />
                  <span className="text-xs font-semibold tracking-wide uppercase">
                    {meta.label}
                  </span>
                  {cue.triggeredAt && (
                    <span className="text-muted-foreground ml-auto text-xs tabular-nums">
                      {formatTime(cue.triggeredAt)}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm leading-snug font-medium">{cue.content}</p>
                {cue.rationale && (
                  <p className="text-muted-foreground mt-1 text-xs leading-snug italic">
                    {cue.rationale}
                  </p>
                )}
                {cue.transcriptSnippet && (
                  <p className="text-muted-foreground mt-2 text-xs leading-snug">
                    <span className="font-medium">{cue.triggeredBySpeaker || 'trigger'}:</span> “
                    {cue.transcriptSnippet}”
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
