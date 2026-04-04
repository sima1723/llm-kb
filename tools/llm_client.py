#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM API 调用封装：支持重试、费用控制、token 统计。
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """超出预算上限时抛出。"""
    pass


class LLMClient:
    """
    封装 Anthropic API 调用，提供：
    - 指数退避重试
    - token 计数和费用累计
    - 预算上限保护
    """

    def __init__(self, config: dict):
        """
        参数：
          config: 来自 config.yaml 的完整配置字典
        """
        try:
            import anthropic
            self._anthropic = anthropic
        except ImportError:
            raise ImportError("请安装 anthropic SDK：pip install anthropic")

        llm_cfg = config.get("llm", {})
        compile_cfg = config.get("compile", {})

        self.model = llm_cfg.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = llm_cfg.get("max_tokens", 8192)
        self.retry_count = llm_cfg.get("retry_count", 3)
        self.retry_delay_base = llm_cfg.get("retry_delay_base", 2)

        self.budget_limit = compile_cfg.get("budget_limit_usd", 5.0)
        self.input_price = compile_cfg.get("input_price_per_mtok", 3.0)   # per 1M tokens
        self.output_price = compile_cfg.get("output_price_per_mtok", 15.0)

        # 认证：优先使用 ANTHROPIC_API_KEY，其次尝试 Claude Code 的 OAuth Bearer token
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            self.client = self._anthropic.Anthropic(api_key=api_key)
        else:
            # Claude Code 远程环境：从 session ingress token 文件读取 Bearer token
            token_file = os.environ.get("CLAUDE_SESSION_INGRESS_TOKEN_FILE", "")
            if token_file and os.path.exists(token_file):
                auth_token = open(token_file).read().strip()
                self.client = self._anthropic.Anthropic(auth_token=auth_token)
            else:
                # 让 SDK 自行从环境变量中查找
                self.client = self._anthropic.Anthropic()

        # 累计统计
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        """计算本次调用费用（USD）。"""
        return (
            input_tokens / 1_000_000 * self.input_price
            + output_tokens / 1_000_000 * self.output_price
        )

    def call(self, prompt: str, system: Optional[str] = None) -> str:
        """
        调用 LLM API，返回纯文本响应。

        参数：
          prompt: 用户消息
          system: 系统提示（可选）

        抛出：
          BudgetExceeded: 累计费用超出 budget_limit_usd
          Exception: 重试耗尽后仍失败
        """
        # 预检费用（粗估：prompt 长度 / 4 ≈ token 数）
        estimated_input = len(prompt) // 4
        estimated_cost = self._calc_cost(estimated_input, self.max_tokens)
        if self._cost_usd + estimated_cost > self.budget_limit:
            raise BudgetExceeded(
                f"预算保护：累计费用 ${self._cost_usd:.3f}，"
                f"本次预估 ${estimated_cost:.3f}，"
                f"超出上限 ${self.budget_limit}"
            )

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        last_error = None
        for attempt in range(self.retry_count):
            try:
                response = self.client.messages.create(**kwargs)

                # 统计 token
                input_tok = response.usage.input_tokens
                output_tok = response.usage.output_tokens
                cost = self._calc_cost(input_tok, output_tok)

                self._calls += 1
                self._input_tokens += input_tok
                self._output_tokens += output_tok
                self._cost_usd += cost

                logger.debug(
                    f"API 调用 #{self._calls}: "
                    f"in={input_tok}, out={output_tok}, "
                    f"cost=${cost:.4f}, total=${self._cost_usd:.4f}"
                )

                # 提取文本内容
                return "".join(
                    block.text
                    for block in response.content
                    if block.type == "text"
                )

            except self._anthropic.APIStatusError as e:
                last_error = e
                if e.status_code in (429, 529):  # rate limit / overload
                    wait = self.retry_delay_base ** (attempt + 1)
                    logger.warning(f"限流，{wait}s 后重试（{attempt+1}/{self.retry_count}）")
                    time.sleep(wait)
                elif e.status_code >= 500:
                    wait = self.retry_delay_base ** (attempt + 1)
                    logger.warning(f"服务器错误 {e.status_code}，{wait}s 后重试")
                    time.sleep(wait)
                else:
                    raise  # 4xx 非限流错误直接抛出

            except Exception as e:
                last_error = e
                wait = self.retry_delay_base ** (attempt + 1)
                logger.warning(f"调用异常 {e}，{wait}s 后重试（{attempt+1}/{self.retry_count}）")
                time.sleep(wait)

        raise Exception(f"API 调用失败（已重试 {self.retry_count} 次）：{last_error}")

    def get_cost_summary(self) -> dict:
        """返回累计调用统计。"""
        return {
            "calls": self._calls,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "cost_usd": round(self._cost_usd, 6),
        }
