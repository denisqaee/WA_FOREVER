import zlib, struct
ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()"
REV = {c: i for i, c in enumerate(ALPHA)}

def decode_print(s):
    out = bytearray(); cache = 0; bits = 0
    for ch in s:
        cache |= REV[ch] << bits; bits += 6
        while bits >= 8:
            out.append(cache & 255); cache >>= 8; bits -= 8
    return bytes(out)

def encode_print(b):
    out = []; i = 0; n = len(b)
    while i + 2 < n:
        c = b[i] | b[i+1] << 8 | b[i+2] << 16; i += 3
        for _ in range(4): out.append(ALPHA[c & 63]); c >>= 6
    cache = 0; bl = 0
    while i < n: cache |= b[i] << bl; bl += 8; i += 1
    while bl > 0: out.append(ALPHA[cache & 63]); cache >>= 6; bl -= 6
    return "".join(out)

class R:
    def __init__(s, b): s.b = b; s.p = 0; s.sr = []; s.tr = []
    def byte(s): v = s.b[s.p]; s.p += 1; return v
    def int(s, n): v = int.from_bytes(s.b[s.p:s.p+n], 'big'); s.p += n; return v
    def raw(s, n): v = s.b[s.p:s.p+n]; s.p += n; return v
    def string(s, n):
        v = s.raw(n).decode('utf-8', 'replace')
        if n > 2: s.sr.append(v)
        return v
    def table(s, n, t=None):
        if t is None: t = {}; s.tr.append(t)
        for _ in range(n):
            k = s.obj(); t[k] = s.obj()
        return t
    def array(s, n, t=None):
        if t is None: t = {}; s.tr.append(t)
        for i in range(1, n+1): t[i] = s.obj()
        return t
    def mixed(s, a, m):
        t = {}; s.tr.append(t); s.array(a, t); s.table(m, t); return t
    def obj(s):
        v = s.byte()
        if v % 2 == 1: return (v - 1) // 2
        if v % 4 == 2:
            typ = (v - 2) // 4; cnt = typ // 4; typ %= 4
            if typ == 0: return s.string(cnt)
            if typ == 1: return s.table(cnt)
            if typ == 2: return s.array(cnt)
            return s.mixed(cnt % 4 + 1, cnt // 4 + 1)
        if v % 8 == 4:
            packed = s.byte() * 256 + v
            return -((packed - 12) // 16) if v % 16 == 12 else (packed - 4) // 16
        t = v // 8
        if t == 0: return None
        if t in (1,2): x = s.int(2); return x if t == 1 else -x
        if t in (3,4): x = s.int(3); return x if t == 3 else -x
        if t in (5,6): x = s.int(4); return x if t == 5 else -x
        if t in (7,8): x = s.int(7); return x if t == 7 else -x
        if t == 9: return struct.unpack('>d', s.raw(8))[0]
        if t in (10,11): x = float(s.raw(s.byte()).decode()); return x if t == 10 else -x
        if t == 12: return True
        if t == 13: return False
        if t == 14: return s.string(s.byte())
        if t == 15: return s.string(s.int(2))
        if t == 16: return s.string(s.int(3))
        if t == 17: return s.table(s.byte())
        if t == 18: return s.table(s.int(2))
        if t == 19: return s.table(s.int(3))
        if t == 20: return s.array(s.byte())
        if t == 21: return s.array(s.int(2))
        if t == 22: return s.array(s.int(3))
        if t == 23: a, m = s.byte(), s.byte(); return s.mixed(a, m)
        if t == 24: a, m = s.int(2), s.int(2); return s.mixed(a, m)
        if t == 25: a, m = s.int(3), s.int(3); return s.mixed(a, m)
        if t in (26,27,28): return s.sr[s.int({26:1,27:2,28:3}[t]) - 1]
        if t in (29,30,31): return s.tr[s.int({29:1,30:2,31:3}[t]) - 1]
        raise ValueError(t)

def decode(s):
    s = s.strip()
    body = s.split('!', 2)[2]
    raw = zlib.decompress(decode_print(body), -15)
    r = R(raw); ver = r.byte(); assert ver in (1, 2), ver
    return r.obj()

# ---- encoder ----
class W:
    def __init__(s): s.o = bytearray([1])
    def int_(s, n):
        if 0 <= n < 128: s.o.append(n * 2 + 1); return
        if -4096 < n < 4096:
            packed = n * 16 + 4 if n >= 0 else (-n) * 16 + 12
            s.o += bytes([packed & 255, packed >> 8]); return
        a = abs(n)
        for size, typ in ((2,1),(3,3),(4,5),(7,7)):
            if a < 256 ** size:
                s.o.append((typ + (0 if n >= 0 else 1)) * 8); s.o += a.to_bytes(size, 'big'); return
        raise ValueError(n)
    def obj(s, v):
        if v is None: s.o.append(0)
        elif v is True: s.o.append(96)
        elif v is False: s.o.append(104)
        elif isinstance(v, int): s.int_(v)
        elif isinstance(v, float):
            if v == int(v) and abs(v) < 2**53: s.int_(int(v))
            else:
                t = repr(abs(v)).encode(); s.o.append((10 if v >= 0 else 11) * 8); s.o.append(len(t)); s.o += t
        elif isinstance(v, str):
            b = v.encode('utf-8')
            if len(b) < 16: s.o.append((len(b) * 4 + 0) * 4 + 2)
            elif len(b) < 256: s.o.append(14 * 8); s.o.append(len(b))
            elif len(b) < 65536: s.o.append(15 * 8); s.o += len(b).to_bytes(2, 'big')
            else: s.o.append(16 * 8); s.o += len(b).to_bytes(3, 'big')
            s.o += b
        elif isinstance(v, (dict, list)):
            if isinstance(v, list): v = {i + 1: x for i, x in enumerate(v)}
            arr = []; i = 1
            while i in v and v[i] is not None: arr.append(v[i]); i += 1
            mp = [(k, x) for k, x in v.items() if not (isinstance(k, int) and 1 <= k <= len(arr)) and x is not None]
            a, m = len(arr), len(mp)
            def sized(base, *ns):
                mx = max(ns)
                size = 1 if mx < 256 else 2 if mx < 65536 else 3
                s.o.append((base + size - 1) * 8)
                for n_ in ns: s.o += n_.to_bytes(size, 'big')
            if a and m:
                if a <= 4 and m <= 4: s.o.append(((m - 1) * 4 + (a - 1)) * 16 + 3 * 4 + 2)
                else: sized(23, a, m)
            elif a:
                if a < 16: s.o.append((a * 4 + 2) * 4 + 2)
                else: sized(20, a)
            else:
                if m < 16: s.o.append((m * 4 + 1) * 4 + 2)
                else: sized(17, m)
            for x in arr: s.obj(x)
            for k, x in mp: s.obj(k); s.obj(x)
        else: raise TypeError(type(v))

def encode(t):
    w = W(); w.obj(t)
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return "!WA:2!" + encode_print(co.compress(bytes(w.o)) + co.flush())
