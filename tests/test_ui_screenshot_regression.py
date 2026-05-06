"""Screenshot regression tests using deterministic visual fingerprints.

The committed baseline is a small JSON file of perceptual hashes and image
metadata. On failure, the test writes actual PNG screenshots and a JSON report
to a temp artifact directory so the changed UI can be inspected.

To intentionally refresh the baseline after reviewing UI changes:

    UPDATE_UI_SCREENSHOTS=1 conda run -n bio_env pytest tests/test_ui_screenshot_regression.py -q
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage

from tests.test_ui_e2e import SAMPLE_FASTA, SAMPLE_PROTEIN
from tests.test_ui_workflows import workflow_boundaries, workflow_window


BASELINE_PATH = Path(__file__).parent / "snapshots" / "ui_screenshot_baselines.json"
ARTIFACT_ROOT = Path(os.environ.get("UI_SCREENSHOT_ARTIFACT_DIR", "/tmp/protein_gui_ui_screenshots"))
HASH_SIZE = 16
HASH_BITS = HASH_SIZE * HASH_SIZE
MAX_HASH_DISTANCE = 28
MIN_UNIQUE_COLORS = 32


def _render_widget(widget, qt_app, width: int, height: int):
    widget.show()
    qt_app.processEvents()
    widget.resize(width, height)
    qt_app.processEvents()
    qt_app.processEvents()
    return widget.grab()


def _scaled_gray_values(image: QImage):
    scaled = image.convertToFormat(QImage.Format_RGB32).scaled(
        HASH_SIZE,
        HASH_SIZE,
        Qt.IgnoreAspectRatio,
        Qt.SmoothTransformation,
    )
    values = []
    for y in range(HASH_SIZE):
        for x in range(HASH_SIZE):
            color = QColor(scaled.pixel(x, y))
            values.append(int(0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()))
    return values


def _average_hash(image: QImage) -> str:
    values = _scaled_gray_values(image)
    avg = sum(values) / len(values)
    bits = ["1" if value >= avg else "0" for value in values]
    return "".join(f"{int(''.join(bits[i:i + 4]), 2):x}" for i in range(0, len(bits), 4))


def _hamming_hex(left: str, right: str) -> int:
    return sum(
        bin(int(a, 16) ^ int(b, 16)).count("1")
        for a, b in zip(left, right)
    ) + abs(len(left) - len(right)) * 4


def _image_stats(image: QImage) -> dict:
    sample = image.convertToFormat(QImage.Format_RGB32).scaled(
        96,
        96,
        Qt.IgnoreAspectRatio,
        Qt.FastTransformation,
    )
    colors = set()
    luminance_values = []
    for y in range(sample.height()):
        for x in range(sample.width()):
            color = QColor(sample.pixel(x, y))
            colors.add((color.red() // 8, color.green() // 8, color.blue() // 8))
            luminance_values.append(
                int(0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue())
            )
    return {
        "width": image.width(),
        "height": image.height(),
        "hash": _average_hash(image),
        "unique_colors": len(colors),
        "mean_luminance": round(sum(luminance_values) / len(luminance_values), 2),
        "luminance_range": max(luminance_values) - min(luminance_values),
    }


def _load_baselines():
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baselines(baselines):
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(baselines, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact_dir(tmp_path):
    path = ARTIFACT_ROOT / tmp_path.name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_png(pixmap, path: Path):
    assert pixmap.save(str(path), "PNG")
    assert path.exists()
    assert path.stat().st_size > 0


def _assert_or_update_snapshot(name: str, pixmap, tmp_path):
    image = pixmap.toImage()
    current = _image_stats(image)
    baselines = _load_baselines()

    if os.environ.get("UPDATE_UI_SCREENSHOTS") == "1":
        baselines[name] = current
        _write_baselines(baselines)
        return

    artifact_dir = _artifact_dir(tmp_path)
    _save_png(pixmap, artifact_dir / f"{name}.png")

    assert current["unique_colors"] >= MIN_UNIQUE_COLORS, (
        f"{name} looks blank or nearly blank: {current}. "
        f"Screenshot: {artifact_dir / f'{name}.png'}"
    )
    assert current["luminance_range"] >= 24, (
        f"{name} has too little visual contrast: {current}. "
        f"Screenshot: {artifact_dir / f'{name}.png'}"
    )

    assert name in baselines, (
        f"No screenshot baseline for {name!r}. "
        "Run with UPDATE_UI_SCREENSHOTS=1 after reviewing the generated screenshot."
    )

    expected = baselines[name]
    distance = _hamming_hex(current["hash"], expected["hash"])
    report = {
        "name": name,
        "current": current,
        "expected": expected,
        "hash_distance": distance,
        "max_hash_distance": MAX_HASH_DISTANCE,
    }
    (artifact_dir / f"{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    assert current["width"] == expected["width"]
    assert current["height"] == expected["height"]
    assert distance <= MAX_HASH_DISTANCE, (
        f"{name} screenshot changed: hash distance {distance} > {MAX_HASH_DISTANCE}. "
        f"Artifacts: {artifact_dir / f'{name}.png'} and {artifact_dir / f'{name}.json'}"
    )


def test_alignment_viewer_screenshot_regression(qt_app, workflow_boundaries, tmp_path):
    from ui.dialogs.alignment_viewer_dialog import AlignmentViewerDialog

    dialog = AlignmentViewerDialog()
    assert dialog.load_alignment(SAMPLE_FASTA)
    pixmap = _render_widget(dialog, qt_app, 960, 640)

    _assert_or_update_snapshot("alignment_viewer_960x640", pixmap, tmp_path)

    dialog.hide()
    qt_app.processEvents()


def test_alignment_results_screenshot_regression(workflow_window, qt_app, tmp_path, monkeypatch):
    class FakeViewer:
        def load_alignment(self, content):
            return True

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    page = workflow_window.alignment_page
    monkeypatch.setattr(page, "_ensure_alignment_viewer_dialog", lambda: FakeViewer())
    page.on_alignment_finished(SAMPLE_FASTA, "/tmp/fake-alignment.fasta")
    workflow_window.tabs.setCurrentWidget(page)

    pixmap = _render_widget(workflow_window, qt_app, 1100, 750)
    _assert_or_update_snapshot("alignment_results_1100x750", pixmap, tmp_path)


def test_clustering_results_screenshot_regression(workflow_window, qt_app, tmp_path):
    page = workflow_window.clustering_page
    workflow_window.tabs.setCurrentWidget(page)
    page.on_clustering_finished(
        {
            "total_sequences": 2,
            "num_clusters": 1,
            "largest_cluster": 2,
            "avg_cluster_size": 2.0,
            "singletons": 0,
            "cluster_size_distribution": {2: 1},
            "clusters": {"seq1": ["seq1", "seq2"]},
        },
        "/tmp/representatives.fasta",
        "/tmp/clusters.tsv",
    )

    pixmap = _render_widget(workflow_window, qt_app, 1100, 750)
    _assert_or_update_snapshot("clustering_results_1100x750", pixmap, tmp_path)


def test_motif_results_screenshot_regression(workflow_window, qt_app, tmp_path):
    from core.motif_worker import ProteinRecord

    page = workflow_window.motif_search_page
    workflow_window.tabs.setCurrentWidget(page)
    record = ProteinRecord(
        seq=SAMPLE_PROTEIN,
        id="seq1",
        species="Homo sapiens",
        phylo=["Mammalia"],
        indices=[1, 12],
    )
    page.on_search_finished(
        {
            "motif": ["N", "~P", "ST"],
            "total_sequences": 1,
            "total_motifs": 2,
            "category_stats": {"Mammalia": {"count": 1, "motifs": 2}},
            "categories": {
                "Actinopterygii": [],
                "Mammalia": [record],
                "Aves": [],
                "Amphibia": [],
                "Other": [],
            },
        }
    )

    pixmap = _render_widget(workflow_window, qt_app, 1100, 750)
    _assert_or_update_snapshot("motif_results_1100x750", pixmap, tmp_path)
