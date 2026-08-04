import sys
p = r"D:\Users\Administrator\Documents\u4ee3\u7801pa_script\scripts\capture_gui\main.py"
with open(p, encoding="utf-8") as f: c = f.read()
old = "if tab == 0:
            self.tab0.pack(fill=tk.X, before=self.sel_text.master)
            pass  # tab1_forget
        else:
            pass  # tab0_forget"
new = "if tab == 0:
            self.tab0.pack(fill=tk.BOTH, expand=True, before=self.tab1)
            self.tab1.pack_forget()
        else:
            self.tab0.pack_forget()
            self.tab1.pack(fill=tk.BOTH, expand=True)"
c = c.replace(old, new)
with open(p, "w", encoding="utf-8") as f: f.write(c)
print("done")
