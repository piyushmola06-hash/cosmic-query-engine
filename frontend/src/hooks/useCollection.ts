import { useSessionStore, nextId } from '../store/sessionStore';
import * as api from '../api/client';

/**
 * Data collection conversation hook.
 * Sends one user message at a time to /collect, renders the system reply.
 * Never contains any knowledge of the S-01 question sequence — the backend drives all logic.
 */
export function useCollection() {
  const store = useSessionStore();

  async function sendMessage(text: string) {
    const { sessionId } = store;
    if (!sessionId) return;

    // Add the user's message to the chat
    store.addMessage({ id: nextId(), role: 'user', text });

    store.setLoading(true);
    try {
      const res = await api.collect(sessionId, text);

      store.addMessage({
        id: nextId(),
        role: 'system',
        text: res.system_message,
        inputHint: res.input_hint,
        quickReplies: res.quick_replies,
      });

      if (res.collection_complete) {
        store.setCollectionComplete(true);
      }
    } catch (err) {
      store.addMessage({
        id: nextId(),
        role: 'system',
        text: 'Something went wrong. Please try again.',
        inputHint: 'free_text',
        quickReplies: null,
      });
    } finally {
      store.setLoading(false);
    }
  }

  return { sendMessage };
}
