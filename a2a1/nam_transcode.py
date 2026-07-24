"""Pure-Python 0.7.0 -> 0.5.x .nam transcoder for standard WaveNet models.

Why this exists
---------------
The A2->A1 pipeline used two torch venvs only because no single Neural Amp Modeler
version could both LOAD an A2 (needs 0.13.0's SlimmableContainer) and EXPORT the
0.5.x .nam the Valeton GP-50 accepts (0.13.0 exports 0.7.0). This module removes the
second venv: train + export a standard A1 entirely in 0.13.0 (0.7.0 format), then
transcode the result down to 0.5.x here, with no torch and no retraining.

It is provably safe because, for the standard WaveNet, the two formats differ ONLY in
their config schema — the flat `weights` array (with `head_scale` as its last element)
is byte-identical across versions. See the proof: loading a standard A1 into 0.13.0 and
re-exporting reproduces the 0.5.x weight array with max|Δ| = 0; the transcoded 0.5.x
config is field-by-field identical to a genuine 0.5.x standard file, and 0.12.2 loads
it and round-trips the weights with max|Δ| = 0.

Scope / safety
--------------
Valid for the STANDARD arch only (no FiLM, slimmable, packing, gating, bottleneck,
head1x1). Those extras are inactive in a standard student, so the transform is a config
reshape plus a passthrough of the weights. If any advanced feature is actually active,
`transcode_070_to_05x` RAISES rather than silently dropping the parameters that
implement it (which would corrupt the model). This is by design: the pipeline only ever
ships standard.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List

MODEL_VERSION_05X = "0.5.4"

# 0.7.0 per-layer-array keys that describe *optional* features. Each maps to an
# "is it active?" predicate; if active for any layer, the model can't be represented
# in 0.5.x and we refuse.
_FILM_KEYS = (
    "conv_pre_film",
    "conv_post_film",
    "activation_pre_film",
    "activation_post_film",
    "input_mixin_pre_film",
    "input_mixin_post_film",
    "layer1x1_post_film",
    "head1x1_post_film",
)


class NotStandardWaveNet(ValueError):
    """Raised when a 0.7.0 model uses features with no 0.5.x representation."""


def _uniform(seq: List[Any], what: str) -> Any:
    """Return the single distinct value in `seq`, or raise if it isn't uniform.

    0.7.0 stores kernel size and activation per-layer; the classic 0.5.x standard
    uses one scalar for the whole array. A standard student always has uniform lists.
    """
    distinct = {json.dumps(v, sort_keys=True) for v in seq}
    if len(distinct) != 1:
        raise NotStandardWaveNet(f"non-uniform {what} across layers: {seq}")
    return seq[0]


def _reshape_layer(i: int, la: Dict[str, Any]) -> Dict[str, Any]:
    # Refuse any active optional feature — its weights have nowhere to go in 0.5.x.
    for k in _FILM_KEYS:
        if isinstance(la.get(k), dict) and la[k].get("active"):
            raise NotStandardWaveNet(f"layer {i}: FiLM '{k}' active")
    if isinstance(la.get("head1x1"), dict) and la["head1x1"].get("active"):
        raise NotStandardWaveNet(f"layer {i}: head1x1 active")
    if la.get("slimmable") is not None:
        raise NotStandardWaveNet(f"layer {i}: slimmable config present")
    if la.get("packing") is not None:
        raise NotStandardWaveNet(f"layer {i}: packing config present")
    if la.get("bottleneck", la["channels"]) != la["channels"]:
        raise NotStandardWaveNet(f"layer {i}: bottleneck != channels")
    gating = la.get("gating_mode", ["none"])
    secondary = la.get("secondary_activation", [None])
    if any(g != "none" for g in gating) or any(s is not None for s in secondary):
        raise NotStandardWaveNet(f"layer {i}: gated activation")
    head = la["head"]
    if head.get("kernel_size", 1) != 1:
        raise NotStandardWaveNet(f"layer {i}: head kernel_size != 1")

    activation = _uniform(la["activation"], "activation")
    if isinstance(activation, dict):  # 0.7.0 wraps it as {"type": "Tanh"}
        activation = activation["type"]
    if "kernel_sizes" in la:
        kernel_size = _uniform(la["kernel_sizes"], "kernel_sizes")
    else:
        kernel_size = la["kernel_size"]

    return {
        "input_size": la["input_size"],
        "condition_size": la["condition_size"],
        "channels": la["channels"],
        "head_size": head["out_channels"],
        "kernel_size": kernel_size,
        "dilations": la["dilations"],
        "activation": activation,
        "gated": False,
        "head_bias": bool(head.get("bias", False)),
    }


def transcode_070_to_05x(model: Dict[str, Any]) -> Dict[str, Any]:
    """Transcode a parsed 0.7.0 standard-WaveNet .nam dict to 0.5.x.

    Weights are copied verbatim; only the config schema is reshaped. Raises
    NotStandardWaveNet if the model uses features 0.5.x can't express.
    """
    if model.get("architecture") != "WaveNet":
        raise NotStandardWaveNet(
            f"architecture is {model.get('architecture')!r}, not WaveNet"
        )
    version = str(model.get("version", ""))
    if not version.startswith("0.7"):
        raise NotStandardWaveNet(f"expected a 0.7.x model, got version {version!r}")

    cfg = model["config"]
    new_layers = [_reshape_layer(i, la) for i, la in enumerate(cfg["layers"])]
    out: Dict[str, Any] = {
        "version": MODEL_VERSION_05X,
        "architecture": "WaveNet",
        "config": {
            "layers": new_layers,
            "head": cfg.get("head"),
            "head_scale": cfg["head_scale"],
        },
        "weights": list(model["weights"]),  # verbatim; head_scale is weights[-1]
        "sample_rate": model.get("sample_rate", 48000),
    }
    if "metadata" in model:
        out["metadata"] = copy.deepcopy(model["metadata"])
    return out


def transcode_file(src_path: str, dst_path: str) -> Dict[str, Any]:
    """Read a 0.7.0 .nam, write its 0.5.x transcode, return the 0.5.x dict."""
    with open(src_path) as fp:
        model = json.load(fp)
    low = transcode_070_to_05x(model)
    with open(dst_path, "w") as fp:
        json.dump(low, fp)
    return low


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: python nam_transcode.py <in_0.7.0.nam> <out_0.5.x.nam>"
        )
    result = transcode_file(sys.argv[1], sys.argv[2])
    l0 = result["config"]["layers"][0]
    print(
        f"transcoded -> version={result['version']} weights={len(result['weights'])} "
        f"layer0_head_size={l0['head_size']}"
    )
