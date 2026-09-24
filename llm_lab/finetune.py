import argparse
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer


def load_model_and_tokenizer(model_name: str, load_4bit: bool):
    quant = None
    if load_4bit:
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype="bfloat16")
    tok = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_name, quantization_config=quant, device_map="auto")
    return model, tok


def lora_config():
    return LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )


def run_sft(args):
    model, tok = load_model_and_tokenizer(args.model, args.load_4bit)
    ds = load_dataset("json", data_files=args.data, split="train")
    cfg = SFTConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        max_length=args.max_length,
        dataset_text_field=args.text_field,
        report_to="none",
    )
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds, processing_class=tok, peft_config=lora_config())
    trainer.train()
    trainer.save_model(args.output)


def run_dpo(args):
    model, tok = load_model_and_tokenizer(args.model, args.load_4bit)
    ds = load_dataset("json", data_files=args.data, split="train")
    cfg = DPOConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        max_length=args.max_length,
        beta=args.beta,
        report_to="none",
    )
    trainer = DPOTrainer(model=model, args=cfg, train_dataset=ds, processing_class=tok, peft_config=lora_config())
    trainer.train()
    trainer.save_model(args.output)


def main():
    p = argparse.ArgumentParser(description="LoRA/QLoRA SFT and DPO")
    p.add_argument("mode", choices=["sft", "dpo"])
    p.add_argument("--model", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--max-length", type=int, default=1024)
    p.add_argument("--text-field", default="text")
    p.add_argument("--beta", type=float, default=0.1)
    p.add_argument("--load-4bit", action="store_true")
    args = p.parse_args()
    (run_sft if args.mode == "sft" else run_dpo)(args)


if __name__ == "__main__":
    main()
