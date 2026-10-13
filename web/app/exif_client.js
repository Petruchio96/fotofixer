// The page's side of the worker. ExifTool requests (read, write) go one at
// a time: the worker owns the single Perl instance, and two calls at once
// crash it. Python requests (coordinate parsing through Pyodide) don't
// touch ExifTool, so they are sent straight away and answered while a
// read or write is in progress.

export class ExifClient {
  constructor(workerUrl) {
    this.worker = new Worker(workerUrl, { type: "module" });
    this.worker.onmessage = (event) => this._onMessage(event.data);
    this.worker.onerror = (event) => this._failAll(new Error(event.message || "the worker failed"));
    this.queue = []; // ExifTool requests waiting
    this.active = null; // the ExifTool request in progress
    this.pending = new Map(); // id -> {resolve, reject} for every request sent
    this.nextId = 1;
    this.onPythonReady = null; // called once Pyodide and the modules are loaded
  }

  /**
   * Read one photo: name and bytes (the bytes are handed to the worker and
   * are unusable afterwards). Resolves with {ok, tags, preview} or
   * {ok: false, error}.
   */
  read(name, bytes) {
    return this._enqueue({ type: "read", name, bytes }, [bytes.buffer]);
  }

  /**
   * Write GPS (gps = {latitude, longitude}) or clear it (gps = null) into a
   * copy of the photo. Resolves with {ok, bytes} (the new file) or
   * {ok: false, error}. The input bytes are handed to the worker.
   */
  write(name, bytes, gps) {
    return this._enqueue({ type: "write", name, bytes, gps }, [bytes.buffer]);
  }

  /**
   * Coordinate parsing in Python: op "pair" (text -> [lat, lon] strings or
   * null), "manual" (lat, lon texts -> [lat, lon] numbers or null),
   * "latitude" / "longitude" (text -> number, or an error).
   * Resolves with {ok, result} or {ok: false, error}.
   */
  parse(op, a, b = null) {
    return this._send({ type: "parse", op, a, b });
  }

  _send(message, transfer = []) {
    return new Promise((resolve, reject) => {
      const id = this.nextId++;
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, ...message }, transfer);
    });
  }

  _enqueue(message, transfer) {
    return new Promise((resolve, reject) => {
      this.queue.push({ message, transfer, resolve, reject });
      this._next();
    });
  }

  _next() {
    if (this.active || !this.queue.length) return;
    const request = this.queue.shift();
    const id = this.nextId++;
    this.active = { id, ...request };
    this.pending.set(id, { resolve: request.resolve, reject: request.reject });
    this.worker.postMessage({ id, ...request.message }, request.transfer);
  }

  _onMessage(reply) {
    if (reply.type === "python-ready") {
      this.onPythonReady?.(reply);
      return;
    }
    const waiting = this.pending.get(reply.id);
    if (!waiting) return;
    this.pending.delete(reply.id);
    if (this.active?.id === reply.id) {
      this.active = null;
      this._next();
    }
    waiting.resolve(reply);
  }

  _failAll(error) {
    const all = [...this.pending.values(), ...this.queue];
    this.pending.clear();
    this.queue = [];
    this.active = null;
    for (const request of all) request.reject(error);
  }

  /** Drop every ExifTool request not yet sent (the one in progress still finishes). */
  cancelPending() {
    const waiting = this.queue;
    this.queue = [];
    for (const request of waiting) request.reject(new Error("cancelled"));
  }
}
