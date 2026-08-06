#!/usr/bin/env python3
"""供 GitHub Actions 验证滚轮事件和多帧拼接的 X11 测试窗口。"""

import tkinter as tk

root = tk.Tk()
root.overrideredirect(True)
root.geometry("420x420+0+0")

canvas = tk.Canvas(root, width=400, height=420, background="white", highlightthickness=0)
scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
canvas.configure(yscrollcommand=scrollbar.set)
canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

content = tk.Frame(canvas, background="white")
canvas.create_window((0, 0), window=content, anchor="nw")
for index in range(120):
    background = "white" if index % 2 == 0 else "#e8e8e8"
    tk.Label(
        content,
        text=f"ScrollShot integration line {index:03d}",
        width=42,
        anchor="w",
        background=background,
        font=("Sans", 12),
    ).pack()

content.update_idletasks()
canvas.configure(scrollregion=canvas.bbox("all"))
canvas.bind_all("<Button-5>", lambda _event: canvas.yview_scroll(3, "units"))
root.mainloop()
