/**
 * The user's rating of wizi's replies (`/api/projects/{id}/feedback`, spec 09, after Kanya's CH-1228). One rating per
 * reply; the reply is known by the SHA-256 of its text (`replyHash`), so a rating is found again after a reload.
 *
 * Kanya's version uses React Query; itos has no data library, so these hooks keep the same names and shape with a
 * small shared cache per project: every reply row reads it, and a change reloads it for all of them.
 */
import { useCallback, useEffect, useState } from "react";

export type Rating = "good" | "bad";

export interface RatingRow {
  reply_hash: string;
  rating: Rating;
  reasons: string[];
}

/** The reasons a reply can be bad, in the order the form shows them. */
export const REASONS: { id: string; label: string }[] = [
  { id: "not_accurate", label: "Not accurate" },
  { id: "not_followed", label: "Didn't follow what I asked" },
  { id: "too_long", label: "Too long" },
  { id: "too_short", label: "Too short" },
  { id: "unsafe", label: "Unsafe or inappropriate" },
  { id: "other", label: "Something else" },
];

export interface RateBody {
  rating: Rating;
  reply: string;
  prompt?: string;
  reasons?: string[];
  note?: string;
}

const cache = new Map<string, Promise<RatingRow[]>>();
const listeners = new Map<string, Set<() => void>>();

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Could not save the rating (${response.status}).`);
  }
  return response;
}

function load(projectId: string): Promise<RatingRow[]> {
  let pending = cache.get(projectId);
  if (!pending) {
    pending = request(`/api/projects/${projectId}/feedback`)
      .then((response) => response.json())
      .then((body: { ratings: RatingRow[] }) => body.ratings);
    cache.set(projectId, pending);
    pending.catch(() => cache.delete(projectId));
  }
  return pending;
}

function changed(projectId: string): void {
  cache.delete(projectId);
  listeners.get(projectId)?.forEach((listener) => listener());
}

export function useRatings(projectId: string): { data: RatingRow[] | undefined } {
  const [data, setData] = useState<RatingRow[]>();
  useEffect(() => {
    let live = true;
    const refresh = () =>
      void load(projectId)
        .then((rows) => live && setData(rows))
        .catch(() => undefined);
    refresh();
    const set = listeners.get(projectId) ?? new Set();
    set.add(refresh);
    listeners.set(projectId, set);
    return () => {
      live = false;
      set.delete(refresh);
    };
  }, [projectId]);
  return { data };
}

interface Action<T> {
  mutate: (value: T, options?: { onSuccess?: () => void }) => void;
  isPending: boolean;
  isSuccess: boolean;
  error: unknown;
}

function useAction<T>(projectId: string, run: (value: T) => Promise<unknown>): Action<T> {
  const [state, setState] = useState<{ isPending: boolean; isSuccess: boolean; error: unknown }>({
    isPending: false,
    isSuccess: false,
    error: null,
  });
  const mutate = useCallback(
    (value: T, options?: { onSuccess?: () => void }) => {
      setState({ isPending: true, isSuccess: false, error: null });
      run(value)
        .then(() => {
          setState({ isPending: false, isSuccess: true, error: null });
          changed(projectId);
          options?.onSuccess?.();
        })
        .catch((error: unknown) => setState({ isPending: false, isSuccess: false, error }));
    },
    [projectId, run],
  );
  return { mutate, ...state };
}

export function useRate(projectId: string): Action<RateBody> {
  const run = useCallback(
    (body: RateBody) =>
      request(`/api/projects/${projectId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    [projectId],
  );
  return useAction(projectId, run);
}

export function useWithdraw(projectId: string): Action<string> {
  const run = useCallback(
    (hash: string) => request(`/api/projects/${projectId}/feedback/${hash}`, { method: "DELETE" }),
    [projectId],
  );
  return useAction(projectId, run);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}
