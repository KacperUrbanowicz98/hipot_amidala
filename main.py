# main.py
"""Punkt wejścia aplikacji Hi-Pot Amidala"""
import tkinter as tk
from gui import AmidalaApp

if __name__ == "__main__":
    root = tk.Tk()
    app  = AmidalaApp(root)
    root.mainloop()