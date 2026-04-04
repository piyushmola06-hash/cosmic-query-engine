import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import type { InputHint } from '../api/client';

interface Props {
  inputHint: InputHint;
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const HINT_PLACEHOLDERS: Record<InputHint, string> = {
  free_text: 'Type your reply...',
  yes_no: 'Type yes or no, or use the buttons above...',
  date: 'e.g. 15 March 1990 or 15/03/1990...',
  location: 'Type a city name...',
};

/**
 * Text input + send button.
 * Never renders browser-native date or time pickers.
 * Sends on Enter (Shift+Enter for newline).
 */
export default function ChatInput({ inputHint, onSend, disabled = false, placeholder }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-focus when enabled
  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const ph = placeholder ?? HINT_PLACEHOLDERS[inputHint];

  return (
    <div className="flex items-end gap-2 p-3 bg-zinc-900 border-t border-zinc-700 rounded-b-xl">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={ph}
        className="
          flex-1 resize-none bg-zinc-800 text-zinc-100 rounded-xl
          px-3 py-2 text-sm leading-relaxed
          placeholder-zinc-500 border border-zinc-700
          focus:outline-none focus:border-purple-500
          disabled:opacity-40 max-h-36 overflow-y-auto
        "
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        aria-label="Send"
        className="
          flex-shrink-0 w-9 h-9 rounded-full
          bg-purple-600 hover:bg-purple-500
          disabled:opacity-40 disabled:cursor-not-allowed
          flex items-center justify-center
          transition-colors duration-150
        "
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-white">
          <path d="M3.105 3.105a.75.75 0 0 1 .815-.162l13.5 6a.75.75 0 0 1 0 1.314l-13.5 6A.75.75 0 0 1 2.75 15.5V11l8.5-1L2.75 9V4.5a.75.75 0 0 1 .355-.395z" />
        </svg>
      </button>
    </div>
  );
}
