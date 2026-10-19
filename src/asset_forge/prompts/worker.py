"""Runs inside models/envs/promptgen: reads one JSON job on stdin, prints one JSON line."""

from __future__ import annotations

import json
import sys
import time


def main() -> None:
    """Load the model once, then answer one JSON job per input line until stdin closes."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = sys.argv[1]
    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(model_id)
    use_gpu = torch.cuda.is_available()
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        dtype=torch.bfloat16 if use_gpu else torch.float32,
        device_map="cuda" if use_gpu else None,
    ).eval()
    load_s = round(time.perf_counter() - t0, 2)
    print(json.dumps({"ready": True, "load_s": load_s}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        t1 = time.perf_counter()
        text = tok.apply_chat_template(
            job["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        ids = tok(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=job["max_new_tokens"], do_sample=False)
        answer = tok.decode(out[0][ids["input_ids"].shape[1] :], skip_special_tokens=True)
        vram = torch.cuda.max_memory_allocated() / 2**20 if use_gpu else 0
        reply = {
            "text": answer,
            "load_s": load_s,
            "gen_s": round(time.perf_counter() - t1, 2),
            "vram_mb": round(vram),
        }
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
