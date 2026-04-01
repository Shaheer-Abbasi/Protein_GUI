from core.db_definitions import (
    LOCAL_NUCLEOTIDE_DEFAULT,
    REMOTE_NUCLEOTIDE_DEFAULT,
    get_blastn_databases,
    get_default_blastn_database,
    is_remote_blastn_database_supported,
)


def test_remote_blastn_database_list_is_curated():
    remote_dbs = get_blastn_databases(True)

    assert REMOTE_NUCLEOTIDE_DEFAULT in remote_dbs
    assert "16S_ribosomal_RNA" not in remote_dbs


def test_blastn_default_database_depends_on_source():
    assert get_default_blastn_database(True) == REMOTE_NUCLEOTIDE_DEFAULT
    assert get_default_blastn_database(False) == LOCAL_NUCLEOTIDE_DEFAULT


def test_remote_blastn_support_check():
    assert is_remote_blastn_database_supported("core_nt") is True
    assert is_remote_blastn_database_supported("16S_ribosomal_RNA") is False
