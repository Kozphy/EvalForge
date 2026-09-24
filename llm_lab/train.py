import argparse
from pathlib import Path
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer

from llm_lab.model import GPTConfig, TinyGPT


class TokenBlockDataset(Dataset):
    def __init__(self, token_ids, block_size):
        usable = max(0, len(token_ids) - block_size - 1)
        self.tokens = torch.tensor(token_ids, dtype=torch.long)
        self.block_size = block_size
        self.length = usable // block_size

    def __len__(self):
        return self.length

    def __getitem__(self, i):
        start = i * self.block_size
        chunk = self.tokens[start : start + self.block_size + 1]
        return chunk[:-1], chunk[1:]


def load_texts(path: str):
    p = Path(path)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    parts = []
    for f in sorted(p.rglob("*.txt")):
        parts.append(f.read_text(encoding="utf-8"))
    if not parts:
        raise FileNotFoundError(f"no .txt files found under {path}")
    return "\n\n".join(parts)


def train(args):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)
    text = load_texts(args.data)
    ids = tokenizer.encode(text, add_special_tokens=False)
    cfg = GPTConfig(
        vocab_size=len(tokenizer),
        block_size=args.block_size,
        n_layer=args.layers,
        n_head=args.heads,
        n_embd=args.embd,
        dropout=args.dropout,
    )
    model = TinyGPT(cfg).to(device)
    ds = TokenBlockDataset(ids, cfg.block_size)
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=True, drop_last=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.1)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")

    model.train()
    step = 0
    for epoch in range(args.epochs):
        for x, y in dl:
            x, y = x.to(device), y.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=device == "cuda"):
                _, loss = model(x, y)
            scaler.scale(loss).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            step += 1
            if step % args.log_every == 0:
                print(f"epoch={epoch} step={step} loss={loss.item():.4f}")
            if args.max_steps and step >= args.max_steps:
                break
        if args.max_steps and step >= args.max_steps:
            break

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"config": cfg.__dict__, "model": model.state_dict(), "tokenizer": args.tokenizer}, out)
    print(f"saved {out} params={model.num_parameters():,}")


def main():
    p = argparse.ArgumentParser(description="TinyGPT pretraining / continued pretraining")
    p.add_argument("--data", required=True)
    p.add_argument("--output", default="artifacts/tinygpt.pt")
    p.add_argument("--tokenizer", default="gpt2")
    p.add_argument("--block-size", type=int, default=256)
    p.add_argument("--layers", type=int, default=6)
    p.add_argument("--heads", type=int, default=6)
    p.add_argument("--embd", type=int, default=384)
    p.add_argument("--dropout", type=float, default=0.0)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--log-every", type=int, default=10)
    train(p.parse_args())


if __name__ == "__main__":
    main()
