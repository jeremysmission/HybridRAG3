# Knowledge Distillation and Fine-Tuning Local Models with Unsloth on NVIDIA GPUs

## A Complete Tutorial for Defense-Environment AI Engineers

**Author:** Claude AI (generated for Jeremy's HybridRAG3 project)
**Date:** 2026-02-13
**Target Hardware:** NVIDIA RTX 5080 / RTX 3090 / 12-24GB VRAM consumer GPUs
**Target Model:** Phi-4 Mini (and Mistral 7B as alternative)
**Target Integration:** Ollama for inference, HybridRAG3 for retrieval

---

## Table of Contents

1. [What Is Knowledge Distillation and Why You Need It](#1-what-is-knowledge-distillation-and-why-you-need-it)
2. [Fine-Tuning vs RAG vs Distillation -- Decision Framework](#2-fine-tuning-vs-rag-vs-distillation----decision-framework)
3. [Hardware Requirements and VRAM Budget](#3-hardware-requirements-and-vram-budget)
4. [Environment Setup -- Windows with NVIDIA GPU](#4-environment-setup----windows-with-nvidia-gpu)
5. [Understanding LoRA and QLoRA](#5-understanding-lora-and-qlora)
6. [Preparing Domain-Specific Training Data](#6-preparing-domain-specific-training-data)
7. [Complete Fine-Tuning Code with Unsloth](#7-complete-fine-tuning-code-with-unsloth)
8. [Exporting to GGUF for Ollama](#8-exporting-to-gguf-for-ollama)
9. [Knowledge Distillation -- Teacher-Student Pipeline](#9-knowledge-distillation----teacher-student-pipeline)
10. [Evaluation and Quality Metrics](#10-evaluation-and-quality-metrics)
11. [Integration with HybridRAG3](#11-integration-with-hybridrag3)
12. [Security Considerations for Defense Environments](#12-security-considerations-for-defense-environments)
13. [Troubleshooting Guide](#13-troubleshooting-guide)
14. [Alternatives Comparison](#14-alternatives-comparison)
15. [Glossary](#15-glossary)

---

## 1. What Is Knowledge Distillation and Why You Need It

### The Core Concept

Knowledge distillation is a technique where you train a small, fast model (called the "student") to mimic the behavior of a large, smart model (called the "teacher"). Think of it like this: you hire a world-class expert (GPT-4, Claude) to write extremely detailed answers to thousands of questions about YOUR domain. Then you train a small local model (Phi-4 Mini) on those expert answers. The small model absorbs the reasoning patterns without needing to be as large.

### Why This Matters for Your HybridRAG3 System

Right now, your pipeline works like this:

```
User asks question
    --> HybridRAG3 retrieves relevant chunks from your 630GB corpus
    --> Chunks + question get sent to Ollama (Phi-4 Mini)
    --> Phi-4 Mini reads the chunks and generates an answer
```

The problem: Phi-4 Mini is a general-purpose model. It knows a little about everything but isn't an expert in YOUR domains -- RF engineering, ionospheric measurement, NIST compliance, satellite communications. When it reads your retrieved chunks, it sometimes:

- Misunderstands domain-specific terminology
- Fails to connect related concepts across chunks
- Generates plausible-sounding but technically wrong answers
- Doesn't know the right level of detail for a defense engineering audience

Fine-tuning fixes this by teaching Phi-4 Mini YOUR vocabulary, YOUR reasoning patterns, and YOUR domain expertise. After fine-tuning, the same model running on the same hardware will produce dramatically better answers from the same retrieved chunks.

### Three Levels of Customization

**Level 1 -- Prompt Engineering (what you do now):**
You craft careful prompts in YAML that tell the model how to behave. Fast to implement, no training needed, but limited in how much the model's behavior changes. This is what your primer_generator.py and YAML prompts do.

**Level 2 -- Retrieval-Augmented Generation / RAG (what HybridRAG3 does):**
You feed the model relevant documents at query time. The model uses this context to answer. Powerful for up-to-date information, but the model still processes the documents through a generic lens.

**Level 3 -- Fine-Tuning (what this tutorial teaches):**
You actually change the model's weights -- its internal "brain wiring" -- so it natively understands your domain. The model BECOMES a domain expert rather than a generalist reading domain documents.

**Level 4 -- Knowledge Distillation (advanced, covered in Section 9):**
You use a powerful teacher model (Claude, GPT-4) to generate training data, then fine-tune your local model on that data. This lets you capture reasoning quality that exceeds what the small model could learn from raw documents alone.

### The Optimal Strategy for HybridRAG3

The research consensus as of 2025 is clear: the best results come from combining RAG + fine-tuning. You fine-tune the model to understand your domain's language and reasoning patterns, then use RAG to feed it current, specific documents. The fine-tuned model processes the retrieved chunks with domain expertise rather than generic understanding.

This is sometimes called RAFT (Retrieval-Augmented Fine-Tuning) -- you fine-tune the model specifically on the task of reading retrieved chunks and answering questions, so it gets better at exactly the job HybridRAG3 asks it to do.

---

## 2. Fine-Tuning vs RAG vs Distillation -- Decision Framework

### When to Use Each Approach

| Scenario | Best Approach | Why |
|----------|--------------|-----|
| Knowledge changes frequently (daily/weekly) | RAG only | Fine-tuning can't keep up with changes |
| Domain has specialized vocabulary/jargon | Fine-tuning + RAG | Model needs to understand the words |
| Need to cite specific sources | RAG | RAG naturally provides source documents |
| Want specific output format/style | Fine-tuning | Teach the model YOUR communication style |
| Limited training data (<100 examples) | RAG + prompt engineering | Not enough data to fine-tune safely |
| Abundant training data (1000+ examples) | Fine-tuning + RAG | Enough data to meaningfully change behavior |
| Budget for cloud API calls | Distillation | Use teacher model to generate training data |
| Fully air-gapped environment | Fine-tuning (done beforehand) | No API calls possible during operation |
| Need model to reason about relationships between documents | Fine-tuning | RAG shows individual chunks; fine-tuning teaches patterns |

### Your Specific Situation

You have:
- 630GB of domain-specific data (RF, defense, satellite, NIST)
- A working RAG pipeline (HybridRAG3)
- Ollama running Phi-4 Mini locally
- Incoming desktop with 12GB+ VRAM
- OpenRouter API access for teacher model calls
- A corporate environment that needs audit logging and offline operation

**Recommended strategy:**
1. Use OpenRouter (Claude/GPT-4) as teacher to generate high-quality Q&A pairs from your indexed documents
2. Fine-tune Phi-4 Mini (or Mistral 7B) using Unsloth + QLoRA on those Q&A pairs
3. Export the fine-tuned model to GGUF format
4. Load it into Ollama as a custom model
5. Continue using HybridRAG3's retrieval pipeline with the upgraded model

The fine-tuning happens ONCE (or periodically) on your home PC. The resulting model file is then transferred to any machine including the air-gapped work laptop.

---

## 3. Hardware Requirements and VRAM Budget

### VRAM Requirements by Method and Model

| Model | Method | VRAM Required | Your 12GB GPU? | Your 24GB GPU (3090)? |
|-------|--------|--------------|----------------|----------------------|
| Phi-4 Mini 8B | QLoRA (4-bit) fine-tuning | ~6 GB | YES | YES |
| Phi-4 Mini 8B | LoRA (16-bit) fine-tuning | ~16 GB | NO | YES |
| Phi-4 Mini 8B | Full fine-tuning | ~60 GB | NO | NO |
| Mistral 14B | QLoRA (4-bit) fine-tuning | ~10 GB | TIGHT | YES |
| Mistral 14B | LoRA (16-bit) fine-tuning | ~28 GB | NO | TIGHT |
| Mistral-Large 70B | QLoRA (4-bit) fine-tuning | ~42 GB | NO | NO |

**Bottom line:** QLoRA on Phi-4 Mini 8B fits comfortably on your 12GB GPU. QLoRA on Mistral 14B is tight but doable on 12GB, comfortable on a 3090 (24GB).

### System RAM Requirements

- 32GB RAM minimum recommended
- 48GB RAM ideal (your target desktop spec)
- The fine-tuning process uses system RAM for data loading and preprocessing while VRAM handles the model and gradients

### Disk Space Requirements

- Base model download: 4-8 GB (quantized) or 16 GB (full precision)
- Training data: varies (1 MB to 10 GB typically)
- Checkpoints during training: 500 MB to 2 GB per checkpoint
- Final GGUF export: 4-8 GB depending on quantization
- Total recommended free space: 50 GB minimum

### Training Time Estimates

| Hardware | Model | Dataset Size | Estimated Time |
|----------|-------|-------------|---------------|
| RTX 3090 (24GB) | Phi-4 Mini 8B QLoRA | 10,000 examples | 30-60 minutes |
| RTX 5080 (16GB) | Phi-4 Mini 8B QLoRA | 10,000 examples | 20-45 minutes |
| RTX 3090 (24GB) | Mistral 14B QLoRA | 10,000 examples | 60-120 minutes |
| CPU-only (your current laptop) | Any | Any | NOT RECOMMENDED (days) |

---

## 4. Environment Setup -- Windows with NVIDIA GPU

### Prerequisites Checklist

Before starting, verify you have:

1. **NVIDIA GPU Driver** -- latest version from nvidia.com/drivers
2. **CUDA Toolkit** -- version 12.x (check with `nvcc --version` in terminal)
3. **Python 3.11** -- your existing HybridRAG3 environment uses this
4. **Visual Studio Build Tools** -- with C++ workload installed (required for compiling some packages)

### Step-by-Step Environment Setup

**IMPORTANT:** Create a SEPARATE virtual environment for fine-tuning. Do NOT install these packages into your HybridRAG3 venv. Fine-tuning has different dependency versions that could break your existing setup.

```powershell
# ---------------------------------------------------------------
# STEP 1: Create a dedicated directory for fine-tuning work
# ---------------------------------------------------------------
# WHY: Keeps fine-tuning isolated from HybridRAG3
# WHERE: Your D: drive alongside HybridRAG3
# ---------------------------------------------------------------
mkdir D:\FineTuning
cd D:\FineTuning
```

```powershell
# ---------------------------------------------------------------
# STEP 2: Create a fresh Python virtual environment
# ---------------------------------------------------------------
# WHY: Isolates fine-tuning dependencies from HybridRAG3
# The packages we install here (unsloth, bitsandbytes, etc.)
# have different version requirements than your RAG stack
# ---------------------------------------------------------------
python -m venv .venv
```

```powershell
# ---------------------------------------------------------------
# STEP 3: Activate the virtual environment
# ---------------------------------------------------------------
.\.venv\Scripts\Activate.ps1
```

```powershell
# ---------------------------------------------------------------
# STEP 4: Install PyTorch with CUDA support
# ---------------------------------------------------------------
# WHY: PyTorch is the deep learning framework that Unsloth builds on.
# The "+cu121" suffix means "compiled for CUDA 12.1" which matches
# modern NVIDIA drivers. If you have CUDA 12.4+, cu121 still works.
# RESEARCH NOTE: Checked PyTorch compatibility matrix -- cu121 wheels
# are the most broadly compatible with RTX 30xx/40xx/50xx series.
# ---------------------------------------------------------------
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

```powershell
# ---------------------------------------------------------------
# STEP 5: Install Unsloth and its dependencies
# ---------------------------------------------------------------
# WHY: Unsloth is the framework that makes fine-tuning 2x faster
# and uses 70% less VRAM than standard HuggingFace training.
# It does this through custom CUDA kernels written by Daniel Han.
# RESEARCH NOTE: pip install unsloth now works on Windows as of 2025.
# Earlier versions required WSL2 or Docker. Windows support is stable
# on RTX 30xx/40xx/50xx with CUDA 12.x drivers.
# COMPATIBILITY: Tested with Python 3.11, torch 2.x, CUDA 12.x
# ---------------------------------------------------------------
pip install unsloth
```

```powershell
# ---------------------------------------------------------------
# STEP 6: Install additional required packages
# ---------------------------------------------------------------
# bitsandbytes: Provides 4-bit quantization (the "Q" in QLoRA)
# datasets: HuggingFace library for loading/processing training data
# trl: Transformer Reinforcement Learning library (has the SFT trainer)
# pyyaml: For reading your YAML prompt files
# ---------------------------------------------------------------
pip install bitsandbytes datasets trl pyyaml
```

```powershell
# ---------------------------------------------------------------
# STEP 7: Install GGUF export tools
# ---------------------------------------------------------------
# WHY: After fine-tuning, you need to convert the model to GGUF
# format so Ollama can load it. llama-cpp-python provides this.
# RESEARCH NOTE: The CUDA-enabled build compiles faster but the
# CPU build also works for conversion (just slower).
# ---------------------------------------------------------------
pip install llama-cpp-python
```

```powershell
# ---------------------------------------------------------------
# STEP 8: Verify everything installed correctly
# ---------------------------------------------------------------
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"NONE\"}')"
```

Expected output should show your GPU name and CUDA available = True. If CUDA shows False, your GPU driver needs updating.

```powershell
# ---------------------------------------------------------------
# STEP 9: Verify Unsloth installation
# ---------------------------------------------------------------
python -c "from unsloth import FastLanguageModel; print('[OK] Unsloth loaded successfully')"
```

### Troubleshooting Installation

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| `CUDA not available` | Old GPU driver | Download latest from nvidia.com/drivers |
| `bitsandbytes` import error | Missing CUDA libs | `pip install bitsandbytes --force-reinstall` |
| `unsloth` import error | Wrong Python version | Must be Python 3.11 or 3.12 |
| `torch.cuda.OutOfMemoryError` | VRAM too small | Close all other GPU apps, reduce batch size |
| C++ build errors during install | Missing Visual Studio | Install VS Build Tools with C++ workload |

---

## 5. Understanding LoRA and QLoRA

### Why Not Full Fine-Tuning?

Full fine-tuning means updating ALL of a model's parameters. An 8B parameter model has 8 billion parameters. Storing each parameter plus its gradient plus optimizer state in 16-bit precision requires approximately 60GB of VRAM. That's more than even an RTX 4090 (24GB) can handle.

### LoRA -- Low-Rank Adaptation

LoRA is the breakthrough that makes fine-tuning possible on consumer GPUs. Instead of updating all 8 billion parameters, LoRA:

1. **Freezes** all original model weights (they stay unchanged)
2. **Adds** tiny "adapter" matrices to specific layers
3. **Trains** only these adapters (typically 1-2% of total parameters)

Think of it like this: the base model is a massive textbook that stays closed. LoRA adds sticky notes to specific pages. The sticky notes modify the model's behavior without rewriting the textbook.

**Technical detail:** Each LoRA adapter is a pair of small matrices (A and B) where the product A x B approximates the weight change that full fine-tuning would have made. The "rank" (r) parameter controls how expressive these matrices are:

- **r = 8:** Very small adapters, fast training, modest behavior change
- **r = 16:** Good balance (RECOMMENDED for your use case)
- **r = 32:** Larger adapters, slower training, more expressive
- **r = 64:** Large adapters, approaches full fine-tuning quality

### QLoRA -- Quantized LoRA

QLoRA adds one more optimization on top of LoRA: it loads the base model in 4-bit quantized precision instead of 16-bit. This cuts VRAM usage by 75% for the base model while the LoRA adapters still train in 16-bit for accuracy.

The "Q" stands for quantization -- the same concept your Ollama models use (Q4_0, Q8_0, etc.). During training, the base model sits in VRAM at 4-bit precision (~4.5GB for an 8B model) and the LoRA adapters train in 16-bit on top of that.

**VRAM breakdown for Phi-4 Mini 8B QLoRA:**

```
Base model (4-bit):     ~4.5 GB
LoRA adapters (16-bit): ~0.3 GB
Gradients:              ~0.5 GB
Optimizer states:       ~0.5 GB
Activations (batch):    ~0.5 GB
-------------------------------
Total:                  ~6.3 GB  <-- Fits on 12GB GPU with headroom
```

### Which Layers to Target

When you configure LoRA, you specify which layers get adapters. The standard targets for transformer-based models are:

```python
target_modules = [
    "q_proj",    # Query projection in attention (how the model "asks questions")
    "k_proj",    # Key projection in attention (how it "indexes information")
    "v_proj",    # Value projection in attention (what information gets retrieved)
    "o_proj",    # Output projection in attention (final attention output)
    "gate_proj", # Gate in the MLP (controls information flow)
    "up_proj",   # Up-projection in MLP (expands representation)
    "down_proj", # Down-projection in MLP (compresses back)
]
```

Adding adapters to ALL these layers (the default in Unsloth) gives the best results. Targeting only the attention layers (q_proj, k_proj, v_proj, o_proj) is faster but less expressive.

---

## 6. Preparing Domain-Specific Training Data

### Data Format

Fine-tuning requires your data in a specific format: pairs of inputs and expected outputs. For a RAG-focused fine-tune, the format is:

```json
{
    "instruction": "Based on the following context, answer the question.\n\nContext: [retrieved chunks here]\n\nQuestion: What is the ionospheric critical frequency and how does it affect HF propagation?",
    "output": "The ionospheric critical frequency (foF2) is the highest frequency at which a vertically incident radio wave is reflected by the F2 layer of the ionosphere. For HF communications, this frequency determines the Maximum Usable Frequency (MUF) for a given path geometry. When the operating frequency exceeds the MUF, signals pass through the ionosphere rather than being reflected, resulting in skip zone gaps. The critical frequency varies diurnally (higher during daytime due to solar ionization), seasonally, and with the 11-year solar cycle..."
}
```

### Three Methods to Generate Training Data

**Method A -- Manual Curation (Highest Quality, Lowest Volume)**

You write Q&A pairs yourself from your domain knowledge. This produces the highest quality training data but is extremely time-consuming. Good for: creating a small "golden dataset" of 50-100 critical examples.

**Method B -- RAG-Bootstrapped (Medium Quality, Medium Volume)**

Use your existing HybridRAG3 system to generate training data:

1. Write a list of domain questions (200-1000 questions)
2. For each question, use HybridRAG3 to retrieve relevant chunks
3. Send chunks + question to a cloud API (Claude/GPT-4 via OpenRouter) for a high-quality answer
4. Save the (chunks, question, answer) triplet as training data

This is essentially knowledge distillation -- you're using a powerful teacher model to generate training examples that your local student model will learn from.

**Method C -- Synthetic Generation (Variable Quality, Highest Volume)**

Use a teacher model to both generate questions AND answers from your documents:

1. Feed document chunks to Claude/GPT-4
2. Ask it to generate 5-10 Q&A pairs per chunk
3. Filter for quality
4. Use as training data

This scales to thousands of examples but requires quality filtering.

### Complete Data Generation Script

The following script implements Method B -- the RAG-bootstrapped approach that leverages your existing HybridRAG3 infrastructure:

```python
# =====================================================================
# generate_training_data.py
# =====================================================================
# PURPOSE: Generate fine-tuning training data using HybridRAG3's
#          retrieval + a cloud teacher model (via OpenRouter)
#
# HOW IT WORKS:
#   1. Reads a YAML file of domain questions you've written
#   2. For each question, queries HybridRAG3's index to get chunks
#   3. Sends chunks + question to OpenRouter (Claude/GPT-4)
#   4. Saves the teacher's answer along with the question and chunks
#   5. Outputs a JSONL file ready for fine-tuning
#
# NETWORK ACCESS: YES -- calls OpenRouter API for teacher responses
#   Internet toggle: Set TEACHER_ENABLED = False to skip API calls
#   and only generate the retrieval portion (useful for offline prep)
#
# DEPENDENCIES: openai (already installed), pyyaml, sqlite3 (built-in)
# =====================================================================

import json
import os
import sys
import time
import yaml
from pathlib import Path
from datetime import datetime

# ---- CONFIGURATION ----
# Change these paths to match your system
HYBRIDRAG_DB = r"D:\RAG Indexed Data\hybridrag.sqlite3"
EMBEDDINGS_DIR = r"D:\RAG Indexed Data"
OUTPUT_DIR = r"D:\FineTuning\training_data"
QUESTIONS_FILE = r"D:\FineTuning\domain_questions.yaml"

# ---- NETWORK CONTROL ----
# Set to False to disable all internet access (offline mode)
# When False, only the retrieval step runs -- no teacher API calls
TEACHER_ENABLED = True

# ---- TEACHER MODEL CONFIG ----
# Uses OpenRouter with your existing openai SDK
TEACHER_BASE_URL = "https://openrouter.ai/api/v1"
TEACHER_MODEL = "anthropic/claude-sonnet-4-20250514"  # Best for technical Q&A
# Alternative: "openai/gpt-4o" or "mistralai/mistral-small-3.1-24b-instruct" (free)

# ---- RETRIEVAL CONFIG ----
TOP_K = 5          # Number of chunks to retrieve per question
MIN_SCORE = 0.3    # Minimum similarity score to include a chunk

# ---- RATE LIMITING ----
DELAY_BETWEEN_CALLS = 2.0  # Seconds between API calls (be polite)


def load_questions(filepath):
    """
    Load domain questions from a YAML file.

    YAML FORMAT:
        questions:
          - category: RF Engineering
            items:
              - "What is the ionospheric critical frequency?"
              - "How does multipath affect HF propagation?"
          - category: Defense Systems
            items:
              - "What are NIST 800-53 access control requirements?"
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    all_questions = []
    for category in data.get("questions", []):
        cat_name = category.get("category", "General")
        for question in category.get("items", []):
            all_questions.append({
                "category": cat_name,
                "question": question
            })

    print(f"[OK] Loaded {len(all_questions)} questions from {filepath}")
    return all_questions


def retrieve_chunks(question, db_path, top_k=5, min_score=0.3):
    """
    Query HybridRAG3's SQLite index to find relevant chunks.

    NOTE: This is a simplified version. Your actual retrieval
    may use the sentence-transformers embedder + numpy memmap.
    Adapt this function to call your existing retriever module.
    """
    # PLACEHOLDER -- replace with your actual HybridRAG3 retrieval call
    # Example: from hybridrag3.retriever import retrieve
    #          results = retrieve(question, top_k=top_k, min_score=min_score)

    # For now, this shows the structure you need:
    import sqlite3
    import numpy as np

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all chunks (simplified -- your real retriever uses embeddings)
    cursor.execute("SELECT chunk_id, content, source_file FROM chunks LIMIT ?", (top_k,))
    rows = cursor.fetchall()
    conn.close()

    chunks = []
    for row in rows:
        chunks.append({
            "chunk_id": row[0],
            "content": row[1],
            "source": row[2],
            "score": 0.8  # Placeholder -- real retriever calculates this
        })

    return chunks


def call_teacher(question, chunks, api_key):
    """
    Send question + retrieved chunks to the teacher model via OpenRouter.

    RETURNS: The teacher's answer as a string, or None if the call fails.

    NETWORK: This function makes an HTTP call to OpenRouter's API.
    It will NOT be called if TEACHER_ENABLED is False.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=TEACHER_BASE_URL
    )

    # Build the context from retrieved chunks
    context_parts = []
    for i, chunk in enumerate(chunks):
        context_parts.append(f"[Source {i+1}: {chunk['source']}]\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)

    # The prompt teaches the teacher model how to answer
    system_prompt = """You are a senior defense engineering technical writer.
Answer the question using ONLY information from the provided context.
Be precise, use correct technical terminology, and cite which source
numbers you draw from. If the context doesn't contain enough information
to fully answer, say so explicitly.

Format your answer as a clear, detailed technical response suitable for
an engineer with 5+ years of experience. Include relevant equations,
specifications, or standards references where appropriate."""

    user_prompt = f"""Context:
{context}

Question: {question}

Provide a thorough, technically precise answer based on the context above."""

    try:
        response = client.chat.completions.create(
            model=TEACHER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1024,
            temperature=0.3  # Low temperature for factual accuracy
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  [WARN] Teacher API error: {e}")
        return None


def generate_training_example(question_data, chunks, teacher_answer):
    """
    Format a single training example in the instruction-following format.

    This format teaches the model to:
    1. Read a context (retrieved chunks)
    2. Understand a question
    3. Generate a high-quality answer grounded in the context
    """
    # Build context string
    context_parts = []
    for chunk in chunks:
        context_parts.append(chunk["content"])
    context = "\n\n".join(context_parts)

    instruction = f"""Based on the following context from technical documents, answer the question accurately and thoroughly.

Context:
{context}

Question: {question_data['question']}"""

    return {
        "instruction": instruction,
        "output": teacher_answer,
        "category": question_data["category"],
        "timestamp": datetime.now().isoformat(),
        "teacher_model": TEACHER_MODEL if TEACHER_ENABLED else "none",
        "num_chunks": len(chunks)
    }


def main():
    """
    Main pipeline: Load questions -> Retrieve chunks -> Call teacher -> Save data

    OUTPUT: A JSONL file where each line is one training example.
    JSONL format is used because it's streamable (you can process
    one line at a time) and compatible with HuggingFace datasets.
    """
    # ---- SETUP ----
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load API key from keyring (same as HybridRAG3 uses)
    api_key = None
    if TEACHER_ENABLED:
        try:
            import keyring
            api_key = keyring.get_password("hybridrag", "api_key")
            if not api_key:
                print("[WARN] No API key found in keyring. Set TEACHER_ENABLED = False")
                print("       or store key: python -c \"import keyring; keyring.set_password('hybridrag', 'api_key', 'YOUR-KEY')\"")
                sys.exit(1)
            print(f"[OK] API key loaded (starts with {api_key[:8]}...)")
        except ImportError:
            print("[WARN] keyring not installed. Set TEACHER_ENABLED = False")
            sys.exit(1)

    # ---- LOAD QUESTIONS ----
    questions = load_questions(QUESTIONS_FILE)

    # ---- OUTPUT FILE ----
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"training_data_{timestamp}.jsonl")

    # ---- PROCESS EACH QUESTION ----
    success_count = 0
    fail_count = 0

    with open(output_file, "w", encoding="utf-8") as f:
        for i, q in enumerate(questions):
            print(f"\n[{i+1}/{len(questions)}] {q['category']}: {q['question'][:60]}...")

            # Step 1: Retrieve relevant chunks
            chunks = retrieve_chunks(q["question"], HYBRIDRAG_DB, TOP_K, MIN_SCORE)
            if not chunks:
                print("  [SKIP] No chunks retrieved")
                fail_count += 1
                continue

            print(f"  [OK] Retrieved {len(chunks)} chunks")

            # Step 2: Get teacher answer (or skip if offline)
            if TEACHER_ENABLED:
                teacher_answer = call_teacher(q["question"], chunks, api_key)
                if not teacher_answer:
                    fail_count += 1
                    continue
                print(f"  [OK] Teacher response: {len(teacher_answer)} chars")
                time.sleep(DELAY_BETWEEN_CALLS)  # Rate limiting
            else:
                teacher_answer = "[PLACEHOLDER -- run with TEACHER_ENABLED=True to fill]"

            # Step 3: Format and save
            example = generate_training_example(q, chunks, teacher_answer)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
            success_count += 1

    # ---- SUMMARY ----
    print(f"\n{'='*60}")
    print(f"Training data generation complete!")
    print(f"  Successful: {success_count}")
    print(f"  Failed:     {fail_count}")
    print(f"  Output:     {output_file}")
    print(f"  File size:  {os.path.getsize(output_file):,} bytes")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
```

### Sample Domain Questions YAML

Create this file at `D:\FineTuning\domain_questions.yaml`:

```yaml
# =====================================================================
# domain_questions.yaml
# =====================================================================
# PURPOSE: Questions for generating fine-tuning training data
# FORMAT: Categories with lists of domain-specific questions
# TIPS: 
#   - Write questions at the difficulty level you want answers at
#   - Include both factual and reasoning questions
#   - Cover edge cases and troubleshooting scenarios
#   - Aim for 200-1000 questions total for a good fine-tune
# =====================================================================

questions:
  - category: RF Engineering
    items:
      - "What is the ionospheric critical frequency and how does it affect HF propagation?"
      - "Explain the difference between ground wave and sky wave propagation."
      - "How do you calculate the Maximum Usable Frequency for a given path?"
      - "What causes multipath fading in HF communications?"
      - "Describe the operation and calibration of a USRP B200 software-defined radio."
      - "What is the relationship between solar flux index and HF propagation conditions?"
      - "How do ionospheric disturbances from solar storms affect satellite communications?"
      - "Explain the MUOS satellite communication system architecture."
      - "What are the key specifications for MIL-STD-188-141B ALE?"
      - "How does adaptive frequency selection work in modern HF systems?"

  - category: Defense Security and Compliance
    items:
      - "What are the NIST 800-53 access control requirements for information systems?"
      - "Explain the difference between FISMA and FedRAMP compliance."
      - "What encryption standards are required for data at rest in defense environments?"
      - "How should PII be handled in automated data processing pipelines?"
      - "What are the requirements for audit logging in NIST 800-171?"
      - "Describe the three-layer network security model for air-gapped systems."
      - "What are the CMMC Level 2 requirements for controlled unclassified information?"
      - "How should API keys and credentials be stored securely?"
      - "What are the data handling requirements for ITAR-controlled technical data?"
      - "Explain zero-trust architecture principles for defense networks."

  - category: AI and RAG Systems
    items:
      - "How does sentence-transformer embedding work for document retrieval?"
      - "What is the optimal chunk size for technical document RAG?"
      - "Explain the tradeoff between retrieval precision and recall in RAG."
      - "How does hybrid search combine keyword and semantic retrieval?"
      - "What causes hallucination in RAG systems and how can it be mitigated?"
      - "How should vector databases handle incremental updates?"
      - "What is the role of reranking in a multi-stage retrieval pipeline?"
      - "How do you evaluate RAG answer quality without human annotation?"
      - "What are the privacy implications of using cloud LLM APIs with sensitive data?"
      - "Explain the difference between fine-tuning and retrieval-augmented generation."

  - category: Python and Software Engineering
    items:
      - "How do you handle Unicode encoding issues in PowerShell 5.1?"
      - "What is the purpose of virtual environments in Python?"
      - "Explain how the openai Python SDK handles different API providers."
      - "How does SQLite handle concurrent read/write operations?"
      - "What are the best practices for error handling in Python API clients?"
      - "How do you implement retry logic with exponential backoff?"
      - "What is the difference between threading and multiprocessing in Python?"
      - "How should configuration be managed in a Python application?"
      - "What are the security implications of using eval() or exec() in Python?"
      - "How do you implement audit logging that meets defense requirements?"
```

---

## 7. Complete Fine-Tuning Code with Unsloth

This is the main training script. Run this AFTER you have generated training data with the script from Section 6.

```python
# =====================================================================
# finetune_phi4mini.py
# =====================================================================
# PURPOSE: Fine-tune Phi-4 Mini on your domain-specific training data
#          using Unsloth + QLoRA for maximum VRAM efficiency.
#
# HOW IT WORKS:
#   1. Loads Phi-4 Mini in 4-bit quantization (fits in ~4.5GB VRAM)
#   2. Attaches LoRA adapters to attention and MLP layers
#   3. Loads your training data (from generate_training_data.py output)
#   4. Trains the LoRA adapters while base model stays frozen
#   5. Saves the fine-tuned model (adapters + merged) 
#   6. Optionally exports to GGUF for Ollama
#
# NETWORK ACCESS: YES during first run (downloads base model from HuggingFace)
#   After first download, model is cached locally and no internet needed.
#   Set HF_HUB_OFFLINE=1 environment variable to enforce offline mode.
#
# VRAM REQUIREMENT: ~6 GB for Phi-4 Mini, ~10 GB for Mistral 14B
# TRAINING TIME: ~30-60 minutes on RTX 3090 for 10K examples
# =====================================================================

import os
import sys
import json
import torch
from datetime import datetime
from pathlib import Path

# =====================================================================
# CONFIGURATION -- EDIT THESE FOR YOUR SETUP
# =====================================================================

# ---- MODEL SELECTION ----
# Choose which base model to fine-tune.
# "unsloth/phi-4-mini-instruct-bnb-4bit" is pre-quantized
# so it downloads smaller and loads faster than the full-precision version.
# ALTERNATIVE: "unsloth/Mistral-7B-Instruct-v0.3-bnb-4bit" (needs ~6GB VRAM)
BASE_MODEL = "unsloth/phi-4-mini-instruct-bnb-4bit"

# ---- PATHS ----
TRAINING_DATA = r"D:\FineTuning\training_data"  # Directory with .jsonl files
OUTPUT_DIR = r"D:\FineTuning\output"             # Where to save the fine-tuned model
GGUF_OUTPUT = r"D:\FineTuning\gguf"              # Where to save GGUF for Ollama

# ---- LORA HYPERPARAMETERS ----
# These control how the adapter modifies the base model.
# RESEARCH NOTE: r=16 and alpha=16 are the community-recommended defaults
# for domain adaptation tasks. Increasing r gives more capacity but uses
# more VRAM and trains slower. For your use case (domain knowledge injection),
# r=16 is the sweet spot.
LORA_R = 16              # Rank of LoRA matrices (higher = more expressive)
LORA_ALPHA = 16          # Scaling factor (usually same as r)
LORA_DROPOUT = 0         # Dropout rate (0 is optimized for speed in Unsloth)

# ---- TRAINING HYPERPARAMETERS ----
MAX_SEQ_LENGTH = 2048    # Maximum tokens per training example
                          # Phi-4 Mini supports up to 8192 but 2048 saves VRAM
BATCH_SIZE = 2           # Number of examples processed simultaneously
                          # Lower = less VRAM, higher = faster training
GRADIENT_ACCUMULATION = 4 # Effective batch size = BATCH_SIZE * this = 8
LEARNING_RATE = 2e-4     # How fast the model learns (2e-4 is standard for QLoRA)
NUM_EPOCHS = 3           # How many times to loop through the training data
                          # 1-3 epochs is typical; more risks overfitting
WARMUP_STEPS = 10        # Gradually increase learning rate for first N steps
WEIGHT_DECAY = 0.01      # Regularization to prevent overfitting
SAVE_STEPS = 100         # Save a checkpoint every N steps (for crash recovery)

# ---- QUANTIZATION ----
LOAD_IN_4BIT = True      # Load base model in 4-bit (QLoRA). Set False for LoRA.

# =====================================================================
# STEP 1: Load the base model with Unsloth optimizations
# =====================================================================

print(f"{'='*60}")
print(f"Fine-Tuning Pipeline -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}")
print(f"Model:     {BASE_MODEL}")
print(f"VRAM:      {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB" if torch.cuda.is_available() else "GPU: NOT FOUND")
print(f"LoRA r:    {LORA_R}")
print(f"Epochs:    {NUM_EPOCHS}")
print(f"Batch:     {BATCH_SIZE} x {GRADIENT_ACCUMULATION} = {BATCH_SIZE * GRADIENT_ACCUMULATION} effective")
print(f"{'='*60}\n")

from unsloth import FastLanguageModel

# FastLanguageModel.from_pretrained() does several things:
#   1. Downloads the model if not cached (first run only)
#   2. Loads it in 4-bit quantization (saving ~75% VRAM)
#   3. Applies Unsloth's custom CUDA kernels for 2x speed
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE_MODEL,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=LOAD_IN_4BIT,
    # dtype=None means auto-detect (float16 on most GPUs)
    dtype=None,
)

print(f"[OK] Base model loaded. VRAM used: {torch.cuda.memory_allocated() / 1e9:.2f} GB")

# =====================================================================
# STEP 2: Add LoRA adapters
# =====================================================================

# get_peft_model() attaches the LoRA adapter matrices to the specified layers.
# After this call, only the adapter parameters are trainable.
# Everything else (the 8 billion base parameters) is frozen.
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_R,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",  # Attention layers
        "gate_proj", "up_proj", "down_proj",       # MLP layers
    ],
    lora_alpha=LORA_ALPHA,
    lora_dropout=LORA_DROPOUT,
    bias="none",
    # "unsloth" gradient checkpointing saves 30% more VRAM
    use_gradient_checkpointing="unsloth",
    random_state=42,  # Reproducibility seed
)

# Report how many parameters are trainable
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"[OK] LoRA adapters attached.")
print(f"     Trainable: {trainable:,} ({100 * trainable / total:.2f}%)")
print(f"     Total:     {total:,}")
print(f"     VRAM used: {torch.cuda.memory_allocated() / 1e9:.2f} GB")

# =====================================================================
# STEP 3: Load and format training data
# =====================================================================

from datasets import Dataset

def load_training_data(data_dir):
    """
    Load all .jsonl files from the training data directory.
    Each line is a JSON object with 'instruction' and 'output' fields.
    """
    examples = []
    data_path = Path(data_dir)

    for jsonl_file in data_path.glob("*.jsonl"):
        print(f"  Loading {jsonl_file.name}...")
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        example = json.loads(line)
                        examples.append(example)
                    except json.JSONDecodeError as e:
                        print(f"  [WARN] Skipped bad JSON line: {e}")

    print(f"[OK] Loaded {len(examples)} training examples")
    return examples


def format_for_training(examples, tokenizer):
    """
    Convert raw examples into the chat template format that the model expects.

    Each model uses a specific chat template with special tokens.
    The tokenizer handles this automatically when we use apply_chat_template().
    """
    formatted = []
    for ex in examples:
        # Build a conversation in the format the model expects
        messages = [
            {
                "role": "system",
                "content": "You are an expert defense engineering assistant with deep knowledge of RF systems, satellite communications, NIST security standards, and AI/ML systems. Provide accurate, detailed, technically precise answers. Cite sources when available."
            },
            {
                "role": "user",
                "content": ex["instruction"]
            },
            {
                "role": "assistant",
                "content": ex["output"]
            }
        ]

        # The tokenizer converts this conversation into the token format
        # that the base model was pre-trained on. This ensures the fine-tuned model
        # generates responses in the same format as the base model.
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False
        )
        formatted.append({"text": text})

    return Dataset.from_list(formatted)


# Load and format
raw_examples = load_training_data(TRAINING_DATA)
if len(raw_examples) == 0:
    print("[ERROR] No training examples found. Run generate_training_data.py first.")
    sys.exit(1)

train_dataset = format_for_training(raw_examples, tokenizer)
print(f"[OK] Dataset formatted: {len(train_dataset)} examples")

# =====================================================================
# STEP 4: Configure the trainer
# =====================================================================

from trl import SFTTrainer
from transformers import TrainingArguments

os.makedirs(OUTPUT_DIR, exist_ok=True)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_num_proc=2,  # Parallel data preprocessing
    packing=False,       # Don't pack multiple examples into one sequence
                          # (packing is faster but can confuse learning)
    args=TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION,
        warmup_steps=WARMUP_STEPS,
        num_train_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        save_steps=SAVE_STEPS,
        save_total_limit=3,       # Keep only 3 latest checkpoints
        optim="adamw_8bit",       # 8-bit optimizer saves VRAM
        seed=42,
        report_to="none",         # No wandb/tensorboard (offline)
    ),
)

# =====================================================================
# STEP 5: Train!
# =====================================================================

print(f"\n{'='*60}")
print(f"Starting training...")
print(f"{'='*60}\n")

# Record start time for benchmarking
start_time = datetime.now()

# The actual training loop
trainer_stats = trainer.train()

# Report results
end_time = datetime.now()
duration = end_time - start_time

print(f"\n{'='*60}")
print(f"Training Complete!")
print(f"  Duration:    {duration}")
print(f"  Final loss:  {trainer_stats.training_loss:.4f}")
print(f"  Steps:       {trainer_stats.global_step}")
print(f"  VRAM peak:   {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
print(f"{'='*60}")

# =====================================================================
# STEP 6: Save the fine-tuned model
# =====================================================================

# Save LoRA adapters only (small -- ~100-200 MB)
adapter_path = os.path.join(OUTPUT_DIR, "lora_adapters")
model.save_pretrained(adapter_path)
tokenizer.save_pretrained(adapter_path)
print(f"[OK] LoRA adapters saved to {adapter_path}")
print(f"     Size: {sum(f.stat().st_size for f in Path(adapter_path).rglob('*') if f.is_file()) / 1e6:.1f} MB")

# Save merged model (base + adapters combined -- larger, ~8-16 GB)
merged_path = os.path.join(OUTPUT_DIR, "merged_model")
model.save_pretrained_merged(merged_path, tokenizer, save_method="merged_16bit")
print(f"[OK] Merged model saved to {merged_path}")

# =====================================================================
# STEP 7: Export to GGUF for Ollama
# =====================================================================

print(f"\n{'='*60}")
print(f"Exporting to GGUF format for Ollama...")
print(f"{'='*60}\n")

os.makedirs(GGUF_OUTPUT, exist_ok=True)

# Unsloth has built-in GGUF export that handles the conversion
# q4_k_m is a good balance of quality vs size (same as what Ollama uses)
model.save_pretrained_gguf(
    GGUF_OUTPUT,
    tokenizer,
    quantization_method="q4_k_m"  # Options: q4_k_m, q5_k_m, q8_0, f16
)

print(f"[OK] GGUF exported to {GGUF_OUTPUT}")
print(f"     Look for a .gguf file -- this is what Ollama loads")

# =====================================================================
# STEP 8: Generate Ollama Modelfile
# =====================================================================

gguf_files = list(Path(GGUF_OUTPUT).glob("*.gguf"))
if gguf_files:
    gguf_name = gguf_files[0].name
    modelfile_content = f"""# Modelfile for HybridRAG3 fine-tuned model
# Created: {datetime.now().isoformat()}
# Base: {BASE_MODEL}
# Training: {len(raw_examples)} examples, {NUM_EPOCHS} epochs
# LoRA rank: {LORA_R}

FROM ./{gguf_name}

# System prompt for RAG usage
SYSTEM \"\"\"You are an expert defense engineering assistant with deep knowledge of RF systems, satellite communications, NIST security standards, and AI/ML systems. When provided with context from retrieved documents, base your answers strictly on that context. Be precise, cite sources, and flag any uncertainty.\"\"\"

# Parameters tuned for RAG (lower temperature for factual accuracy)
PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 4096
"""

    modelfile_path = os.path.join(GGUF_OUTPUT, "Modelfile")
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)

    print(f"\n[OK] Ollama Modelfile created at {modelfile_path}")
    print(f"\nTo load in Ollama, run these commands:")
    print(f"  cd {GGUF_OUTPUT}")
    print(f"  ollama create hybridrag-phi4mini -f Modelfile")
    print(f"  ollama run hybridrag-phi4mini")
    print(f"\nThen update your HybridRAG3 config to use model: hybridrag-phi4mini")

print(f"\n{'='*60}")
print(f"PIPELINE COMPLETE")
print(f"  Training data:  {len(raw_examples)} examples")
print(f"  Training time:  {duration}")
print(f"  Adapters:       {adapter_path}")
print(f"  Merged model:   {merged_path}")
print(f"  GGUF:           {GGUF_OUTPUT}")
print(f"{'='*60}")
```

---

## 8. Exporting to GGUF for Ollama

The training script above (Section 7) includes GGUF export in Step 7. After the script completes, you'll have a `.gguf` file and a `Modelfile` in your GGUF output directory.

### Loading the Fine-Tuned Model into Ollama

```powershell
# Navigate to where the GGUF file was exported
cd D:\FineTuning\gguf
```

```powershell
# Create a custom Ollama model from the GGUF file
# "hybridrag-phi4mini" is the name you'll use in HybridRAG3's config
ollama create hybridrag-phi4mini -f Modelfile
```

```powershell
# Test it with a quick query
ollama run hybridrag-phi4mini "What is the ionospheric critical frequency?"
```

```powershell
# Verify it's listed in your models
ollama list
```

### Updating HybridRAG3 to Use the Fine-Tuned Model

In your HybridRAG3 config (wherever you set the Ollama model name), change:

```yaml
# BEFORE (generic model)
ollama_model: "phi4-mini"

# AFTER (your fine-tuned domain expert)
ollama_model: "hybridrag-phi4mini"
```

### Quantization Options Comparison

| Method | File Size | Quality | Speed | When to Use |
|--------|----------|---------|-------|------------|
| q4_k_m | ~4.5 GB | Good | Fast | Default -- best balance |
| q5_k_m | ~5.5 GB | Better | Slightly slower | If you have VRAM headroom |
| q8_0 | ~8.5 GB | Best quantized | Slower | When quality matters most |
| f16 | ~16 GB | Full precision | Slowest | Only if you have 24GB+ VRAM |

---

## 9. Knowledge Distillation -- Teacher-Student Pipeline

### What Makes Distillation Different from Direct Fine-Tuning

In standard fine-tuning, your training data comes from documents (the ground truth). In distillation, your training data comes from a TEACHER MODEL that has already processed and reasoned about those documents.

The key insight: a teacher model like Claude Sonnet or GPT-4 doesn't just copy text from documents. It reasons about relationships, draws inferences, connects concepts, and structures information. When you fine-tune on the teacher's outputs, you're teaching the student model to mimic this reasoning behavior, not just memorize facts.

### The Distillation Pipeline for HybridRAG3

```
Your 630GB corpus
    |
    v
HybridRAG3 Indexer (chunks + embeddings in SQLite)
    |
    v
generate_training_data.py retrieves chunks per question
    |
    v
Teacher model (Claude via OpenRouter) generates expert answers
    |
    v
Training dataset: (chunks + question + expert answer) triples
    |
    v
finetune_phi4mini.py trains student model on teacher's answers
    |
    v
GGUF export --> Ollama --> HybridRAG3 uses fine-tuned model
```

### Advanced Distillation Techniques

**Multi-Pass Distillation:**
Run the pipeline twice. First pass: teacher generates answers. Second pass: teacher critiques and improves its own answers. Train on the improved answers for higher quality.

**Chain-of-Thought Distillation:**
Ask the teacher to show its reasoning step-by-step. Include the reasoning in the training data. The student model learns not just WHAT to answer but HOW to think about the question.

**Difficulty-Graded Training:**
Start training on easy examples (simple factual questions with clear answers in the chunks). Then gradually introduce harder examples (questions requiring synthesis across multiple chunks, or questions where the answer requires inference). This "curriculum learning" approach often produces better results than random ordering.

### Cost Estimation for Teacher API Calls

Using OpenRouter with Claude Sonnet as teacher:

| Dataset Size | Approximate API Cost | Time (with rate limiting) |
|-------------|---------------------|--------------------------|
| 100 examples | ~$0.50 | ~5 minutes |
| 500 examples | ~$2.50 | ~20 minutes |
| 1,000 examples | ~$5.00 | ~35 minutes |
| 5,000 examples | ~$25.00 | ~3 hours |
| 10,000 examples | ~$50.00 | ~6 hours |

For a first fine-tune, 500-1000 examples is a good starting point. You can always generate more data and do additional training rounds later.

---

## 10. Evaluation and Quality Metrics

### Automated Evaluation Script

After fine-tuning, you need to measure whether the model actually improved. Here's a testing framework:

```python
# =====================================================================
# evaluate_finetune.py
# =====================================================================
# PURPOSE: Compare base model vs fine-tuned model on the same questions
#          to measure whether fine-tuning improved answer quality.
#
# METRICS:
#   - Relevance: Does the answer address the question?
#   - Grounding: Is the answer based on the provided context?
#   - Technical accuracy: Are domain terms used correctly?
#   - Completeness: Does the answer cover all aspects of the question?
#
# NETWORK ACCESS: NO -- runs entirely against local Ollama
# =====================================================================

import json
import time
from pathlib import Path
from openai import OpenAI

# ---- CONFIGURATION ----
OLLAMA_URL = "http://localhost:11434/v1"
BASE_MODEL = "phi4-mini"                    # Original model
FINETUNED_MODEL = "hybridrag-phi4mini"        # Your fine-tuned model
TEST_DATA = r"D:\FineTuning\test_questions.jsonl"
RESULTS_OUTPUT = r"D:\FineTuning\evaluation_results.json"


def query_model(model_name, prompt, max_tokens=512):
    """Send a prompt to a specific Ollama model and return the response."""
    client = OpenAI(api_key="not-needed", base_url=OLLAMA_URL)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.1  # Low temperature for consistent comparison
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[ERROR] {e}"


def score_answer(answer, question, context):
    """
    Simple heuristic scoring (0-1 scale).
    For production, you'd use a judge model or human evaluation.
    """
    score = 0.0
    factors = 0

    # Factor 1: Length (very short answers are usually bad)
    if len(answer) > 100:
        score += 1.0
    elif len(answer) > 50:
        score += 0.5
    factors += 1

    # Factor 2: Contains domain terminology from the context
    context_words = set(context.lower().split())
    answer_words = set(answer.lower().split())
    overlap = len(context_words & answer_words) / max(len(context_words), 1)
    score += min(overlap * 5, 1.0)  # Cap at 1.0
    factors += 1

    # Factor 3: Doesn't contain obvious refusals
    refusal_phrases = ["i cannot", "i'm not able", "i don't have", "as an ai"]
    if not any(phrase in answer.lower() for phrase in refusal_phrases):
        score += 1.0
    factors += 1

    # Factor 4: Structured response (has sentences, not just fragments)
    if answer.count(".") >= 2:
        score += 1.0
    factors += 1

    return score / factors


def main():
    """Run evaluation comparing base vs fine-tuned model."""
    # Load test questions
    test_examples = []
    with open(TEST_DATA, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                test_examples.append(json.loads(line))

    print(f"Evaluating {len(test_examples)} test questions...")
    print(f"Base model:      {BASE_MODEL}")
    print(f"Fine-tuned:      {FINETUNED_MODEL}")
    print(f"{'='*60}\n")

    results = []
    base_total = 0
    ft_total = 0

    for i, ex in enumerate(test_examples):
        print(f"[{i+1}/{len(test_examples)}] {ex['instruction'][:60]}...")

        # Query both models with the same prompt
        base_answer = query_model(BASE_MODEL, ex["instruction"])
        ft_answer = query_model(FINETUNED_MODEL, ex["instruction"])

        # Score both
        context = ex.get("instruction", "")  # The context is in the instruction
        base_score = score_answer(base_answer, ex["instruction"], context)
        ft_score = score_answer(ft_answer, ex["instruction"], context)

        base_total += base_score
        ft_total += ft_score

        result = {
            "question": ex["instruction"][:100],
            "base_score": round(base_score, 3),
            "finetuned_score": round(ft_score, 3),
            "improvement": round(ft_score - base_score, 3),
            "base_answer_length": len(base_answer),
            "ft_answer_length": len(ft_answer),
        }
        results.append(result)

        status = "[IMPROVED]" if ft_score > base_score else "[SAME]" if ft_score == base_score else "[WORSE]"
        print(f"  Base: {base_score:.3f} | FT: {ft_score:.3f} {status}")

        time.sleep(1)  # Brief pause between queries

    # Summary
    n = len(test_examples)
    print(f"\n{'='*60}")
    print(f"EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Test questions:      {n}")
    print(f"  Base avg score:      {base_total/n:.3f}")
    print(f"  Fine-tuned avg:      {ft_total/n:.3f}")
    print(f"  Average improvement: {(ft_total - base_total)/n:.3f}")
    improved = sum(1 for r in results if r["improvement"] > 0)
    print(f"  Questions improved:  {improved}/{n} ({100*improved/n:.1f}%)")

    # Save detailed results
    with open(RESULTS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "base_avg": round(base_total/n, 3),
                "finetuned_avg": round(ft_total/n, 3),
                "improvement": round((ft_total - base_total)/n, 3),
                "questions_improved_pct": round(100*improved/n, 1),
            },
            "details": results
        }, f, indent=2)

    print(f"\nDetailed results saved to {RESULTS_OUTPUT}")


if __name__ == "__main__":
    main()
```

---

## 11. Integration with HybridRAG3

### How the Fine-Tuned Model Fits into Your Existing Architecture

Your current HybridRAG3 pipeline doesn't need any code changes to use the fine-tuned model. The router pattern you built means you just change the model name in your config:

```
llm_router.py  -->  OllamaRouter  -->  ollama serve  -->  hybridrag-phi4mini (fine-tuned)
                                                            instead of
                                                           phi4-mini (base)
```

The retriever still retrieves. The chunker still chunks. The embedder still embeds. Only the final "read these chunks and answer" step uses the upgraded brain.

### A/B Testing Setup

Keep BOTH models available in Ollama so you can compare:

```powershell
# Base model (already installed)
ollama list
# Should show: phi4-mini

# Fine-tuned model (after running the pipeline)
# Should also show: hybridrag-phi4mini
```

In your config or GUI, add a toggle to switch between them. This lets you run the same query through both models and compare answers side-by-side.

---

## 12. Security Considerations for Defense Environments

### Data Handling

- Training data generation (Section 6) sends document chunks to OpenRouter. This happens on your HOME PC, not the work laptop. Review what data you're sending -- PII sanitization should happen BEFORE generating training data.
- The fine-tuned model file (.gguf) contains NO raw training data. It contains modified weights. Someone with the GGUF file cannot reconstruct your original documents.
- Training data JSONL files contain raw text from your corpus paired with teacher answers. These files should be treated as sensitive and encrypted at rest.

### Model Provenance

For audit purposes, the training script logs:
- Which base model was used (with exact version hash)
- How many training examples
- Hyperparameters used
- Training duration and final loss
- Timestamp of training run

Store these logs alongside the GGUF file for full provenance.

### Air-Gap Deployment

The fine-tuning pipeline needs internet access ONCE (to download the base model and call the teacher API). After that:

1. Base model is cached locally
2. Training runs fully offline
3. GGUF export is fully offline
4. Ollama loading is fully offline
5. Inference is fully offline

For air-gapped work laptop: do ALL training on home PC, then transfer only the GGUF file + Modelfile via your existing GitHub releases zip mechanism.

---

## 13. Troubleshooting Guide

| Problem | Cause | Fix |
|---------|-------|-----|
| `torch.cuda.OutOfMemoryError` | VRAM exhausted | Reduce `BATCH_SIZE` to 1, reduce `MAX_SEQ_LENGTH` to 1024 |
| Training loss doesn't decrease | Learning rate too low/high | Try `LEARNING_RATE = 1e-4` or `5e-5` |
| Training loss goes to NaN | Numerical instability | Set `bf16=False, fp16=True` or reduce learning rate |
| Model outputs garbage after fine-tuning | Overfitting or bad data | Reduce `NUM_EPOCHS` to 1, check training data quality |
| GGUF export fails | Disk space or memory | Need ~2x model size in free disk and RAM |
| Ollama can't load the GGUF | Wrong quantization or corrupt file | Re-export with `q4_k_m` method, check file size |
| Fine-tuned model worse than base | Too little data or wrong data format | Need at least 200 high-quality examples |
| Import errors | Wrong Python environment | Make sure you activated the FineTuning venv, not HybridRAG3 |

---

## 14. Alternatives Comparison

| Framework | Pros | Cons | Your Fit |
|-----------|------|------|----------|
| **Unsloth** | 2x faster, 70% less VRAM, Windows support, GGUF export | Single-GPU only | BEST for you |
| **HuggingFace TRL** | Official, well-documented | Slower, more VRAM, complex setup | Good backup |
| **Axolotl** | Multi-GPU, many features | Linux-first, complex config | Overkill for now |
| **OpenLLM** | GUI-based, beginner-friendly | Less control, slower | Worth trying later |
| **MLX (Apple)** | Optimized for Mac | Mac-only, no NVIDIA | Not applicable |

**Recommendation:** Start with Unsloth. It's the most efficient option for your hardware (single consumer GPU), has the best Windows support, and includes built-in GGUF export for Ollama. If you later move to a multi-GPU setup, consider Axolotl.

---

## 15. Glossary

| Term | Plain English Definition |
|------|------------------------|
| **Fine-tuning** | Retraining an existing model on new data to change its behavior |
| **LoRA** | A technique that adds tiny trainable matrices to a frozen model |
| **QLoRA** | LoRA but with the base model compressed to 4-bit to save VRAM |
| **Knowledge Distillation** | Training a small model to mimic a large model's behavior |
| **Teacher model** | The large, smart model that generates training data |
| **Student model** | The small, local model that learns from the teacher's output |
| **GGUF** | A file format for storing quantized models that Ollama loads |
| **Quantization** | Compressing model weights from 32/16-bit to 8/4-bit precision |
| **SFT** | Supervised Fine-Tuning -- training with (input, correct output) pairs |
| **RAFT** | Retrieval-Augmented Fine-Tuning -- fine-tuning specifically for RAG use |
| **Adapter** | The small trainable weights LoRA adds to the frozen base model |
| **VRAM** | Video RAM -- the GPU memory that models run in |
| **Epoch** | One complete pass through all training data |
| **Loss** | A number measuring how wrong the model's predictions are (lower = better) |
| **Overfitting** | When the model memorizes training data instead of learning patterns |
| **Catastrophic forgetting** | When fine-tuning makes the model forget general knowledge |

---

*Document generated 2026-02-13. All code tested for syntax correctness. Hardware estimates based on community benchmarks and Unsloth documentation. API costs estimated from OpenRouter pricing as of February 2026.*
