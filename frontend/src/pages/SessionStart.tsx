import { useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { useSession } from '../hooks/useSession';
import type { ProfileData } from '../api/client';

interface Props {
  onStarted: () => void;
}

/**
 * Welcome screen and profile confirmation.
 * Shows profile confirmation if a saved profile is found.
 * Otherwise goes directly to the reading screen to begin collection.
 */
export default function SessionStart({ onStarted }: Props) {
  const { isLoading } = useSessionStore();
  const { startSession } = useSession();
  const [error, setError] = useState<string | null>(null);

  async function handleStart() {
    setError(null);
    try {
      await startSession();
      onStarted();
    } catch (e) {
      setError('Could not connect to the server. Please check your connection and try again.');
    }
  }

  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 py-12 min-w-0">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <h1 className="text-2xl font-semibold text-zinc-100 mb-2">Cosmic Query Engine</h1>
          <p className="text-zinc-400 text-sm leading-relaxed">
            Ask a question. We'll look at it through six different lenses and give you
            an honest picture of what they converge on.
          </p>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-red-950 border border-red-800 text-red-300 text-sm">
            {error}
          </div>
        )}

        <button
          onClick={handleStart}
          disabled={isLoading}
          className="
            w-full py-3 rounded-xl
            bg-purple-600 hover:bg-purple-500
            text-white font-medium text-sm
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150
          "
        >
          {isLoading ? 'Starting...' : 'Begin a reading'}
        </button>

        <p className="mt-6 text-center text-xs text-zinc-600">
          No account needed. Your birth data is only used to compute your reading.
        </p>
      </div>
    </div>
  );
}
