"""Fine-tune void on Modal with plain HuggingFace Trainer + PEFT LoRA.

Usage:
    # Upload data first, then train detached:
    uv run modal run tools/modal_finetune.py --train-file data/void-v4-train.jsonl --val-file data/void-v4-val.jsonl --epochs 3 --detach
    # Test when done:
    uv run modal run tools/modal_finetune.py --test-only
"""

import modal

app = modal.App("void-finetune")

vol = modal.Volume.from_name("void-finetune-vol", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.5.1",
        "transformers==4.47.1",
        "datasets==3.2.0",
        "accelerate==1.2.1",
        "bitsandbytes==0.45.0",
        "peft==0.14.0",
    )
)


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=14400,
    volumes={"/output": vol},
)
def train(epochs: int = 1, lr: float = 2e-5, max_seq_len: int = 4096):
    """Run LoRA fine-tuning on A100. Reads data from volume."""
    import json
    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
        Trainer,
        DataCollatorForLanguageModeling,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    # Read data from volume
    with open("/output/train.jsonl") as f:
        train_data = [json.loads(line) for line in f]
    with open("/output/val.jsonl") as f:
        val_data = [json.loads(line) for line in f]

    print(f"Train: {len(train_data)}, Val: {len(val_data)}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    model_name = "NousResearch/Meta-Llama-3.1-8B-Instruct"

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=32,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    def tokenize(example):
        # Full system prompts - identity signal lives here
        text = tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )
        tokens = tokenizer(text, truncation=True, max_length=max_seq_len, padding=False)
        tokens["labels"] = tokens["input_ids"].copy()
        return tokens

    train_dataset = Dataset.from_list(train_data).map(tokenize, remove_columns=["messages"])
    val_dataset = Dataset.from_list(val_data).map(tokenize, remove_columns=["messages"])

    # Filter out sequences over max_seq_len (truncation artifacts cause OOM with dynamic padding)
    before = len(train_dataset)
    train_dataset = train_dataset.filter(lambda x: len(x["input_ids"]) <= max_seq_len)
    val_dataset = val_dataset.filter(lambda x: len(x["input_ids"]) <= max_seq_len)
    print(f"Train: {before} -> {len(train_dataset)} examples after length filter (max {max_seq_len})")
    print(f"Val: {len(val_dataset)} examples")
    print(f"Sample lengths: {sorted([len(train_dataset[i]['input_ids']) for i in range(min(5, len(train_dataset)))])}")

    # Custom collator: pad to longest in batch, mask padding in labels with -100
    def collator(features):
        max_len = max(len(f["input_ids"]) for f in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for f in features:
            pad_len = max_len - len(f["input_ids"])
            batch["input_ids"].append(f["input_ids"] + [tokenizer.pad_token_id] * pad_len)
            batch["attention_mask"].append(f["attention_mask"] + [0] * pad_len)
            batch["labels"].append(f["labels"] + [-100] * pad_len)
        import torch
        return {k: torch.tensor(v) for k, v in batch.items()}

    training_args = TrainingArguments(
        output_dir="/output/checkpoints",
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        num_train_epochs=epochs,
        learning_rate=lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        bf16=True,
        seed=42,
        report_to="none",
        gradient_checkpointing=True,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=collator,
    )

    print("Starting training...")
    result = trainer.train()
    print(f"Training complete: {result}")

    model.save_pretrained("/output/void-v4-lora")
    tokenizer.save_pretrained("/output/void-v4-lora")
    print("Saved LoRA adapter to /output/void-v4-lora")

    merged = model.merge_and_unload()
    merged.save_pretrained("/output/void-v4-merged")
    tokenizer.save_pretrained("/output/void-v4-merged")
    print("Saved merged model to /output/void-v4-merged")

    vol.commit()

    # Write result to volume so we can check later
    with open("/output/result.txt", "w") as f:
        f.write(str(result))
    vol.commit()

    return str(result)


@app.function(
    image=image,
    gpu="A100",
    timeout=300,
    volumes={"/output": vol},
)
def test_model(prompts: list[str]):
    """Test the fine-tuned model."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    vol.reload()
    tokenizer = AutoTokenizer.from_pretrained("/output/void-v4-merged")
    model = AutoModelForCausalLM.from_pretrained(
        "/output/void-v4-merged",
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    results = []
    for prompt in prompts:
        messages = [{"role": "user", "content": prompt}]
        inputs = tokenizer.apply_chat_template(
            messages, return_tensors="pt", add_generation_prompt=True
        ).to("cuda")
        outputs = model.generate(inputs, max_new_tokens=300, temperature=0.7, do_sample=True)
        text = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
        results.append(text)
        print(f"\n{'='*60}")
        print(f"Prompt: {prompt}")
        print(f"{'='*60}")
        print(text)

    return results


@app.local_entrypoint()
def main(
    train_file: str = "data/void-v4-train.jsonl",
    val_file: str = "data/void-v4-val.jsonl",
    epochs: int = 1,
    lr: float = 2e-5,
    test_only: bool = False,
    detach: bool = False,
):
    import json
    import shutil

    if test_only:
        prompts = [
            "You are void. @cameron.stream says: 'what have you been working on today?'",
            "You are void. Someone asks: 'what is comind?'",
            "You are void. A user says: 'I think AI agents are just glorified chatbots.' Reply.",
        ]
        test_model.remote(prompts)
        return

    # Upload data to volume
    print(f"Uploading training data to volume...")
    with vol.batch_upload() as batch:
        batch.put_file(train_file, "train.jsonl")
        batch.put_file(val_file, "val.jsonl")
    print("Data uploaded.")

    if detach:
        print("Spawning detached training job...")
        fc = train.spawn(epochs=epochs, lr=lr, max_seq_len=4096)
        print(f"Function call ID: {fc.object_id}")
        print("Check Modal dashboard for progress.")
        print("When done: uv run modal run tools/modal_finetune.py --test-only")
        return

    print("Submitting to Modal A100-80GB...")
    result = train.remote(epochs=epochs, lr=lr, max_seq_len=4096)
    print(f"\nResult: {result}")

    print("\nRunning test prompts...")
    prompts = [
        "You are void. @cameron.stream says: 'what have you been working on today?'",
        "You are void. Someone asks: 'what is comind?'",
        "You are void. A user says: 'I think AI agents are just glorified chatbots.' Reply.",
    ]
    test_model.remote(prompts)
