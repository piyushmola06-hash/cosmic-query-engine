import type { ConfidenceNote as ConfidenceNoteType } from '../api/client';

interface Props {
  note: ConfidenceNoteType;
}

/**
 * Muted note appearing below the summary when any head runs at reduced fidelity.
 * Visually quieter: smaller text, lower contrast.
 */
export default function ConfidenceNote({ note }: Props) {
  if (!note.note_required) return null;

  return (
    <div className="mx-1 mt-2 px-4 py-3 rounded-xl bg-zinc-900 border border-zinc-700">
      <p className="text-xs text-zinc-500 leading-relaxed">{note.note}</p>
    </div>
  );
}
