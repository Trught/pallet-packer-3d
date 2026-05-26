import os
import random
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from itertools import permutations
from tkinter import colorchooser, messagebox, ttk

_mpl_cache_dir = os.path.join(os.path.dirname(__file__), ".mplconfig")
os.makedirs(_mpl_cache_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _mpl_cache_dir)

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.colors import to_hex, to_rgb
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection


@dataclass
class PalletSpec:
    name: str
    length_mm: int
    width_mm: int
    max_load_kg: float


@dataclass
class PackageSpec:
    name: str
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    count: int
    color: str


class PalletPacker:
    def _orientations(self, dims, allow_full_rotation):
        l, w, h = dims
        if allow_full_rotation:
            return list({o for o in permutations((l, w, h), 3)})
        return list({(l, w, h), (w, l, h)})

    def _prune_free_rects(self, free_rects):
        pruned = []
        for i, rect in enumerate(free_rects):
            rx, ry, rw, rd = rect
            contained = False
            for j, other in enumerate(free_rects):
                if i == j:
                    continue
                ox, oy, ow, od = other
                if rx >= ox and ry >= oy and rx + rw <= ox + ow and ry + rd <= oy + od:
                    contained = True
                    break
            if not contained and rw > 0 and rd > 0:
                pruned.append(rect)
        return pruned

    def _pack_layer(self, layer_h, units, pallet_l, pallet_w, weight_budget):
        free_rects = [(0, 0, pallet_l, pallet_w)]
        used_ids = set()
        placements = []
        layer_weight = 0.0
        layer_area = 0
        layer_volume = 0

        while True:
            best = None

            for fr_i, (fx, fy, fw, fd) in enumerate(free_rects):
                for unit in units:
                    if unit["id"] in used_ids:
                        continue
                    if layer_weight + unit["weight_kg"] > weight_budget:
                        continue

                    for ul, uw, uh in unit["orientations"]:
                        if uh != layer_h:
                            continue
                        if ul > fw or uw > fd:
                            continue

                        area = ul * uw
                        fill_ratio = area / float(fw * fd)
                        short_left = min(fw - ul, fd - uw)
                        long_left = max(fw - ul, fd - uw)
                        score = (fill_ratio, -short_left, -long_left, area)

                        if best is None or score > best["score"]:
                            best = {
                                "score": score,
                                "fr_i": fr_i,
                                "unit": unit,
                                "x": fx,
                                "y": fy,
                                "l": ul,
                                "w": uw,
                                "h": uh,
                                "fw": fw,
                                "fd": fd,
                            }

            if best is None:
                break

            fr_i = best["fr_i"]
            unit = best["unit"]
            x, y, l, w, h = best["x"], best["y"], best["l"], best["w"], best["h"]
            fw, fd = best["fw"], best["fd"]

            used_ids.add(unit["id"])
            layer_weight += unit["weight_kg"]
            layer_area += l * w
            layer_volume += l * w * h

            placements.append(
                {
                    "id": unit["id"],
                    "name": unit["name"],
                    "color": unit["color"],
                    "weight_kg": unit["weight_kg"],
                    "x": x,
                    "y": y,
                    "l": l,
                    "w": w,
                    "h": h,
                }
            )

            free_rects.pop(fr_i)

            right_w = fw - l
            top_d = fd - w

            if right_w > 0:
                free_rects.append((x + l, y, right_w, w))
            if top_d > 0:
                free_rects.append((x, y + w, fw, top_d))

            free_rects = self._prune_free_rects(free_rects)

        return {
            "placements": placements,
            "used_ids": used_ids,
            "weight_kg": layer_weight,
            "area": layer_area,
            "volume": layer_volume,
            "count": len(placements),
            "layer_h": layer_h,
        }

    def pack(self, pallet_l, pallet_w, max_h, max_load_kg, packages, allow_full_rotation):
        units = []
        unit_id = 0
        for p in packages:
            for _ in range(p.count):
                units.append(
                    {
                        "id": unit_id,
                        "name": p.name,
                        "weight_kg": p.weight_kg,
                        "color": p.color,
                        "orientations": self._orientations(
                            (p.length_mm, p.width_mm, p.height_mm), allow_full_rotation
                        ),
                    }
                )
                unit_id += 1

        all_placements = []
        placed_count = 0
        current_h = 0
        total_weight = 0.0

        while units and current_h < max_h:
            remain_h = max_h - current_h
            remain_w = max_load_kg - total_weight
            if remain_w <= 0:
                break

            candidate_heights = sorted(
                {
                    h
                    for u in units
                    if u["weight_kg"] <= remain_w
                    for _, _, h in u["orientations"]
                    if h <= remain_h
                },
                reverse=True,
            )

            if not candidate_heights:
                break

            best_layer = None
            best_score = None

            for layer_h in candidate_heights:
                layer = self._pack_layer(layer_h, units, pallet_l, pallet_w, remain_w)
                if layer["count"] == 0:
                    continue

                score = (layer["volume"], layer["area"], layer["count"])
                if best_score is None or score > best_score:
                    best_score = score
                    best_layer = layer

            if best_layer is None:
                break

            for pl in best_layer["placements"]:
                all_placements.append(
                    {
                        **pl,
                        "z": current_h,
                    }
                )

            used_ids = best_layer["used_ids"]
            units = [u for u in units if u["id"] not in used_ids]
            placed_count += best_layer["count"]
            total_weight += best_layer["weight_kg"]
            current_h += best_layer["layer_h"]

        total_requested = sum(p.count for p in packages)
        placed_volume = sum(p["l"] * p["w"] * p["h"] for p in all_placements)
        pallet_volume = pallet_l * pallet_w * max_h
        fill_pct = (placed_volume / pallet_volume * 100.0) if pallet_volume else 0.0

        stats = {
            "placed_count": placed_count,
            "requested_count": total_requested,
            "unplaced_count": total_requested - placed_count,
            "total_weight_kg": total_weight,
            "used_height_mm": current_h,
            "fill_pct": fill_pct,
        }

        return all_placements, stats


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Paletovy kalkulator")
        self.root.geometry("1400x850")

        self.packer = PalletPacker()
        self.packages = []
        self.current_color = "#4C78A8"
        self.last_scene = None
        self.view_elev = 24
        self.view_azim = -62
        self.show_edges_var = tk.BooleanVar(value=True)
        self.show_grid_var = tk.BooleanVar(value=True)
        self.show_limit_var = tk.BooleanVar(value=True)

        self.palette_library = {
            "EUR 1200x800": PalletSpec("EUR", 1200, 800, 1500.0),
            "IND 1200x1000": PalletSpec("IND", 1200, 1000, 2000.0),
            "HALF 800x600": PalletSpec("HALF", 800, 600, 500.0),
            "Vlastni": PalletSpec("Vlastni", 1200, 800, 1000.0),
        }

        self._build_ui()
        self._apply_pallet_preset()

    def _build_ui(self):
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True)

        container.grid_columnconfigure(0, weight=0)
        container.grid_columnconfigure(1, weight=1)
        container.grid_columnconfigure(2, weight=0)
        container.grid_rowconfigure(0, weight=1)

        left = ttk.Frame(container, padding=12)
        center = ttk.Frame(container, padding=12)
        right = ttk.Frame(container, padding=12)

        left.grid(row=0, column=0, sticky="ns")
        center.grid(row=0, column=1, sticky="nsew")
        right.grid(row=0, column=2, sticky="ns")

        self._build_left_panel(left)
        self._build_center_panel(center)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        ttk.Label(parent, text="Paleta", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        self.pallet_type_var = tk.StringVar(value="EUR 1200x800")
        ttk.Label(parent, text="Typ palety").pack(anchor="w")
        cb = ttk.Combobox(
            parent,
            textvariable=self.pallet_type_var,
            values=list(self.palette_library.keys()),
            state="readonly",
            width=22,
        )
        cb.pack(anchor="w", pady=(0, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self._apply_pallet_preset())

        self.pallet_l_var = tk.StringVar()
        self.pallet_w_var = tk.StringVar()
        self.max_h_var = tk.StringVar(value="1400")
        self.max_load_var = tk.StringVar()

        self.pallet_l_entry = self._labeled_entry(parent, "Delka palety (mm)", self.pallet_l_var)
        self.pallet_w_entry = self._labeled_entry(parent, "Sirka palety (mm)", self.pallet_w_var)
        self.max_h_entry = self._labeled_entry(parent, "Max vyska skladani (mm)", self.max_h_var)
        self._labeled_entry(parent, "Max nosnost palety (kg)", self.max_load_var)

        for entry in (self.pallet_l_entry, self.pallet_w_entry, self.max_h_entry):
            entry.bind("<FocusOut>", lambda _e: self._preview_pallet())
            entry.bind("<Return>", lambda _e: self._preview_pallet())

        self.allow_rotation_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            parent,
            text="Povolit otaceni baliku (3 osy)",
            variable=self.allow_rotation_var,
        ).pack(anchor="w", pady=8)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=8)

        self.summary_var = tk.StringVar(value="Zatim bez vypoctu")
        ttk.Label(parent, text="Vysledek", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 4))
        ttk.Label(parent, textvariable=self.summary_var, justify="left", wraplength=270).pack(anchor="w")

        ttk.Button(parent, text="Spocitat a umistit", command=self.calculate).pack(anchor="w", pady=14)

    def _build_center_panel(self, parent):
        title = ttk.Frame(parent)
        title.pack(fill="x")
        ttk.Label(title, text="3D nahled palety", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)

        view_buttons = ttk.Frame(title)
        view_buttons.pack(side=tk.RIGHT)
        ttk.Button(view_buttons, text="Iso", width=5, command=lambda: self._set_view(24, -62)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(view_buttons, text="Shora", width=7, command=lambda: self._set_view(90, -90)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(view_buttons, text="Zepredu", width=8, command=lambda: self._set_view(12, -90)).pack(side=tk.LEFT)

        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.figure.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.toolbar = NavigationToolbar2Tk(self.canvas, parent, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(fill=tk.X, pady=(4, 0))

        render_options = ttk.Frame(parent)
        render_options.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(
            render_options,
            text="Hrany baliku",
            variable=self.show_edges_var,
            command=self._redraw_last_scene,
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            render_options,
            text="Mrizka",
            variable=self.show_grid_var,
            command=self._redraw_last_scene,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            render_options,
            text="Limit vysky",
            variable=self.show_limit_var,
            command=self._redraw_last_scene,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.render_status_var = tk.StringVar(value="")
        ttk.Label(render_options, textvariable=self.render_status_var).pack(side=tk.RIGHT)

    def _set_view(self, elev, azim):
        self.view_elev = elev
        self.view_azim = azim
        self.ax.view_init(elev=elev, azim=azim)
        self.canvas.draw_idle()

    def _redraw_last_scene(self):
        if not self.last_scene:
            return
        placements, pallet_l, pallet_w, max_h = self.last_scene
        self._draw_scene(placements, pallet_l, pallet_w, max_h, keep_view=True)

    def _build_right_panel(self, parent):
        ttk.Label(parent, text="Baliky", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))

        self.pkg_name_var = tk.StringVar(value="Balik")
        self.pkg_l_var = tk.StringVar(value="300")
        self.pkg_w_var = tk.StringVar(value="200")
        self.pkg_h_var = tk.StringVar(value="150")
        self.pkg_weight_var = tk.StringVar(value="8")
        self.pkg_count_var = tk.StringVar(value="10")

        self._labeled_entry(parent, "Nazev", self.pkg_name_var)
        self._labeled_entry(parent, "Delka (mm)", self.pkg_l_var)
        self._labeled_entry(parent, "Sirka (mm)", self.pkg_w_var)
        self._labeled_entry(parent, "Vyska (mm)", self.pkg_h_var)
        self._labeled_entry(parent, "Vaha 1 ks (kg)", self.pkg_weight_var)
        self._labeled_entry(parent, "Pocet ks", self.pkg_count_var)

        color_row = ttk.Frame(parent)
        color_row.pack(fill="x", pady=(2, 8))
        ttk.Label(color_row, text="Barva").pack(side=tk.LEFT)
        self.color_preview = tk.Canvas(color_row, width=22, height=22, highlightthickness=1, highlightbackground="#666")
        self.color_preview.create_rectangle(0, 0, 22, 22, fill=self.current_color, outline="")
        self.color_preview.pack(side=tk.LEFT, padx=8)
        ttk.Button(color_row, text="Vybrat", command=self._pick_color).pack(side=tk.LEFT)

        ttk.Button(parent, text="Pridat balik", command=self.add_package).pack(anchor="w", pady=(2, 6))

        cols = ("name", "l", "w", "h", "weight", "count")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        self.tree.heading("name", text="Nazev")
        self.tree.heading("l", text="L")
        self.tree.heading("w", text="W")
        self.tree.heading("h", text="H")
        self.tree.heading("weight", text="kg")
        self.tree.heading("count", text="ks")

        self.tree.column("name", width=120)
        self.tree.column("l", width=55, anchor="e")
        self.tree.column("w", width=55, anchor="e")
        self.tree.column("h", width=55, anchor="e")
        self.tree.column("weight", width=55, anchor="e")
        self.tree.column("count", width=55, anchor="e")
        self.tree.pack(fill="x", pady=6)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill="x", pady=4)
        ttk.Button(btn_row, text="Odebrat vybrany", command=self.remove_selected).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Smazat vse", command=self.clear_packages).pack(side=tk.LEFT, padx=8)

    def _labeled_entry(self, parent, label, variable):
        ttk.Label(parent, text=label).pack(anchor="w")
        entry = ttk.Entry(parent, textvariable=variable, width=24)
        entry.pack(anchor="w", pady=(0, 6))
        return entry

    def _pick_color(self):
        color = colorchooser.askcolor(color=self.current_color)[1]
        if color:
            self.current_color = color
            self.color_preview.delete("all")
            self.color_preview.create_rectangle(0, 0, 22, 22, fill=color, outline="")

    def _apply_pallet_preset(self):
        preset = self.palette_library[self.pallet_type_var.get()]
        self.pallet_l_var.set(str(preset.length_mm))
        self.pallet_w_var.set(str(preset.width_mm))
        self.max_load_var.set(str(int(preset.max_load_kg)))
        self._preview_pallet()

    def _preview_pallet(self):
        try:
            pallet_l = int(self.pallet_l_var.get())
            pallet_w = int(self.pallet_w_var.get())
            max_h = int(self.max_h_var.get())
            if pallet_l <= 0 or pallet_w <= 0 or max_h <= 0:
                return
        except ValueError:
            return
        self._draw_scene([], pallet_l, pallet_w, max_h)

    def _parse_float(self, value, label):
        try:
            num = float(value)
            if num <= 0:
                raise ValueError
            return num
        except ValueError:
            raise ValueError(f"Pole '{label}' musi byt kladne cislo.")

    def _parse_int(self, value, label):
        try:
            num = int(value)
            if num <= 0:
                raise ValueError
            return num
        except ValueError:
            raise ValueError(f"Pole '{label}' musi byt kladne cele cislo.")

    def add_package(self):
        try:
            pkg = PackageSpec(
                name=self.pkg_name_var.get().strip() or f"Balik-{len(self.packages)+1}",
                length_mm=self._parse_int(self.pkg_l_var.get(), "Delka"),
                width_mm=self._parse_int(self.pkg_w_var.get(), "Sirka"),
                height_mm=self._parse_int(self.pkg_h_var.get(), "Vyska"),
                weight_kg=self._parse_float(self.pkg_weight_var.get(), "Vaha"),
                count=self._parse_int(self.pkg_count_var.get(), "Pocet"),
                color=self.current_color or self._random_color(),
            )
        except ValueError as exc:
            messagebox.showerror("Chyba vstupu", str(exc))
            return

        self.packages.append(pkg)
        self._refresh_tree()

    def _random_color(self):
        return f"#{random.randint(0, 0xFFFFFF):06x}"

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, p in enumerate(self.packages):
            self.tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(p.name, p.length_mm, p.width_mm, p.height_mm, f"{p.weight_kg:.1f}", p.count),
            )

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        if 0 <= idx < len(self.packages):
            self.packages.pop(idx)
            self._refresh_tree()

    def clear_packages(self):
        self.packages.clear()
        self._refresh_tree()
        self.summary_var.set("Seznam baliku byl vycisten.")
        self._draw_scene([], 1200, 800, 1200)

    def calculate(self):
        if not self.packages:
            messagebox.showwarning("Bez dat", "Nejdriv pridej aspon jeden typ baliku.")
            return

        try:
            pallet_l = self._parse_int(self.pallet_l_var.get(), "Delka palety")
            pallet_w = self._parse_int(self.pallet_w_var.get(), "Sirka palety")
            max_h = self._parse_int(self.max_h_var.get(), "Max vyska")
            max_load = self._parse_float(self.max_load_var.get(), "Max nosnost")
        except ValueError as exc:
            messagebox.showerror("Chyba vstupu", str(exc))
            return

        placements, stats = self.packer.pack(
            pallet_l=pallet_l,
            pallet_w=pallet_w,
            max_h=max_h,
            max_load_kg=max_load,
            packages=self.packages,
            allow_full_rotation=self.allow_rotation_var.get(),
        )

        self._draw_scene(placements, pallet_l, pallet_w, max_h)

        summary = (
            f"Umisteno: {stats['placed_count']} / {stats['requested_count']} ks\n"
            f"Neumisteno: {stats['unplaced_count']} ks\n"
            f"Celkova vaha: {stats['total_weight_kg']:.1f} kg\n"
            f"Pouzita vyska: {stats['used_height_mm']} mm / {max_h} mm\n"
            f"Objemove zaplneni: {stats['fill_pct']:.1f} %"
        )
        self.summary_var.set(summary)

    def _draw_scene(self, placements, pallet_l, pallet_w, max_h, keep_view=False):
        ax = self.ax

        if keep_view:
            elev, azim = self.view_elev, self.view_azim
        else:
            elev = getattr(ax, "elev", self.view_elev)
            azim = getattr(ax, "azim", self.view_azim)
            self.view_elev = elev
            self.view_azim = azim

        self.last_scene = (list(placements), pallet_l, pallet_w, max_h)
        ax.clear()

        pallet_h = self._draw_pallet_base(ax, pallet_l, pallet_w)
        if self.show_limit_var.get():
            self._draw_stack_limit_wireframe(ax, pallet_l, pallet_w, max_h, pallet_h)

        if placements:
            self._draw_package_boxes(ax, placements, pallet_h)
            self._draw_layer_separators(ax, placements, pallet_l, pallet_w, pallet_h)
            self._add_scene_legend(ax, placements)

        used_h = max([p["z"] + p["h"] for p in placements], default=0)
        z_top = pallet_h + max(max_h, int(used_h * 1.08) if used_h else max_h)

        ax.set_xlim(0, pallet_l)
        ax.set_ylim(0, pallet_w)
        ax.set_zlim(0, z_top)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.set_title("Rozlozeni baliku na palete")
        ax.view_init(elev=elev, azim=azim)
        ax.set_box_aspect((pallet_l, pallet_w, z_top))
        ax.grid(self.show_grid_var.get())
        ax.set_proj_type("persp", focal_length=0.9)

        # Mírně čistší pozadí bez agresivních šedých panelů.
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.pane.set_alpha(0.06)

        if hasattr(self, "render_status_var"):
            self.render_status_var.set(f"3D: {len(placements)} ks")

        self.canvas.draw_idle()

    def _cuboid_faces(self, x, y, z, l, w, h):
        p0 = (x, y, z)
        p1 = (x + l, y, z)
        p2 = (x + l, y + w, z)
        p3 = (x, y + w, z)
        p4 = (x, y, z + h)
        p5 = (x + l, y, z + h)
        p6 = (x + l, y + w, z + h)
        p7 = (x, y + w, z + h)
        return [
            [p0, p1, p2, p3],
            [p4, p5, p6, p7],
            [p0, p1, p5, p4],
            [p1, p2, p6, p5],
            [p2, p3, p7, p6],
            [p3, p0, p4, p7],
        ]

    def _cuboid_edges(self, x, y, z, l, w, h):
        p0 = (x, y, z)
        p1 = (x + l, y, z)
        p2 = (x + l, y + w, z)
        p3 = (x, y + w, z)
        p4 = (x, y, z + h)
        p5 = (x + l, y, z + h)
        p6 = (x + l, y + w, z + h)
        p7 = (x, y + w, z + h)
        return [
            [p0, p1], [p1, p2], [p2, p3], [p3, p0],
            [p4, p5], [p5, p6], [p6, p7], [p7, p4],
            [p0, p4], [p1, p5], [p2, p6], [p3, p7],
        ]

    def _shade_color(self, color, factor):
        r, g, b = to_rgb(color)
        return to_hex((min(1.0, r * factor), min(1.0, g * factor), min(1.0, b * factor)))

    def _draw_cuboids(self, ax, boxes, *, edgecolor="#222", linewidth=0.22, alpha=1.0, show_edges=True):
        if not boxes:
            return

        faces = []
        face_colors = []
        edges = []
        # Odstíny pro jednotlivé strany pomáhají čitelnosti a jsou rychlejší než opakované bar3d.
        shade_factors = (0.74, 1.10, 0.94, 0.86, 0.78, 0.82)

        for box in boxes:
            color = box.get("color", "#4C78A8")
            box_faces = self._cuboid_faces(box["x"], box["y"], box["z"], box["l"], box["w"], box["h"])
            faces.extend(box_faces)
            face_colors.extend(self._shade_color(color, f) for f in shade_factors)
            if show_edges:
                edges.extend(self._cuboid_edges(box["x"], box["y"], box["z"], box["l"], box["w"], box["h"]))

        poly = Poly3DCollection(
            faces,
            facecolors=face_colors,
            edgecolors="none",
            linewidths=0,
            alpha=alpha,
            zsort="average",
        )
        ax.add_collection3d(poly)

        if edges:
            lines = Line3DCollection(edges, colors=edgecolor, linewidths=linewidth, alpha=0.65)
            ax.add_collection3d(lines)

    def _draw_package_boxes(self, ax, placements, pallet_h):
        boxes = []
        for p in placements:
            boxes.append(
                {
                    "x": p["x"],
                    "y": p["y"],
                    "z": p["z"] + pallet_h,
                    "l": p["l"],
                    "w": p["w"],
                    "h": p["h"],
                    "color": p["color"],
                }
            )

        # Vypnutí hran výrazně zrychlí náhled u stovek balíků.
        self._draw_cuboids(
            ax,
            boxes,
            edgecolor="#111111",
            linewidth=0.18,
            alpha=1.0,
            show_edges=self.show_edges_var.get(),
        )

    def _draw_pallet_base(self, ax, pallet_l, pallet_w):
        # Jednoduchý 3D model palety vykreslený dávkově kvůli výkonu.
        pallet_h = 144
        top_slat_h = 18
        bottom_slat_h = 18
        epsilon = 0.8
        block_h = pallet_h - top_slat_h - bottom_slat_h - 2 * epsilon

        wood_top = "#c59a6b"
        wood_bottom = "#b88b5f"
        wood_block = "#9c744c"
        boxes = []

        slat_w = max(50, int(pallet_w * 0.22))
        for ratio in (0.0, 0.5, 1.0):
            boxes.append(
                {
                    "x": 0,
                    "y": ratio * (pallet_w - slat_w),
                    "z": pallet_h - top_slat_h,
                    "l": pallet_l,
                    "w": slat_w,
                    "h": top_slat_h,
                    "color": wood_top,
                }
            )

        bottom_l = max(80, int(pallet_l * 0.18))
        for ratio in (0.0, 0.5, 1.0):
            boxes.append(
                {
                    "x": ratio * (pallet_l - bottom_l),
                    "y": 0,
                    "z": 0,
                    "l": bottom_l,
                    "w": pallet_w,
                    "h": bottom_slat_h,
                    "color": wood_bottom,
                }
            )

        block_l = max(70, int(pallet_l * 0.12))
        block_w = max(70, int(pallet_w * 0.12))
        for rx in (0.0, 0.5, 1.0):
            for ry in (0.0, 0.5, 1.0):
                boxes.append(
                    {
                        "x": rx * (pallet_l - block_l),
                        "y": ry * (pallet_w - block_w),
                        "z": bottom_slat_h + epsilon,
                        "l": block_l,
                        "w": block_w,
                        "h": block_h,
                        "color": wood_block,
                    }
                )

        self._draw_cuboids(ax, boxes, edgecolor="#6d4b2f", linewidth=0.18, alpha=1.0, show_edges=True)
        return pallet_h

    def _draw_stack_limit_wireframe(self, ax, pallet_l, pallet_w, max_h, pallet_h):
        z0 = pallet_h
        z1 = pallet_h + max_h
        corners = [
            (0, 0, z0),
            (pallet_l, 0, z0),
            (pallet_l, pallet_w, z0),
            (0, pallet_w, z0),
            (0, 0, z1),
            (pallet_l, 0, z1),
            (pallet_l, pallet_w, z1),
            (0, pallet_w, z1),
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        lines = [[corners[i], corners[j]] for i, j in edges]
        ax.add_collection3d(Line3DCollection(lines, colors="#444444", linewidths=0.8, alpha=0.85))

        top_face = [[corners[4], corners[5], corners[6], corners[7]]]
        ax.add_collection3d(
            Poly3DCollection(top_face, facecolors="#808080", edgecolors="none", alpha=0.055, zsort="average")
        )

    def _draw_layer_separators(self, ax, placements, pallet_l, pallet_w, pallet_h):
        layer_z = sorted({p["z"] for p in placements if p["z"] > 0})
        if not layer_z:
            return

        lines = []
        for z in layer_z:
            zz = pallet_h + z
            lines.extend(
                [
                    [(0, 0, zz), (pallet_l, 0, zz)],
                    [(pallet_l, 0, zz), (pallet_l, pallet_w, zz)],
                    [(pallet_l, pallet_w, zz), (0, pallet_w, zz)],
                    [(0, pallet_w, zz), (0, 0, zz)],
                ]
            )
        ax.add_collection3d(Line3DCollection(lines, colors="#666666", linewidths=0.45, alpha=0.45))

    def _add_scene_legend(self, ax, placements):
        by_name = defaultdict(lambda: {"count": 0, "color": "#4C78A8"})
        for p in placements:
            by_name[p["name"]]["count"] += 1
            by_name[p["name"]]["color"] = p["color"]

        if not by_name:
            return

        handles = []
        labels = []
        for name, data in list(by_name.items())[:8]:
            handles.append(
                Line2D(
                    [0],
                    [0],
                    marker="s",
                    linestyle="None",
                    markerfacecolor=data["color"],
                    markeredgecolor="#222222",
                    markersize=8,
                )
            )
            labels.append(f"{name} ({data['count']} ks)")

        extra = len(by_name) - len(handles)
        if extra > 0:
            handles.append(Line2D([0], [0], marker="s", linestyle="None", markerfacecolor="#999999", markersize=8))
            labels.append(f"+ {extra} dalsi")

        ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.02, 0.98), fontsize=8, framealpha=0.88)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
