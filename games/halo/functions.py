"""Clean room: the engine's function textures (rasterizer/), computed from
their formulas. These are mathematical tables, not art: a normalization
cube map, a distance attenuation volume, a glow falloff, noise.

Where an orientation is not known (cube faces), every candidate is computed
and the one that agrees with the kept 4x4 grid is used.
"""
import numpy as np


def _grid(rgb):
    h, w, _ = rgb.shape
    ys, xs = (np.arange(5) * h) // 4, (np.arange(5) * w) // 4
    return np.array([[rgb[ys[j]:ys[j + 1], xs[i]:xs[i + 1]].reshape(-1, 3).mean(0) for i in range(4)] for j in range(4)])


def _face_dirs(n):
    """direction of every texel of the six D3D cube faces: (6, n, n, 3)"""
    t = (np.arange(n) + 0.5) / n * 2 - 1
    u, v = np.meshgrid(t, t)
    one = np.ones_like(u)
    faces = [(one, -v, -u), (-one, -v, u), (u, one, v), (u, -one, -v), (u, -v, one), (-u, -v, -one)]
    return np.stack([np.stack(f, -1) for f in faces])


def vector_normalization(name, tag, sk, index, im, face, base):
    n = im["w"]
    dirs = _face_dirs(n)
    rgb = (dirs / np.linalg.norm(dirs, axis=-1, keepdims=True)) * 127.5 + 127.5
    want = np.asarray(im["faces"][face]["grid"], np.float32).reshape(4, 4, 3)
    best, best_err = None, 1e18
    for f in range(6):
        for k in range(8):      # the eight symmetries of a face
            cand = np.rot90(rgb[f], k % 4)
            if k >= 4:
                cand = cand[:, ::-1]
            for order in ((0, 1, 2), (2, 1, 0), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1)):
                c = cand[..., order]
                err = float(((_grid(c) - want) ** 2).sum()) if n >= 4 else float(((c.mean((0, 1)) - want.mean((0, 1))) ** 2).sum())
                if err < best_err:
                    best, best_err = c, err
    out = np.full((n, n, 4), 255, np.float32)
    out[..., :3] = best
    return out


def glow(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    y, x = np.mgrid[0:h, 0:w]
    r = np.hypot(x - w / 2 + 0.5, y - h / 2 + 0.5) / (w / 2)
    v = np.clip(1 - r, 0, 1) ** 2 * 255
    return np.stack([v, v, v, v], -1).astype(np.float32)


def video_noise(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    rng = np.random.default_rng(7)
    mean = np.asarray(im["faces"][face]["grid"], np.float32).mean(0)
    n = rng.random((h, w, 1)).astype(np.float32)
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = np.clip(mean * (0.6 + 0.8 * n), 0, 255)
    out[..., 3] = rng.random((h, w)) * 255
    return out


def video_mask(name, tag, sk, index, im, face, base):
    w, h = im["w"], im["h"]
    y, x = np.mgrid[0:h, 0:w]
    dx, dy = np.abs(x - w / 2 + 0.5) - w * 0.3, np.abs(y - h / 2 + 0.5) - h * 0.36
    r = h * 0.08
    dist = np.hypot(np.maximum(dx + r, 0), np.maximum(dy + r, 0)) - r
    inside = np.clip(-dist / (h * 0.2), 0, 1)
    out = np.zeros((h, w, 4), np.float32)
    out[..., 1] = 110 * (dist <= 0)
    out[..., 0] = out[..., 2] = 80 * (dist <= 0)
    out[..., 3] = np.where(dist > 0, 255, 255 * (1 - inside) ** 2)
    return out


def distance_attenuation(w, h, d, z):
    """1 - r^2 from the middle of the volume, one slice"""
    y, x = np.mgrid[0:h, 0:w]
    r2 = ((x + 0.5) / w * 2 - 1) ** 2 + ((y + 0.5) / h * 2 - 1) ** 2 + ((z + 0.5) / d * 2 - 1) ** 2
    v = np.clip(1 - r2, 0, 1) * 255
    return np.stack([v, v, v, v], -1).astype(np.uint8)


VOLUMES = {"rasterizer/distance attenuation.bitmap": distance_attenuation}

DRAWERS = [
    (r"^rasterizer/vector normalization", vector_normalization),
    (r"^rasterizer/glow", glow),
    (r"^rasterizer/video noise", video_noise),
    (r"^rasterizer/video mask", video_mask),
]
