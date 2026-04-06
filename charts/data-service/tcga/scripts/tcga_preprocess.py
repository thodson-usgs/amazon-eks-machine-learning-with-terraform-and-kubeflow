#!/usr/bin/env python3
"""
TCGA Open-Access Data Preprocessing Pipeline
=============================================
Downloads raw TCGA data from the AWS Open Data Registry (s3://tcga-2-open)
and the GDC API, then preprocesses it into general-purpose, analysis-ready
Parquet files organized by project (cancer type).

Output structure:
    {output_dir}/
        {PROJECT_ID}/                   # e.g. TCGA-BRCA
            clinical.parquet            # One row per case (patient)
            expression_matrix.parquet   # Genes × samples (raw counts)
            mutations.parquet           # Long-format somatic mutations
            copy_number.parquet         # Gene-level copy number scores
            mirna_expression.parquet    # miRNA expression quantification
            file_manifest.parquet       # Maps file UUIDs to case/sample IDs
        metadata/
            projects.parquet            # All TCGA project summaries
            gene_id_mapping.parquet     # Ensembl ID ↔ gene symbol
            sample_type_codes.parquet   # TCGA sample type code reference
            processing_log.json         # Run metadata and statistics

Requirements:
    pip install pandas pyarrow requests tqdm

Usage:
    python tcga_preprocess.py --output-dir /efs/data/tcga_processed
    python tcga_preprocess.py --output-dir /efs/data/tcga_processed --projects TCGA-BRCA TCGA-COAD
    python tcga_preprocess.py --output-dir /efs/data/tcga_processed --skip-download
"""

import argparse
import gzip
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Third-party imports (installed at runtime if missing)
# ---------------------------------------------------------------------------
def _ensure_packages():
    """Install required packages if they are not already available."""
    required = {"pandas": "pandas", "pyarrow": "pyarrow", "tqdm": "tqdm"}
    missing = []
    for imp_name, pip_name in required.items():
        try:
            __import__(imp_name)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q"]
            + missing
        )

_ensure_packages()

import pandas as pd  # noqa: E402
from tqdm import tqdm  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tcga_preprocess")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GDC_API = "https://api.gdc.cancer.gov"
S3_BUCKET = "tcga-2-open"
S3_REGION = "us-east-1"

# TCGA sample-type code reference
SAMPLE_TYPE_CODES = {
    "01": "Primary Solid Tumor",
    "02": "Recurrent Solid Tumor",
    "03": "Primary Blood Derived Cancer - Peripheral Blood",
    "04": "Recurrent Blood Derived Cancer - Bone Marrow",
    "05": "Additional - New Primary",
    "06": "Metastatic",
    "07": "Additional Metastatic",
    "10": "Blood Derived Normal",
    "11": "Solid Tissue Normal",
    "12": "Buccal Cell Normal",
    "13": "EBV Immortalized Normal",
    "14": "Bone Marrow Normal",
    "20": "Control Analyte",
    "40": "Recurrent Blood Derived Cancer - Peripheral Blood",
    "50": "Cell Lines",
    "60": "Primary Xenograft Tissue",
    "61": "Cell Line Derived Xenograft Tissue",
}

# Clinical fields to request from the GDC cases endpoint
CLINICAL_FIELDS = [
    "case_id",
    "submitter_id",
    "project.project_id",
    "project.name",
    "project.primary_site",
    "project.disease_type",
    "demographic.gender",
    "demographic.race",
    "demographic.ethnicity",
    "demographic.year_of_birth",
    "demographic.year_of_death",
    "demographic.vital_status",
    "demographic.days_to_death",
    "demographic.age_at_index",
    "diagnoses.diagnosis_id",
    "diagnoses.primary_diagnosis",
    "diagnoses.age_at_diagnosis",
    "diagnoses.classification_of_tumor",
    "diagnoses.days_to_last_follow_up",
    "diagnoses.days_to_last_known_disease_status",
    "diagnoses.days_to_recurrence",
    "diagnoses.last_known_disease_status",
    "diagnoses.morphology",
    "diagnoses.prior_malignancy",
    "diagnoses.site_of_resection_or_biopsy",
    "diagnoses.tissue_or_organ_of_origin",
    "diagnoses.tumor_grade",
    "diagnoses.tumor_stage",
    "diagnoses.ajcc_clinical_stage",
    "diagnoses.ajcc_pathologic_stage",
    "diagnoses.ajcc_pathologic_t",
    "diagnoses.ajcc_pathologic_n",
    "diagnoses.ajcc_pathologic_m",
    "diagnoses.icd_10_code",
    "diagnoses.year_of_diagnosis",
    "diagnoses.treatments.treatment_type",
    "exposures.alcohol_history",
    "exposures.alcohol_intensity",
    "exposures.bmi",
    "exposures.cigarettes_per_day",
    "exposures.pack_years_smoked",
    "exposures.tobacco_smoking_status",
    "exposures.years_smoked",
    "follow_ups.days_to_follow_up",
    "follow_ups.vital_status",
    "follow_ups.progression_or_recurrence",
]

# GDC files endpoint fields for building the file→case manifest
FILE_MANIFEST_FIELDS = [
    "file_id",
    "file_name",
    "data_category",
    "data_type",
    "data_format",
    "experimental_strategy",
    "analysis.workflow_type",
    "cases.case_id",
    "cases.submitter_id",
    "cases.samples.sample_id",
    "cases.samples.submitter_id",
    "cases.samples.sample_type",
    "cases.samples.tissue_type",
    "cases.samples.tumor_descriptor",
    "cases.project.project_id",
    "file_size",
    "access",
    "md5sum",
]

# Open-access data categories on the S3 bucket
OPEN_DATA_TYPES = [
    "Clinical Supplement",
    "Biospecimen Supplement",
    "Gene Expression Quantification",
    "miRNA-Seq Isoform Expression Quantification",
    "miRNA Expression Quantification",
    "Genotyping Array Copy Number Segment",
    "Genotyping Array Masked Copy Number Segment",
    "Genotyping Array Gene Level Copy Number Scores",
    "Masked Somatic Mutation",
]


# ═══════════════════════════════════════════════════════════════════════════
#  GDC API helpers
# ═══════════════════════════════════════════════════════════════════════════

def gdc_request(endpoint: str, params: dict | None = None,
                post_data: dict | None = None, retries: int = 3) -> dict:
    """Make a request to the GDC API with retry logic."""
    url = f"{GDC_API}/{endpoint}"
    for attempt in range(retries):
        try:
            if post_data is not None:
                data = json.dumps(post_data).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            else:
                if params:
                    url = f"{url}?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(url)

            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            if attempt < retries - 1:
                wait = 2 ** attempt * 5
                log.warning("GDC API error (%s), retrying in %ds…", exc, wait)
                time.sleep(wait)
            else:
                raise RuntimeError(f"GDC API request failed after {retries} attempts: {exc}") from exc
    return {}  # unreachable


def gdc_paginate(endpoint: str, fields: list[str], filters: dict | None = None,
                 page_size: int = 500) -> list[dict]:
    """Paginate through all results from a GDC endpoint."""
    all_hits = []
    offset = 0
    total = None
    while True:
        post_body: dict = {
            "fields": ",".join(fields),
            "from": offset,
            "size": page_size,
            "format": "json",
        }
        if filters:
            post_body["filters"] = filters
        resp = gdc_request(endpoint, post_data=post_body)
        data = resp.get("data", {})
        hits = data.get("hits", [])
        if total is None:
            total = data.get("pagination", {}).get("total", 0)
            log.info("  %s: %d total records", endpoint, total)
        all_hits.extend(hits)
        offset += page_size
        if offset >= total or not hits:
            break
    return all_hits


# ═══════════════════════════════════════════════════════════════════════════
#  Step 1: Discover TCGA projects
# ═══════════════════════════════════════════════════════════════════════════

def fetch_tcga_projects() -> pd.DataFrame:
    """Fetch all TCGA project summaries from the GDC API."""
    log.info("Fetching TCGA project list from GDC…")
    filters = {
        "op": "in",
        "content": {
            "field": "program.name",
            "value": ["TCGA"],
        },
    }
    hits = gdc_paginate(
        "projects",
        fields=[
            "project_id", "name", "primary_site", "disease_type",
            "summary.case_count", "summary.file_count",
            "summary.data_categories.data_category",
            "summary.data_categories.file_count",
        ],
        filters=filters,
        page_size=100,
    )
    rows = []
    for h in hits:
        rows.append({
            "project_id": h.get("project_id"),
            "name": h.get("name"),
            "primary_site": ", ".join(h.get("primary_site", [])) if isinstance(h.get("primary_site"), list) else h.get("primary_site"),
            "disease_type": ", ".join(h.get("disease_type", [])) if isinstance(h.get("disease_type"), list) else h.get("disease_type"),
            "case_count": h.get("summary", {}).get("case_count", 0),
            "file_count": h.get("summary", {}).get("file_count", 0),
        })
    df = pd.DataFrame(rows).sort_values("project_id").reset_index(drop=True)
    log.info("Found %d TCGA projects", len(df))
    return df


# ═══════════════════════════════════════════════════════════════════════════
#  Step 2: Download raw data from S3
# ═══════════════════════════════════════════════════════════════════════════

def download_from_s3(raw_dir: str, projects: list[str] | None = None) -> None:
    """
    Download open-access TCGA files from s3://tcga-2-open using the AWS CLI.

    The S3 bucket is organized by UUID folders. We download everything and
    then map files to projects during preprocessing. If *projects* is given,
    we first build a file manifest from the GDC API and download only the
    UUIDs that belong to the requested projects.
    """
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)

    # Check for aws cli
    try:
        subprocess.run(["aws", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        log.info("AWS CLI not found — installing via pip…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q", "awscli"]
        )

    if projects:
        # Selective download: get file UUIDs for requested projects only
        log.info("Building download manifest for projects: %s", projects)
        manifest = _build_download_manifest(projects)
        manifest_path = raw_path / "download_manifest.tsv"
        manifest.to_csv(manifest_path, sep="\t", index=False)
        log.info("Manifest contains %d files across %d projects", len(manifest), len(projects))

        # Download each UUID folder
        for file_id in tqdm(manifest["file_id"], desc="Downloading from S3"):
            dest = raw_path / file_id
            if dest.exists() and any(dest.iterdir()):
                continue  # already downloaded
            cmd = [
                "aws", "s3", "sync",
                f"s3://{S3_BUCKET}/{file_id}/",
                str(dest) + "/",
                "--no-sign-request",
                "--region", S3_REGION,
                "--quiet",
            ]
            subprocess.run(cmd, capture_output=True)
    else:
        # Full download — sync the entire bucket
        log.info("Downloading entire s3://%s to %s (this may take hours)…", S3_BUCKET, raw_dir)
        cmd = [
            "aws", "s3", "sync",
            f"s3://{S3_BUCKET}/",
            str(raw_path) + "/",
            "--no-sign-request",
            "--region", S3_REGION,
        ]
        subprocess.run(cmd, check=True)

    log.info("S3 download complete → %s", raw_dir)


def _build_download_manifest(projects: list[str]) -> pd.DataFrame:
    """Query GDC for open-access file UUIDs belonging to the given projects."""
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.project.project_id", "value": projects}},
            {"op": "=",  "content": {"field": "access", "value": "open"}},
        ],
    }
    hits = gdc_paginate(
        "files",
        fields=["file_id", "file_name", "data_type", "data_category", "file_size",
                "cases.project.project_id"],
        filters=filters,
        page_size=1000,
    )
    rows = []
    for h in hits:
        proj = ""
        for c in h.get("cases", []):
            p = c.get("project", {}).get("project_id", "")
            if p:
                proj = p
                break
        rows.append({
            "file_id": h["file_id"],
            "file_name": h.get("file_name", ""),
            "data_type": h.get("data_type", ""),
            "data_category": h.get("data_category", ""),
            "file_size": h.get("file_size", 0),
            "project_id": proj,
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
#  Step 3: Build file→case manifest from GDC
# ═══════════════════════════════════════════════════════════════════════════

def build_file_manifest(projects: list[str] | None = None) -> pd.DataFrame:
    """
    Query the GDC API for open-access TCGA files and return a manifest
    mapping each file UUID to its case, sample, data type, and project.
    """
    log.info("Building file-to-case manifest from GDC API…")
    filters: dict = {
        "op": "and",
        "content": [
            {"op": "=",  "content": {"field": "access", "value": "open"}},
        ],
    }
    project_filter = {
        "op": "in",
        "content": {"field": "cases.project.project_id",
                     "value": projects if projects else ["TCGA-%"]},
    }
    if projects:
        filters["content"].append(project_filter)
    else:
        # Filter for TCGA program
        filters["content"].append({
            "op": "=",
            "content": {"field": "cases.project.program.name", "value": "TCGA"},
        })

    hits = gdc_paginate("files", fields=FILE_MANIFEST_FIELDS, filters=filters, page_size=1000)

    rows = []
    for h in hits:
        base = {
            "file_id": h.get("file_id"),
            "file_name": h.get("file_name"),
            "data_category": h.get("data_category"),
            "data_type": h.get("data_type"),
            "data_format": h.get("data_format"),
            "experimental_strategy": h.get("experimental_strategy"),
            "workflow_type": (h.get("analysis") or {}).get("workflow_type"),
            "file_size": h.get("file_size"),
            "access": h.get("access"),
            "md5sum": h.get("md5sum"),
        }
        cases = h.get("cases", [{}])
        for case in cases:
            case_row = {
                **base,
                "case_id": case.get("case_id"),
                "case_submitter_id": case.get("submitter_id"),
                "project_id": (case.get("project") or {}).get("project_id"),
            }
            samples = case.get("samples", [{}])
            for samp in samples:
                rows.append({
                    **case_row,
                    "sample_id": samp.get("sample_id"),
                    "sample_submitter_id": samp.get("submitter_id"),
                    "sample_type": samp.get("sample_type"),
                    "tissue_type": samp.get("tissue_type"),
                    "tumor_descriptor": samp.get("tumor_descriptor"),
                })

    df = pd.DataFrame(rows)
    log.info("File manifest: %d rows, %d unique files", len(df), df["file_id"].nunique())
    return df


# ═══════════════════════════════════════════════════════════════════════════
#  Step 4: Fetch clinical data from GDC
# ═══════════════════════════════════════════════════════════════════════════

def fetch_clinical_data(project_id: str) -> pd.DataFrame:
    """
    Fetch clinical metadata for all cases in a TCGA project from the
    GDC cases endpoint. Flattens the nested JSON into a single row per case.
    """
    log.info("  Fetching clinical data for %s…", project_id)
    filters = {
        "op": "=",
        "content": {"field": "project.project_id", "value": project_id},
    }
    hits = gdc_paginate("cases", fields=CLINICAL_FIELDS, filters=filters, page_size=500)

    rows = []
    for h in hits:
        row: dict = {
            "case_id": h.get("case_id"),
            "submitter_id": h.get("submitter_id"),
            "project_id": (h.get("project") or {}).get("project_id"),
            "project_name": (h.get("project") or {}).get("name"),
            "primary_site": _join_or_str((h.get("project") or {}).get("primary_site")),
            "disease_type": _join_or_str((h.get("project") or {}).get("disease_type")),
        }
        # Demographic (flat — one per case)
        demo = h.get("demographic") or {}
        for key in ["gender", "race", "ethnicity", "year_of_birth", "year_of_death",
                     "vital_status", "days_to_death", "age_at_index"]:
            row[f"demographic_{key}"] = demo.get(key)

        # Diagnosis (take the first / primary diagnosis)
        diags = h.get("diagnoses") or [{}]
        diag = diags[0] if diags else {}
        for key in ["diagnosis_id", "primary_diagnosis", "age_at_diagnosis",
                     "classification_of_tumor", "days_to_last_follow_up",
                     "days_to_last_known_disease_status", "days_to_recurrence",
                     "last_known_disease_status", "morphology", "prior_malignancy",
                     "site_of_resection_or_biopsy", "tissue_or_organ_of_origin",
                     "tumor_grade", "tumor_stage",
                     "ajcc_clinical_stage", "ajcc_pathologic_stage",
                     "ajcc_pathologic_t", "ajcc_pathologic_n", "ajcc_pathologic_m",
                     "icd_10_code", "year_of_diagnosis"]:
            row[f"diagnosis_{key}"] = diag.get(key)

        # Treatments from the first diagnosis
        treatments = diag.get("treatments") or []
        row["treatment_types"] = "; ".join(
            t.get("treatment_type", "") for t in treatments if t.get("treatment_type")
        ) or None

        # Exposures (take the first)
        exps = h.get("exposures") or [{}]
        exp = exps[0] if exps else {}
        for key in ["alcohol_history", "alcohol_intensity", "bmi",
                     "cigarettes_per_day", "pack_years_smoked",
                     "tobacco_smoking_status", "years_smoked"]:
            row[f"exposure_{key}"] = exp.get(key)

        # Follow-ups: take the most recent by days_to_follow_up
        fups = h.get("follow_ups") or []
        if fups:
            fups_sorted = sorted(fups, key=lambda f: f.get("days_to_follow_up") or 0, reverse=True)
            latest = fups_sorted[0]
            row["latest_followup_days"] = latest.get("days_to_follow_up")
            row["latest_followup_vital_status"] = latest.get("vital_status")
            row["latest_followup_progression"] = latest.get("progression_or_recurrence")
        else:
            row["latest_followup_days"] = None
            row["latest_followup_vital_status"] = None
            row["latest_followup_progression"] = None

        # Compute overall survival fields for convenience
        row["os_time"] = (
            row["demographic_days_to_death"]
            if row["demographic_days_to_death"] is not None
            else row["diagnosis_days_to_last_follow_up"]
        )
        row["os_event"] = 1 if row["demographic_vital_status"] == "Dead" else 0

        rows.append(row)

    df = pd.DataFrame(rows)
    log.info("  Clinical data: %d cases for %s", len(df), project_id)
    return df


def _join_or_str(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


# ═══════════════════════════════════════════════════════════════════════════
#  Step 5: Process gene expression data
# ═══════════════════════════════════════════════════════════════════════════

def process_expression(raw_dir: str, manifest: pd.DataFrame,
                       project_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read individual STAR gene expression quantification TSVs and
    consolidate into a genes × samples expression matrix (raw counts).

    Returns (expression_matrix, gene_id_mapping).
    """
    log.info("  Processing gene expression for %s…", project_id)
    expr_files = manifest[
        (manifest["project_id"] == project_id)
        & (manifest["data_type"] == "Gene Expression Quantification")
    ].drop_duplicates(subset="file_id")

    if expr_files.empty:
        log.warning("  No expression files found for %s", project_id)
        return pd.DataFrame(), pd.DataFrame()

    gene_map: dict[str, str] = {}  # ENSG → gene_name
    sample_counts: dict[str, dict[str, int]] = {}

    for _, row in tqdm(expr_files.iterrows(), total=len(expr_files),
                       desc=f"  Expression ({project_id})", leave=False):
        file_id = row["file_id"]
        file_name = row["file_name"]
        case_submitter = row.get("case_submitter_id", "")
        sample_submitter = row.get("sample_submitter_id", "")
        sample_label = sample_submitter or case_submitter or file_id

        fpath = _find_data_file(raw_dir, file_id, file_name)
        if fpath is None:
            continue

        try:
            df = _read_tsv_flexible(fpath)
        except Exception as exc:
            log.debug("  Could not read %s: %s", fpath, exc)
            continue

        if df.empty:
            continue

        # Identify columns — the STAR augmented format has:
        # gene_id, gene_name, gene_type, unstranded, stranded_first, stranded_second, ...
        gene_id_col = _find_col(df, ["gene_id", "Ensembl_ID"])
        gene_name_col = _find_col(df, ["gene_name", "gene_symbol"])
        count_col = _find_col(df, ["unstranded", "expected_count", "raw_count",
                                    "read_count", "HTSeq - Counts"])

        if gene_id_col is None or count_col is None:
            # Fallback: legacy HTSeq format (two columns: gene_id, count)
            if len(df.columns) == 2:
                gene_id_col = df.columns[0]
                count_col = df.columns[1]
            else:
                log.debug("  Unrecognised expression format in %s", file_name)
                continue

        # Filter out metadata rows (N_unmapped, N_multimapping, etc.)
        mask = df[gene_id_col].astype(str).str.startswith("ENSG")
        df = df.loc[mask].copy()
        if df.empty:
            continue

        # Strip version suffix from Ensembl IDs
        df["gene_id_clean"] = df[gene_id_col].astype(str).str.replace(r"\.\d+$", "", regex=True)

        # Build gene name mapping
        if gene_name_col and gene_name_col in df.columns:
            for gid, gname in zip(df["gene_id_clean"], df[gene_name_col]):
                if gid not in gene_map and pd.notna(gname):
                    gene_map[gid] = str(gname)

        # Store counts
        counts = dict(zip(df["gene_id_clean"], pd.to_numeric(df[count_col], errors="coerce").fillna(0).astype(int)))
        sample_counts[sample_label] = counts

    if not sample_counts:
        return pd.DataFrame(), pd.DataFrame()

    # Build matrix
    log.info("  Assembling expression matrix (%d samples)…", len(sample_counts))
    expr_matrix = pd.DataFrame(sample_counts).fillna(0).astype(int)
    expr_matrix.index.name = "gene_id"

    # Gene mapping table
    gene_mapping = pd.DataFrame([
        {"gene_id": gid, "gene_name": gname}
        for gid, gname in gene_map.items()
    ])

    log.info("  Expression matrix: %d genes × %d samples", expr_matrix.shape[0], expr_matrix.shape[1])
    return expr_matrix, gene_mapping


# ═══════════════════════════════════════════════════════════════════════════
#  Step 6: Process somatic mutations (MAF)
# ═══════════════════════════════════════════════════════════════════════════

# Key columns to retain from MAF files
MAF_KEEP_COLS = [
    "Hugo_Symbol", "Entrez_Gene_Id", "NCBI_Build", "Chromosome",
    "Start_Position", "End_Position", "Strand", "Variant_Classification",
    "Variant_Type", "Reference_Allele", "Tumor_Seq_Allele1", "Tumor_Seq_Allele2",
    "Tumor_Sample_Barcode", "Matched_Norm_Sample_Barcode",
    "HGVSc", "HGVSp", "HGVSp_Short", "IMPACT", "SIFT", "PolyPhen",
    "t_depth", "t_ref_count", "t_alt_count",
    "n_depth", "n_ref_count", "n_alt_count",
    "FILTER",
]


def process_mutations(raw_dir: str, manifest: pd.DataFrame,
                      project_id: str) -> pd.DataFrame:
    """
    Read masked somatic mutation (MAF) files and consolidate into a
    single long-format mutation table.
    """
    log.info("  Processing somatic mutations for %s…", project_id)
    mut_files = manifest[
        (manifest["project_id"] == project_id)
        & (manifest["data_type"].isin(["Masked Somatic Mutation", "Somatic Mutation"]))
    ].drop_duplicates(subset="file_id")

    if mut_files.empty:
        log.warning("  No mutation files found for %s", project_id)
        return pd.DataFrame()

    frames = []
    for _, row in tqdm(mut_files.iterrows(), total=len(mut_files),
                       desc=f"  Mutations ({project_id})", leave=False):
        fpath = _find_data_file(raw_dir, row["file_id"], row["file_name"])
        if fpath is None:
            continue
        try:
            df = _read_tsv_flexible(fpath, comment="#")
            if df.empty:
                continue
            # Keep only the columns that exist
            keep = [c for c in MAF_KEEP_COLS if c in df.columns]
            df = df[keep].copy()
            df["source_file_id"] = row["file_id"]
            # Extract case ID from barcode (first 12 chars: TCGA-XX-XXXX)
            if "Tumor_Sample_Barcode" in df.columns:
                df["case_submitter_id"] = df["Tumor_Sample_Barcode"].astype(str).str[:12]
            frames.append(df)
        except Exception as exc:
            log.debug("  Could not read MAF %s: %s", fpath, exc)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["project_id"] = project_id
    log.info("  Mutations: %d variants for %s", len(result), project_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Step 7: Process copy number data
# ═══════════════════════════════════════════════════════════════════════════

def process_copy_number(raw_dir: str, manifest: pd.DataFrame,
                        project_id: str) -> pd.DataFrame:
    """
    Read gene-level copy number scores and/or copy number segment files.
    """
    log.info("  Processing copy number data for %s…", project_id)
    cn_files = manifest[
        (manifest["project_id"] == project_id)
        & (manifest["data_type"].isin([
            "Gene Level Copy Number",
            "Gene Level Copy Number Scores",
            "Copy Number Segment",
            "Masked Copy Number Segment",
        ]))
    ].drop_duplicates(subset="file_id")

    if cn_files.empty:
        log.warning("  No copy number files found for %s", project_id)
        return pd.DataFrame()

    frames = []
    for _, row in tqdm(cn_files.iterrows(), total=len(cn_files),
                       desc=f"  Copy Number ({project_id})", leave=False):
        fpath = _find_data_file(raw_dir, row["file_id"], row["file_name"])
        if fpath is None:
            continue
        try:
            df = _read_tsv_flexible(fpath)
            if df.empty:
                continue
            df["file_id"] = row["file_id"]
            df["data_type"] = row["data_type"]
            df["case_submitter_id"] = row.get("case_submitter_id", "")
            df["sample_submitter_id"] = row.get("sample_submitter_id", "")
            frames.append(df)
        except Exception as exc:
            log.debug("  Could not read CN file %s: %s", fpath, exc)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["project_id"] = project_id
    log.info("  Copy number: %d rows for %s", len(result), project_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Step 8: Process miRNA expression
# ═══════════════════════════════════════════════════════════════════════════

def process_mirna(raw_dir: str, manifest: pd.DataFrame,
                  project_id: str) -> pd.DataFrame:
    """Read miRNA expression quantification files."""
    log.info("  Processing miRNA expression for %s…", project_id)
    mi_files = manifest[
        (manifest["project_id"] == project_id)
        & (manifest["data_type"].isin([
            "miRNA Expression Quantification",
            "Isoform Expression Quantification",
        ]))
    ].drop_duplicates(subset="file_id")

    if mi_files.empty:
        log.warning("  No miRNA files found for %s", project_id)
        return pd.DataFrame()

    frames = []
    for _, row in tqdm(mi_files.iterrows(), total=len(mi_files),
                       desc=f"  miRNA ({project_id})", leave=False):
        fpath = _find_data_file(raw_dir, row["file_id"], row["file_name"])
        if fpath is None:
            continue
        try:
            df = _read_tsv_flexible(fpath)
            if df.empty:
                continue
            df["file_id"] = row["file_id"]
            df["case_submitter_id"] = row.get("case_submitter_id", "")
            df["sample_submitter_id"] = row.get("sample_submitter_id", "")
            frames.append(df)
        except Exception as exc:
            log.debug("  Could not read miRNA file %s: %s", fpath, exc)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["project_id"] = project_id
    log.info("  miRNA: %d rows for %s", len(result), project_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  File I/O helpers
# ═══════════════════════════════════════════════════════════════════════════

def _find_data_file(raw_dir: str, file_id: str, file_name: str) -> str | None:
    """
    Locate a downloaded data file. GDC downloads create a directory per
    file UUID containing the actual data file.
    """
    raw = Path(raw_dir)

    # Standard GDC layout: raw_dir/UUID/filename
    candidate = raw / file_id / file_name
    if candidate.exists():
        return str(candidate)

    # Sometimes the file is directly in raw_dir/UUID/ (single file)
    uuid_dir = raw / file_id
    if uuid_dir.is_dir():
        data_files = [f for f in uuid_dir.iterdir()
                      if f.is_file() and f.name != "logs" and not f.name.endswith(".parcel")]
        if len(data_files) == 1:
            return str(data_files[0])
        # Try matching by extension
        for f in data_files:
            if f.suffix in (".tsv", ".maf", ".txt", ".gz"):
                return str(f)

    # Also check raw_dir/filename directly
    direct = raw / file_name
    if direct.exists():
        return str(direct)

    # Search recursively (slower, last resort)
    matches = list(raw.rglob(file_name))
    if matches:
        return str(matches[0])

    return None


def _read_tsv_flexible(fpath: str, comment: str | None = None) -> pd.DataFrame:
    """Read a TSV file, handling gzip and various header styles."""
    path = Path(fpath)

    opener = gzip.open if path.suffix == ".gz" or path.name.endswith(".gz") else open
    mode = "rt" if path.suffix == ".gz" or path.name.endswith(".gz") else "r"

    with opener(fpath, mode) as fh:
        # Skip comment lines at the top
        lines = []
        header_found = False
        for line in fh:
            if comment and line.startswith(comment) and not header_found:
                continue
            header_found = True
            lines.append(line)

    if not lines:
        return pd.DataFrame()

    text = "".join(lines)
    return pd.read_csv(StringIO(text), sep="\t", low_memory=False, na_values=["", "NA", "--"])


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name from candidates that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    # Case-insensitive fallback
    lower_map = {col.lower(): col for col in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def preprocess(
    raw_dir: str,
    output_dir: str,
    projects: list[str] | None = None,
    skip_download: bool = False,
    skip_expression: bool = False,
):
    """
    Main orchestration function.

    1. Fetch project metadata from GDC.
    2. Download raw data from S3 (unless --skip-download).
    3. Build file manifest from GDC API.
    4. For each project: extract clinical, expression, mutation, CNV, miRNA.
    5. Write analysis-ready Parquet files.
    """
    start_time = datetime.now(timezone.utc)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta_dir = out / "metadata"
    meta_dir.mkdir(exist_ok=True)

    stats: dict = {"started_at": start_time.isoformat(), "projects": {}}

    # ── 1. Project metadata ──────────────────────────────────────────────
    projects_df = fetch_tcga_projects()
    projects_df.to_parquet(meta_dir / "projects.parquet", index=False)
    log.info("Saved project metadata → %s", meta_dir / "projects.parquet")

    if projects:
        valid = set(projects_df["project_id"]) & set(projects)
        invalid = set(projects) - valid
        if invalid:
            log.warning("Unknown project IDs (skipping): %s", invalid)
        project_ids = sorted(valid)
    else:
        project_ids = sorted(projects_df["project_id"].tolist())

    log.info("Processing %d projects: %s", len(project_ids), project_ids)

    # ── 2. Download raw data ─────────────────────────────────────────────
    if not skip_download:
        download_from_s3(raw_dir, projects=project_ids)
    else:
        log.info("Skipping S3 download (--skip-download)")

    # ── 3. Build file manifest ───────────────────────────────────────────
    manifest = build_file_manifest(projects=project_ids)
    manifest.to_parquet(meta_dir / "file_manifest_full.parquet", index=False)

    # ── 4. Sample type codes reference ───────────────────────────────────
    sample_types_df = pd.DataFrame([
        {"code": k, "sample_type": v} for k, v in SAMPLE_TYPE_CODES.items()
    ])
    sample_types_df.to_parquet(meta_dir / "sample_type_codes.parquet", index=False)

    # ── 5. Process each project ──────────────────────────────────────────
    all_gene_maps = []

    for pid in project_ids:
        log.info("═" * 60)
        log.info("Processing %s", pid)
        log.info("═" * 60)
        proj_dir = out / pid
        proj_dir.mkdir(exist_ok=True)
        proj_stats: dict = {}

        # Clinical
        try:
            clinical_df = fetch_clinical_data(pid)
            if not clinical_df.empty:
                clinical_df.to_parquet(proj_dir / "clinical.parquet", index=False)
                proj_stats["clinical_cases"] = len(clinical_df)
        except Exception as exc:
            log.error("  Clinical data failed for %s: %s", pid, exc)
            proj_stats["clinical_error"] = str(exc)

        # Gene expression
        if not skip_expression:
            try:
                expr_df, gene_map_df = process_expression(raw_dir, manifest, pid)
                if not expr_df.empty:
                    expr_df.to_parquet(proj_dir / "expression_matrix.parquet")
                    proj_stats["expression_genes"] = expr_df.shape[0]
                    proj_stats["expression_samples"] = expr_df.shape[1]
                if not gene_map_df.empty:
                    all_gene_maps.append(gene_map_df)
            except Exception as exc:
                log.error("  Expression processing failed for %s: %s", pid, exc)
                proj_stats["expression_error"] = str(exc)

        # Somatic mutations
        try:
            mut_df = process_mutations(raw_dir, manifest, pid)
            if not mut_df.empty:
                mut_df.to_parquet(proj_dir / "mutations.parquet", index=False)
                proj_stats["mutation_variants"] = len(mut_df)
        except Exception as exc:
            log.error("  Mutation processing failed for %s: %s", pid, exc)
            proj_stats["mutation_error"] = str(exc)

        # Copy number
        try:
            cn_df = process_copy_number(raw_dir, manifest, pid)
            if not cn_df.empty:
                cn_df.to_parquet(proj_dir / "copy_number.parquet", index=False)
                proj_stats["copy_number_rows"] = len(cn_df)
        except Exception as exc:
            log.error("  Copy number processing failed for %s: %s", pid, exc)
            proj_stats["copy_number_error"] = str(exc)

        # miRNA expression
        try:
            mirna_df = process_mirna(raw_dir, manifest, pid)
            if not mirna_df.empty:
                mirna_df.to_parquet(proj_dir / "mirna_expression.parquet", index=False)
                proj_stats["mirna_rows"] = len(mirna_df)
        except Exception as exc:
            log.error("  miRNA processing failed for %s: %s", pid, exc)
            proj_stats["mirna_error"] = str(exc)

        # Per-project file manifest slice
        proj_manifest = manifest[manifest["project_id"] == pid]
        if not proj_manifest.empty:
            proj_manifest.to_parquet(proj_dir / "file_manifest.parquet", index=False)

        stats["projects"][pid] = proj_stats
        log.info("  ✓ %s complete", pid)

    # ── 6. Consolidated gene ID mapping ──────────────────────────────────
    if all_gene_maps:
        gene_map_combined = pd.concat(all_gene_maps, ignore_index=True).drop_duplicates(subset="gene_id")
        gene_map_combined.to_parquet(meta_dir / "gene_id_mapping.parquet", index=False)
        log.info("Gene ID mapping: %d genes → %s", len(gene_map_combined),
                 meta_dir / "gene_id_mapping.parquet")

    # ── 7. Processing log ────────────────────────────────────────────────
    end_time = datetime.now(timezone.utc)
    stats["finished_at"] = end_time.isoformat()
    stats["duration_seconds"] = (end_time - start_time).total_seconds()
    stats["output_dir"] = str(output_dir)
    stats["raw_dir"] = str(raw_dir)
    stats["total_projects_processed"] = len(project_ids)

    log_path = meta_dir / "processing_log.json"
    with open(log_path, "w") as f:
        json.dump(stats, f, indent=2, default=str)

    log.info("═" * 60)
    log.info("PREPROCESSING COMPLETE")
    log.info("  Output: %s", output_dir)
    log.info("  Projects: %d", len(project_ids))
    log.info("  Duration: %.1f minutes", stats["duration_seconds"] / 60)
    log.info("  Log: %s", log_path)
    log.info("═" * 60)


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TCGA Open-Access Data Preprocessing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./tcga_processed",
        help="Directory for analysis-ready Parquet output (default: ./tcga_processed)",
    )
    parser.add_argument(
        "--raw-dir", "-r",
        default="./tcga_raw",
        help="Directory for raw S3 downloads (default: ./tcga_raw)",
    )
    parser.add_argument(
        "--projects", "-p",
        nargs="+",
        default=None,
        help="Specific TCGA project IDs to process (e.g. TCGA-BRCA TCGA-COAD). "
             "Default: all 33 projects.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip S3 download (use existing raw data in --raw-dir)",
    )
    parser.add_argument(
        "--skip-expression",
        action="store_true",
        help="Skip gene expression processing (large and slow)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    preprocess(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        projects=args.projects,
        skip_download=args.skip_download,
        skip_expression=args.skip_expression,
    )
