# Open-Source LLMs for Local Inference (≤ 16 GB VRAM)

_Compiled 2026-11-03 from a live web search plus prior knowledge. Many sources are blogs or vendor-adjacent, so treat figures as indicative and verify on the model cards and on your own hardware._

## Requirements

- Local inference possible
- Fits in 16 GB VRAM (4-bit quantized, with room for KV cache)
- Open-source / open-weight license
- Good reasoning and summarization accuracy
- Handles long context
- Strong benchmarks

## Shortlist

| Model | Size | VRAM (quantized) | Context | License | Notes |
|---|---|---|---|---|---|
| **gpt-oss-20b** (OpenAI) | 21B MoE (~3.6B active) | ~12–14 GB (native MXFP4; GGUF ≈ 12.1 GB) | 128K | Apache 2.0 | Top pick in most 16 GB guides. Reported ~42 tok/s at ~13.7 GB VRAM, stable up to 60K context. Adjustable reasoning effort and good tool use. |
| **Gemma 4 12B** (Google, Apr 2026) | 12B | ~8 GB quantized (FP16 needs ~24 GB, so use a quant) | long (128K+) | Apache 2.0 | MMLU-Pro ≈ 77, GPQA Diamond ≈ 78.8, LiveCodeBench v6 ≈ 72. Multimodal and multilingual. Best all-rounder. |
| **Qwen 3.5 9B** (Alibaba, Feb–Mar 2026) | 9B | ~5 GB (Q4_K_M) | long | Apache 2.0 | GPQA ≈ 81.7 per one list. Better tool calling than Gemma 4 12B in an independent 16 GB test. Best for agents. |
| **Gemma 4 26B A4B** | 26B MoE (~4B active) | ~14–16 GB at Q4 (tight) | long | Apache 2.0 | Larger option. Verify the fit and the KV-cache headroom. |
| **Devstral Small 2** (Mistral) | ~24B | ~14.5 GB (Q4_K_M) | long | Check model card | Coding-focused. Uses nearly all 16 GB, so little room for context. |
| **Qwen3-14B** | 14B | ~9–10 GB | 32K (131K with YaRN) | Apache 2.0 | Hybrid thinking / non-thinking mode. Strong summarization and math. |
| **Phi-4 / Phi-4-reasoning** (Microsoft) | 14B | ~9–10 GB | 16–32K | MIT | Very strong reasoning for its size, but short context. |
| **Mistral Small 3.2** | 24B | ~14 GB | 128K | Apache 2.0 | Accurate instruction following and summaries. |
| **Gemma 3 27B QAT** | 27B | ~14–15 GB | 128K | Gemma terms | Strong summarization. Older generation. |

The Qwen3-14B, Phi-4, Mistral Small 3.2 and Gemma 3 rows come from prior knowledge, not this search. Verify them before relying on them.

## Notes from the search

- Gemma 4 launched on 2026-04-02 under Apache 2.0 in 31B, 26B A4B, 12B, 4B and ~2B sizes.
- Qwen's newer 3.6 and 3.8 lines reportedly have no open model below 27B, so **Qwen 3.5** is the small-model option in that family. A 27B model at Q4 is about 18 GB and will not fit 16 GB without offload.
- Artificial Analysis Intelligence Index (sub-32B): Qwen3.5 27B (Reasoning) scores 42 using 98M output tokens. Gemma 4 31B (Reasoning) scores 39 using 39M. Gemma 4 is more token-efficient and Qwen has the higher raw score. Neither fits 16 GB without heavy quantization.
- I could not verify a "Qwen3.8-27B" model name against a primary source.
- The search gave little 2026 data on Llama, so I excluded it. Llama 3.1 8B remains an option with a mature ecosystem but lower reasoning.

## Recommendations

| Need | Pick |
|---|---|
| Best overall reasoning + speed | **gpt-oss-20b** |
| Best all-rounder / summarization / multimodal | **Gemma 4 12B** |
| Agents / tool calling / smallest footprint | **Qwen 3.5 9B** |
| Max reasoning, short context | **Phi-4-reasoning** |
| Coding | **Devstral Small 2** (tight on VRAM) |

For the LinkedIn lead agent (LLM judge, planner and summaries), start with **Qwen 3.5 9B** or **gpt-oss-20b**. Both give reliable structured JSON output and tool use.

## Practical tips

- Long context costs VRAM. A 128K KV cache can add 5–10+ GB. Use KV-cache quantization (q8) or cap the context to 32–64K.
- Runtimes: llama.cpp, Ollama, LM Studio, Jan, vLLM (AWQ/GPTQ) and SGLang.
- Benchmark on your own task before committing. Public leaderboards don't measure lead-qualification quality.

## Sources

- [Best Local LLMs for 16GB VRAM: Practical Performance Testing 2026](https://localllm.in/blog/best-local-llms-16gb-vram)
- [Best Open-Source LLMs to Self-Host in 2026: VRAM Tier Guide](https://www.spheron.network/blog/best-open-source-llms-self-host-2026-vram-guide/)
- [Best Local LLM by VRAM: 8, 12, 16, 24 and 32 GB (2026)](https://vdf.ai/blog/best-local-llm-by-vram/)
- [Best Local AI & LLMs 2026: Tier List by VRAM](https://www.promptquorum.com/local-llms)
- [Sub-32B Open Weights (Artificial Analysis)](https://artificialanalysis.ai/articles/sub-32b-open-weights)
- [Gemma 4 vs Qwen 3.5: E4B, 12B, 26B, 31B Benchmark Matchups](https://gemma4all.com/blog/gemma-4-vs-qwen-3-5-benchmarks)
- [Gemma vs Qwen (2026)](https://www.betterclaw.io/blog/gemma-4-vs-qwen-3-5)
- [xigh/open-weight-models (GitHub)](https://github.com/xigh/open-weight-models)
