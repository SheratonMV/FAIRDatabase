"""Synthetic data that mimics the real structure and its messiness. No real data.

VIDs start at 99000 and every name carries a token, so nothing can collide with or
link to real rows in the database.
"""
import copy
import io
import json
import os
import zipfile

import yaml
from openpyxl import Workbook
from PIL import Image

from plugins.imagehub import config

NESTED_PREFIX = "Annotation/Shared annotation set"
EXAMPLE_CONFIG = os.path.join(config.DATASET_DIRS[0], "spheroid_example.yaml")


def example_raw():
    """The shipped example config, as parsed YAML."""
    with open(EXAMPLE_CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def dataset(token="GOLD", base=None):
    """The example config, fitted to the synthetic disk of ``token``.

    Names that carry the token (experiments, nested zips) cannot be in a static
    file, so they are filled in here. ``base`` replaces the example config.
    """
    raw = copy.deepcopy(base if base is not None else example_raw())
    n = names(token)
    images, annotations = raw["images"], raw.setdefault("annotations", {"format": "via"})
    archive = images.setdefault("annotation_archive", {"zip": "Annotation.zip"})
    archive["nested_groups"] = {"SYNTH10_AA.zip": n["experiment_b"], "SYNTH10_BB.zip": n["experiment_b"]}
    images["match"]["infer_single"] = {"field": "vid", "groups": [n["experiment_b"]]}
    annotations["nested_annotators"] = {"SYNTH10_AA.zip": "AA", "SYNTH10_BB.zip": "BB"}
    annotations["nested_image_folders"] = {"SYNTH10_BB.zip": "SYNTH10_AA.zip!/SYNTH"}
    return config.Dataset(raw, f"synthetic {token}")


def jpeg(colour=120):
    out = io.BytesIO()
    Image.new("RGB", (64, 48), (colour, colour, colour)).save(out, "JPEG")
    return out.getvalue()


def tiff(colour=128):
    out = io.BytesIO()
    Image.new("L", (64, 48), colour).save(out, "TIFF")
    return out.getvalue()


def names(token):
    return {
        "workbook": f"SYNTH{token} family - Pooled sample sheet.xlsx",
        "experiment_a": f"SYNTH{token} exp (AA)",
        "folder_a": f"SYNTH{token} exp",
        "experiment_b": f"BD991 SYNTH{token} one vid",
        "folder_no_metadata": f"SYNTH{token} no metadata",
    }


def make_workbook(path, token):
    """Two sheets and a Legend, with what the real workbooks get wrong."""
    n = names(token)
    book = Workbook()
    a = book.active
    a.title = "EXP-A"
    a.append([
        "Experiment ", "VID", "Well", "Volgnummer", "Treatment", "Tissue", "Stimulation",
        "Concentration (nM)", "Viability (%)", "proliferation index (CLL)",
        "proliferation index (CLL)", "Specific Lysis (%)", "Sex", "Sample date", "Target", None,
    ])
    a.append([n["experiment_a"], 99001.0, "A1", 7, "Ibrutinib", "PB", "IL2/IL15/IL21/CpG", 10, 80.5, 1.5, 1.6, 12, "male", None, "BTK", None])
    a.append([n["experiment_a"], "99002;99003", "A2 ", 7, "ABT-199;S-63845", "PB", "IL-2/15/21/CpG;aCD3/aCD28", "1;2", 70, None, None, None, "female", None, "JAK1/2/3, TYK2, ACVR1", None])
    a.append([n["experiment_a"], 99001, "A3", 8, "rituximab ", "LN", "unstimulated ", 5, None, None, None, None, "niet aanwezig in CLL export bestand (ziekte)", None, None, "stray"])
    a.append([n["experiment_a"], 99001, "A5", 8, "CONFIDENTIAL", "LN", None, None, None, None, None, None, None, None, None, None])
    a.append([None, None, "A4", None, None, None, None, None, None, None, None, None, None, None, None, None])
    a.append([None] * 16)

    b = book.create_sheet("EXP-B")
    # Age, like Sex, is a personal column the example config excludes from exports.
    b.append(["Experiment", "VID", "Well", "Volgnummer", "Treatment", "Tissue", "Stimulation", "Concentration (ng/mL)", "Specific lysis (%)", "Proliferation index (CLL)", " age"])
    for well, age in (("B1", 61), ("B2", "about 70 at sampling")):
        b.append([n["experiment_b"], "BD991", well, 9, "Bay", "PB", "aCD3/aCD29", 3, 30, 2.5, age])

    legend = book.create_sheet("Legend")
    legend.append(["VID", "Video ID"])
    legend.append(["Sex", '"'])
    legend.append(["Viability (%)", "Percentage of live cells"])
    book.save(path)
    return path


def _via(entries):
    return json.dumps({
        f"{name}{size}": {"filename": name, "size": size, "regions": regions, "file_attributes": {}}
        for name, size, regions in entries
    })


def _ellipse(cx=10, cy=10):
    return {"shape_attributes": {"name": "ellipse", "cx": cx, "cy": cy, "rx": 3, "ry": 4}, "region_attributes": {}}


def _polygon():
    return {"shape_attributes": {"name": "polygon", "all_points_x": [1, 9, 5], "all_points_y": [1, 1, 9]}, "region_attributes": {}}


def make_disk(root, token):
    """Zips as on the external disk, with annotation files and nested zips."""
    n = names(token)
    with zipfile.ZipFile(os.path.join(root, "NK.zip"), "w") as z:
        z.writestr(f"NK/{n['folder_a']}/images/VID99001_A1_1_01d00h00m.tif", tiff())
        z.writestr(f"NK/{n['folder_a']}/images/VID99001_A1_1_04d00h00m.jpg", jpeg())
        z.writestr(f"NK/{n['folder_a']}/images/VID99002_A2_1_00d12h00m.jpg", jpeg())
        z.writestr(f"NK/{n['folder_a']}/images/VID99003_A2_1_00d12h00m.jpg", jpeg())
        z.writestr(f"NK/{n['folder_a']}/images/VID99001_H9_1_00d00h00m.jpg", jpeg())
        z.writestr(f"NK/{n['folder_a']}/images/Snapshot.PNG", b"not parsed")
        z.writestr(f"NK/{n['folder_a']}/raw.zip", b"not opened")
        z.writestr(f"NK/{n['folder_a']}/images/__MACOSX/._VID99001_A1_1_01d00h00m.tif", b"x")
        z.writestr(f"NK/{n['folder_no_metadata']}/VID99009_A1_1_00d00h00m.jpg", jpeg())
    with zipfile.ZipFile(os.path.join(root, "Btk.zip"), "w") as z:
        z.writestr(f"Btk/{n['experiment_b']}/BD991_B1_1_00d00h00m.jpg", jpeg())
        z.writestr(f"Btk/{n['experiment_b']}/Phase_B1_1_00d00h00m.tif", tiff())
        z.writestr(f"Btk/{n['experiment_b']}/Brightfield_B1_1_00d00h00m.tif", tiff())
        z.writestr(f"Btk/{n['experiment_b']}/PC_H9_1_00d00h00m.tif", tiff())

    annotated = "VID99001_A1_1_04d00h00m.jpg"
    size = len(jpeg())
    aa_nested, bb_nested = io.BytesIO(), io.BytesIO()
    nested_image = "BF_B1_1_06d12h00m-1L.jpg"
    with zipfile.ZipFile(aa_nested, "w") as z:
        z.writestr(f"SYNTH/{nested_image}", jpeg())
        z.writestr("SYNTH/via_region_data_AA10.json", _via([(nested_image, size, [_ellipse(), _ellipse(20, 20)])]))
    with zipfile.ZipFile(bb_nested, "w") as z:
        z.writestr(nested_image, jpeg())
        z.writestr("via_region_data.json", _via([(nested_image, size, [_ellipse()])]))
    folder = f"Annotation/{token}/set"
    with zipfile.ZipFile(os.path.join(root, "Annotation.zip"), "w") as z:
        z.writestr(f"{folder}/{annotated}", jpeg())
        z.writestr(f"{folder}/set_AA.json", _via([
            (annotated, size, [_ellipse(), _polygon()]),
            ("VID99999_A1_1_00d00h00m.jpg", 5, [_ellipse()]),
        ]))
        z.writestr(f"{folder}/set.json", _via([(annotated, size, [])]))
        z.writestr(f"{folder}/wrong_size_AA.json", _via([(annotated, size + 1, [_ellipse()])]))
        z.writestr(f"{NESTED_PREFIX}/{token}/SYNTH10_AA.zip", aa_nested.getvalue())
        z.writestr(f"{NESTED_PREFIX}/{token}/SYNTH10_BB.zip", bb_nested.getvalue())
    return {
        "annotated": annotated,
        "nested_image": nested_image,
        "via_aa": f"{folder}/set_AA.json",
        "via_unknown": f"{folder}/set.json",
        "via_wrong_size": f"{folder}/wrong_size_AA.json",
        "via_nested_aa": f"{NESTED_PREFIX}/{token}/SYNTH10_AA.zip!/SYNTH/via_region_data_AA10.json",
        "via_nested_bb": f"{NESTED_PREFIX}/{token}/SYNTH10_BB.zip!/via_region_data.json",
    }
