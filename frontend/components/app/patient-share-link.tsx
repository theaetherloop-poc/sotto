'use client';

import * as React from 'react';
import { useState } from 'react';
import { cn } from '@/lib/shadcn/utils';

interface PatientShareLinkProps extends React.HTMLAttributes<HTMLDivElement> {
  url: string;
}

export function PatientShareLink({ url, className, ...props }: PatientShareLinkProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be blocked; the input below still lets the user copy manually.
    }
  };

  return (
    <div
      className={cn(
        'border-border bg-card text-card-foreground rounded-lg border p-3 shadow-sm',
        className
      )}
      {...props}
    >
      <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        Patient join link
      </h3>
      <div className="mt-2 flex items-center gap-2">
        <input
          readOnly
          value={url}
          onFocus={(e) => e.currentTarget.select()}
          className="border-border bg-background min-w-0 flex-1 truncate rounded-md border px-2 py-1 text-xs"
        />
        <button
          type="button"
          onClick={copy}
          className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0 rounded-md px-3 py-1 text-xs font-semibold"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">
        Send this to the patient to join the consult.
      </p>
    </div>
  );
}
