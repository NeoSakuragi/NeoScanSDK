#!/usr/bin/env python3
"""The shared Player's accounts (TODO T2; tools/feedback/server.py "THE SHARED PLAYER"): hashes only, never a password.

    share_accounts.py make PLAIN_FILE OUT_JSON     PLAIN_FILE: "name<TAB or spaces>password" lines (# comments);
                                                   OUT_JSON = {name: {salt, hash}} (scrypt n=2^14 r=8 p=1), chmod 600
    share_accounts.py check OUT_JSON NAME          asks the password (no echo), says whether it matches

The plain file stays on brunux (/data/brawler-share/accounts.txt, chmod 600, out of the repo); OUT_JSON goes to the VPS
as /data/brawler/feedback/share/accounts.json (deploy: tools/feedback/deploy_vps.sh, then scp)."""
import getpass, hashlib, hmac, json, os, secrets, sys


def hash_pw(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=salt, n=1 << 14, r=8, p=1, dklen=32).hex()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == 'make':
        out = {}
        for ln in open(sys.argv[2]):
            ln = ln.strip()
            if not ln or ln.startswith('#'): continue
            name, pw = ln.split(None, 1)
            salt = secrets.token_bytes(16)
            out[name] = {'salt': salt.hex(), 'hash': hash_pw(pw.strip(), salt)}
        fd = os.open(sys.argv[3], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as o: json.dump(out, o, indent=1)
        print('%d accounts hashed into %s: %s' % (len(out), sys.argv[3], ', '.join(out)))
    elif len(sys.argv) == 4 and sys.argv[1] == 'check':
        a = json.load(open(sys.argv[2]))[sys.argv[3]]
        ok = hmac.compare_digest(hash_pw(getpass.getpass('password: '), bytes.fromhex(a['salt'])), a['hash'])
        print('match' if ok else 'NO match'); sys.exit(0 if ok else 1)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
