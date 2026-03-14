# HybridRAG3 Demo Learning Resource Library

**Created:** 2026-02-22  
**Last updated:** 2026-03-14 13:55 America/Denver  
**Purpose:** external reading library for demo leads and learners who already finished the repo-first path in [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md).

This file is no longer the primary curriculum.

Use it this way:

- start with [STUDY_GUIDE.md](../08_learning/STUDY_GUIDE.md) for the canonical HybridRAG3 learning sequence
- use [DEMO_PREP.md](DEMO_PREP.md), [DEMO_GUIDE.md](DEMO_GUIDE.md), and [DEMO_QA_PREP.md](DEMO_QA_PREP.md) for the live presentation workflow
- come back here only when you need extra background on RAG foundations, evaluation, security, ROI, or change management
- do not try to read every item before the first demo

## Fastest High-Impact Use

| If you need to improve... | Start with |
|---|---|
| a plain-English explanation of RAG | resources `#1-#4` |
| technical credibility on retrieval and evaluation | resources `#5-#13` |
| security and prompt-injection answers | resources `#14-#21` |
| leadership, ROI, and adoption answers | resources `#24-#32` |
| advanced follow-up material after the demo | resources `#33-#38` |

**Research basis:** 38 curated resources across videos, courses, articles, books, GitHub repos, and security guides.

---

## PHASE 1: FOUNDATIONS (Read/Watch FIRST)

**Goal**: Understand what RAG is, how each component works, and why it matters. After this phase you can answer: "What is RAG?", "How does it work?", "What are embeddings?", "What is a vector database?", "How is chunking done?", "Why not just use ChatGPT?"

**Estimated time: 12-18 hours**

---

### 1. IBM Technology -- "What is Retrieval-Augmented Generation (RAG)?"
- **URL**: https://www.ibm.com/think/videos/rag
- **Why useful**: IBM Senior Research Scientist explains RAG in plain language with clear visuals. Covers the core "retrieve then generate" loop, why LLMs need external data, and the two key advantages (up-to-date facts, source attribution). The single best first thing to watch.
- **Questions it prepares you for**: What is RAG? Why do LLMs hallucinate? How does RAG fix that? What are the components?
- **Difficulty**: Beginner
- **Format**: Video (YouTube)
- **Time**: 10 minutes

---

### 2. Pinecone Learning Center -- "Retrieval-Augmented Generation (RAG)" Series
- **URL**: https://www.pinecone.io/learn/series/rag/
- **Why useful**: Well-structured multi-part series covering the full RAG pipeline: ingestion, embedding, retrieval, augmentation, and generation. Clear diagrams and explanations of vector similarity search. Vendor-neutral enough to be educational.
- **Questions it prepares you for**: What is the RAG pipeline? How do embeddings work? What is similarity search? How is data ingested? What is a vector database?
- **Difficulty**: Beginner
- **Format**: Article series with diagrams
- **Time**: 2-3 hours

---

### 3. Pinecone -- "What are Vector Embeddings?"
- **URL**: https://www.pinecone.io/learn/vector-embeddings/
- **Why useful**: The single best standalone explanation of embeddings for non-data-scientists. Covers how text becomes numbers, why similar meanings end up near each other in vector space, and real-world analogies. Essential for answering "but how does the computer understand meaning?"
- **Questions it prepares you for**: What are embeddings? How does semantic search differ from keyword search? What is vector space?
- **Difficulty**: Beginner
- **Format**: Article with diagrams
- **Time**: 30 minutes

---

### 4. Learn by Building -- "Build a RAG Application from Scratch"
- **URL**: https://learnbybuilding.ai/tutorial/rag-from-scratch/
- **Why useful**: Strips away all framework abstraction and shows raw RAG mechanics in plain Python. No LangChain, no LlamaIndex -- just the core concepts. Essential for explaining what is actually happening under the hood.
- **Questions it prepares you for**: What happens step-by-step when a query runs? How is context injected into the prompt? How does retrieval actually work at the code level?
- **Difficulty**: Beginner-Intermediate
- **Format**: Interactive tutorial with code
- **Time**: 2-3 hours

---

### 5. Weaviate Blog -- "Chunking Strategies for RAG"
- **URL**: https://weaviate.io/blog/chunking-strategies-for-rag
- **Why useful**: Chunking is one of the most-asked-about topics at demos. Covers fixed-size, sentence-based, paragraph-based, semantic, and late chunking with clear visuals, decision frameworks, and code examples. Explains why chunk size directly impacts retrieval quality.
- **Questions it prepares you for**: What is chunking? What chunk size should we use? How do you handle PDFs vs spreadsheets? What if a chunk splits a paragraph?
- **Difficulty**: Beginner-Intermediate
- **Format**: Article with diagrams and code
- **Time**: 1 hour

---

### 6. Prompt Engineering Guide -- "RAG Techniques"
- **URL**: https://www.promptingguide.ai/techniques/rag
- **Why useful**: Concise reference covering Naive RAG, Advanced RAG, and Modular RAG architectures. Includes HyDE, Step-Back prompting, sub-queries, and multi-query approaches. Good for building vocabulary and understanding the landscape.
- **Questions it prepares you for**: What are the different types of RAG? What is hybrid search? What is re-ranking? How has RAG evolved?
- **Difficulty**: Beginner-Intermediate
- **Format**: Reference article
- **Time**: 45 minutes

---

### 7. Medium (Manali Somani) -- "Fine-Tuning vs RAG in 2025"
- **URL**: https://manalisomani099.medium.com/fine-tuning-vs-rag-in-2025-which-approach-wins-99dca6fd00df
- **Why useful**: The single most common "gotcha" question at demos is "why not just fine-tune?" Clear comparison of RAG vs fine-tuning vs long-context approaches, including when to use each, cost tradeoffs, and hybrid approach.
- **Questions it prepares you for**: Why RAG instead of fine-tuning? What about 1M token context windows? When should we fine-tune? Can we combine approaches?
- **Difficulty**: Beginner-Intermediate
- **Format**: Article
- **Time**: 20 minutes

---

### 8. Meilisearch -- "RAG vs. Long-Context LLMs: A Side-by-Side Comparison"
- **URL**: https://www.meilisearch.com/blog/rag-vs-long-context-llms
- **Why useful**: Addresses "aren't long-context models making RAG obsolete?" with data. Covers "Lost in the Middle" attention degradation, cost comparison, and why RAG remains 1,250x cheaper per query.
- **Questions it prepares you for**: Is RAG going to be obsolete? What is "Lost in the Middle"? Which approach costs less at scale?
- **Difficulty**: Intermediate
- **Format**: Article with benchmarks
- **Time**: 20 minutes

---

## PHASE 2: DEPTH AND SECURITY (Read/Watch SECOND)

**Goal**: Go deeper on evaluation, security, hallucination mitigation, and production realities. After this phase you can answer: "How do you measure accuracy?", "What about prompt injection?", "Is this secure?", "How do you prevent hallucination?", "Can this run air-gapped?"

**Estimated time: 15-22 hours**

---

### 9. FreeCodeCamp / Lance Martin -- "Learn RAG from Scratch (Full Course)"
- **URL**: https://www.freecodecamp.org/news/mastering-rag-from-scratch/
- **GitHub**: https://github.com/langchain-ai/rag-from-scratch
- **Why useful**: 2.5-hour comprehensive video from a LangChain engineer (Stanford PhD) covering 14+ RAG papers with open-source notebooks. Covers indexing, retrieval, generation, query translation (Multi-Query, RAG Fusion, Decomposition, Step-Back, HyDE), routing, and self-correction. 450K+ views. The most thorough single video resource available.
- **Questions it prepares you for**: How do advanced retrieval techniques work? What is RAG Fusion? How do you route queries? How does self-correcting RAG work?
- **Difficulty**: Intermediate
- **Format**: Video course + Jupyter notebooks
- **Time**: 3-4 hours

---

### 10. DeepLearning.AI -- "Building and Evaluating Advanced RAG Applications"
- **URL**: https://www.deeplearning.ai/short-courses/building-evaluating-advanced-rag/
- **Why useful**: Free course taught by Jerry Liu (LlamaIndex CEO) and Anupam Datta (TruEra). Covers the "RAG Triad" evaluation framework: Context Relevance, Groundedness, and Answer Relevance. Critical for answering "how do you know it is accurate?"
- **Questions it prepares you for**: How do you evaluate RAG accuracy? What metrics matter? What is groundedness? How do you iterate on a pipeline?
- **Difficulty**: Intermediate
- **Format**: Free video course (6 lessons)
- **Time**: 2 hours

---

### 11. DeepLearning.AI / Coursera -- "Retrieval Augmented Generation (RAG)"
- **URL**: https://www.deeplearning.ai/courses/retrieval-augmented-generation-rag/
- **Why useful**: 5-module course covering keyword search, semantic search, BM25, hybrid search, Reciprocal Rank Fusion, chunking, and indexing. Builds a domain-specific chatbot from scratch.
- **Questions it prepares you for**: How do different search methods compare? What is BM25? What is hybrid search?
- **Difficulty**: Beginner-Intermediate
- **Format**: Online course (free, certificate $49)
- **Time**: 15-20 hours (self-paced)

---

### 12. Cohorte Projects -- "Evaluating RAG Systems in 2025: RAGAS Deep Dive"
- **URL**: https://www.cohorte.co/blog/evaluating-rag-systems-in-2025-ragas-deep-dive-giskard-showdown-and-the-future-of-context
- **Why useful**: Deep comparison of RAGAS, Giskard, TruLens, and DeepEval evaluation frameworks. Explains Context Precision, Context Recall, Faithfulness, and Answer Relevancy metrics.
- **Questions it prepares you for**: What is RAGAS? How do you measure hallucination? What is faithfulness scoring? How do you build a golden dataset?
- **Difficulty**: Intermediate
- **Format**: Article with examples
- **Time**: 1 hour

---

### 13. Meilisearch -- "RAG Evaluation: Metrics, Methodologies, Best Practices"
- **URL**: https://www.meilisearch.com/blog/rag-evaluation
- **Why useful**: Practical evaluation guide covering retrieval metrics (precision, recall, MRR, NDCG), generation metrics (faithfulness, relevancy), and end-to-end approaches. More actionable than academic papers.
- **Questions it prepares you for**: What are precision and recall in RAG? How do you build evaluation datasets? What is MRR?
- **Difficulty**: Intermediate
- **Format**: Article
- **Time**: 45 minutes

---

### 14. OWASP -- "Top 10 for LLM Applications 2025" (Full PDF)
- **URL**: https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf
- **Why useful**: Industry-standard security reference. 2025 edition adds RAG-specific vulnerabilities (Vector and Embedding Weaknesses), System Prompt Leakage, and Agentic AI Security. Your cybersecurity analyst will ask about this by name.
- **Questions it prepares you for**: What are the top LLM security risks? What is prompt injection? What are embedding attacks?
- **Difficulty**: Intermediate
- **Format**: PDF (44 pages)
- **Time**: 2-3 hours

---

### 15. OWASP -- "LLM Prompt Injection Prevention Cheat Sheet"
- **URL**: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
- **Why useful**: Concise, actionable cheat sheet on preventing prompt injection. Covers direct vs indirect injection, input validation, output sanitization, privilege control, and defense-in-depth.
- **Questions it prepares you for**: What is prompt injection? How do you defend against it? What is indirect injection?
- **Difficulty**: Intermediate
- **Format**: Reference webpage
- **Time**: 30 minutes

---

### 16. Lakera AI -- "Prompt Injection Attacks Handbook"
- **URL**: https://www.lakera.ai/ai-security-guides/prompt-injection-attacks-handbook
- **Why useful**: Based on insights from ~30 million attack data points from their Gandalf prompt-injection game (1M+ players). Taxonomy of attack types with real examples. More engaging than academic papers.
- **Questions it prepares you for**: What do real prompt injection attacks look like? How creative can attackers be? What defenses work?
- **Difficulty**: Intermediate
- **Format**: Downloadable handbook
- **Time**: 1-2 hours

---

### 17. Lakera AI -- "Comprehensive Guide to LLM Security"
- **URL**: https://www.lakera.ai/blog/llm-security
- **Why useful**: Broader than prompt injection -- covers data leakage, insecure output handling, training data poisoning, model DoS, and supply chain vulnerabilities.
- **Questions it prepares you for**: What are the full security risks? How do you prevent data leakage? What is training data poisoning?
- **Difficulty**: Intermediate
- **Format**: Long-form article
- **Time**: 1 hour

---

### 18. GitHub (requie) -- "LLMSecurityGuide"
- **URL**: https://github.com/requie/LLMSecurityGuide
- **Why useful**: Open-source reference covering OWASP GenAI Top-10, prompt injection, adversarial attacks, real-world incidents, red-teaming tool catalogs, guardrails, and mitigation strategies. Updated with OWASP Top 10 for Agentic Applications 2026.
- **Questions it prepares you for**: What tools exist for red-teaming? What real-world incidents have occurred? What guardrails are available?
- **Difficulty**: Intermediate-Advanced
- **Format**: GitHub repository
- **Time**: 2-3 hours (browse relevant sections)

---

### 19. RAG About It -- "Ultimate Guide to Air-Gapped Local AI Setup"
- **URL**: https://ragaboutit.com/ultimate-guide-to-air-gapped-local-ai-setup-for-sensitive-documents/
- **Why useful**: Directly addresses "can this run with no internet?" Covers local model deployment, air-gapped vector databases, and security architecture for sensitive documents.
- **Questions it prepares you for**: Can RAG run fully offline? What models work air-gapped? How do you handle updates without internet?
- **Difficulty**: Intermediate
- **Format**: Article/guide
- **Time**: 45 minutes

---

### 20. Software Analyst Substack -- "Securing AI/LLMs in 2025"
- **URL**: https://softwareanalyst.substack.com/p/securing-aillms-in-2025-a-practical
- **Why useful**: Practical deployment security covering runtime protection, AI-SBOMs (Software Bill of Materials), red teaming, continuous monitoring, and compliance alignment. Addresses shadow AI risk.
- **Questions it prepares you for**: How do you secure an LLM in production? What is an AI-SBOM? How do you handle shadow AI?
- **Difficulty**: Intermediate
- **Format**: Substack article
- **Time**: 30 minutes

---

### 21. Promptfoo -- "How to Red Team RAG Applications"
- **URL**: https://www.promptfoo.dev/docs/red-team/rag/
- **GitHub**: https://github.com/promptfoo/promptfoo
- **Why useful**: Open-source tool and guide for security-testing RAG applications. 50+ vulnerability types, declarative test configs, CI/CD integration. When Cyber asks "how do you test security?" -- this is your answer.
- **Questions it prepares you for**: How do you pen-test a RAG system? What vulnerability types exist? How do you automate security testing?
- **Difficulty**: Intermediate-Advanced
- **Format**: Documentation + open-source tool
- **Time**: 1-2 hours

---

## PHASE 3: ENTERPRISE, PRESENTATION, AND CHANGE MANAGEMENT (Read/Watch THIRD)

**Goal**: Prepare for business, organizational, and presentation questions. After this phase you can answer: "What is the ROI?", "How does this scale?", "Who else is using this?", "How do we get buy-in?", and handle skeptics with confidence.

**Estimated time: 10-16 hours**

---

### 22. Chip Huyen -- "AI Engineering: Building Applications with Foundation Models" (Book)
- **URL**: https://www.amazon.com/AI-Engineering-Building-Applications-Foundation/dp/1098166302
- **GitHub**: https://github.com/chiphuyen/aie-book
- **Why useful**: Currently the most-read book on O'Reilly. Covers model selection, evaluation, prompt engineering, RAG (chunking, metadata extraction), hallucination mitigation, and production optimization. "Crystal clear explanations and great analogies." Best single book for the full lifecycle.
- **Questions it prepares you for**: How do you choose models? How do you evaluate end-to-end? What does production RAG look like?
- **Difficulty**: Intermediate
- **Format**: Book (O'Reilly, ~400 pages)
- **Time**: 8-12 hours

---

### 23. Abhinav Kimothi -- "A Simple Guide to Retrieval Augmented Generation" (Book)
- **URL**: https://www.manning.com/books/a-simple-guide-to-retrieval-augmented-generation
- **Why useful**: Written specifically for non-data-scientists who need to understand and build RAG. Plain English with realistic Python code. Progresses from basic to modular RAG and multimodal data (images, spreadsheets). Best book for a field engineer.
- **Questions it prepares you for**: How do you build RAG step-by-step? How do you handle images and spreadsheets? What is modular RAG?
- **Difficulty**: Beginner-Intermediate
- **Format**: Book (Manning)
- **Time**: 6-8 hours

---

### 24. Vectara -- "Enterprise RAG Predictions for 2025"
- **URL**: https://www.vectara.com/blog/top-enterprise-rag-predictions
- **Why useful**: Industry analysis: enterprises choosing RAG for 30-60% of use cases, retrieval bottleneck at scale, why evaluation frameworks are critical. Good for PM and leadership audience.
- **Questions it prepares you for**: What percentage of enterprises use RAG? What are adoption trends? What are production challenges?
- **Difficulty**: Beginner-Intermediate
- **Format**: Blog post
- **Time**: 20 minutes

---

### 25. Uptech -- "Top 10 RAG Use Cases and Business Benefits"
- **URL**: https://www.uptech.team/blog/rag-use-cases
- **Why useful**: Concrete case studies with business metrics. Bank of America (42M users, 65% handle time reduction), Siemens (knowledge management), IBM Watson (matching oncologists 96%). Essential for ROI conversations.
- **Questions it prepares you for**: Who is using RAG in production? What are measurable outcomes? What ROI have others achieved?
- **Difficulty**: Beginner
- **Format**: Article with case studies
- **Time**: 30 minutes

---

### 26. Stratagem Systems -- "RAG Implementation Cost 2026: Real Pricing and ROI"
- **URL**: https://www.stratagem-systems.com/blog/rag-implementation-cost-roi-analysis
- **Why useful**: Data from 89 real RAG deployments. Implementation costs $8K-$45K. Breaks down hardware, API, development, and maintenance costs. The PM will ask "what does this cost?" -- this gives real numbers.
- **Questions it prepares you for**: What does RAG cost? What are ongoing costs? What is expected ROI timeline?
- **Difficulty**: Beginner
- **Format**: Article with cost breakdowns
- **Time**: 20 minutes

---

### 27. HBR -- "Overcoming the Organizational Barriers to AI Adoption"
- **URL**: https://hbr.org/2025/11/overcoming-the-organizational-barriers-to-ai-adoption
- **Why useful**: Why AI projects fail organizationally. Gap between pilot and production, why leadership buy-in is necessary but insufficient, how to build organizational scaffolding. Essential for understanding room dynamics.
- **Questions it prepares you for**: Why do AI projects fail to scale? What organizational barriers exist? How do you get from pilot to production?
- **Difficulty**: Beginner
- **Format**: Article
- **Time**: 20 minutes

---

### 28. HBR -- "Most AI Initiatives Fail. This 5-Part Framework Can Help."
- **URL**: https://hbr.org/2025/11/most-ai-initiatives-fail-this-5-part-framework-can-help
- **Why useful**: Concrete 5-part framework for successful AI initiatives. Why 80% fail and how to be in the 20%. Good for framing your demo as proactively addressing failure modes.
- **Questions it prepares you for**: What is the success rate for AI projects? What framework ensures success?
- **Difficulty**: Beginner
- **Format**: Article
- **Time**: 20 minutes

---

### 29. Prosci -- "AI Adoption: Driving Change With a People-First Approach"
- **URL**: https://www.prosci.com/blog/ai-adoption
- **Why useful**: Data-driven change management for AI. Key stats: 29% worry about displacement, 38% cite lack of training, organizations that prepare workforce are 7x more likely to meet objectives. Essential for handling skeptics.
- **Questions it prepares you for**: Why do people resist AI? How do you address job fears? What training is needed?
- **Difficulty**: Beginner
- **Format**: Article
- **Time**: 20 minutes

---

### 30. McKinsey -- "Reconfiguring Work: Change Management in the Age of Gen AI"
- **URL**: https://www.mckinsey.com/capabilities/quantumblack/our-insights/reconfiguring-work-change-management-in-the-age-of-gen-ai
- **Why useful**: Companies investing in AI trust are 2x more likely to see 10%+ revenue growth. Covers AI "superusers" as change agents. Directly applicable -- you are the superuser being asked to evangelize.
- **Questions it prepares you for**: How do you build trust? What is the business impact of trust-building? How do you create AI champions?
- **Difficulty**: Beginner-Intermediate
- **Format**: Article/report
- **Time**: 30 minutes

---

### 31. Plus AI -- "How to Present Technical Knowledge to a Non-Technical Audience"
- **URL**: https://plusai.com/blog/how-to-present-technical-knowledge-to-a-non-technical-audience
- **Why useful**: Practical tips: remove jargon, use analogies, lead with business impact, "a 30-second demo beats 3 paragraphs," keep slides to 1 message with 1-2 visuals. Directly applicable to your mixed audience.
- **Questions it prepares you for**: How do you explain RAG without jargon? How do you structure a demo? How do you handle mixed technical levels?
- **Difficulty**: Beginner
- **Format**: Article
- **Time**: 15 minutes

---

### 32. Plum.io -- "The Psychology of AI Resistance"
- **URL**: https://www.plum.io/blog/the-psychology-of-ai-resistance-cultural-transformation-strategies-that-work
- **Why useful**: Employees using AI were perceived as less competent by peers even when work quality improved -- resistance is often social, not technical. Covers sandbox environments, reframing AI as augmentation, leveraging champions, turning skeptics into advocates.
- **Questions it prepares you for**: Why are people hostile to AI? How do you handle jealousy? How do you turn skeptics into allies?
- **Difficulty**: Beginner
- **Format**: Article
- **Time**: 20 minutes

---

## BONUS RESOURCES: Reference Repositories and Deep Dives

Not required reading but invaluable for specific questions that may come up.

---

### 33. GitHub (NirDiamant) -- "RAG_Techniques"
- **URL**: https://github.com/NirDiamant/RAG_Techniques
- **Why useful**: 30+ Jupyter notebook implementations of advanced RAG techniques including adaptive retrieval, fusion retrieval, feedback loops, Graph RAG, and knowledge graph integration.
- **Difficulty**: Intermediate-Advanced
- **Format**: GitHub repository with notebooks
- **Time**: Browse as needed

---

### 34. GitHub (Danielskry) -- "Awesome-RAG"
- **URL**: https://github.com/Danielskry/Awesome-RAG
- **Why useful**: Curated master list of RAG tools, frameworks, techniques, papers, and learning materials.
- **Difficulty**: All levels
- **Format**: GitHub awesome-list
- **Time**: Browse as needed

---

### 35. Class Central -- "12 Best RAG Courses in 2026"
- **URL**: https://www.classcentral.com/report/best-rag-courses/
- **Why useful**: Independently ranked comparison of 10 courses across 6 platforms (6 free). For continued learning or recommending to team members.
- **Difficulty**: All levels
- **Format**: Course review article
- **Time**: 15 minutes to read

---

### 36. Lakera AI -- "Guide to Hallucinations in Large Language Models"
- **URL**: https://www.lakera.ai/blog/guide-to-hallucinations-in-large-language-models
- **Why useful**: Deep-dive on hallucination causes, types, and mitigation. Why LLMs hallucinate, detection methods, practical mitigation including prompt engineering and calibration.
- **Difficulty**: Intermediate
- **Format**: Article
- **Time**: 30 minutes

---

### 37. Firecrawl Blog -- "Best Chunking Strategies for RAG in 2025"
- **URL**: https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025
- **Why useful**: NVIDIA 2024 benchmark results testing 7 chunking strategies across 5 datasets. Page-level won at 0.648 accuracy, but optimal size depends on query type.
- **Difficulty**: Intermediate
- **Format**: Article with benchmark data
- **Time**: 30 minutes

---

### 38. Paul Iusztin and Maxime Labonne -- "LLM Engineer's Handbook" (Book)
- **URL**: https://www.amazon.com/LLM-Engineers-Handbook-engineering-production/dp/1836200072
- **GitHub**: https://github.com/PacktPublishing/LLM-Engineers-Handbook
- **Why useful**: Production-focused handbook covering RAG pipelines, fine-tuning, evaluation, and deployment. More code-heavy than Chip Huyen's book. Best for hardening your system after the demo.
- **Difficulty**: Intermediate-Advanced
- **Format**: Book (Packt, 10,000+ copies sold)
- **Time**: 10-15 hours

---

## QUICK-REFERENCE: Demo Questions Mapped to Resources

| # | Question | Best Resource(s) |
|---|----------|-----------------|
| 1 | What is RAG? | #1 (IBM video), #2 (Pinecone series) |
| 2 | How does it work? | #4 (Learn by Building), #2 (Pinecone) |
| 3 | What are embeddings? | #3 (Pinecone embeddings) |
| 4 | What is a vector database? | #2 (Pinecone series) |
| 5 | What is chunking? | #5 (Weaviate), #37 (Firecrawl benchmarks) |
| 6 | Why not just use ChatGPT? | #7 (Fine-tuning vs RAG), #1 (IBM) |
| 7 | Why RAG instead of fine-tuning? | #7 (Fine-tuning vs RAG) |
| 8 | Are long-context models making RAG obsolete? | #8 (Meilisearch comparison) |
| 9 | How accurate is this? | #10 (DeepLearning.AI eval), #12 (RAGAS) |
| 10 | How do you measure accuracy? | #10, #12, #13 (Meilisearch eval) |
| 11 | What if it hallucinates? | #36 (Lakera hallucination), #22 (Chip Huyen) |
| 12 | What is prompt injection? | #15 (OWASP cheat sheet), #16 (Lakera) |
| 13 | Is this secure? | #14 (OWASP Top 10), #17 (Lakera LLM security) |
| 14 | Can this run air-gapped? | #19 (Air-gapped guide) |
| 15 | How do you test security? | #21 (Promptfoo), #18 (LLMSecurityGuide) |
| 16 | Who else is using RAG? | #25 (Use cases), #24 (Vectara) |
| 17 | What is the ROI? | #26 (Cost/ROI), #25 (case studies) |
| 18 | What does this cost? | #26 (Stratagem cost analysis) |
| 19 | How does this scale? | #24 (Vectara), #22 (Chip Huyen) |
| 20 | Will this replace our jobs? | #29 (Prosci), #32 (Psychology of resistance) |
| 21 | How do you get organizational buy-in? | #27 (HBR), #30 (McKinsey) |
| 22 | How do you handle skeptics? | #32 (Psychology of resistance), #29 (Prosci) |
| 23 | How do you explain this to non-technical people? | #31 (Plus AI presentation guide) |
| 24 | What are the known limitations? | #12 (RAGAS), #22 (Chip Huyen) |
| 25 | What advanced techniques exist? | #9 (Lance Martin), #33 (RAG_Techniques repo) |

---

## SUGGESTED 2-WEEK STUDY SCHEDULE

### Week 1: Foundations + Security
| Day | Resources | Hours | Focus |
|-----|-----------|-------|-------|
| 1 | #1, #2, #3 | 3 | Core concepts |
| 2 | #4, #5 | 3 | Hands-on + chunking |
| 3 | #6, #7, #8 | 1.5 | RAG vs alternatives |
| 4 | #9 | 3 | Lance Martin deep course |
| 5 | #10, #12, #13 | 3.5 | Evaluation |
| 6 | #14, #15, #16 | 4 | Security (OWASP + injection) |
| 7 | #17, #19, #20, #21 | 3 | Security depth + air-gapped |

### Week 2: Enterprise + Presentation
| Day | Resources | Hours | Focus |
|-----|-----------|-------|-------|
| 8 | #24, #25, #26 | 1 | Case studies + ROI |
| 9 | #27, #28 | 0.7 | HBR organizational barriers |
| 10 | #29, #30 | 0.8 | Change management |
| 11 | #31, #32 | 0.6 | Presentation + resistance |
| 12-14 | #22 | 8-12 | Chip Huyen book (comprehensive) |

---

## KEY STATISTICS TO MEMORIZE FOR THE DEMO

These are the numbers your audience will remember:

- RAG reduces hallucination by **70-90%** compared to standard LLMs (industry benchmark)
- **30-60%** of enterprise AI use cases now use RAG (Vectara 2025)
- **85%** of executives misestimate AI project costs by >10% (Xenoss/TCO research)
- **70%** of AI adoption challenges are people/process, not technical (BCG)
- **54%** of executives cite resistance to change as #1 AI adoption obstacle (PwC)
- Organizations that prepare workforce are **7x more likely** to meet AI objectives (Prosci)
- Companies building AI trust are **2x more likely** to see 10%+ revenue growth (McKinsey)
- RAG implementation costs **$8K-$45K** based on 89 real deployments (Stratagem)
- **Bank of America Erica**: 42M users, 2B+ interactions, 65% handle time reduction
- **IBM Watson Health**: matched oncologist treatment recommendations 96% of the time
