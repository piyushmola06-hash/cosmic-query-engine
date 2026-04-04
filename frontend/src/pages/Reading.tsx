import { useEffect, useRef, useState } from 'react';
import { useSessionStore, nextId } from '../store/sessionStore';
import { useSession } from '../hooks/useSession';
import { useCollection } from '../hooks/useCollection';

import ChatMessage from '../components/ChatMessage';
import ChatInput from '../components/ChatInput';
import QuickReply from '../components/QuickReply';
import Summary from '../components/Summary';
import ConfidenceNote from '../components/ConfidenceNote';
import TrailAccordion from '../components/TrailAccordion';
import type { InputHint } from '../api/client';

const MAX_QUERIES = 3;

/**
 * Main reading page: chat + collection + reading output.
 * Collection conversation runs until collection_complete.
 * After collection: user submits their query to trigger all heads + synthesis.
 * No page refresh — session_id lives in Zustand store for the session lifetime.
 */
export default function Reading() {
  const store = useSessionStore();
  const { submitQuery, fetchTrail, endSession } = useSession();
  const { sendMessage } = useCollection();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [queryInput, setQueryInput] = useState('');
  const [sessionEnded, setSessionEnded] = useState(false);
  const [savePrompt, setSavePrompt] = useState<string | null>(null);
  const [isEndingSession, setIsEndingSession] = useState(false);

  // Inject the opening system message once on mount
  useEffect(() => {
    if (store.messages.length === 0 && store.sessionId) {
      store.addMessage({
        id: nextId(),
        role: 'system',
        text: "What's your question?",
        inputHint: 'free_text',
        quickReplies: null,
      });
    }
  }, [store.sessionId]);

  // Scroll to bottom whenever messages update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [store.messages, store.summary, store.showTrail]);

  // Determine the current input hint from the last system message
  const lastSystemMsg = [...store.messages].reverse().find((m) => m.role === 'system');
  const currentHint: InputHint = lastSystemMsg?.inputHint ?? 'free_text';
  const currentQuickReplies = lastSystemMsg?.quickReplies ?? null;

  async function handleCollectionSend(text: string) {
    await sendMessage(text);
  }

  async function handleQuerySend() {
    const q = queryInput.trim();
    if (!q) return;
    setQueryInput('');
    await submitQuery(q);
  }

  async function handleShowTrail() {
    await fetchTrail();
  }

  async function handleEndSession() {
    setIsEndingSession(true);
    try {
      const res = await endSession();
      if (res?.save_prompt) {
        setSavePrompt(res.save_prompt);
      }
      setSessionEnded(true);
    } finally {
      setIsEndingSession(false);
    }
  }

  const atQueryLimit = store.queryCount >= MAX_QUERIES;

  return (
    <div className="flex flex-col flex-1 w-full max-w-2xl mx-auto min-w-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <span className="text-sm font-medium text-zinc-300">Cosmic Query Engine</span>
        {store.summary && !sessionEnded && (
          <button
            onClick={handleEndSession}
            disabled={isEndingSession}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40"
          >
            {isEndingSession ? 'Ending...' : 'End session'}
          </button>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {store.messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {/* Quick replies shown after last system message, only during collection */}
        {!store.collectionComplete &&
          !store.isLoading &&
          currentQuickReplies &&
          currentQuickReplies.length > 0 && (
            <div className="flex justify-start pl-1">
              <QuickReply
                options={currentQuickReplies}
                onSelect={handleCollectionSend}
                disabled={store.isLoading}
              />
            </div>
          )}

        {/* Summary + confidence note */}
        {store.summary && (
          <>
            <Summary
              summary={store.summary}
              tendencyWindow={store.tendencyWindow}
              onShowTrail={handleShowTrail}
              isLoadingTrail={store.isLoading && store.trail === null}
            />
            {store.confidenceNote?.note_required && (
              <ConfidenceNote note={store.confidenceNote} />
            )}
          </>
        )}

        {/* Trail accordion */}
        {store.showTrail && store.trail && (
          <TrailAccordion
            trail={store.trail}
            onClose={() => store.setShowTrail(false)}
          />
        )}

        {/* Session ended state */}
        {sessionEnded && (
          <div className="mt-4 mx-1 p-4 rounded-xl bg-zinc-800 border border-zinc-700 text-sm text-zinc-300">
            {savePrompt ?? 'Your session has ended.'}
          </div>
        )}

        {/* Query limit reached */}
        {atQueryLimit && store.collectionComplete && !sessionEnded && (
          <div className="mt-4 mx-1 p-4 rounded-xl bg-zinc-800 border border-zinc-700 text-sm text-zinc-400">
            You've reached the maximum of {MAX_QUERIES} queries for this session.{' '}
            <button
              onClick={handleEndSession}
              className="text-purple-400 hover:text-purple-300 underline underline-offset-2"
            >
              End this session and start a new one
            </button>{' '}
            to ask another question.
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      {!sessionEnded && (
        <div className="border-t border-zinc-800">
          {!store.collectionComplete ? (
            // Collection phase: free text input driven by input_hint
            <ChatInput
              inputHint={currentHint}
              onSend={handleCollectionSend}
              disabled={store.isLoading}
            />
          ) : !store.summary && !store.isLoading ? (
            // Post-collection, pre-query: show query input
            <div className="flex items-end gap-2 p-3 bg-zinc-900 border-t border-zinc-700">
              <textarea
                rows={1}
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleQuerySend();
                  }
                }}
                placeholder="Ask your question..."
                className="
                  flex-1 resize-none bg-zinc-800 text-zinc-100 rounded-xl
                  px-3 py-2 text-sm leading-relaxed
                  placeholder-zinc-500 border border-zinc-700
                  focus:outline-none focus:border-purple-500 max-h-36 overflow-y-auto
                "
              />
              <button
                onClick={handleQuerySend}
                disabled={!queryInput.trim()}
                className="
                  flex-shrink-0 w-9 h-9 rounded-full bg-purple-600 hover:bg-purple-500
                  disabled:opacity-40 disabled:cursor-not-allowed
                  flex items-center justify-center transition-colors duration-150
                "
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-white">
                  <path d="M3.105 3.105a.75.75 0 0 1 .815-.162l13.5 6a.75.75 0 0 1 0 1.314l-13.5 6A.75.75 0 0 1 2.75 15.5V11l8.5-1L2.75 9V4.5a.75.75 0 0 1 .355-.395z" />
                </svg>
              </button>
            </div>
          ) : store.summary && !atQueryLimit && !sessionEnded ? (
            // Post-reading: allow follow-up queries
            <div className="flex items-end gap-2 p-3 bg-zinc-900 border-t border-zinc-700">
              <textarea
                rows={1}
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleQuerySend();
                  }
                }}
                disabled={store.isLoading}
                placeholder="Ask another question..."
                className="
                  flex-1 resize-none bg-zinc-800 text-zinc-100 rounded-xl
                  px-3 py-2 text-sm leading-relaxed
                  placeholder-zinc-500 border border-zinc-700
                  focus:outline-none focus:border-purple-500 max-h-36 overflow-y-auto
                  disabled:opacity-40
                "
              />
              <button
                onClick={handleQuerySend}
                disabled={store.isLoading || !queryInput.trim()}
                className="
                  flex-shrink-0 w-9 h-9 rounded-full bg-purple-600 hover:bg-purple-500
                  disabled:opacity-40 disabled:cursor-not-allowed
                  flex items-center justify-center transition-colors duration-150
                "
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-white">
                  <path d="M3.105 3.105a.75.75 0 0 1 .815-.162l13.5 6a.75.75 0 0 1 0 1.314l-13.5 6A.75.75 0 0 1 2.75 15.5V11l8.5-1L2.75 9V4.5a.75.75 0 0 1 .355-.395z" />
                </svg>
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
