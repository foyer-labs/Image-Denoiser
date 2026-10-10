import numpy as np
import pytest
from PIL import Image

from denoiser.batch import collect_inputs, process_file
from denoiser.image import ImageMeta
from denoiser.io import UnsupportedImageError, load_image, save_image
from denoiser.io.naming import output_path, render_name, unique_path
from denoiser.settings import OutputSettings, Settings
from synthetic import clean_display


@pytest.mark.parametrize("fmt,bits", [("tiff", 16), ("tiff", 8), ("png", 16), ("png", 8)])
def test_lossless_roundtrip(tmp_path, fmt, bits):
    img = clean_display(64)
    path = save_image(img, tmp_path / f"out.{fmt}", fmt, bit_depth=bits)
    loaded = load_image(path)
    step = 1 / 255 if bits == 8 else 1 / 65535
    assert loaded.pixels.shape == img.shape
    assert np.abs(loaded.pixels - img).max() <= step


def test_jpeg_roundtrip_and_alpha_png(tmp_path):
    img = clean_display(64)
    path = save_image(img, tmp_path / "out.jpg", "jpeg", jpeg_quality=95)
    assert np.abs(load_image(path).pixels - img).mean() < 0.02

    alpha = np.linspace(0, 1, 64 * 64, dtype=np.float32).reshape(64, 64)
    path = save_image(img, tmp_path / "alpha.png", "png", bit_depth=16, alpha=alpha)
    loaded = load_image(path)
    assert loaded.alpha is not None
    assert np.abs(loaded.alpha - alpha).max() < 1e-4


def test_unicode_path(tmp_path):
    folder = tmp_path / "foto è già"
    path = save_image(clean_display(32), folder / "città.png", "png")
    assert load_image(path).pixels.shape == (32, 32, 3)


def test_grayscale_png_becomes_rgb(tmp_path):
    path = tmp_path / "gray.png"
    Image.fromarray((np.linspace(0, 255, 32 * 32).reshape(32, 32)).astype(np.uint8)).save(path)
    loaded = load_image(path)
    assert loaded.pixels.shape == (32, 32, 3)


def test_unsupported_and_missing_files(tmp_path):
    with pytest.raises(UnsupportedImageError):
        load_image(tmp_path / "manca.nef")
    bogus = tmp_path / "finto.nef"
    bogus.write_bytes(b"non sono un raw")
    with pytest.raises(UnsupportedImageError) as exc:
        load_image(bogus, use_dng_converter=False)
    assert "Adobe DNG Converter" in str(exc.value)


def test_naming_template(tmp_path):
    meta = ImageMeta(source=tmp_path / "DSC_0001.NEF", kind="raw", iso=6400, date="20260110")
    out = OutputSettings(format="tiff", folder="denoised", name_template="{nome}_{metodo}_{iso}_{data}")
    assert output_path(meta, out, "wavelet") == tmp_path / "denoised" / "DSC_0001_wavelet_6400_20260110.tif"
    assert render_name("{nome}:{sconosciuto}", meta, "nlm") == "DSC_0001_{sconosciuto}"
    existing = tmp_path / "a.tif"
    existing.write_bytes(b"")
    assert unique_path(existing) == tmp_path / "a_1.tif"


def test_batch_on_folder(tmp_path, dng_pair):
    _, noisy = dng_pair
    folder = tmp_path / "foto"
    folder.mkdir()
    (folder / "scatto.dng").write_bytes(noisy.read_bytes())
    save_image(clean_display(48), folder / "web.jpg", "jpeg")
    (folder / "note.txt").write_text("ignorami")
    files = collect_inputs([folder])
    assert sorted(f.name for f in files) == ["scatto.dng", "web.jpg"]

    settings = Settings()
    settings.output.format = "png"
    results = [process_file(f, settings) for f in files]
    assert all(r.ok for r in results), [r.error for r in results]
    outputs = sorted(p.name for p in (folder / "denoised").iterdir())
    assert outputs == ["scatto_dn.png", "web_dn.png"]
    # Una seconda esecuzione non sovrascrive.
    again = process_file(files[0], settings)
    assert again.output.name == "scatto_dn_1.png"
