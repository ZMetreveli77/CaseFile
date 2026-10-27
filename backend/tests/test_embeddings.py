"""The shared embedding model: loaded once and used by one thread at a time (fake model, no download)."""
import threading
import time

import fastembed
import numpy
import pytest

from casefile.retrieval.embeddings import EMBEDDING_BATCH_SIZE, FastEmbedEmbedder


class FakeTextEmbedding:
    """Counts how often it's created and how many calls overlap."""

    created = 0
    running = 0
    most_running_at_once = 0
    batch_sizes: list[int] = []

    def __init__(self, model_name):
        FakeTextEmbedding.created += 1
        time.sleep(0.05)  # loading takes a while, so two first requests overlap

    def track_overlap(self):
        FakeTextEmbedding.running += 1
        FakeTextEmbedding.most_running_at_once = max(FakeTextEmbedding.most_running_at_once, FakeTextEmbedding.running)
        time.sleep(0.01)
        FakeTextEmbedding.running -= 1

    def embed(self, texts, batch_size):
        FakeTextEmbedding.batch_sizes.append(len(texts))
        self.track_overlap()
        return [numpy.ones(3) for _ in texts]

    def query_embed(self, texts):
        self.track_overlap()
        return [numpy.ones(3) for _ in texts]


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    """A fresh fake for every test, so counts from one test don't leak into the next."""
    FakeTextEmbedding.created = FakeTextEmbedding.running = FakeTextEmbedding.most_running_at_once = 0
    FakeTextEmbedding.batch_sizes = []
    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)


def test_parallel_requests_load_the_model_once_and_never_embed_at_the_same_time():
    embedder = FastEmbedEmbedder()
    threads = [threading.Thread(target=embedder.embed_query, args=(f"question {number}",)) for number in range(5)]
    threads.append(threading.Thread(target=embedder.embed_documents, args=([f"chunk {n}" for n in range(10)],)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert FakeTextEmbedding.created == 1
    assert FakeTextEmbedding.most_running_at_once == 1
    # Documents are embedded in small batches (the lock is released between them, so questions don't wait long).
    assert FakeTextEmbedding.batch_sizes == [EMBEDDING_BATCH_SIZE, EMBEDDING_BATCH_SIZE, 10 - 2 * EMBEDDING_BATCH_SIZE]


def test_vectors_come_back_in_order_as_lists():
    vectors = FastEmbedEmbedder().embed_documents(["a", "b", "c", "d", "e"])
    assert vectors == [[1.0, 1.0, 1.0]] * 5
