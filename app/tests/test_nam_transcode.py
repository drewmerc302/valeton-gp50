"""Hermetic tests for a2a1.nam_transcode (pure-Python 0.7.0 -> 0.5.x, no torch).

The end-to-end proof (0.13.0 re-export byte-identical; 0.12.2 loads the transcode)
lives in the slow suite / session notes. These lock in the config reshape, the
verbatim weight passthrough, and — critically — the refusal to transcode any model
that uses features 0.5.x cannot represent.
"""

import pytest

from a2a1 import nam_transcode

STD_DILATIONS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]


def _std_070_layer(input_size, channels, head_out, head_bias):
    """A standard-WaveNet layer array in 0.7.0 export shape (all extras inactive)."""
    inactive_film = {"active": False, "shift": True, "groups": 1}
    return {
        "input_size": input_size,
        "condition_size": 1,
        "channels": channels,
        "bottleneck": channels,
        "head": {"out_channels": head_out, "kernel_size": 1, "bias": head_bias},
        "kernel_sizes": [3] * 10,
        "dilations": STD_DILATIONS,
        "activation": [{"type": "Tanh"}] * 10,
        "gating_mode": ["none"] * 10,
        "secondary_activation": [None] * 10,
        "conv_pre_film": inactive_film,
        "conv_post_film": inactive_film,
        "activation_pre_film": inactive_film,
        "activation_post_film": inactive_film,
        "input_mixin_pre_film": inactive_film,
        "input_mixin_post_film": inactive_film,
        "layer1x1_post_film": inactive_film,
        "head1x1_post_film": inactive_film,
        "head1x1": {"active": False, "out_channels": 1, "groups": 1},
        "layer1x1": {"active": True, "groups": 1},
        "groups_input": 1,
        "groups_input_mixin": 1,
        "slimmable": None,
    }


def _std_070_model():
    return {
        "version": "0.7.0",
        "architecture": "WaveNet",
        "config": {
            "layers": [
                _std_070_layer(1, 16, 8, False),
                _std_070_layer(16, 8, 1, True),
            ],
            "head": None,
            "head_scale": 0.02,
        },
        "weights": [0.1, -0.2, 0.3, 0.02],  # last element = head_scale, by convention
        "sample_rate": 48000,
    }


def test_transcode_reshapes_config_to_05x():
    low = nam_transcode.transcode_070_to_05x(_std_070_model())
    assert low["version"].startswith("0.5")
    assert low["architecture"] == "WaveNet"
    l0, l1 = low["config"]["layers"]
    assert sorted(l0) == [
        "activation",
        "channels",
        "condition_size",
        "dilations",
        "gated",
        "head_bias",
        "head_size",
        "input_size",
        "kernel_size",
    ]
    assert (l0["head_size"], l0["head_bias"], l0["kernel_size"]) == (8, False, 3)
    assert l0["activation"] == "Tanh" and l0["gated"] is False
    assert (l1["head_size"], l1["head_bias"]) == (1, True)
    assert low["config"]["head_scale"] == 0.02


def test_weights_are_copied_verbatim():
    model = _std_070_model()
    low = nam_transcode.transcode_070_to_05x(model)
    assert low["weights"] == model["weights"]
    assert low["weights"][-1] == low["config"]["head_scale"]  # head_scale convention


def test_refuses_non_070_input():
    m = _std_070_model()
    m["version"] = "0.5.0"
    with pytest.raises(nam_transcode.NotStandardWaveNet):
        nam_transcode.transcode_070_to_05x(m)


def test_refuses_active_film():
    m = _std_070_model()
    m["config"]["layers"][0]["conv_pre_film"]["active"] = True
    with pytest.raises(nam_transcode.NotStandardWaveNet):
        nam_transcode.transcode_070_to_05x(m)


def test_refuses_gated_activation():
    m = _std_070_model()
    m["config"]["layers"][0]["gating_mode"] = ["tanh_sigmoid"] * 10
    with pytest.raises(nam_transcode.NotStandardWaveNet):
        nam_transcode.transcode_070_to_05x(m)


def test_refuses_nonuniform_kernel_sizes():
    m = _std_070_model()
    m["config"]["layers"][0]["kernel_sizes"] = [3] * 9 + [5]
    with pytest.raises(nam_transcode.NotStandardWaveNet):
        nam_transcode.transcode_070_to_05x(m)


def test_refuses_head_kernel_size_not_one():
    m = _std_070_model()
    m["config"]["layers"][0]["head"]["kernel_size"] = 3
    with pytest.raises(nam_transcode.NotStandardWaveNet):
        nam_transcode.transcode_070_to_05x(m)
