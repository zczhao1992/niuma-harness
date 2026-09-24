def print_box(lines: list[str]) -> None:
    inner = max(len(line) for line in lines) + 2
    print("┌" + "─" * inner + "┐")
    for line in lines:
        print("│ " + line.center(inner - 2) + " │")
    print("└" + "─" * inner + "┘")


print_box(["你好世界"])

name = input("请输入你的姓名：").strip() or "陌生人"

print()
print_box([f"你好，{name}！", "很高兴认识你 (◕‿◕)"])
