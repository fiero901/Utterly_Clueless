/*
 * JeevanRoute — browser-side local memory module
 * =================================================
 * Architecture:
 *   - localStorage  : tiny user prefs only (language, district, consent flag)
 *   - IndexedDB     : structured memories (preferences, user facts, episodic
 *                     memory) with optional local embeddings
 *   - Embeddings    : Transformers.js (Xenova/paraphrase-multilingual-MiniLM-L12-v2,
 *                     384-dim, multilingual incl. Nepali + English). The
 *                     runtime library loads from jsDelivr; the model weights +
 *                     tokenizer are served locally by app.py at /models, so no
 *                     huggingface.co access is needed. Lazy-loaded, cached in a
 *                     module-level variable.
 *   - Privacy       : ALL data stays on this device. Nothing is ever sent to a
 *                     server. Withdrawal of consent wipes everything.
 *
 * Exposed as window.jeevanMemory (plain object, async/await based).
 * No imports, no build step, no npm — single self-contained file, injected
 * into the Gradio page via gr.HTML.
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  const DB_NAME = "jeevanroute";
  const DB_VERSION = 1;
  const STORE_NAME = "memories";

  const PREF_KEYS = ["jr_language", "jr_district", "jr_consent", "jr_location_shared"];

  const MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
  const TRANSFORMERS_CDN = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2";

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------
  let pipeline = null; // cached transformers.js pipeline instance
  let pipelineLoading = null; // in-flight load promise (dedupes concurrent loads)
  let idbPromise = null; // in-flight IndexedDB open promise

  // ---------------------------------------------------------------------------
  // Prefs layer (localStorage)
  // ---------------------------------------------------------------------------
  function getPref(key) {
    try {
      if (PREF_KEYS.indexOf(key) === -1) return null;
      const raw = localStorage.getItem(key);
      if (raw === null) return null;
      if (key === "jr_consent" || key === "jr_location_shared") return raw === "true";
      return raw;
    } catch (err) {
      console.warn("[jeevanMemory] getPref failed:", err);
      return null;
    }
  }

  function setPref(key, value) {
    try {
      if (PREF_KEYS.indexOf(key) === -1) return false;
      const toStore =
        (key === "jr_consent" || key === "jr_location_shared")
          ? String(Boolean(value))
          : String(value);
      localStorage.setItem(key, toStore);
      return true;
    } catch (err) {
      console.warn("[jeevanMemory] setPref failed:", err);
      return false;
    }
  }

  function clearPrefs() {
    try {
      PREF_KEYS.forEach((k) => localStorage.removeItem(k));
    } catch (err) {
      console.warn("[jeevanMemory] clearPrefs failed:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // IndexedDB layer
  // ---------------------------------------------------------------------------
  function openDB() {
    if (idbPromise) return idbPromise;
    idbPromise = new Promise((resolve, reject) => {
      let req;
      try {
        req = indexedDB.open(DB_NAME, DB_VERSION);
      } catch (err) {
        reject(err);
        return;
      }
      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
          store.createIndex("by_key", "key", { unique: false });
          store.createIndex("by_created", "createdAt", { unique: false });
        }
      };
      req.onsuccess = (event) => {
        const db = event.target.result;
        db.onversionchange = () => db.close();
        resolve(db);
      };
      req.onerror = () => reject(req.error || new Error("IndexedDB open failed"));
      req.onblocked = () =>
        reject(new Error("IndexedDB open blocked by another connection"));
    });
    // Don't let a failed open poison future attempts.
    idbPromise.catch(() => {
      idbPromise = null;
    });
    return idbPromise;
  }

  function tx(db, mode) {
    return db.transaction(STORE_NAME, mode).objectStore(STORE_NAME);
  }

  function reqToPromise(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function idbGetAll() {
    const db = await openDB();
    const store = tx(db, "readonly");
    return reqToPromise(store.getAll());
  }

  async function idbPut(record) {
    const db = await openDB();
    const store = tx(db, "readwrite");
    return reqToPromise(store.put(record));
  }

  async function idbClear() {
    const db = await openDB();
    const store = tx(db, "readwrite");
    return reqToPromise(store.clear());
  }

  // ---------------------------------------------------------------------------
  // Embeddings (Transformers.js, lazy-loaded, graceful degradation)
  // ---------------------------------------------------------------------------
  async function loadPipeline() {
    if (pipeline) return pipeline;
    if (pipelineLoading) return pipelineLoading;

    pipelineLoading = (async () => {
      const transformers = await import(TRANSFORMERS_CDN);
      const pipe = await transformers.pipeline("feature-extraction", MODEL_ID, {
        dtype: "q8", // quantized: smaller download, fine for cosine similarity
        // Serve the model from our own app (./models, served at /models by
        // app.py) instead of huggingface.co — offline-friendly and avoids
        // external-CDN failures. The library appends the full model id
        // (e.g. "Xenova/paraphrase-multilingual-MiniLM-L12-v2/tokenizer.json").
        localModelPath: "./models",
      });
      pipeline = pipe;
      return pipeline;
    })();

    try {
      return await pipelineLoading;
    } finally {
      pipelineLoading = null;
    }
  }

  async function embed(text) {
    try {
      const pipe = await loadPipeline();
      const output = await pipe(String(text), {
        pooling: "mean",
        normalize: true,
      });
      // output is a Tensor; .data is a Float32Array
      const arr = output.data;
      return Array.isArray(arr) ? new Float32Array(arr) : arr;
    } catch (err) {
      console.warn(
        "[jeevanMemory] embedding unavailable (offline or model load failed):",
        err
      );
      return null;
    }
  }

  function cosineSimilarity(a, b) {
    if (!a || !b || a.length !== b.length || a.length === 0) return 0;
    let dot = 0;
    let normA = 0;
    let normB = 0;
    for (let i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }
    if (normA === 0 || normB === 0) return 0;
    return dot / (Math.sqrt(normA) * Math.sqrt(normB));
  }

  // ---------------------------------------------------------------------------
  // Memory API
  // ---------------------------------------------------------------------------
  function makeId() {
    const rand =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID().slice(0, 8)
        : Math.random().toString(36).slice(2, 10);
    return "mem_" + Date.now() + "_" + rand;
  }

  function defaultMetadata(metadata) {
    const m = metadata && typeof metadata === "object" ? metadata : {};
    return {
      source: m.source === "agent" ? "agent" : "user",
      sensitivity: m.sensitivity === "public" ? "public" : "personal",
    };
  }

  async function remember({ text, type, key, metadata } = {}) {
    try {
      if (typeof text !== "string" || text.trim() === "") return null;
      const now = new Date().toISOString();
      const record = {
        id: makeId(),
        type:
          type === "preference" || type === "user_fact" || type === "episodic"
            ? type
            : "episodic",
        key: typeof key === "string" && key !== "" ? key : null,
        text: text,
        embedding: null,
        metadata: defaultMetadata(metadata),
        createdAt: now,
        updatedAt: now,
      };
      // Embed best-effort; a failed embed must not block the memory write.
      record.embedding = await embed(record.text);
      await idbPut(record);
      return record;
    } catch (err) {
      console.warn("[jeevanMemory] remember failed:", err);
      return null;
    }
  }

  async function get(key) {
    try {
      if (typeof key !== "string" || key === "") return null;
      const all = await idbGetAll();
      // Most recent record wins for a given key.
      const matches = all.filter((r) => r.key === key);
      if (matches.length === 0) return null;
      matches.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
      return matches[0];
    } catch (err) {
      console.warn("[jeevanMemory] get failed:", err);
      return null;
    }
  }

  async function search(query, k = 5) {
    try {
      const all = await idbGetAll();
      if (all.length === 0) return [];
      const limit = Math.max(1, Math.floor(k) || 5);

      const queryVec =
        typeof query === "string" && query.trim() !== ""
          ? await embed(query)
          : null;

      if (!queryVec) {
        // No model available → recency-only fallback.
        return all
          .slice()
          .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
          .slice(0, limit)
          .map((r) => ({ ...r, score: 0 }));
      }

      const embedded = all.filter(
        (r) => r.embedding && r.embedding.length === queryVec.length
      );
      if (embedded.length === 0) {
        // Nothing is embedded yet (model wasn't ready when memories were
        // stored) → recency fallback instead of returning nothing.
        return all
          .slice()
          .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
          .slice(0, limit)
          .map((r) => ({ ...r, score: 0 }));
      }
      return embedded
        .map((r) => ({ ...r, score: cosineSimilarity(r.embedding, queryVec) }))
        .sort((a, b) => b.score - a.score)
        .slice(0, limit);
    } catch (err) {
      console.warn("[jeevanMemory] search failed:", err);
      return [];
    }
  }

  async function list() {
    try {
      const all = await idbGetAll();
      return all.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
    } catch (err) {
      console.warn("[jeevanMemory] list failed:", err);
      return [];
    }
  }

  async function clear() {
    try {
      await idbClear();
      clearPrefs();
      return true;
    } catch (err) {
      console.warn("[jeevanMemory] clear failed:", err);
      return false;
    }
  }

  // ---------------------------------------------------------------------------
  // Consent
  // ---------------------------------------------------------------------------
  function hasConsent() {
    return getPref("jr_consent") === true;
  }

  function giveConsent() {
    return setPref("jr_consent", true);
  }

  async function withdrawConsent() {
    setPref("jr_consent", false);
    return clear();
  }

  // ---------------------------------------------------------------------------
  // Status
  // ---------------------------------------------------------------------------
  async function status() {
    let count = 0;
    try {
      const all = await idbGetAll();
      count = all.length;
    } catch (err) {
      console.warn("[jeevanMemory] status failed:", err);
    }
    return {
      modelLoaded: pipeline !== null,
      memoryCount: count,
      consent: hasConsent(),
    };
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------
  window.jeevanMemory = {
    remember,
    get,
    search,
    list,
    clear,
    hasConsent,
    giveConsent,
    withdrawConsent,
    getPref,
    setPref,
    status,
  };
})();
