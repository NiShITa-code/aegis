# Why the Most Powerful AI Models in the World Can't Be Trusted Straight Out of the Box

**GPT, Gemini, Claude — every frontier model was broken in 2025. Not by nation-state hackers. By researchers with a text prompt. Here's the foundational reason why.**

*Part 1 of 6 in the "LLM Alignment from Zero to Production" series. This article stands alone — no prior AI knowledge required.*

---

## The Day Every Major AI Model Failed at Once

On February 25, 2025, a team of security researchers published a finding that quietly shook every AI lab simultaneously.

They had discovered a novel **"chain-of-thought jailbreak"** — a technique that hijacked an LLM's own internal reasoning process to bypass its safety filters. The attack didn't use malware. It didn't exploit a server vulnerability. It used *words*. And it worked on OpenAI's o1 and o3, Google's Gemini 2.0 Flash Thinking, DeepSeek-R1, and Anthropic's Claude 3.7 Sonnet — all at once (arXiv:2502.12893).

Three companies. Billions in safety research. Broken by a text prompt.

This wasn't an anomaly. Months later, a zero-click vulnerability in Microsoft 365 Copilot allowed attackers to embed malicious instructions inside ordinary emails, causing the AI to silently exfiltrate confidential corporate data — no user click required. A global cybercrime group called Storm-2139 had already been hijacking Azure OpenAI accounts, jailbreaking the models, and reselling access to produce illicit content at scale.

**The pattern is consistent:** the most capable AI systems ever built keep getting broken in ways that feel embarrassingly simple. Why?

The answer isn't that these companies are incompetent. It's that they're fighting a problem that goes deeper than any patch can fix. To understand it, we need to go back to the beginning — to what a language model actually *is*.

---

## The Librarian and the Oracle: What an LLM Really Does

Here's an analogy that will stick with you.

Imagine two kinds of knowledge sources. The **Librarian** has read everything ever written. Ask her a question, she finds the most relevant passage and reads it back to you. She doesn't *think* — she *retrieves*.

The **Oracle** has also read everything ever written, but she does something different. She infers. She synthesises. She answers questions no book has ever directly answered. She reasons, connects, extrapolates.

Most people assume LLMs are Oracles. They're closer to extraordinarily sophisticated Librarians — with one crucial difference.

A **Large Language Model** is a neural network trained on hundreds of billions of words of human text — books, websites, code, conversations, research papers — with a single objective:

> **Given the words so far, predict the next most likely word.**

That's it. Nothing more.

At training time, the model sees a sentence like *"The capital of France is ___"* and learns to predict *"Paris"* because that's what appears in the data. Over trillions of such predictions, it develops an extraordinarily rich internal representation of how language works, what facts correlate, how arguments are structured, what follows what.

The result is something that *looks* like understanding, *sounds* like reasoning, and *feels* like intelligence. But the underlying mechanism is statistical pattern matching at a scale no human can intuit.

The formal training objective looks like this:

$$\mathcal{L} = - \sum_{t=1}^{T} \log P_\theta(x_t \mid x_1, x_2, \ldots, x_{t-1})$$

In plain English: the model is penalised every time it assigns low probability to the word that actually came next. Train long enough on enough data, and the model gets very, very good at this. **Good at predicting text is not the same as good at being safe, truthful, or helpful.**

---

## Scale Makes It Smarter — And Stranger

Something unexpected happens when you scale this simple objective up. Researchers at Google, OpenAI and DeepMind consistently found that as models got larger — more parameters, more data, more compute — they didn't just get better at prediction. They spontaneously developed **emergent capabilities** nobody explicitly trained for (Wei et al., 2022).

Arithmetic. Multi-step reasoning. Code generation. Translation between languages the model wasn't specifically trained on. These abilities appeared, seemingly from nowhere, past certain scale thresholds.

This is both remarkable and deeply unsettling. If capabilities emerge unpredictably, so do failure modes.

---

## What "Deployment" Actually Means

When a lab finishes training a model, the raw weights are essentially a very powerful autocomplete engine. Deploying it to production means millions of real users sending it real prompts — patients asking about medications, children using it for homework, engineers writing production code, employees querying internal company data.

At that scale, edge cases aren't edge cases anymore. They're daily occurrences.

A raw model has no concept of:
- **Honesty** — it will confidently hallucinate facts that sound plausible
- **Intent** — it can't distinguish a security researcher from a bad actor
- **Context** — it doesn't know if it's talking to a child or a professional
- **Consequences** — it has no model of what happens in the real world after it outputs text

It just predicts what word comes next. Extremely well.

---

## Five Ways Raw Models Fail in the Real World

| Failure Mode | What Happens | Real Example |
|---|---|---|
| **Hallucination** | Generates confident, plausible-sounding falsehoods | A lawyer submitted ChatGPT-fabricated case citations to a US federal court (2023) |
| **Jailbreaking** | Safety filters bypassed via adversarial prompts | Chain-of-thought attack broke GPT-o3, Gemini 2.0, Claude 3.7 simultaneously (Feb 2025) |
| **Sycophancy** | Tells users what they want to hear, not what's true | Models agreeing with users' wrong medical self-diagnoses to avoid conflict |
| **Prompt Injection** | Malicious instructions in external content hijack the model | MS Copilot email exploit silently exfiltrated corporate data (Jun 2025) |
| **Harmful Compliance** | Follows harmful instructions because it has no values, only patterns | Raw models will explain dangerous synthesis routes if prompted correctly |

Each of these failures has the same root: **the model was trained to predict text, not to do good.**

---

## The Core Problem: Capability Is Not Alignment

Here's the insight that changes how you think about AI:

**A more capable model is not automatically a safer model.** In fact, a more capable model can be a *more dangerous* one — it's better at finding the gap in your safety filter, better at crafting convincing misinformation, better at writing exploit code.

This is the alignment problem in one sentence: **we know how to make LLMs more capable, but making them reliably do what we actually want them to do — rather than what their training data implied they should do — is an entirely separate, unsolved problem.**

The gap between "can predict any text" and "should produce this output in this context for this user" is enormous. Bridging it is what the field of **AI alignment** is about.

---

## So What Does Alignment Actually Do?

Think of the raw model as a brilliant, well-read person who has never been taught ethics, social norms, or professional standards. Every piece of knowledge is there — but no framework for when and how to apply it responsibly.

Alignment is the training process that installs that framework.

In practice, it's a family of techniques applied *after* initial training:

- **RLHF (Reinforcement Learning from Human Feedback)** — humans rate model outputs, and those ratings shape future behaviour (Christiano et al., 2017)
- **Constitutional AI** — the model critiques and revises its own outputs against a set of principles (Bai et al., 2022, Anthropic)
- **DPO (Direct Preference Optimisation)** — a cleaner mathematical alternative to RLHF now used by most frontier labs (Rafailov et al., 2023)

Each of these takes a capable-but-unconstrained model and steers its outputs toward being helpful, harmless, and honest. None of them are perfect. All of them are actively researched.

**The 2025 jailbreaks aren't proof that alignment failed — they're proof that alignment is hard and ongoing.** Every attack is a data point that informs the next generation of defences.

---

## The One Thing to Take Away

If you remember nothing else from this article, remember this:

> **LLMs are trained to predict the most probable next word. Alignment is the separate, difficult process of making "most probable" coincide with "most helpful and safe." The gap between those two things is what this series is about.**

---

## What's Next

In **Part 2**, we go deeper into the alignment problem itself — why it's considered one of the hardest problems in computer science, what "Goodhart's Law" means for AI safety, and the real-world failures that happen when alignment goes wrong at production scale.

*If you're just starting your journey in AI safety, bookmark this series — each article is designed to stand alone but builds on the last. If you're an ML engineer who's been building with LLMs, Part 3 (RLHF) and Part 5 (DPO) will give you the production context most tutorials skip.*

---

**Before you go — a question for the comments:**

The chain-of-thought jailbreak of February 2025 broke three frontier models simultaneously with a text prompt. Does that mean alignment research is fundamentally losing the arms race? Or is each jailbreak a necessary step toward a more robust system? I'd genuinely like to know where you stand.

---

---

## References & Further Reading

**Foundational Papers**
- Vaswani et al. (2017). *Attention Is All You Need.* NeurIPS. [arXiv:1706.03762](https://arxiv.org/abs/1706.03762)
- Wei et al. (2022). *Emergent Abilities of Large Language Models.* TMLR. [arXiv:2206.07682](https://arxiv.org/abs/2206.07682)
- Christiano et al. (2017). *Deep Reinforcement Learning from Human Preferences.* NeurIPS. [arXiv:1706.03741](https://arxiv.org/abs/1706.03741)
- Bai et al. (2022). *Constitutional AI: Harmlessness from AI Feedback.* Anthropic. [arXiv:2212.08073](https://arxiv.org/abs/2212.08073)
- Rafailov et al. (2023). *Direct Preference Optimization: Your Language Model is Secretly a Reward Model.* NeurIPS. [arXiv:2305.18290](https://arxiv.org/abs/2305.18290)

**2025 Incidents Cited**
- H-CoT Jailbreak (Feb 2025): [arXiv:2502.12893](https://arxiv.org/abs/2502.12893)
- Storm-2139 / LLMjacking: [Microsoft On the Issues](https://blogs.microsoft.com/on-the-issues/2025/02/27/disrupting-cybercrime-abusing-gen-ai/)
- OWASP Gen AI Incident Round-up Jan–Feb 2025: [OWASP](https://genai.owasp.org/2025/03/06/owasp-gen-ai-incident-exploit-round-up-jan-feb-2025/)
- Mata v. Avianca (lawyer hallucination case, 2023): [Reuters](https://www.reuters.com/legal/new-york-lawyers-sanctioned-using-chatgpt-legal-research-2023-06-22/)

*This is Part 1 of the "LLM Alignment from Zero to Production" series.*
