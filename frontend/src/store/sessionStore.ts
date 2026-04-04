import { create } from 'zustand';
import type { InputHint, ConfidenceNote, TendencyWindow, HeadTrail, ProfileData } from '../api/client';

// ── Message model ─────────────────────────────────────────────────────────────

export type MessageRole = 'system' | 'user' | 'progress';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  inputHint?: InputHint;
  quickReplies?: string[] | null;
}

// ── Store shape ───────────────────────────────────────────────────────────────

interface SessionState {
  sessionId: string | null;
  profileFound: boolean;
  profileData: ProfileData | null;
  messages: ChatMessage[];
  collectionComplete: boolean;
  isLoading: boolean;
  currentHead: string | null;
  summary: string | null;
  confidenceNote: ConfidenceNote | null;
  tendencyWindow: TendencyWindow | null;
  trail: HeadTrail[] | null;
  queryCount: number;
  showTrail: boolean;
}

interface SessionActions {
  setSession: (id: string, profileFound: boolean, profileData: ProfileData | null) => void;
  addMessage: (msg: ChatMessage) => void;
  updateLastSystemMessage: (text: string, inputHint?: InputHint, quickReplies?: string[] | null) => void;
  setCollectionComplete: (val: boolean) => void;
  setLoading: (val: boolean) => void;
  setCurrentHead: (head: string | null) => void;
  setSummary: (summary: string, note: ConfidenceNote | null, window: TendencyWindow | null) => void;
  setTrail: (trail: HeadTrail[]) => void;
  setShowTrail: (val: boolean) => void;
  incrementQueryCount: () => void;
  reset: () => void;
}

// ── Initial state ─────────────────────────────────────────────────────────────

const initialState: SessionState = {
  sessionId: null,
  profileFound: false,
  profileData: null,
  messages: [],
  collectionComplete: false,
  isLoading: false,
  currentHead: null,
  summary: null,
  confidenceNote: null,
  tendencyWindow: null,
  trail: null,
  queryCount: 0,
  showTrail: false,
};

// ── Store ─────────────────────────────────────────────────────────────────────

let msgCounter = 0;
function nextId(): string {
  return `msg-${++msgCounter}`;
}

export const useSessionStore = create<SessionState & SessionActions>((set) => ({
  ...initialState,

  setSession: (id, profileFound, profileData) =>
    set({ sessionId: id, profileFound, profileData }),

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  updateLastSystemMessage: (text, inputHint, quickReplies) =>
    set((s) => {
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'system') {
          msgs[i] = { ...msgs[i], text, inputHint, quickReplies };
          break;
        }
      }
      return { messages: msgs };
    }),

  setCollectionComplete: (val) => set({ collectionComplete: val }),

  setLoading: (val) => set({ isLoading: val }),

  setCurrentHead: (head) => set({ currentHead: head }),

  setSummary: (summary, note, window) =>
    set({ summary, confidenceNote: note, tendencyWindow: window }),

  setTrail: (trail) => set({ trail }),

  setShowTrail: (val) => set({ showTrail: val }),

  incrementQueryCount: () => set((s) => ({ queryCount: s.queryCount + 1 })),

  reset: () => set({ ...initialState }),
}));

export { nextId };
