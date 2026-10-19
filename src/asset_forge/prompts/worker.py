"""Runs inside models/envs/promptgen: reads one JSON job on stdin, prints one JSON line."""

from __future__ import annotations

import json
import sys
import time


def main() -> None:
    job = json.load(sys.stdin)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(job["model"])
    use_gpu = torch.cuda.is_available()
    model = AutoModelForCausalLM.from_pretrained(
        job["model"],
        dtype=torch.bfloat16 if use_gpu else torch.float32,
        device_map="cuda" if use_gpu else None,
    ).eval()
    t1 = time.perf_counter()
    text = tok.apply_chat_template(
        job["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    ids = tok(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=job["max_new_tokens"], do_sample=False)
    answer = tok.decode(out[0][ids["input_ids"].shape[1] :], skip_special_tokens=True)
    t2 = time.perf_counter()
    vram = torch.cuda.max_memory_allocated() / 2**20 if use_gpu else 0
    print(
        json.dumps(
            {
                "text": answer,
                "load_s": round(t1 - t0, 2),
                "gen_s": round(t2 - t1, 2),
                "vram_mb": round(vram),
            }
        )
    )


if __name__ == "__main__":
    main()
