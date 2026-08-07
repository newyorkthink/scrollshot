#!/usr/bin/env python3
"""X11 scrolling window with fixed header and footer for integration tests."""

import tkinter as tk

root = tk.Tk()
root.overrideredirect(True)
root.geometry("420x420+0+0")
root.configure(background="white")

header = tk.Label(
    root,
    text="FIXED HEADER",
    height=2,
    foreground="white",
    background="#263238",
    font=("Sans", 13, "bold"),
)
header.pack(side="top", fill="x")

footer = tk.Label(
    root,
    text="FIXED FOOTER",
    height=2,
    foreground="black",
    background="#cfd8dc",
    font=("Sans", 12, "bold"),
)
footer.pack(side="bottom", fill="x")

body = tk.Frame(root, background="white")
body.pack(side="top", fill="both", expand=True)
canvas = tk.Canvas(body, width=400, background="white", highlightthickness=0)
scrollbar = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
canvas.configure(yscrollcommand=scrollbar.set)
canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

content = tk.Frame(canvas, background="white")
canvas.create_window((0, 0), window=content, anchor="nw")
for index in range(180):
    background = "white" if index % 2 == 0 else "#e8e8e8"
    tk.Label(
        content,
        text=f"Integration line {index:03d}",
        width=42,
        anchor="w",
        background=background,
        font=("Sans", 12),
    ).pack()

content.update_idletasks()
canvas.configure(scrollregion=canvas.bbox("all"))
canvas.bind_all("<Button-5>", lambda _event: canvas.yview_scroll(15, "units"))
root.mainloop()
