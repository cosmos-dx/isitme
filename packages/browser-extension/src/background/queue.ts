// Persistent offline event queue. Survives service-worker suspension by living
// in chrome.storage.local. Drops oldest events past a cap so memory/storage
// can't grow unbounded while offline.
import type { RawEvent } from "../common/types";

const QUEUE_KEY = "isitme.queue";

export class EventQueue {
  private maxSize: number;

  constructor(maxSize: number) {
    this.maxSize = maxSize;
  }

  setMaxSize(n: number): void {
    this.maxSize = n;
  }

  async all(): Promise<RawEvent[]> {
    const raw = await chrome.storage.local.get(QUEUE_KEY);
    return (raw[QUEUE_KEY] as RawEvent[] | undefined) ?? [];
  }

  async size(): Promise<number> {
    return (await this.all()).length;
  }

  async enqueue(events: RawEvent[]): Promise<number> {
    if (events.length === 0) return this.size();
    let queue = await this.all();
    queue.push(...events);
    if (queue.length > this.maxSize) {
      queue = queue.slice(queue.length - this.maxSize);
    }
    await chrome.storage.local.set({ [QUEUE_KEY]: queue });
    return queue.length;
  }

  /** Peek the head of the queue without removing it. */
  async peek(limit: number): Promise<RawEvent[]> {
    const queue = await this.all();
    return queue.slice(0, limit);
  }

  /** Remove the first `count` events (after a successful send). */
  async drop(count: number): Promise<number> {
    const queue = await this.all();
    const remaining = queue.slice(count);
    await chrome.storage.local.set({ [QUEUE_KEY]: remaining });
    return remaining.length;
  }

  async clear(): Promise<void> {
    await chrome.storage.local.set({ [QUEUE_KEY]: [] });
  }
}
