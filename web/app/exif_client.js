// The page's side of the ExifTool worker: one request at a time, each a
// promise. The worker owns the single Perl instance (two calls at once
// crash it), so this client never sends the next request before the
// previous answer arrives.

export class ExifClient {
  constructor(workerUrl) {
    this.worker = new Worker(workerUrl, { type: "module" });
    this.worker.onmessage = (event) => this._onMessage(event.data);
    this.worker.onerror = (event) => this._failAll(new Error(event.message || "the ExifTool worker failed"));
    this.queue = [];
    this.active = null;
    this.nextId = 1;
  }

  /**
   * Read one photo: name and bytes (the bytes are handed to the worker and
   * are unusable afterwards). Resolves with the worker's reply:
   * {ok, tags, preview} or {ok: false, error}.
   */
  read(name, bytes) {
    return new Promise((resolve, reject) => {
      this.queue.push({ id: this.nextId++, name, bytes, resolve, reject });
      this._next();
    });
  }

  _next() {
    if (this.active || !this.queue.length) return;
    this.active = this.queue.shift();
    const { id, name, bytes } = this.active;
    this.worker.postMessage({ id, type: "read", name, bytes }, [bytes.buffer]);
  }

  _onMessage(reply) {
    const request = this.active;
    if (!request || request.id !== reply.id) return;
    this.active = null;
    request.resolve(reply);
    this._next();
  }

  _failAll(error) {
    const requests = [this.active, ...this.queue].filter(Boolean);
    this.active = null;
    this.queue = [];
    for (const request of requests) request.reject(error);
  }

  /** Drop every request not yet sent (the one in progress still finishes). */
  cancelPending() {
    const waiting = this.queue;
    this.queue = [];
    for (const request of waiting) request.reject(new Error("cancelled"));
  }
}
