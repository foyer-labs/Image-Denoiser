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


def test_dng_export_roundtrip(tmp_path, dng_pair):
    from denoiser.batch import export_image
    from denoiser.io.raw import decode_raw
    from denoiser.pipeline import analyze, denoise_region

    _, noisy = dng_pair
    image = load_image(noisy)
    analysis = analyze(image)
    for stage in ("sensor", "rgb"):
        settings = Settings()
        settings.output.format = "dng"
        settings.denoise.raw_stage = stage
        path = export_image(image, analysis, settings, tmp_path / f"{stage}.dng")
        back = decode_raw(path, measure_noise=False)
        expected = denoise_region(image, analysis, settings)
        assert back.pixels.shape == expected.shape
        assert np.abs(back.pixels - expected).max() < 1e-3


def test_dng_export_refused_for_jpeg(tmp_path):
    from denoiser.batch import process_file

    src = save_image(clean_display(32), tmp_path / "foto.jpg", "jpeg")
    settings = Settings()
    settings.output.format = "dng"
    result = process_file(src, settings)
    assert not result.ok and "solo per le foto RAW" in result.error


def test_bayer_dng_with_camera_matrix(tmp_path, dng_pair):
    """Percorso dei RAW proprietari: matrice colore e bilanciamento presi da LibRaw."""
    from denoiser.io.dng import XYZ_TO_SRGB, SensorData, write_bayer_dng
    from denoiser.io.raw import decode_raw

    _, noisy = dng_pair
    original = decode_raw(noisy, measure_noise=False)
    import rawpy

    with rawpy.imread(str(noisy)) as raw:
        cfa = raw.raw_image_visible.copy()
    sensor = SensorData(
        cfa=cfa, pattern=np.array([[0, 1], [1, 2]], dtype=np.uint8), black=np.full((2, 2), 256.0),
        white=4095, xyz_to_camera=XYZ_TO_SRGB, camera_neutral=np.ones(3), flip=6,
    )
    path = write_bayer_dng(tmp_path / "camera.dng", sensor, "Marca", "Modello")
    back = decode_raw(path, measure_noise=False)
    # Orientamento 6: l'immagine riletta è ruotata di 90° in senso orario.
    assert back.pixels.shape == (original.width, original.height, 3)
    diff = np.abs(back.pixels - np.rot90(original.pixels, -1))
    # Pochi pixel isolati possono differire per le scelte locali della demosaicizzazione AHD.
    assert diff.mean() < 1e-3 and np.percentile(diff, 99) < 5e-3
    assert back.meta.camera == "Marca Modello"
