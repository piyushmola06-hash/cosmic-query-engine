import { useState } from 'react';
import type { HeadTrail } from '../api/client';

interface SectionProps {
  title: string;
  content: string;
  available: boolean;
  unavailableReason?: string;
}

function TrailSection({ title, content, available, unavailableReason }: SectionProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-zinc-700 last:border-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-zinc-700/30 transition-colors"
      >
        <span className={`text-sm font-medium ${available ? 'text-zinc-200' : 'text-zinc-500'}`}>
          {title}
        </span>
        <span className="text-zinc-500 text-xs ml-2">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1">
          {available ? (
            <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{content}</p>
          ) : (
            <p className="text-sm text-zinc-500 italic">
              {unavailableReason ?? 'Not available for this reading.'}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

interface HeadBlockProps {
  trail: HeadTrail;
}

function HeadBlock({ trail }: HeadBlockProps) {
  const [open, setOpen] = useState(true);
  const label = trail.label && trail.label !== 'unknown' ? trail.label : 'Head';

  return (
    <div className="mb-3 rounded-xl border border-zinc-700 bg-zinc-800 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-zinc-750 hover:bg-zinc-700/50 transition-colors"
      >
        <span className="text-sm font-semibold text-purple-300">{label}</span>
        <span className="text-zinc-500 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div>
          {trail.sections.map((s, i) => (
            <TrailSection
              key={i}
              title={s.title}
              content={s.content}
              available={s.available}
              unavailableReason={s.unavailable_reason}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface Props {
  trail: HeadTrail[];
  onClose: () => void;
}

/**
 * Expandable per-head explainability trail.
 * Hidden by default — triggered by "Show me more" button.
 * One accordion block per head. Unavailable sections shown muted.
 */
export default function TrailAccordion({ trail, onClose }: Props) {
  return (
    <div className="mt-4 mx-1">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
          How we got here
        </h2>
        <button
          onClick={onClose}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          Close
        </button>
      </div>

      {trail.map((head, i) => (
        <HeadBlock key={i} trail={head} />
      ))}
    </div>
  );
}
