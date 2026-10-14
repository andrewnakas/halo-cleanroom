"""The coarse spectro-temporal outline of a sound, and shaping a clean sound to it.

Kept fact (owner's request 2026-10-10, "CC0 sounds modified to closely resemble the original"):
per permutation, the energy in 8 octave-wide bands over at most 64 time windows (never
shorter than ~46 ms), in 3 dB steps. It is the audio counterpart of the 4x4 colour grid of
a texture: where the sound is bright or dull and how it swells and dies, not its waveform.
No sample of the original is kept, and none can be rebuilt from it.

The clean room runs a CC0 sample (plus noise for what the sample lacks) through a bank of
the same bands and sets each band's level over time to the outline.
"""
import numpy as np
from scipy.signal import istft, stft

EDGES = (0, 150, 300, 600, 1200, 2400, 4800, 9600, 1e9)     # Hz
SEG, HOP = 512, 256
FLOOR = -72
MAX_WINDOWS = 64


def _power(x, rate):
    """STFT power (frames, bins) and the band of every bin"""
    x = np.asarray(x, np.float32)
    if len(x) < SEG:
        x = np.concatenate([x, np.zeros(SEG - len(x), np.float32)])
    f, _, z = stft(x, fs=rate, nperseg=SEG, noverlap=SEG - HOP, boundary="zeros", padded=True)
    band = np.searchsorted(np.asarray(EDGES[1:]), f, side="right").clip(0, len(EDGES) - 2)
    return z, band


def _windows(frames, count):
    return (np.arange(count + 1) * frames) // count


def measure(x, rate, count=None):
    """band energies in dB (windows, 8) of float samples -1..1"""
    z, band = _power(x, rate)
    p = (np.abs(z) ** 2).T                                   # (frames, bins)
    frames = p.shape[0]
    count = count or int(min(MAX_WINDOWS, max(1, frames // 4)))      # 4 hops ~ 46 ms at 22 kHz
    edges = _windows(frames, count)
    out = np.empty((count, len(EDGES) - 1), np.float32)
    for b in range(len(EDGES) - 1):
        pb = p[:, band == b].sum(1) if (band == b).any() else np.zeros(frames, np.float32)
        for i in range(count):
            out[i, b] = pb[edges[i]:max(edges[i + 1], edges[i] + 1)].mean()
    return 10 * np.log10(np.maximum(out, 1e-12))


def outline(pcm, rate):
    """the kept fact: [[8 ints] per window], dB in 3 dB steps, floored"""
    mono = np.asarray(pcm, np.float64)
    mono = mono.mean(1) if mono.ndim == 2 else mono
    db = measure(mono / 32768.0, rate)
    return np.maximum(FLOOR, 3 * np.round(db / 3)).astype(int).tolist()


def flatness(pcm):
    """0 (a pure tone) .. 1 (noise), one decimal: which kind of source suits the sound"""
    mono = np.asarray(pcm, np.float64)
    mono = mono.mean(1) if mono.ndim == 2 else mono
    if len(mono) < 64:
        return 1.0
    p = np.abs(np.fft.rfft(mono * np.hanning(len(mono)))) ** 2 + 1e-9
    p = p[1:]
    return round(float(np.exp(np.log(p).mean()) / p.mean()) ** 0.25, 1)


def _apply(x, gain_db, rate):
    """per window and band gains (dB) applied to x"""
    z, band = _power(x, rate)
    frames = z.shape[1]
    centres = (np.arange(len(gain_db)) + 0.5) * frames / len(gain_db)
    g = np.empty((frames, len(EDGES) - 1), np.float32)
    for b in range(len(EDGES) - 1):
        g[:, b] = np.interp(np.arange(frames), centres, gain_db[:, b])
    _, y = istft(z * (10 ** (g[:, band] / 20)).T, fs=rate, nperseg=SEG, noverlap=SEG - HOP, boundary=True)
    out = np.zeros(max(len(x), SEG), np.float32)
    m = min(len(y), len(out))
    out[:m] = y[:m]
    return out


def shape(x, target, rate, rng, steady=False, quiet=False):
    """x (float, any content) with every band's level over time set to the outline.
    Bands the source hardly holds are filled from noise, but only bands that matter in
    the sound (within 24 dB of its loudest band at that moment): a faint band made of
    noise is heard as static. steady (loops, ambience): the outline is smoothed over time
    first, so 3 dB steps between windows do not flutter (a fluttering hiss is static)."""
    target = np.asarray(target, np.float32)
    n = len(x)
    want = np.where(target <= FLOOR, -120.0, target)
    if steady and len(want) >= 3:
        from scipy.ndimage import gaussian_filter1d
        audible = want > -119
        smooth = gaussian_filter1d(np.where(audible, want, FLOOR), 2.0, axis=0, mode="wrap")
        want = np.where(audible, smooth, -120.0)
    source = np.asarray(x, np.float32)
    if len(source) < SEG:
        source = np.concatenate([source, np.zeros(SEG - len(source), np.float32)])
    # quiet: no noise anywhere and at most 12 dB of lift (a lifted band lifts the sample's own
    # noise floor with it: 30 dB of lift plus noise fill was heard as hiss and static)
    cap = 12.0 if quiet else 30.0
    lift = want - measure(source, rate, len(target))
    out = _apply(source, np.clip(lift, -120.0, cap), rate)
    # noise carries what the source could not reach, in the bands that carry the sound
    matters = want >= want.max(1, keepdims=True) - 24.0
    noise = rng.standard_normal(len(source)).astype(np.float32) * 0.05
    fill = np.where((lift > cap) & matters & (not quiet), want - measure(noise, rate, len(target)), -120.0)
    out = out + _apply(noise, fill, rate)
    # the gains glide between windows, which smears sharp attacks: correct once more
    # (downward freely, upward only a little: lifting a near-empty band lifts its noise)
    for _ in range(2):
        out = _apply(out, np.clip(want - measure(out, rate, len(target)), -24.0, 3.0 if quiet else 6.0 if steady else 12.0), rate)
    out = out[:n]
    # a few LSB of noise so silence is ours, and a soft ceiling
    return np.tanh(out * 1.1) / 1.1 + rng.normal(0, 4e-4, n).astype(np.float32)
