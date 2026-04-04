interface Props {
  options: string[];
  onSelect: (value: string) => void;
  disabled?: boolean;
}

/**
 * Yes/No quick-reply button pair.
 * Typed response is always accepted too — this is supplementary.
 */
export default function QuickReply({ options, onSelect, disabled = false }: Props) {
  return (
    <div className="flex gap-2 mt-2 mb-1">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onSelect(opt)}
          disabled={disabled}
          className="
            px-4 py-2 rounded-full text-sm font-medium
            border border-purple-500 text-purple-300
            hover:bg-purple-500 hover:text-white
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-colors duration-150
          "
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
