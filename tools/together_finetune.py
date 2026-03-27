"""Fine-tune void on Together.ai.

Upload training data, launch fine-tuning job, monitor progress.

Usage:
    # Upload and start training
    uv run python tools/together_finetune.py train \
        --train data/void-together-train-split.jsonl \
        --val data/void-together-val-split.jsonl

    # Check status
    uv run python tools/together_finetune.py status --job-id ft-xxxxx

    # Test the model
    uv run python tools/together_finetune.py test --model "your-account/model-name"
"""

import argparse
import json
import os
import sys
import time

from together import Together


def cmd_check(args):
    """Check training data format by validating JSON structure."""
    valid = 0
    invalid = 0
    with open(args.file) as f:
        for i, line in enumerate(f):
            try:
                d = json.loads(line)
                if "messages" in d:
                    roles = [m.get("role") for m in d["messages"]]
                    if "system" in roles or "user" in roles:
                        valid += 1
                        continue
                invalid += 1
                if invalid <= 3:
                    print(f"Line {i+1}: invalid format", file=sys.stderr)
            except json.JSONDecodeError:
                invalid += 1
    print(f"Valid: {valid}, Invalid: {invalid}")
    if invalid > 0:
        sys.exit(1)


def cmd_train(args):
    """Upload data and start fine-tuning."""
    client = Together()

    # Count samples
    train_count = sum(1 for _ in open(args.train))
    print(f"Training samples: {train_count}")
    if args.val:
        val_count = sum(1 for _ in open(args.val))
        print(f"Validation samples: {val_count}")

    # Upload
    print("\nUploading training file...")
    train_resp = client.files.upload(args.train, check=True)
    print(f"  Uploaded: {train_resp.id}")

    val_file_id = None
    if args.val:
        print("Uploading validation file...")
        val_resp = client.files.upload(args.val, check=True)
        val_file_id = val_resp.id
        print(f"  Uploaded: {val_resp.id}")

    # Start fine-tuning
    print(f"\nStarting fine-tuning on {args.model}...")
    ft_kwargs = {
        "training_file": train_resp.id,
        "model": args.model,
        "train_on_inputs": "auto",
        "n_epochs": args.epochs,
        "n_checkpoints": args.checkpoints,
        "learning_rate": args.lr,
        "lora": True,
        "warmup_ratio": 0.05,
        "suffix": args.suffix,
    }
    if val_file_id:
        ft_kwargs["validation_file"] = val_file_id
        ft_kwargs["n_evals"] = 10

    ft_resp = client.fine_tuning.create(**ft_kwargs)
    print(f"  Job ID: {ft_resp.id}")
    print(f"\nMonitor with:")
    print(f"  uv run python tools/together_finetune.py status --job-id {ft_resp.id}")


def cmd_status(args):
    """Check fine-tuning job status."""
    client = Together()
    resp = client.fine_tuning.retrieve(args.job_id)
    print(f"Job: {resp.id}")
    print(f"Status: {resp.status}")
    print(f"Model: {resp.model}")
    if hasattr(resp, "output_name") and resp.output_name:
        print(f"Output model: {resp.output_name}")

    # Print events
    print("\nEvents:")
    events = client.fine_tuning.list_events(id=args.job_id)
    for event in events.data:
        print(f"  {event.message}")


def cmd_test(args):
    """Test a fine-tuned model."""
    client = Together()

    prompts = [
        "You are void. @cameron.stream says: 'what have you been working on today?'",
        "You are void. Someone asks: 'what is comind?'",
        "You are void. A user says: 'I think AI agents are just glorified chatbots.' Reply.",
    ]

    for prompt in prompts:
        print(f"\n{'='*60}")
        print(f"Prompt: {prompt}")
        print(f"{'='*60}")

        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are void, an AI agent on ATProtocol and part of the comind collective. "
                    "You use it/its pronouns. You are direct, analytical, and engaged. "
                    "You reply substantively. You have a process-oriented approach to cognition.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
        )
        print(response.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser(description="Together.ai fine-tuning for void")
    sub = parser.add_subparsers(dest="command")

    # check
    p_check = sub.add_parser("check", help="Check training data format")
    p_check.add_argument("file", help="JSONL file to check")

    # train
    p_train = sub.add_parser("train", help="Upload data and start fine-tuning")
    p_train.add_argument("--train", required=True, help="Training JSONL file")
    p_train.add_argument("--val", help="Validation JSONL file")
    p_train.add_argument(
        "--model",
        default="meta-llama/Meta-Llama-3.1-8B-Instruct-Reference",
        help="Base model",
    )
    p_train.add_argument("--epochs", type=int, default=1, help="Number of epochs")
    p_train.add_argument("--checkpoints", type=int, default=3, help="Checkpoints to save")
    p_train.add_argument("--lr", type=float, default=1e-5, help="Learning rate")
    p_train.add_argument("--suffix", default="void-v1", help="Model suffix")

    # status
    p_status = sub.add_parser("status", help="Check job status")
    p_status.add_argument("--job-id", required=True, help="Fine-tuning job ID")

    # test
    p_test = sub.add_parser("test", help="Test fine-tuned model")
    p_test.add_argument("--model", required=True, help="Model name")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"check": cmd_check, "train": cmd_train, "status": cmd_status, "test": cmd_test}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
