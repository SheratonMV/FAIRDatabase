"""Workbook parsing on a synthetic workbook. No database, no real data."""
import zipfile

from openpyxl import Workbook

from plugins.imagehub.config import Dataset
from plugins.imagehub.ingest import derived_mappings, propose_aliases, read_metadata
from plugins.imagehub.tests import synthetic

EXAMPLE = synthetic.dataset()


def _read(path, dataset=EXAMPLE):
    return read_metadata(str(path), dataset=dataset)


def _workbook(path):
    wb = Workbook()
    ws = wb.active
    ws.title = "EXP1"
    ws.append(["Experiment ", "VID", "Well", "Volgnummer", "Treatment", "Tissue",
               "Stimulation", "Concentration (nM)", "Viability (%)", "Viability (%)", None])
    ws.append(["Exp one (AA)", 2832.0, "A1", 7, "Ibrutinib", "PB", "CD40L", 10, 80.5, 81, None])
    ws.append(["Exp one (AA)", "3494;3495", "C2 ", 7, "ABT-199;S-63845", "PB", None, None, None, None, "stray"])
    ws.append([None, None, "A3", None, None, None, None, None, None, None, None])
    ws.append([None, None, None, None, None, None, None, None, None, None, None])
    legend = wb.create_sheet("Legend")
    legend.append(["Experiment", "Explanation"])
    wb.save(path)


def test_read_metadata_rows(tmp_path):
    path = tmp_path / "Family - Pooled sample sheet.xlsx"
    _workbook(path)
    data = _read(path)

    assert len(data["wells"]) == 2
    first, second = data["wells"]
    assert first["vid"] == "2832" and first["vids"] == ["2832"]
    assert first["experiment"] == "Exp one (AA)"
    assert first["treatment_raw"] == "Ibrutinib"
    assert first["treatment_norm"] == ["ibrutinib"]
    assert first["concentration"] == "10" and first["concentration_unit"] == "nM"
    assert first["props"] == {"Viability (%)": 80.5, "Viability (%)_2": 81}
    assert first["source_row"] == 2

    assert second["vids"] == ["3494", "3495"]
    assert second["well"] == "C2"
    assert second["treatment_raw"] == "ABT-199;S-63845"
    assert second["treatment_norm"] == ["venetoclax", "s-63845"]
    assert second["props"]["(no header, column 11)"] == "stray"

    assert [r[3] for r in data["report"]] == ["skipped_no_vid", "skipped_blank"]
    assert data["legends"][0]["rows"] == [["Experiment", "Explanation"]]
    assert derived_mappings(data["wells"], EXAMPLE)["treatment_norm"]["Ibrutinib"] == (["ibrutinib"], 1)
    assert data["sheets"][0]["missing_core"] == []

    # ``fields`` holds exactly the config's fields and derived fields.
    names = {*EXAMPLE.metadata["fields"], "concentration_unit", *EXAMPLE.metadata["derived"]}
    for well in data["wells"]:
        assert well["dataset"] == "spheroid_example"
        assert well["fields"] == {n: well[n] for n in names if well[n] is not None}


def test_reports_no_vid_row_that_holds_data(tmp_path):
    path = tmp_path / "f.xlsx"
    wb = Workbook()
    wb.active.append(["Experiment", "VID", "Well", "Treatment"])
    wb.active.append(["E", None, "A1", "ibrutinib"])
    wb.save(path)
    assert _read(path)["sheets"][0]["skipped_no_vid_with_data"] == 1


def test_sheet_without_treatment_column_does_not_crash(tmp_path):
    # The old reader looked up the Treatment column for every row without a VID.
    path = tmp_path / "f.xlsx"
    wb = Workbook()
    wb.active.append(["Experiment", "VID", "Well", "Viability (%)"])
    wb.active.append(["E", None, "A1", None])
    wb.active.append(["E", "7", "A2", 50])
    wb.save(path)
    data = _read(path)
    sheet = data["sheets"][0]
    assert sheet["skipped_no_vid"] == 1 and "skipped_no_vid_with_data" not in sheet
    assert sheet["missing_core"] == ["Stimulation", "Tissue", "Treatment", "Volgnummer", "Concentration"]
    assert data["wells"][0]["treatment_norm"] == [] and data["wells"][0]["concentration_unit"] is None


def test_another_dataset_reads_its_own_columns(tmp_path):
    # Invented dataset: one key column, no wells, no VID, its own cleaning.
    raw = {
        "id": "leaf_discs", "title": "Leaf discs",
        "metadata": {
            "required": ["sample_id"],
            "fields": {
                "sample_id": {"header": "Sample ID", "strip": True},
                "species": {"header": "Species"},
                "dose": {"header_regex": r"^Dose\s*\((?P<unit>[^)]+)\)$"},
            },
            "derived": {"species_norm": {"from": "species", "steps": ["strip", "lower", {"synonyms": {"q. robur": "oak"}}]}},
        },
        "images": {"extensions": [".png"], "archives": [{"zip": "leaves.zip", "folder_level": 1}],
                   "filename": {"pattern": r"^(?P<s>.+)\.png$", "fields": {"sample_id": {"groups": ["s"]}}}},
    }
    path = tmp_path / "leaves.csv"
    path.write_text("Sample ID,Species,Dose (mg),Plot\n LEAF-1 ,Q. robur,5,north\n,Oak,,south\n,,,\n", encoding="utf-8")
    data = _read(path, Dataset(raw, "leaf.yaml"))
    assert data["wells"] == [{
        "sample_id": "LEAF-1", "species": "Q. robur", "species_norm": ["oak"], "dose": "5",
        "dose_unit": "mg", "dataset": "leaf_discs", "source_workbook": "leaves.csv",
        "source_sheet": "leaves", "source_row": 2, "props": {"Plot": "north"},
        "fields": {"sample_id": "LEAF-1", "species": "Q. robur", "species_norm": ["oak"],
                   "dose": "5", "dose_unit": "mg"},
    }]
    assert data["dataset"] == "leaf_discs"
    # Without a position field, a row with any value left is a lost sample, not blank.
    assert [r[3] for r in data["report"]] == ["skipped_no_sample_id", "skipped_blank"]


def test_reads_csv_folder_and_zip_and_skips_lock_files(tmp_path):
    folder = tmp_path / "metadata"
    folder.mkdir()
    (folder / "plain.csv").write_text("Experiment,VID,Well,Treatment,Viability (%)\nE,1,A1,x,5\n,,,,\n", encoding="utf-8")
    _workbook(folder / "Family - Pooled sample sheet.xlsx")
    (folder / "~$Family - Pooled sample sheet.xlsx").write_bytes(b"lock")

    from_csv = _read(folder / "plain.csv")
    assert len(from_csv["wells"]) == 1 and from_csv["wells"][0]["source_sheet"] == "plain"
    assert from_csv["wells"][0]["props"] == {"Viability (%)": "5"}
    assert from_csv["report"] == [("plain.csv", "plain", 3, "skipped_blank")]

    assert len(_read(folder)["wells"]) == 3  # the lock file is left out

    archive = tmp_path / "Metadata.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(folder / "Family - Pooled sample sheet.xlsx", "Metadata/Family - Pooled sample sheet.xlsx")
        z.write(folder / "~$Family - Pooled sample sheet.xlsx", "Metadata/~$Family - Pooled sample sheet.xlsx")
    assert len(_read(archive)["wells"]) == 2


def _well(experiment, vids, well, workbook="Fam - x.xlsx"):
    return {"experiment": experiment, "vids": vids, "well": well, "source_workbook": workbook}


def _folder(name, pairs, family="Fam"):
    return {"zip": "z.zip", "family": family, "folder": name,
            "images": sum(pairs.values()), "pairs": pairs}


def test_propose_aliases_kinds_and_family_guard():
    wells = [
        _well("Exact name (AA)", ["1"], "A1"),
        _well("20241004_EXP36_T cell", ["2"], "B1"),
        _well("20230802_EXP18_Drug", ["3"], "C1", workbook="Other - x.xlsx"),
        _well("Unused", ["4"], "D1"),
    ]
    folders = [
        _folder("Exact name", {("1", "A1"): 3, ("1", "A2"): 1}),
        _folder("20240927_EXP36_T-cells", {("2", "B1"): 2}),
        # EXP18 exists in another family only, so this must not be linked.
        _folder("20240506_EXP18_NK", {("9", "A1"): 1}),
    ]
    results, unused = propose_aliases(wells, folders, dataset=synthetic.dataset())
    by_folder = {r["folder"]: r for r in results}
    assert by_folder["Exact name"]["kind"] == "exact"
    assert by_folder["Exact name"]["matched"] == 3
    assert by_folder["20240927_EXP36_T-cells"]["kind"] == "proposed"
    assert by_folder["20240506_EXP18_NK"]["kind"] == "none"
    assert unused == ["20230802_EXP18_Drug", "Unused"]


def test_propose_aliases_without_lab_tokens_proposes_nothing():
    raw = synthetic.example_raw()
    del raw["images"]["match"]["lab_tokens"]
    wells = [_well("20241004_EXP36_T cell", ["2"], "B1")]
    results, _ = propose_aliases(wells, [_folder("20240927_EXP36_T-cells", {("2", "B1"): 2})],
                                 dataset=Dataset(raw, "no tokens"))
    assert results[0]["kind"] == "none"


def test_dry_run_lists_changed_and_flagged_values_and_counts_the_rest(tmp_path, capsys):
    from plugins.imagehub import cli
    workbook = synthetic.make_workbook(tmp_path / "w.xlsx", "CLI")
    cli._print_mappings(_read(workbook))
    out = capsys.readouterr().out
    assert "'ABT-199;S-63845' | venetoclax + s-63845 | 1 |" in out
    assert "'IL2/IL15/IL21/CpG' | il-2/15/21/cpg | 1 |" in out
    # VIDs only split as written: counted, not listed.
    assert "vids: raw" in out and "'99002;99003'" not in out
    assert "vids: raw | cleaned | rows | flag\n(3 values kept as written)" in out
