import json

from denoiser.cli import main
from denoiser.presets import BUILTIN_PRESETS, load_preset, resolve_preset, save_preset
from denoiser.settings import Settings


def test_preset_roundtrip(tmp_path):
    s = Settings()
    s.denoise.algorithm = "nlm"
    s.denoise.params = {"search_window": 15}
    s.develop.wb_custom = (1.9, 1.0, 1.4)
    path = save_preset(s, tmp_path / "mio")
    assert path.suffix == ".json"
    loaded = load_preset(path)
    assert loaded == s


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "vecchio.json"
    path.write_text(json.dumps({"denoise": {"algorithm": "bilateral", "chiave_rimossa": 1}, "extra": {}}))
    assert load_preset(path).denoise.algorithm == "bilateral"


def test_builtin_presets_resolve():
    for name in BUILTIN_PRESETS:
        assert resolve_preset(name.lower()).denoise.algorithm


def test_cli_elabora(tmp_path, dng_pair, capsys):
    _, noisy = dng_pair
    target = tmp_path / "in.dng"
    target.write_bytes(noisy.read_bytes())
    code = main([
        "elabora", str(target), "--algoritmo", "nlm", "--param", "search_window=11",
        "--formato", "jpeg", "--cartella", str(tmp_path / "out"), "--nome", "{nome}_{metodo}",
    ])
    assert code == 0
    assert (tmp_path / "out" / "in_nlm.jpg").is_file()


def test_cli_rejects_unknown_param(tmp_path, dng_pair):
    _, noisy = dng_pair
    try:
        main(["elabora", str(noisy), "--param", "inesistente=1"])
    except SystemExit as exc:
        assert "inesistente" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("atteso errore")


def test_cli_analizza(dng_pair, capsys):
    _, noisy = dng_pair
    assert main(["analizza", str(noisy)]) == 0
    out = capsys.readouterr().out
    assert "Bayer RGGB" in out
    assert "livello 3" in out
