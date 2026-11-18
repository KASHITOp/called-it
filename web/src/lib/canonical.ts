// calledit-ledger-v1 canonicaliser: the JS twin of nowcaster/ledger/canonical.py.
//
// Both implementations are pinned by tests/fixtures/hash_vectors.json. Phase 5's browser
// "verify" button reuses this module, so it uses only Web Crypto and erasable TypeScript
// syntax (runs under Node 24 native type stripping and in the browser, no dependencies).
//
// Rules: a value is a string, an array of values, or a plain object whose keys match
// ^[a-z][a-z0-9_]*$. Numbers, booleans and null are rejected. String characters must be
// printable ASCII 0x20-0x7E excluding double quote (0x22) and backslash (0x5C), so
// JSON.stringify never escapes anything and the bytes equal Python's json.dumps output.

export type Canon = string | Canon[] | { [key: string]: Canon };

export const SCHEME = "calledit-ledger-v1";
export const GENESIS_PREV_HASH = "0".repeat(64);

const KEY_RE = /^[a-z][a-z0-9_]*$/;

export class CanonicalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CanonicalError";
  }
}

function checkString(value: string, path: string): void {
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code < 0x20 || code > 0x7e || code === 0x22 || code === 0x5c) {
      const hex = code.toString(16).toUpperCase().padStart(2, "0");
      throw new CanonicalError(`${path}: disallowed character 0x${hex}`);
    }
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

export function validate(value: unknown, path = "$"): asserts value is Canon {
  if (typeof value === "string") {
    checkString(value, path);
  } else if (Array.isArray(value)) {
    value.forEach((item, index) => validate(item, `${path}[${index}]`));
  } else if (isPlainObject(value)) {
    for (const key of Object.keys(value)) {
      if (!KEY_RE.test(key)) {
        throw new CanonicalError(`${path}: key must match ^[a-z][a-z0-9_]*$`);
      }
      validate(value[key], `${path}.${key}`);
    }
  } else {
    const kind = value === null ? "null" : typeof value;
    throw new CanonicalError(`${path}: ${kind} not allowed (strings only)`);
  }
}

function encode(value: Canon): string {
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(encode).join(",") + "]";
  // Keys are ASCII, so the default UTF-16 code-unit sort equals Python's code-point sort.
  const keys = Object.keys(value).sort();
  return "{" + keys.map((key) => JSON.stringify(key) + ":" + encode(value[key])).join(",") + "}";
}

export function canonicalize(value: unknown): string {
  validate(value);
  return encode(value);
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}
