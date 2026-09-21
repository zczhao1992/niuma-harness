import tiktoken


def get_tokeniuzer(model: str):
    """获取指定模型的 tiktoken 编码器 (Encoder) 回调函数。

    Args:
        model (str): 目标模型名称（如 "gpt-4o", "gpt-3.5-turbo" 等）。

    Returns:
        Callable[[str], list[int]]: 接收字符串并返回 Token ID 列表的编码函数。
    """
    try:
        # 尝试获取对应模型的特定编码器
        encoding = tiktoken.encoding_for_model(model)
        return encoding.encode
    except Exception:
        # 若模型不在 tiktoken 官方库列表中（如自定义/开源模型），降级使用通用的 cl100k_base 编码器
        encoding = tiktoken.get_encoding("cl100k_base")
        return encoding.encode


def count_tokens(text: str, model: str = "deepseek-chat") -> int:
    """计算给定文本在指定模型下的准确 Token 数量。

    Args:
        text (str): 待计算的文本内容。
        model (str, optional): 调用的模型标识，默认为 "gpt-4o"。

    Returns:
        int: Token 总数。若编码失败则返回估算值。
    """
    tokenizer = get_tokeniuzer(model)

    if tokenizer:
        return len(tokenizer(text))
    # 兜底降级方案：字符数粗略估算
    return estimate_tokens(text)


def estimate_tokens(text: str) -> int:
    """当无法获得精确分词器时的 Token 粗略估算函数。

    按照行业通用的经验法则(English/Code 场景下约 4 个字符折算 1 个 Token)计算。

    Args:
        text (str): 目标文本。

    Returns:
        int: 估算的 Token 数量(最小值为 1)。
    """
    return max(1, len(text) // 4)


def truncate_text(text: str, model: str, max_tokens: int, suffix: str = "\n... [truncated]", preserve_lines: bool = True):
    """按 Token 上限安全截断长文本。

    如果文本总 Token 数超过 `max_tokens`，将自动扣减后缀所占用的 Token 数，
    并对前缀部分进行按行或按字符的智能截断。

    Args:
        text (str): 待截断的原始文本。
        model (str): 使用的 LLM 模型标识。
        max_tokens (int): 允许的最大 Token 上限。
        suffix (str, optional): 截断后追加的后缀标识。默认为 "\n... [truncated]"。
        preserve_lines (bool, optional): 是否优先保持完整行结构（不把某一行从中间砍断）。默认为 True。

    Returns:
        str: 截断并拼接后缀后的符合 Token 规则的文本。
    """

    current_tokens = count_tokens(text, model)
    # 未超出上限直接原样返回
    if current_tokens <= max_tokens:
        return text
    # 计算预留给后缀的 Token 空间
    suffix_tokens = count_tokens(suffix, model)
    target_tokens = max_tokens - suffix_tokens
    # 若后缀本身已经超标，直接返回清洗后的后缀
    if target_tokens <= 0:
        return suffix.strip()
    # 根据策略选择按行截断或按字符二分截断
    if preserve_lines:
        return _truncate_by_lines(text, target_tokens, suffix, model)
    else:
        return _truncate_by_chars(text, target_tokens, suffix, model)


def _truncate_by_lines(text: str, target_tokens: int, suffix: str, model: str):
    """按行安全截断文本（保持每行完整性）。

    逐行累加 Token 数量，当加上下一行会导致整体超标时立刻停止。

    Args:
        text (str): 原始文本。
        target_tokens (int): 扣除后缀后留给正文的最大 Token 预算。
        suffix (str): 后缀文本。
        model (str): 模型标识。

    Returns:
        str: 截断后的结果；若第一行就超过预算，则降级为 `_truncate_by_chars`。
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    current_tokens = 0

    for line in lines:
        # 注意补回 split 掉的换行符进行精确计算
        line_tokens = count_tokens(line + "\n", model)
        if current_tokens + line_tokens > target_tokens:
            break
        result_lines.append(line)
        current_tokens += line_tokens
    # 若连第一行都放不下，则退化为按字符二分精准截断
    if not result_lines:
        return _truncate_by_chars(text, target_tokens, suffix, model)

    return "\n".join(result_lines) + suffix


def _truncate_by_chars(text: str, target_tokens: int, suffix: str, model: str):
    """按字符二分查找精准截断文本。

    利用二分查找 (Binary Search) 快速定位符合 `target_tokens` 的最大字符索引位置，
    相比逐字递增计算大幅降低了调用 `tiktoken` 的计算开销。

    Args:
        text (str): 原始文本。
        target_tokens (int): 目标 Token 预算。
        suffix (str): 后缀文本。
        model (str): 模型标识。

    Returns:
        str: 截断后的结果。
    """
    low, high = 0, len(text)
    # 二分搜索寻找最长合法前缀位置
    while low < high:
        mid = (low + high + 1) // 2
        if count_tokens(text[:mid], model) <= target_tokens:
            low = mid   # mid 是合法的，尝试更长的位置
        else:
            high = mid - 1  # mid 超标了，往左收缩

    return text[:low] + suffix
