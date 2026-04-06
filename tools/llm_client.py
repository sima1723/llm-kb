#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM API 调用封装：支持重试、费用控制、token 统计。
"""

import os
import time
import logging
from pathlib import Path
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

    def __init__(self, config: dict, tool: Optional[str] = None):
        """
        参数：
          config: 来自 config.yaml 的完整配置字典
          tool:   工具名（如 "compile" / "stub_fill" / "ask"），
                  用于从 model_by_tool 自动选取合适模型和计价
        """
        try:
            import anthropic
            self._anthropic = anthropic
        except ImportError:
            raise ImportError("请安装 anthropic SDK：pip install anthropic")

        llm_cfg = config.get("llm", {})
        compile_cfg = config.get("compile", {})

        # 按工具选模型；未配置则用默认模型
        default_model = llm_cfg.get("model", "claude-sonnet-4-6")
        self.model = llm_cfg.get("model_by_tool", {}).get(tool, default_model) if tool else default_model

        self.max_tokens = llm_cfg.get("max_tokens", 4096)
        self.retry_count = llm_cfg.get("retry_count", 3)
        self.retry_delay_base = llm_cfg.get("retry_delay_base", 2)

        self.budget_limit = compile_cfg.get("budget_limit_usd", 5.0)

        # 按实际所选模型查定价；兜底：旧字段 input_price_per_mtok
        pricing = llm_cfg.get("pricing", {}).get(self.model, {})
        self.input_price  = pricing.get("input",  compile_cfg.get("input_price_per_mtok",  3.0))
        self.output_price = pricing.get("output", compile_cfg.get("output_price_per_mtok", 15.0))

        if tool:
            logger.debug(f"LLMClient tool={tool} → model={self.model} "
                         f"(${self.input_price}/${self.output_price} per M tokens)")

        # 认证优先级：config.yaml api_key > 环境变量 ANTHROPIC_API_KEY > Claude Code OAuth token
        api_key = config.get("api_key", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "")
        # base_url：支持 AnyRouter / OpenRouter 等兼容中转服务
        base_url = config.get("base_url", "").strip() or os.environ.get("ANTHROPIC_BASE_URL", "")

        client_kwargs = {}
        if base_url:
            client_kwargs["base_url"] = base_url

        if api_key:
            self.client = self._anthropic.Anthropic(api_key=api_key, **client_kwargs)
        else:
            # Claude Code 远程环境：从 session ingress token 文件读取 Bearer token
            token_file = os.environ.get("CLAUDE_SESSION_INGRESS_TOKEN_FILE", "")
            if token_file and os.path.exists(token_file):
                auth_token = Path(token_file).read_text().strip()
                self.client = self._anthropic.Anthropic(auth_token=auth_token, **client_kwargs)
            else:
                # 让 SDK 自行从环境变量中查找
                self.client = self._anthropic.Anthropic(**client_kwargs)

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

    def call(self, prompt: str, system: Optional[str] = None,
             max_tokens: Optional[int] = None) -> str:
        """
        调用 LLM API，返回纯文本响应。

        参数：
          prompt:     用户消息
          system:     系统提示（可选）
          max_tokens: 覆盖默认 max_tokens（用于简单任务节省成本）

        抛出：
          BudgetExceeded: 累计费用超出 budget_limit_usd
          Exception:      重试耗尽后仍失败
        """
        effective_max_tokens = max_tokens or self.max_tokens
        # 预检费用（粗估：prompt 长度 / 4 ≈ token 数）
        estimated_input = len(prompt) // 4
        estimated_cost = self._calc_cost(estimated_input, effective_max_tokens)
        if self._cost_usd + estimated_cost > self.budget_limit:
            raise BudgetExceeded(
                f"预算保护：累计费用 ${self._cost_usd:.3f}，"
                f"本次预估 ${estimated_cost:.3f}，"
                f"超出上限 ${self.budget_limit}"
            )

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": self.model,
            "max_tokens": effective_max_tokens,
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
                # 完整错误体（供调试）
                err_body = getattr(e, 'body', None) or str(e)
                if e.status_code in (429, 529):  # rate limit / overload
                    wait = self.retry_delay_base ** (attempt + 1)
                    logger.warning(f"限流，{wait}s 后重试（{attempt+1}/{self.retry_count}）")
                    time.sleep(wait)
                elif e.status_code >= 500:
                    wait = self.retry_delay_base ** (attempt + 1)
                    logger.warning(f"服务器错误 {e.status_code}，{wait}s 后重试\n  详情: {err_body}")
                    time.sleep(wait)
                else:
                    # 4xx：配置错误（model_not_found、invalid_api_key 等），立即失败
                    logger.error(f"API 错误 {e.status_code}（不重试）: {err_body}")
                    raise

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
