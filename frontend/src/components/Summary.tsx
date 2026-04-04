import type { TendencyWindow } from '../api/client';

interface Props {
  summary: string;
  tendencyWindow: TendencyWindow | null;
  onShowTrail: () => void;
  isLoadingTrail: boolean;
}

/**
 * Reading output display.
 * Summary is always plain prose — no headers, bullets, or bold within the text.
 * Tendency window is woven into the prose by the backend; not a separate element here.
 */
export default function Summary({ summary, tendencyWindow, onShowTrail, isLoadingTrail }: Props) {
  return (
    <div className="mt-4 mx-1">
      <div className="bg-zinc-800 rounded-2xl p-5 border border-zinc-700">
        <p className="text-zinc-100 text-base leading-relaxed whitespace-pre-wrap">{summary}</p>

        {tendencyWindow && (
          <p className="mt-3 text-sm text-zinc-400 italic">
            Tendency window: {tendencyWindow.expressed_as}.
          </p>
        )}
      </div>

      <div className="mt-3 flex justify-end">
        <button
          onClick={onShowTrail}
          disabled={isLoadingTrail}
          className="
            text-sm text-purple-400 hover:text-purple-300
            underline underline-offset-2
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150
          "
        >
          {isLoadingTrail ? 'Loading...' : 'Show me more'}
        </button>
      </div>
    </div>
  );
}
