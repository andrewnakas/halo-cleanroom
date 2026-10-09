"""Pixel and sample codecs for Halo tags (numpy, no retail data).

DXT1/DXT3/DXT5 encode + decode (bitmap tags), Xbox ADPCM encode + decode
(sound tags: IMA ADPCM, 36-byte blocks per channel = 64 samples).

    python -m games.halo.codecs        # self-test: round trips, prints PSNR/SNR
"""
import numpy as np

# ---------- DXT


def _blocks(rgba):
    h, w, _ = rgba.shape
    ph, pw = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    if (ph, pw) != (h, w):
        rgba = np.pad(rgba, ((0, ph - h), (0, pw - w), (0, 0)), mode="edge")
    return rgba.reshape(ph // 4, 4, pw // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4), ph, pw


def _unblocks(b, h, w):
    ph, pw = (h + 3) // 4 * 4, (w + 3) // 4 * 4
    return b.reshape(ph // 4, pw // 4, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(ph, pw, 4)[:h, :w]


def _to565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.uint32)
    return ((c[..., 0] * 31 + 127) // 255) << 11 | ((c[..., 1] * 63 + 127) // 255) << 5 | ((c[..., 2] * 31 + 127) // 255)


def _from565(v):
    v = v.astype(np.uint32)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack([(r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31], -1).astype(np.float32)


def _color_block(px, punch):
    """px: (n,16,3) float, punch: (n,16) bool transparent (DXT1 alpha) -> (n,) u64 colour halves"""
    n = len(px)
    mean = px.mean(1, keepdims=True)
    cen = px - mean
    cov = np.einsum("nki,nkj->nij", cen, cen)
    axis = np.ones((n, 3), np.float32)
    for _ in range(6):  # power iteration: principal axis
        axis = np.einsum("nij,nj->ni", cov, axis)
        axis /= np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-6)
    t = np.einsum("nki,ni->nk", cen, axis)
    lo = mean[:, 0] + axis * t.min(1, keepdims=True)
    hi = mean[:, 0] + axis * t.max(1, keepdims=True)
    c0, c1 = _to565(hi), _to565(lo)
    any_punch = punch.any(1)
    # 4-colour mode needs c0 > c1, 3-colour (+transparent) needs c0 <= c1
    swap = np.where(any_punch, c0 > c1, c0 < c1)
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    four = ~any_punch
    eq = (c0 == c1) & four
    c1 = np.where(eq & (c0 > 0), c0 - 1, c1)
    c0 = np.where(eq & (c0 == 0), 1, c0)
    p0, p1 = _from565(c0), _from565(c1)
    pal4 = np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1)
    pal3 = np.stack([p0, p1, (p0 + p1) / 2, np.zeros_like(p0)], 1)
    pal = np.where(four[:, None, None], pal4, pal3)
    d = ((px[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)
    d[:, :, 3] = np.where(four[:, None], d[:, :, 3], np.inf)
    idx = d.argmin(-1)
    idx = np.where(punch, 3, idx).astype(np.uint64)
    bits = (idx << (2 * np.arange(16, dtype=np.uint64))).sum(1)
    return c0.astype(np.uint64) | c1.astype(np.uint64) << 16 | bits << 32


def encode_dxt(rgba, fmt):
    """rgba (h,w,4) uint8 -> bytes; fmt in dxt1, dxt3, dxt5"""
    b, _, _ = _blocks(np.asarray(rgba, np.uint8))
    px, a = b[..., :3].astype(np.float32), b[..., 3]
    if fmt == "dxt1":
        return _color_block(px, a < 128).astype("<u8").tobytes()
    col = _color_block(px, np.zeros(a.shape, bool))
    if fmt == "dxt3":
        q = (a.astype(np.uint64) * 15 + 127) // 255
        alpha = (q << (4 * np.arange(16, dtype=np.uint64))).sum(1)
    else:
        lo, hi = a.min(1).astype(np.float32), a.max(1).astype(np.float32)
        a0, a1 = hi, lo
        same = a0 == a1
        a0 = np.where(same & (a0 < 255), a0 + 1, a0)
        a1 = np.where(same & (a0 == a1), a1 - 1, a1)
        w = np.arange(8, dtype=np.float32)
        pal = np.stack([a0, a1] + [((7 - i) * a0 + i * a1) / 7 for i in range(1, 7)], 1)
        idx = np.abs(a[:, :, None].astype(np.float32) - pal[:, None, :]).argmin(-1).astype(np.uint64)
        alpha = a0.astype(np.uint64) | a1.astype(np.uint64) << 8 | \
            (idx << (16 + 3 * np.arange(16, dtype=np.uint64))).sum(1)
        del w
    out = np.empty((len(col), 2), "<u8")
    out[:, 0], out[:, 1] = alpha, col
    return out.tobytes()


def decode_dxt(data, w, h, fmt):
    bs = 8 if fmt == "dxt1" else 16
    n = ((h + 3) // 4) * ((w + 3) // 4)
    raw = np.frombuffer(data[:n * bs], "<u8").reshape(n, bs // 8)
    col = raw[:, -1]
    c0, c1 = (col & 0xFFFF), (col >> 16) & 0xFFFF
    p0, p1 = _from565(c0), _from565(c1)
    four = (c0 > c1) | (fmt != "dxt1")
    pal = np.where(four[:, None, None], np.stack([p0, p1, (2 * p0 + p1) / 3, (p0 + 2 * p1) / 3], 1),
                   np.stack([p0, p1, (p0 + p1) / 2, np.zeros_like(p0)], 1))
    idx = ((col[:, None] >> (32 + 2 * np.arange(16, dtype=np.uint64))) & 3).astype(np.int64)
    rgb = np.take_along_axis(pal, idx[..., None], 1)
    if fmt == "dxt1":
        a = np.where((~four[:, None]) & (idx == 3), 0, 255)
    elif fmt == "dxt3":
        a = ((raw[:, 0][:, None] >> (4 * np.arange(16, dtype=np.uint64))) & 15) * 17
    else:
        al = raw[:, 0]
        a0, a1 = (al & 255).astype(np.float32), ((al >> 8) & 255).astype(np.float32)
        big = a0 > a1
        pal_a = np.stack([a0, a1] + [np.where(big, ((7 - i) * a0 + i * a1) / 7,
                                              ((5 - i) * a0 + i * a1) / 5 if i < 5 else (0 if i == 5 else 255) + 0 * a0)
                                     for i in range(1, 7)], 1)
        ai = ((al[:, None] >> (16 + 3 * np.arange(16, dtype=np.uint64))) & 7).astype(np.int64)
        a = np.take_along_axis(pal_a, ai, 1)
    out = np.concatenate([rgb, np.asarray(a, np.float32)[..., None]], -1)
    return np.clip(np.rint(_unblocks(out, h, w)), 0, 255).astype(np.uint8)


# ---------- Xbox ADPCM (IMA, 36-byte blocks per channel, 64 samples each)

STEPS = np.array([
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88,
    97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
    724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660,
    4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818,
    18500, 20350, 22385, 24623, 27086, 29794, 32767])
INDEX = [-1, -1, -1, -1, 2, 4, 6, 8]


def _ima_step(pred, idx, code):
    step = int(STEPS[idx])
    diff = step >> 3
    if code & 4:
        diff += step
    if code & 2:
        diff += step >> 1
    if code & 1:
        diff += step >> 2
    pred = pred - diff if code & 8 else pred + diff
    pred = max(-32768, min(32767, pred))
    idx = max(0, min(88, idx + INDEX[code & 7]))
    return pred, idx


def encode_xbox_adpcm(pcm):
    """pcm (n, channels) int16 -> bytes; pads to 64-sample blocks"""
    pcm = np.asarray(pcm, np.int16)
    if pcm.ndim == 1:
        pcm = pcm[:, None]
    n, ch = pcm.shape
    blocks = (n + 63) // 64
    pcm = np.pad(pcm, ((0, blocks * 64 - n), (0, 0)))
    out = bytearray()
    state = [(int(pcm[0, c]), 0) for c in range(ch)]
    for b in range(blocks):
        seg = pcm[b * 64:(b + 1) * 64]
        heads, codes = [], []
        for c in range(ch):
            pred, idx = int(seg[0, c]), state[c][1]
            heads.append(np.array([pred], "<i2").tobytes() + bytes([idx, 0]))
            cs = []
            for s in seg[1:, c]:
                step = int(STEPS[idx])
                d = int(s) - pred
                code = 8 if d < 0 else 0
                d = abs(d)
                if d >= step:
                    code |= 4
                    d -= step
                if d >= step >> 1:
                    code |= 2
                    d -= step >> 1
                if d >= step >> 2:
                    code |= 1
                pred, idx = _ima_step(pred, idx, code)
                cs.append(code)
            cs.append(0)  # 63 coded samples + pad nibble
            state[c] = (pred, idx)
            codes.append(cs)
        out += b"".join(heads)
        for word in range(8):  # 8 words of 8 nibbles per channel, interleaved
            for c in range(ch):
                nib = codes[c][word * 8:(word + 1) * 8]
                out += bytes(nib[i] | nib[i + 1] << 4 for i in range(0, 8, 2))
    return bytes(out)


def decode_xbox_adpcm(data, channels):
    bsz = 36 * channels
    blocks = len(data) // bsz
    out = np.zeros((blocks * 64, channels), np.int16)
    for b in range(blocks):
        blk = data[b * bsz:(b + 1) * bsz]
        preds, idxs = [], []
        for c in range(channels):
            preds.append(int(np.frombuffer(blk[4 * c:4 * c + 2], "<i2")[0]))
            idxs.append(blk[4 * c + 2])
            out[b * 64, c] = preds[c]
        pos = [1] * channels
        body = blk[4 * channels:]
        for word in range(8):
            for c in range(channels):
                chunk = body[(word * channels + c) * 4:(word * channels + c) * 4 + 4]
                for byte in chunk:
                    for code in (byte & 15, byte >> 4):
                        if pos[c] < 64:
                            preds[c], idxs[c] = _ima_step(preds[c], idxs[c], code)
                            out[b * 64 + pos[c], c] = preds[c]
                            pos[c] += 1
    return out


def _selftest():
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:64, 0:48]
    img = np.stack([xx * 5, yy * 4, (xx + yy) * 2, (xx * 5) % 256], -1).astype(np.uint8)
    img += rng.integers(0, 6, img.shape, dtype=np.uint8)
    for fmt in ("dxt1", "dxt3", "dxt5"):
        src = img.copy()
        if fmt == "dxt1":
            src[..., 3] = np.where(src[..., 3] > 128, 255, 0)
        dec = decode_dxt(encode_dxt(src, fmt), 48, 64, fmt)
        keep = src[..., 3] >= 128 if fmt == "dxt1" else np.ones(src.shape[:2], bool)
        err = ((dec[..., :3].astype(float) - src[..., :3]) ** 2)[keep].mean()
        rgb = 10 * np.log10(255 ** 2 / max(err, 1e-9))
        aerr = np.abs(dec[..., 3].astype(int) - src[..., 3]).max()
        print(f"{fmt}: rgb PSNR {rgb:.1f} dB, alpha max err {aerr}")
    t = np.arange(4000) / 22050
    pcm = np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 300 * t)], -1) * 12000
    pcm = pcm.astype(np.int16)
    enc = encode_xbox_adpcm(pcm)
    dec = decode_xbox_adpcm(enc, 2)[:len(pcm)]
    snr = 10 * np.log10((pcm.astype(float) ** 2).mean() / ((dec.astype(float) - pcm) ** 2).mean())
    print(f"xbox adpcm: {len(enc)} bytes for {len(pcm)} stereo samples ({len(enc) / 72:.0f} blocks), SNR {snr:.1f} dB")


if __name__ == "__main__":
    _selftest()
