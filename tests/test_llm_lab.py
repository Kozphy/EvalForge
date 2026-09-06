import torch
from llm_lab.model import GPTConfig, TinyGPT
from llm_lab.rag_agent import Document, LocalRetriever


def test_tinygpt_forward_shape_and_loss():
    cfg = GPTConfig(vocab_size=128, block_size=16, n_layer=2, n_head=2, n_embd=32)
    model = TinyGPT(cfg)
    x = torch.randint(0, cfg.vocab_size, (2, 8))
    logits, loss = model(x, x)
    assert logits.shape == (2, 8, cfg.vocab_size)
    assert loss is not None and torch.isfinite(loss)


def test_generation_grows_sequence():
    cfg = GPTConfig(vocab_size=64, block_size=8, n_layer=1, n_head=2, n_embd=16)
    model = TinyGPT(cfg)
    x = torch.randint(0, cfg.vocab_size, (1, 4))
    y = model.generate(x, max_new_tokens=3, top_k=10)
    assert y.shape == (1, 7)


def test_local_retriever_prefers_relevant_finance_doc():
    r = LocalRetriever([
        Document("cashflow", "Free cash flow equals operating cash flow less capital expenditures."),
        Document("nft", "An NFT is a non-fungible blockchain token."),
    ])
    hits = r.search("How do I calculate free cash flow?", k=1)
    assert hits[0][0].id == "cashflow"
