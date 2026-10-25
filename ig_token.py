#!/usr/bin/env python3
"""Keep the live Instagram token current without anyone editing GitHub secrets.

Instagram's weekly refresh can hand back a NEW long-lived token. A workflow can't
write that into the IG_TOKEN secret, so the new token is stored here, encrypted,
in ig_token.enc. The IG_TOKEN secret never changes and is only used as the key.

  python3 -I ig_token.py export   # in a workflow: masks the live token and sets IG_LIVE
  NEW_TOKEN=... python3 -I ig_token.py save   # encrypt NEW_TOKEN into ig_token.enc

If ig_token.enc is missing, or was made with a different IG_TOKEN (for example after
someone pastes a fresh token into the secret), the IG_TOKEN secret itself is used.
Standard library only: SHA-256 in counter mode for the keystream, HMAC-SHA256 for integrity.
"""
import base64, hashlib, hmac, json, os, secrets, sys, time

FILE = "ig_token.enc"


def keys(secret):
    k = hashlib.sha256(b"ig-token-v1|" + secret.encode()).digest()
    return hashlib.sha256(b"enc|" + k).digest(), hashlib.sha256(b"mac|" + k).digest()


def stream(key, nonce, n):
    out, i = b"", 0
    while len(out) < n:
        out += hashlib.sha256(key + nonce + i.to_bytes(8, "big")).digest()
        i += 1
    return out[:n]


def encrypt(secret, token):
    ek, mk = keys(secret)
    nonce = secrets.token_bytes(16)
    pt = token.encode()
    ct = bytes(a ^ b for a, b in zip(pt, stream(ek, nonce, len(pt))))
    mac = hmac.new(mk, nonce + ct, hashlib.sha256).digest()
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "nonce": b(nonce), "ct": b(ct), "mac": b(mac),
            "saved_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())}


def decrypt(secret, blob):
    ek, mk = keys(secret)
    d = lambda k: base64.b64decode(blob[k])
    nonce, ct, mac = d("nonce"), d("ct"), d("mac")
    if not hmac.compare_digest(mac, hmac.new(mk, nonce + ct, hashlib.sha256).digest()):
        return None
    return bytes(a ^ b for a, b in zip(ct, stream(ek, nonce, len(ct)))).decode()


def live_token(secret):
    if os.path.exists(FILE):
        try:
            tok = decrypt(secret, json.load(open(FILE)))
        except Exception:
            tok = None
        if tok:
            return tok, "ig_token.enc"
        print("::warning::ig_token.enc does not match the IG_TOKEN secret; using the secret itself.")
    return secret, "IG_TOKEN secret"


def main():
    secret = os.environ.get("IG_TOKEN", "").strip()
    if not secret:
        sys.exit("IG_TOKEN is not set")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export":
        tok, src = live_token(secret)
        print("::add-mask::" + tok)
        env = os.environ.get("GITHUB_ENV")
        if not env:
            sys.exit("GITHUB_ENV is not set (run this inside a workflow)")
        with open(env, "a") as f:
            f.write("IG_LIVE=" + tok + "\n")
        print("Live Instagram token loaded from the " + src)
    elif cmd == "save":
        new = os.environ.get("NEW_TOKEN", "").strip()
        if not new:
            sys.exit("NEW_TOKEN is not set")
        blob = encrypt(secret, new)
        assert decrypt(secret, blob) == new
        with open(FILE, "w") as f:
            json.dump(blob, f, indent=1)
            f.write("\n")
        print("Saved the new Instagram token to " + FILE + " (encrypted)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
