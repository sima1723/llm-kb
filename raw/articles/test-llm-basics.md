---
source_type: article
source_url: https://example.com/test
clipped_at: 2025-01-01
---
# LLM 基础知识

大语言模型（LLM，Large Language Model）是基于 Transformer 架构的大规模神经网络，通过在海量文本上进行自监督预训练获得语言理解与生成能力。

## 核心机制

LLM 的核心是注意力机制（Attention Mechanism），允许模型在处理每个 token 时关注序列中所有其他 token 的信息。Transformer 由编码器和解码器组成，现代 LLM（如 GPT、Claude）通常只使用解码器部分。

## 预训练与微调

预训练（Pre-training）阶段，模型在数万亿 token 的文本上学习下一个 token 的预测任务。微调（Fine-tuning）阶段，通过有监督数据或强化学习（RLHF）使模型的输出更符合人类意图。

## 涌现能力

当模型参数量超过某个阈值，会出现在小模型上不存在的能力，称为涌现（Emergence）。常见涌现能力包括上下文学习（In-context Learning）、思维链推理（Chain-of-Thought）等。

## 常见模型

GPT 系列（OpenAI）、Claude 系列（Anthropic）、Gemini（Google）、Llama 系列（Meta）是当前主流的大语言模型。
