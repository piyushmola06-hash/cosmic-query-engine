import { useSessionStore, nextId } from '../store/sessionStore';
import * as api from '../api/client';

/**
 * Session lifecycle hook.
 * Handles start, query submission, trail fetch, and session end.
 */
export function useSession() {
  const store = useSessionStore();

  async function startSession() {
    store.setLoading(true);
    try {
      // Use a stable anonymous identifier for v0.1 (no auth system yet)
      const identifier = `web-${Date.now()}`;
      const res = await api.startSession(identifier);
      store.setSession(res.session_id, res.profile_found, res.profile_data);
      return res;
    } finally {
      store.setLoading(false);
    }
  }

  async function submitQuery(queryText: string) {
    const { sessionId } = store;
    if (!sessionId) return;

    store.setLoading(true);

    // Show per-head progress messages
    const heads = [
      { key: 'vedic',       label: 'Reading your Vedic chart...' },
      { key: 'western',     label: 'Calculating your Western chart...' },
      { key: 'numerology',  label: 'Computing your numerology...' },
      { key: 'chinese',     label: 'Consulting Chinese astrology...' },
      { key: 'philosophy',  label: 'Applying philosophical frameworks...' },
      { key: 'iching',      label: 'Consulting the I Ching...' },
      { key: 'synthesis',   label: 'Bringing it all together...' },
    ];

    for (const h of heads) {
      store.setCurrentHead(h.key);
      store.addMessage({ id: nextId(), role: 'progress', text: h.label });
      // Small visual delay between progress messages
      await new Promise((r) => setTimeout(r, 300));
    }

    try {
      const res = await api.query(sessionId, queryText);
      store.setSummary(res.summary, res.confidence_note ?? null, res.tendency_window ?? null);
      store.incrementQueryCount();
    } finally {
      store.setCurrentHead(null);
      store.setLoading(false);
    }
  }

  async function fetchTrail() {
    const { sessionId } = store;
    if (!sessionId) return;
    store.setLoading(true);
    try {
      const res = await api.getTrail(sessionId);
      if (res.rendered) {
        store.setTrail(res.trail);
        store.setShowTrail(true);
      }
    } finally {
      store.setLoading(false);
    }
  }

  async function endSession() {
    const { sessionId } = store;
    if (!sessionId) return null;
    try {
      return await api.endSession(sessionId);
    } finally {
      store.reset();
    }
  }

  return { startSession, submitQuery, fetchTrail, endSession };
}
