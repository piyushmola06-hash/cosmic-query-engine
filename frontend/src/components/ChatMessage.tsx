import type { ChatMessage as ChatMessageType } from '../store/sessionStore';

interface Props {
  message: ChatMessageType;
}

/**
 * Single message bubble.
 * System messages: left-aligned, muted background.
 * User messages: right-aligned, accent background.
 * Progress messages: centered, italic, no bubble.
 */
export default function ChatMessage({ message }: Props) {
  const { role, text } = message;

  if (role === 'progress') {
    return (
      <div className="flex justify-center my-1">
        <span className="text-sm italic text-purple-400 opacity-80">{text}</span>
      </div>
    );
  }

  const isUser = role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`
          max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed
          ${isUser
            ? 'bg-purple-700 text-white rounded-br-sm'
            : 'bg-zinc-800 text-zinc-100 rounded-bl-sm'
          }
        `}
      >
        {text}
      </div>
    </div>
  );
}
