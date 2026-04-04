/**
 * API client — thin typed wrapper over fetch.
 * Base URL from VITE_API_URL env var, defaults to localhost:8000.
 * No API keys are used or stored on the frontend.
 */

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

// ── Response types ────────────────────────────────────────────────────────────

export interface StartSessionResponse {
  session_id: string;
  profile_found: boolean;
  profile_data: ProfileData | null;
  confirm_prompt: string | null;
}

export interface ProfileData {
  full_birth_name: string;
  dob: string;
  birth_time: string;
  birth_location: string;
  gender: string | null;
}

export type InputHint = 'free_text' | 'yes_no' | 'date' | 'location';

export interface CollectResponse {
  system_message: string;
  input_hint: InputHint;
  collection_complete: boolean;
  quick_replies: string[] | null;
}

export interface ConfidenceNote {
  note_required: boolean;
  note: string;
  affected_heads: string[];
  severity: 'minor' | 'major';
}

export interface TendencyWindow {
  composite_min_weeks: number;
  composite_max_weeks: number;
  contributing_heads: string[];
  expressed_as: string;
}

export interface QueryResponse {
  summary: string;
  confidence_note: ConfidenceNote | null;
  tendency_window: TendencyWindow | null;
  query_index: number;
}

export interface TrailSection {
  title: string;
  content: string;
  available: boolean;
  unavailable_reason?: string;
}

export interface HeadTrail {
  label: string;
  sections: TrailSection[];
}

export interface TrailResponse {
  rendered: boolean;
  trail: HeadTrail[];
}

export interface EndSessionResponse {
  save_prompt: string;
  session_status: string;
}

export interface ApiError {
  error: true;
  code: string;
  message: string;
  retry_safe: boolean;
}

// ── Internal fetch helper ─────────────────────────────────────────────────────

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const data = await res.json();

  if (!res.ok) {
    const err = data as ApiError;
    throw new Error(err.message ?? `Request failed: ${res.status}`);
  }

  return data as T;
}

// ── Public API ────────────────────────────────────────────────────────────────

export function startSession(userIdentifier: string): Promise<StartSessionResponse> {
  return post<StartSessionResponse>('/session/start/', { user_identifier: userIdentifier });
}

export function collect(sessionId: string, message: string): Promise<CollectResponse> {
  return post<CollectResponse>(`/session/${sessionId}/collect/`, { message });
}

export function query(sessionId: string, queryText: string): Promise<QueryResponse> {
  return post<QueryResponse>(`/session/${sessionId}/query/`, { query: queryText });
}

export function getTrail(sessionId: string): Promise<TrailResponse> {
  return post<TrailResponse>(`/session/${sessionId}/trail/`, { user_requested: true });
}

export function endSession(sessionId: string): Promise<EndSessionResponse> {
  return post<EndSessionResponse>(`/session/${sessionId}/end/`, {});
}
