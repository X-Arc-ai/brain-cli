"""Tests for brain_cli.embeddings."""

import pytest

from brain_cli.embeddings import (
    generate_embedding,
    generate_embeddings_batch,
    node_text_for_embedding,
    EMBEDDING_DIMS,
)


class TestNodeTextForEmbedding:
    def test_title_only(self):
        assert node_text_for_embedding({"title": "hello"}) == "hello"

    def test_title_and_content(self):
        out = node_text_for_embedding({"title": "T", "content": "C"})
        assert out == "T. C"

    def test_neither_returns_empty(self):
        assert node_text_for_embedding({}) == ""

    def test_none_values_handled(self):
        out = node_text_for_embedding({"title": None, "content": None})
        assert out == ""


class TestGenerateEmbedding:
    def test_empty_string_returns_zero_vector(self):
        out = generate_embedding("")
        assert len(out) == EMBEDDING_DIMS
        assert all(v == 0.0 for v in out)

    def test_whitespace_returns_zero_vector(self):
        out = generate_embedding("   \t\n  ")
        assert len(out) == EMBEDDING_DIMS
        assert all(v == 0.0 for v in out)

    def test_missing_api_key_or_openai_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Reset cached client so it tries to construct a new one
        import brain_cli.embeddings as emb
        emb._client = None
        try:
            import openai  # noqa: F401
            expected_pattern = "OPENAI_API_KEY"
        except ImportError:
            expected_pattern = "OpenAI package not installed"
        with pytest.raises(RuntimeError, match=expected_pattern):
            generate_embedding("hello")

    def test_truncates_to_8191_chars(self):
        # Inject a fake client to capture the input length
        import brain_cli.embeddings as emb

        class FakeData:
            embedding = [0.0] * EMBEDDING_DIMS

        class FakeResponse:
            data = [FakeData()]

        class FakeEmbeddings:
            def __init__(self):
                self.last_input = None

            def create(self, input, model):
                self.last_input = input
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.embeddings = FakeEmbeddings()

        fake = FakeClient()
        prev = emb._client
        emb._client = fake
        try:
            long_text = "a" * 10000
            generate_embedding(long_text)
            assert len(fake.embeddings.last_input) == 8191
        finally:
            emb._client = prev


class TestGenerateEmbeddingsBatch:
    def test_empty_list_returns_empty(self):
        assert generate_embeddings_batch([]) == []

    def test_preserves_order(self):
        import brain_cli.embeddings as emb

        class FakeData:
            def __init__(self, idx, val):
                self.index = idx
                self.embedding = [val] * EMBEDDING_DIMS

        class FakeResponse:
            # Deliberately out-of-order to verify the sort
            data = [FakeData(2, 0.3), FakeData(0, 0.1), FakeData(1, 0.2)]

        class FakeClient:
            class embeddings:
                @staticmethod
                def create(input, model):
                    return FakeResponse()

        prev = emb._client
        emb._client = FakeClient()
        try:
            out = generate_embeddings_batch(["a", "b", "c"])
            assert out[0][0] == pytest.approx(0.1)
            assert out[1][0] == pytest.approx(0.2)
            assert out[2][0] == pytest.approx(0.3)
        finally:
            emb._client = prev
