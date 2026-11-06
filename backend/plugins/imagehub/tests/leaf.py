"""Synthetic data for the invented leaf disc dataset (tests/leaf_discs.yaml).

Everything is made here, in the test's temporary folder: a workbook and a zip of
PNG photos. No real data, nothing binary in git.
"""
import io
import os
import zipfile

from openpyxl import Workbook
from PIL import Image

from plugins.imagehub import config

CONFIG = os.path.join(os.path.dirname(__file__), "leaf_discs.yaml")
TRIAL = "Trial 2026"
# Invented names in a column the config excludes from exports.
GROWERS = ("Grower Example One", "Grower Example Two")


def dataset():
    return config.load_file(CONFIG)


def png(shade):
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (20, shade, 40)).save(out, "PNG")
    return out.getvalue()


def make_workbook(path):
    """One trial sheet; LEAF-0005 has no photos, and a blank row is skipped."""
    book = Workbook()
    sheet = book.active
    sheet.title = TRIAL
    sheet.append(["Sample ID", "Plot", "Species", "Fertiliser", "Dose (g/m2)", "Chlorophyll (SPAD)", "Grower"])
    sheet.append(["LEAF-0001 ", "north", "Q. robur", "none", 0, 31.5, GROWERS[0]])
    sheet.append(["LEAF-0002", "north", "Quercus robur", "nitrogen", 12, 38.0, GROWERS[0]])
    sheet.append(["LEAF-0003", "south", "Fagus sylvatica", "nitrogen", 12, 35.2, GROWERS[1]])
    sheet.append(["LEAF-0004", "south", "fagus sylvatica ", "none", 0, 29.9, GROWERS[1]])
    sheet.append(["LEAF-0005", "south", "Fagus sylvatica", "none", 0, None, GROWERS[1]])
    sheet.append([None] * 7)
    book.save(path)
    return path


def make_disk(disk):
    """leaves.zip with one folder per trial: two days and two sides per disc,
    one photo of a disc that is not in the sheet, and a file that is no photo."""
    names = []
    with zipfile.ZipFile(os.path.join(disk, "leaves.zip"), "w") as z:
        for number in range(1, 5):
            for day in (1, 3):
                for side in ("top", "bottom"):
                    name = f"LEAF-{number:04d}_day{day:02d}_{side}.png"
                    z.writestr(f"{TRIAL}/{name}", png(60 + 20 * number + day))
                    names.append(name)
        z.writestr(f"{TRIAL}/LEAF-0099_day01_top.png", png(10))
        z.writestr(f"{TRIAL}/notes.txt", "not a photo")
    return names
