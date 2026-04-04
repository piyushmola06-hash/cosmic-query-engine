/**
 * Animated "computing" status indicator shown while heads run.
 */
export default function ProgressMessage({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 justify-center py-2">
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-bounce"
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </span>
      <span className="text-sm text-purple-300 italic">{text}</span>
    </div>
  );
}
