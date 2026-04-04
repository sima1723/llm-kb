---
source_type: article
source_url: https://example.com/transformer
clipped_at: 2025-01-02
---
# Transformer 架构

Transformer 是由 Vaswani 等人在 2017 年论文《Attention Is All You Need》中提出的神经网络架构，彻底改变了自然语言处理领域。

## 自注意力机制

自注意力（Self-Attention）让序列中每个位置都能直接关注其他所有位置，捕捉长距离依赖关系。计算公式：Attention(Q,K,V) = softmax(QK^T / √d_k)V，其中 Q、K、V 分别为查询、键、值矩阵。

## 多头注意力

多头注意力（Multi-Head Attention）并行运行多个注意力头，每个头学习不同的表示子空间，最后拼接输出。这使模型能同时关注不同位置的不同特征。

## 位置编码

由于注意力机制本身对位置不敏感，Transformer 使用位置编码（Positional Encoding）为序列注入位置信息。原始论文使用正弦/余弦函数，现代模型多用 RoPE（旋转位置编码）。

## 与 LLM 的关系

现代大语言模型（LLM）均基于 Transformer 架构构建，通常采用仅解码器（Decoder-only）变体，通过自回归方式生成文本。
