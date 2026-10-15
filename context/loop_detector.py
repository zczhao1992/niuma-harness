from collections import deque
from typing import Any


class LoopDetector:
    def __init__(self):
        self.max_exact_repeats = 3
        self.max_cycle_length = 3
        self._history: deque[str] = deque(maxlen=20)

    def record_action(self, action_type: str, **details: Any):
        output = [action_type]

        if action_type == "tool_call":
            output.append(details.get("tool_name", ""))
            args = details.get("args", {})

            if isinstance(args, dict):
                for k in sorted(args.keys()):
                    output.append(f"{k}={str(args[k])}")
        elif action_type == "response":
            output.append(details.get("text", ""))

        signature = "|".join(output)
        self._history.append(signature)

    def check_for_loop(self) -> str | None:
        if len(self._history) < 2:
            return None

        if len(self._history) >= self.max_exact_repeats:
            recent = list(self._history)[-self.max_exact_repeats:]
            if len(set(recent)) == 1:
                return f"重复同样的事件 {self.max_exact_repeats} 次"

        if len(self._history) >= self.max_cycle_length * 2:
            history = list(self._history)

            for cycle_len in range(
                2, min(self.max_cycle_length + 1, len(history) // 2 + 1)
            ):
                recent = history[-cycle_len * 2:]
                if recent[:cycle_len] == recent[cycle_len:]:
                    return f"检测到重复循环，长度为 {cycle_len}"

        return None

    def clear(self) -> None:
        self._history.clear()
