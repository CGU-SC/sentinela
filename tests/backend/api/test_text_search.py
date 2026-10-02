import polars as pl

from backend.api.utils.text_search import apply_token_search, normalize_search_text, tokenize_search_text


def test_search_text_normalizes_unicode_accents_case_and_whitespace():
    assert normalize_search_text(None) == ""
    assert normalize_search_text("  João   DA   Silva ") == "joao da silva"
    assert normalize_search_text(123) == "123"
    assert tokenize_search_text(None) == []
    assert tokenize_search_text("A de São Paulo") == ["de", "sao", "paulo"]
    assert tokenize_search_text("A B C", min_length=1) == ["a", "b", "c"]


def test_token_search_matches_every_token_across_available_columns_and_is_literal():
    frame = pl.DataFrame(
        {
            "nome": ["Farmácia São Paulo", "São Paulo Farmácia", None, "Farma.* de Minas"],
            "cidade": ["Campinas", "", "São Paulo", "Ouro Preto"],
            "ignore": ["x", "x", "x", "x"],
        }
    )
    filtered = apply_token_search(frame, "sao farmacia", ["nome", "cidade", "missing"])
    assert filtered.get_column("nome").to_list() == ["Farmácia São Paulo", "São Paulo Farmácia"]
    assert filtered.columns == frame.columns
    literal = apply_token_search(frame, ".*", ["nome"], min_token_length=1)
    assert literal.height == 1 and literal.item(0, "nome") == "Farma.* de Minas"


def test_token_search_returns_original_frame_for_no_tokens_empty_rows_or_missing_columns():
    frame = pl.DataFrame({"nome": ["Ana"]})
    assert apply_token_search(frame, "x", ["nome"]) is frame
    assert apply_token_search(frame.head(0), "ana", ["nome"]).is_empty()
    assert apply_token_search(frame, "ana", ["missing"]) is frame
