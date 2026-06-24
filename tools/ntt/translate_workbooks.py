#!/usr/bin/env python3
"""Produce English copies of the three Indonesian source workbooks.

Translates column headers, sheet titles, and the common categorical/label cell
values (not free-text notes) so a partner can read the workbooks in English. The
original files are never modified — copies are written to
data_indonesia/source_ntt/english/.

Usage:
    python -m tools.ntt.translate_workbooks --src-dir <folder-with-3-xlsx>
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[2]

# Phrase-level dictionary (longest-first matching). Headers, sheet names, and
# frequent categorical values. Free-text notes are left as-is.
GLOSSARY = {
    # --- administrative / identity ---
    "NAMA_PROV": "PROVINCE", "NAMA_KAB": "REGENCY", "NAMA_KEC": "DISTRICT",
    "NAMA_DESA": "VILLAGE", "NAMA_KOMODITAS": "COMMODITY",
    "Nama Desa": "Village", "Kecamatan": "District", "Kabupaten": "Regency",
    "Provinsi": "Province", "Kode Desa": "Village Code",
    "Longitude": "Longitude", "Latitude": "Latitude",
    # --- potensi-desa columns ---
    "lapangan_usaha_utama": "main_business_sector_code",
    "nama_lapangan_usaha": "main_business_sector",
    "subsektor_pertanian_utama": "main_agri_subsector_code",
    "nama_subsektor_pertanian": "main_agri_subsector",
    "jml_kel_listrik_pln": "households_on_PLN_grid",
    "jml_kel_listrik_nonpln": "households_on_nonPLN_electricity",
    "jml_kel_tanpa_listrik": "households_without_electricity",
    "kel_lampu_tenaga_surya": "households_with_solar_lamps",
    "penerangan_jalan_tenaga_surya": "solar_street_lighting",
    "penerangan_jalan_utama": "main_street_lighting",
    "sumber_penerangan_jalan_utama": "main_street_lighting_source",
    "GHI Rata-rata (kWh/m²/hari)": "Average GHI (kWh/m2/day)",
    # --- sector / subsector values ---
    "Pertanian, kehutanan, dan perikanan": "Agriculture, forestry & fisheries",
    "Perdagangan besar dan eceran, reparasi mobil dan motor":
        "Wholesale & retail trade, vehicle repair",
    "Administrasi pemerintahan, pertahanan, dan jaminan sosial wajib":
        "Public administration, defence & social security",
    "Industri pengolahan": "Manufacturing", "Konstruksi": "Construction",
    "Pendidikan": "Education", "Aktivitas jasa lainnya": "Other services",
    "Tanaman Pangan": "Food crops", "Tanaman Hortikultura": "Horticulture",
    "Tanaman Perkebunan": "Estate crops", "Peternakan": "Livestock",
    "Perikanan": "Fisheries", "Kehutanan": "Forestry", "Hortikultura": "Horticulture",
    # --- common categorical values ---
    "Ada, sebagian kecil": "Present, small share",
    "Ada, sebagian besar": "Present, large share",
    "Ada": "Present", "Tidak ada": "Absent",
    "Listrik diusahakan oleh pemerintah": "Electricity provided by government",
    "Listrik diusahakan oleh non-pemerintah": "Electricity provided by non-government",
    "ton": "ton", "Ikan": "Fish", "Es": "Ice",
    # --- KDKMP calculator sheet titles / labels (high-value headers) ---
    "Ringkasan Dataset NTT": "NTT Dataset Summary",
    "Sumber File": "Source File", "Keterangan": "Description",
    "Rata-rata": "Mean", "Minimum": "Minimum", "Maksimum": "Maximum",
    "Std. Deviasi": "Std. Deviation",
    "Parameter": "Parameter", "Satuan": "Unit", "Nilai": "Value",
}

# Common commodity terms (substring translation inside commodity strings).
COMMODITY_TERMS = {
    "Padi sawah inbrida": "Inbred paddy rice", "Padi sawah hibrida": "Hybrid paddy rice",
    "Jagung lokal": "Local maize", "Jagung hibrida": "Hybrid maize",
    "Jagung Manis": "Sweet corn", "Jagung komposit": "Composite maize",
    "Ubi kayu": "Cassava", "Kacang tanah": "Peanut", "Bawang Merah": "Shallot",
    "Tomat": "Tomato", "Kelapa": "Coconut", "Kemiri": "Candlenut",
    "Sapi Potong: Sapi Bali": "Beef cattle: Bali cattle",
    "Petsai/Sawi Putih": "Chinese cabbage",
}


def translate_cell(value):
    """Translate a single cell value if it (or a known substring) is in the glossary."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s in GLOSSARY:
        return GLOSSARY[s]
    if s in COMMODITY_TERMS:
        return COMMODITY_TERMS[s]
    # substring pass for commodity strings
    for idn, en in COMMODITY_TERMS.items():
        if idn in value:
            return value.replace(idn, en)
    return value


def translate_workbook(src: Path, dst: Path) -> int:
    shutil.copyfile(src, dst)
    wb = openpyxl.load_workbook(dst)
    n = 0
    for ws in wb.worksheets:
        if ws.title in GLOSSARY:
            ws.title = GLOSSARY[ws.title][:31]   # Excel sheet-name limit
        for row in ws.iter_rows():
            for cell in row:
                new = translate_cell(cell.value)
                if new != cell.value:
                    cell.value = new
                    n += 1
    wb.save(dst)
    return n


def main():
    ap = argparse.ArgumentParser(description="Write English copies of the 3 source workbooks.")
    ap.add_argument("--src-dir", required=True)
    args = ap.parse_args()
    src = Path(args.src_dir)
    out = REPO / "data_indonesia" / "source_ntt" / "english"
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "Data potensi desa.xlsx": "Village_Potential_Data_EN.xlsx",
        "NTT_Data_Desa.xlsx": "NTT_Village_Dataset_EN.xlsx",
        "Kalkulator Desa Perikanan KDKMP_v6_editable.xlsx":
            "Fishing_Village_Calculator_KDKMP_EN.xlsx",
    }
    for idn, en in files.items():
        s = src / idn
        if not s.exists():
            print(f"  SKIP (missing): {idn}")
            continue
        n = translate_workbook(s, out / en)
        print(f"  {idn}  ->  {en}  ({n} cells translated)")
    print(f"English copies written to {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
