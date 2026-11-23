"""
Initialisation du package reader_core
"""
from reader_core.macro_splitter import split_sections
from reader_core.zone_pdf_generator import generate_zone_pdfs, extract_numero_and_date
from reader_core.avis_micro_splitter import segment_avis_annonces
from reader_core.pdf_reader_pipeline import process_single_pdf

__all__ = [
    "split_sections",
    "generate_zone_pdfs",
    "extract_numero_and_date",
    "segment_avis_annonces",
    "process_single_pdf",
]
