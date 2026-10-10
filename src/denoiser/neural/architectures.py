"""Ricostruzione in ONNX delle reti DRUNet e SCUNet a partire dai pesi originali.

Le architetture seguono fedelmente il codice ufficiale:
- DRUNet: KAIR, ``models/network_unet.py`` (UNetRes), licenza MIT, © Kai Zhang;
- SCUNet: ``models/network_scunet.py`` del repository SCUNet, licenza Apache 2.0, © Kai Zhang.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import onnx

from .graph import GraphBuilder

StateDict = Mapping[str, np.ndarray]


def _count(sd: StateDict, prefix: str, suffix: str) -> int:
    """Numero di blocchi ``prefix.<i>suffix`` presenti nei pesi."""
    n = 0
    while f"{prefix}.{n}{suffix}" in sd:
        n += 1
    return n


# ============================================================================ DRUNet


def build_drunet(sd: StateDict) -> onnx.ModelProto:
    """Input: (1, 4, H, W) = RGB in [0, 1] + mappa del livello di rumore; H, W multipli di 8."""
    g = GraphBuilder()

    def bias(key: str):
        return sd.get(key.replace(".weight", ".bias"))

    def conv3(x: str, key: str) -> str:
        return g.conv(x, sd[key], bias(key), stride=1, pad=1)

    def resblock(x: str, prefix: str) -> str:
        y = g.relu(conv3(x, f"{prefix}.res.0.weight"))
        y = conv3(y, f"{prefix}.res.2.weight")
        return g.add(x, y)

    def down(x: str, name: str) -> str:
        nb = _count(sd, name, ".res.0.weight")
        for i in range(nb):
            x = resblock(x, f"{name}.{i}")
        key = f"{name}.{nb}.weight"
        return g.conv(x, sd[key], bias(key), stride=2, pad=0)

    def up(x: str, name: str) -> str:
        x = g.conv_transpose(x, sd[f"{name}.0.weight"], stride=2)
        i = 1
        while f"{name}.{i}.res.0.weight" in sd:
            x = resblock(x, f"{name}.{i}")
            i += 1
        return x

    x1 = conv3("input", "m_head.weight")
    x2 = down(x1, "m_down1")
    x3 = down(x2, "m_down2")
    x4 = down(x3, "m_down3")
    x = x4
    for i in range(_count(sd, "m_body", ".res.0.weight")):
        x = resblock(x, f"m_body.{i}")
    x = up(g.add(x, x4), "m_up3")
    x = up(g.add(x, x3), "m_up2")
    x = up(g.add(x, x2), "m_up1")
    out = conv3(g.add(x, x1), "m_tail.weight")
    out = g.op("Identity", [out])
    in_channels = sd["m_head.weight"].shape[1]
    return g.build([("input", [1, in_channels, "H", "W"])], out, "drunet")


# ============================================================================ SCUNet

_WINDOW = 8
_HEAD_DIM = 32


def relative_position_bias(params: np.ndarray, window: int = _WINDOW) -> np.ndarray:
    """(teste, 2p-1, 2p-1) -> (teste, p*p, p*p), come WMSA.relative_embedding."""
    cord = np.array([[i, j] for i in range(window) for j in range(window)])
    relation = cord[:, None, :] - cord[None, :, :] + window - 1
    return params[:, relation[:, :, 0], relation[:, :, 1]].astype(np.float32)


def shifted_window_mask(h_windows: int, w_windows: int, window: int = _WINDOW) -> np.ndarray:
    """Maschera additiva (1, 1, finestre, p*p, p*p), come WMSA.generate_mask per le finestre spostate."""
    p = window
    s = p - window // 2
    mask = np.zeros((h_windows, w_windows, p, p, p, p), dtype=bool)
    mask[-1, :, :s, :, s:, :] = True
    mask[-1, :, s:, :, :s, :] = True
    mask[:, -1, :, :s, :, s:] = True
    mask[:, -1, :, s:, :, :s] = True
    mask = mask.reshape(h_windows * w_windows, p * p, p * p)[None, None]
    return np.where(mask, -1e9, 0.0).astype(np.float32)


def _wmsa(g: GraphBuilder, x: str, sd: StateDict, prefix: str, h: int, w: int, c: int, shifted: bool) -> str:
    """Attenzione a finestre (Swin) su x di forma (1, h, w, c)."""
    p = _WINDOW
    heads = c // _HEAD_DIM
    hw, ww = h // p, w // p
    nw, npix = hw * ww, p * p
    shift = p // 2
    if shifted:
        x = g.roll(g.roll(x, -shift, 1, h), -shift, 2, w)
    x = g.reshape(x, [1, hw, p, ww, p, c])
    x = g.transpose(x, [0, 1, 3, 2, 4, 5])
    x = g.reshape(x, [1, nw, npix, c])
    qkv = g.linear(x, sd[f"{prefix}.embedding_layer.weight"], sd[f"{prefix}.embedding_layer.bias"])
    qkv = g.reshape(qkv, [1, nw, npix, 3 * heads, _HEAD_DIM])
    qkv = g.transpose(qkv, [3, 0, 1, 2, 4])  # (3*teste, 1, nw, np, hd)
    q, k, v = g.op("Split", [qkv, g.ints([heads, heads, heads])], n_out=3, axis=0)
    kt = g.transpose(k, [0, 1, 2, 4, 3])
    sim = g.mul(g.op("MatMul", [q, kt]), g.const(_HEAD_DIM**-0.5, "scale"))
    bias = relative_position_bias(sd[f"{prefix}.relative_position_params"])[:, None, None]
    sim = g.add(sim, g.const(bias, "relpos"))
    if shifted:
        sim = g.add(sim, g.const(shifted_window_mask(hw, ww), "mask"))
    probs = g.op("Softmax", [sim], axis=-1)
    out = g.op("MatMul", [probs, v])  # (teste, 1, nw, np, hd)
    out = g.transpose(out, [1, 2, 3, 0, 4])
    out = g.reshape(out, [1, nw, npix, c])
    out = g.linear(out, sd[f"{prefix}.linear.weight"], sd[f"{prefix}.linear.bias"])
    out = g.reshape(out, [1, hw, ww, p, p, c])
    out = g.transpose(out, [0, 1, 3, 2, 4, 5])
    out = g.reshape(out, [1, h, w, c])
    if shifted:
        out = g.roll(g.roll(out, shift, 1, h), shift, 2, w)
    return out


def swin_block(g: GraphBuilder, x: str, sd: StateDict, prefix: str, h: int, w: int, c: int, shifted: bool) -> str:
    """Block di SCUNet su (1, h, w, c)."""
    y = g.layer_norm(x, sd[f"{prefix}.ln1.weight"], sd[f"{prefix}.ln1.bias"])
    x = g.add(x, _wmsa(g, y, sd, f"{prefix}.msa", h, w, c, shifted))
    y = g.layer_norm(x, sd[f"{prefix}.ln2.weight"], sd[f"{prefix}.ln2.bias"])
    y = g.gelu(g.linear(y, sd[f"{prefix}.mlp.0.weight"], sd[f"{prefix}.mlp.0.bias"]))
    y = g.linear(y, sd[f"{prefix}.mlp.2.weight"], sd[f"{prefix}.mlp.2.bias"])
    return g.add(x, y)


def _conv_trans_block(g: GraphBuilder, x: str, sd: StateDict, prefix: str, h: int, w: int, shifted: bool) -> str:
    w11 = sd[f"{prefix}.conv1_1.weight"]
    total = w11.shape[0]
    trans_dim = sd[f"{prefix}.trans_block.ln1.weight"].shape[0]
    conv_dim = total - trans_dim
    y = g.conv(x, w11, sd[f"{prefix}.conv1_1.bias"])
    conv_x, trans_x = g.op("Split", [y, g.ints([conv_dim, trans_dim])], n_out=2, axis=1)
    c = g.relu(g.conv(conv_x, sd[f"{prefix}.conv_block.0.weight"], pad=1))
    c = g.conv(c, sd[f"{prefix}.conv_block.2.weight"], pad=1)
    conv_x = g.add(c, conv_x)
    t = g.transpose(trans_x, [0, 2, 3, 1])
    t = swin_block(g, t, sd, f"{prefix}.trans_block", h, w, trans_dim, shifted)
    t = g.transpose(t, [0, 3, 1, 2])
    res = g.conv(g.op("Concat", [conv_x, t], axis=1), sd[f"{prefix}.conv1_2.weight"], sd[f"{prefix}.conv1_2.bias"])
    return g.add(x, res)


def build_scunet(sd: StateDict, size: int) -> onnx.ModelProto:
    """Input: (1, 3, size, size) RGB in [0, 1]; ``size`` multiplo di 64 (le finestre sono fisse)."""
    if size % 64:
        raise ValueError("La dimensione del tassello per SCUNet deve essere multipla di 64")
    g = GraphBuilder()

    def stage(x: str, name: str, first: int, count: int, res: int) -> str:
        # Come nel codice originale: blocchi pari a finestre fisse, dispari a finestre spostate
        # (input_resolution di costruzione = 256, sempre maggiore della finestra).
        for i in range(count):
            x = _conv_trans_block(g, x, sd, f"{name}.{first + i}", res, res, shifted=bool(i % 2))
        return x

    def n_blocks(name: str, first: int) -> int:
        n = 0
        while f"{name}.{first + n}.conv1_1.weight" in sd:
            n += 1
        return n

    x1 = g.conv("input", sd["m_head.0.weight"], pad=1)
    n = n_blocks("m_down1", 0)
    x = stage(x1, "m_down1", 0, n, size)
    x2 = g.conv(x, sd[f"m_down1.{n}.weight"], stride=2)
    n = n_blocks("m_down2", 0)
    x = stage(x2, "m_down2", 0, n, size // 2)
    x3 = g.conv(x, sd[f"m_down2.{n}.weight"], stride=2)
    n = n_blocks("m_down3", 0)
    x = stage(x3, "m_down3", 0, n, size // 4)
    x4 = g.conv(x, sd[f"m_down3.{n}.weight"], stride=2)
    x = stage(x4, "m_body", 0, n_blocks("m_body", 0), size // 8)
    x = g.conv_transpose(g.add(x, x4), sd["m_up3.0.weight"], stride=2)
    x = stage(x, "m_up3", 1, n_blocks("m_up3", 1), size // 4)
    x = g.conv_transpose(g.add(x, x3), sd["m_up2.0.weight"], stride=2)
    x = stage(x, "m_up2", 1, n_blocks("m_up2", 1), size // 2)
    x = g.conv_transpose(g.add(x, x2), sd["m_up1.0.weight"], stride=2)
    x = stage(x, "m_up1", 1, n_blocks("m_up1", 1), size)
    out = g.conv(g.add(x, x1), sd["m_tail.0.weight"], pad=1)
    out = g.op("Identity", [out])
    return g.build([("input", [1, 3, size, size])], out, "scunet")
