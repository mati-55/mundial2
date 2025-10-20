# elimination.py
import tkinter as tk
from tkinter import ttk, messagebox
from utils import apply_style, center_fullscreen
from core import Torneo, Partido, Equipo
import pandas as pd
import os
import random

class EliminationUI:
    """
    Gestiona octavos, cuartos, semis y final.
    Recibe Torneo ya con resultados de fase de grupos para calcular clasificados.
    Avance entre fases con botones manuales.
    """
    def __init__(self, master, torneo: Torneo):
        self.master = master
        self.master.title("Fases Eliminatorias")
        apply_style(self.master)
        center_fullscreen(self.master)
        self.torneo = torneo
        self.current_phase = 'Octavos'
        self.phases_order = ['Octavos','Cuartos','Semifinal','Final']
        # storage for matches per phase
        self.phase_matches = {p: [] for p in self.phases_order}
        # calculate qualifiers (IDs)
        try:
            self.qualifiers = self._calculate_qualifiers()
        except Exception as e:
            # _calculate_qualifiers mostrará mensajes adecuados
            self.qualifiers = None
        # generate octavos according to reglamento (simplified common mapping)
        if self.qualifiers:
            self._generate_octavos()
        self.build_ui()
        self.load_phase(self.current_phase)

    def _calculate_qualifiers(self):
        # Build mapping pais -> id for safe lookup
        pais_to_id = {e.pais: id for id, e in self.torneo.equipos.items()}

        # take top 2 from each group (return IDs, keep order)
        groups = sorted(set(e.grupo for e in self.torneo.equipos.values()))
        firsts = []; seconds = []; thirds = []
        for g in groups:
            tabla = self.torneo.calcular_tabla_posiciones(g)
            if len(tabla) >= 1:
                pid = pais_to_id.get(tabla[0].pais)
                if pid: firsts.append(pid)
            if len(tabla) >= 2:
                pid = pais_to_id.get(tabla[1].pais)
                if pid: seconds.append(pid)
            if len(tabla) >= 3:
                # store pais and stats for sorting best thirds
                thirds.append({'pais': tabla[2].pais, 'grupo': g, 'stats': tabla[2].stats})

        # choose best 4 thirds by Pts, DG, GF (convert to ids)
        thirds_sorted = sorted(thirds, key=lambda t: (t['stats']['Pts'], t['stats']['DG'], t['stats']['GF']), reverse=True)
        best_thirds_paises = [t['pais'] for t in thirds_sorted[:4]]
        best_thirds = [pais_to_id[p] for p in best_thirds_paises if p in pais_to_id]

        # combine lists preserving order and remove duplicates while preserving order
        combined = []
        for lst in (firsts, seconds, best_thirds):
            for id_ in lst:
                if id_ not in combined:
                    combined.append(id_)

        # After building, there must be exactly 16 unique teams for octavos
        if len(combined) != 16:
            messagebox.showerror("Error", f"Se esperaban 16 equipos para octavos, pero se encontraron {len(combined)}. Revisa los resultados de fase de grupos.")
            raise Exception("Insuficientes clasificados para octavos")

        # return structured dict of ids to preserve previous API
        # We'll keep keys '1os','2os','3os_best' but with IDs
        # For convenience, compute firsts_ids and seconds_ids trimmed to group counts
        # reconstruct firsts and seconds in same order but only ids (avoid duplicates)
        # Note: original UI expects qualifiers['1os'] etc; keep same keys but with IDs
        # We'll return firsts (6), seconds (6), best_thirds (4)
        # Ensure lengths: firsts len(groups), seconds len(groups)
        firsts_ids = [id for id in firsts if id in self.torneo.equipos]
        seconds_ids = [id for id in seconds if id in self.torneo.equipos]
        third_ids = best_thirds
        return {'1os': firsts_ids, '2os': seconds_ids, '3os_best': third_ids}

    def _generate_octavos(self):
        # Use the validated qualifier IDs to build 8 matches without duplicates
        if not self.qualifiers:
            return

        f = self.qualifiers['1os']
        s = self.qualifiers['2os']
        t = self.qualifiers['3os_best']

        # Validate we have exactly 16 unique IDs
        combined = []
        for lst in (f, s, t):
            for id_ in lst:
                if id_ not in combined:
                    combined.append(id_)
        if len(combined) != 16:
            messagebox.showerror("Error", "No se pudo generar Octavos: la lista de clasificados no contiene 16 equipos únicos.")
            return

        # Build 8 pairs determinísticamente: emparejar en orden (0-1, 2-3, ...)
        pairs = []
        for i in range(0, 16, 2):
            a = combined[i]; b = combined[i+1]
            # safety: si por alguna razón a==b (no debería): intentar buscar un compañero distinto
            if a == b:
                # buscar primer id distinto
                for cand in combined:
                    if cand != a and (a, cand) not in pairs and (cand, a) not in pairs:
                        b = cand
                        break
            if a != b:
                pairs.append((a, b))

        # If for alguna razón no llegamos a 8 parejas, intentar rellenar
        i = 0
        ids = combined.copy()
        while len(pairs) < 8 and i + 1 < len(ids):
            if (ids[i], ids[i+1]) not in pairs and ids[i] != ids[i+1]:
                pairs.append((ids[i], ids[i+1]))
            i += 2

        # create Partido objects
        for a, b in pairs:
            p = Partido(a, b, fecha="", hora="", fase="Octavos")
            mid = self.torneo.agregar_partido(p)
            self.phase_matches['Octavos'].append(mid)

    def build_ui(self):
        header = ttk.Frame(self.master,padding=8); header.pack(fill='x')
        ttk.Label(header, text="Fases Eliminatorias", style="Header.TLabel").pack()
        top = ttk.Frame(self.master,padding=8); top.pack(fill='x')
        self.phase_label = ttk.Label(top, text=self.current_phase); self.phase_label.pack(side='left')
        ttk.Button(top, text="Guardar Fase", command=self.save_phase).pack(side='right')
        ttk.Button(top, text="Continuar (siguiente fase)", command=self.next_phase).pack(side='right', padx=6)

        cols = ("ID","Fase","Equipo1","G1","vs","G2","Equipo2","Resultado")
        self.tree = ttk.Treeview(self.master, columns=cols, show='headings')
        for c in cols: self.tree.heading(c, text=c)
        self.tree.pack(fill='both', expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", self._on_double_click)

    def load_phase(self, phase):
        self.phase_label.config(text=phase)
        self.tree.delete(*self.tree.get_children())
        # show matches that have p.fase == phase
        for mid, p in self.torneo.calendario.items():
            if p.fase != phase: continue
            e1 = self.torneo.equipos.get(p.id_equipo1).pais if p.id_equipo1 in self.torneo.equipos else p.id_equipo1
            e2 = self.torneo.equipos.get(p.id_equipo2).pais if p.id_equipo2 in self.torneo.equipos else p.id_equipo2
            res = f"{p.goles_e1} : {p.goles_e2}" if p.goles_e1 is not None else "PENDIENTE"
            self.tree.insert("", tk.END, iid=mid, values=(mid, p.fase, e1, p.goles_e1 if p.goles_e1 is not None else "", "vs", p.goles_e2 if p.goles_e2 is not None else "", e2, res))

    def _on_double_click(self, event):
        item = self.tree.selection()
        if not item:
            return
        mid = item[0]
        p = self.torneo.calendario.get(mid)
        if not p:
            messagebox.showerror("Error", "No se encontró el partido seleccionado en el calendario interno.")
            return

        # create dialog
        win = tk.Toplevel(self.master); win.title(f"Editar {mid}")
        win.geometry("360x200"); win.transient(self.master); win.grab_set()

        frm = ttk.Frame(win, padding=8); frm.pack(fill='both', expand=True)

        # get team objects (fallback to id if missing)
        e1_obj = self.torneo.equipos.get(p.id_equipo1)
        e2_obj = self.torneo.equipos.get(p.id_equipo2)
        e1_name = e1_obj.pais if e1_obj else p.id_equipo1
        e2_name = e2_obj.pais if e2_obj else p.id_equipo2
        e1_abbr = e1_obj.abreviatura if e1_obj and e1_obj.abreviatura else (e1_name[:3].upper() if e1_name else "")
        e2_abbr = e2_obj.abreviatura if e2_obj and e2_obj.abreviatura else (e2_name[:3].upper() if e2_name else "")

        # header showing both teams + abreviaturas
        ttk.Label(frm, text=f"{e1_name} ({e1_abbr})  vs  {e2_name} ({e2_abbr})").pack(pady=(0,6))

        row = ttk.Frame(frm); row.pack()
        ttk.Label(row, text=f"Goles {e1_abbr}").pack(side='left', padx=6)
        e1 = ttk.Entry(row, width=6); e1.pack(side='left')
        ttk.Label(row, text=f"Goles {e2_abbr}").pack(side='left', padx=6)
        e2 = ttk.Entry(row, width=6); e2.pack(side='left')

        # prefill existing goles
        e1.insert(0, "" if p.goles_e1 is None else str(p.goles_e1))
        e2.insert(0, "" if p.goles_e2 is None else str(p.goles_e2))

        def simulate_alargue_and_penales(g1, g2):
            # Simula alargue: pequeños goles aleatorios (0-2)
            et1 = random.randint(0, 2)
            et2 = random.randint(0, 2)
            g1_et = g1 + et1
            g2_et = g2 + et2
            if g1_et != g2_et:
                return (g1_et, g2_et, (et1, et2), None)
            # Si sigue empate, simular penales (5 primero)
            def simulate_penales():
                # Each team shoots 5; count converted (0-5)
                pen1 = sum(random.choice([0,1]) for _ in range(5))
                pen2 = sum(random.choice([0,1]) for _ in range(5))
                # if tie, sudden death
                while pen1 == pen2:
                    # each shoots one more
                    pen1 += random.choice([0,1])
                    pen2 += random.choice([0,1])
                return pen1, pen2
            pen1, pen2 = simulate_penales()
            return (g1_et, g2_et, (et1, et2), (pen1, pen2))

        def save():
            try:
                g1 = int(e1.get()); g2 = int(e2.get())
            except Exception:
                messagebox.showerror("Error", "Goles deben ser enteros.")
                return

            # If this match is in an elimination phase, handle tie-break rules
            if p.fase in self.phases_order:
                # if tie, simulate alargue and possibly penales
                if g1 == g2:
                    g1_final, g2_final, alargue_res, penales_res = simulate_alargue_and_penales(g1, g2)
                    # store final goles (including alargue) and also attach extra info
                    p.goles_e1 = g1_final
                    p.goles_e2 = g2_final
                    if alargue_res:
                        p.alargue = {'goles_et1': alargue_res[0], 'goles_et2': alargue_res[1]}
                    else:
                        p.alargue = {'goles_et1': 0, 'goles_et2': 0}
                    if penales_res:
                        p.penales = {'p1': penales_res[0], 'p2': penales_res[1]}
                        # Winner determined by penales; do not alter goles, penales decide
                        winner = e1_name if penales_res[0] > penales_res[1] else e2_name
                        msg = f"Empate en tiempo regular ({g1} - {g2}). Alargue: {alargue_res[0]} - {alargue_res[1]}. Penales: {penales_res[0]} - {penales_res[1]}. Clasificado: {winner}."
                    else:
                        # Winner by alargue
                        winner = e1_name if g1_final > g2_final else e2_name
                        msg = f"Empate en tiempo regular ({g1} - {g2}). Resultado tras alargue: {g1_final} - {g2_final}. Clasificado: {winner}."
                else:
                    # No empate: resultado normal
                    p.goles_e1 = g1; p.goles_e2 = g2
                    # clear previous tie-break attributes if present
                    if hasattr(p, 'alargue'): delattr(p, 'alargue') if False else None
                    if hasattr(p, 'penales'): delattr(p, 'penales') if False else None
                    winner = e1_name if g1 > g2 else e2_name
                    msg = f"Resultado guardado: {e1_name} {g1} : {g2} {e2_name}. Clasificado: {winner}."
            else:
                # Not an elimination match: just save as entered
                p.goles_e1 = g1; p.goles_e2 = g2
                msg = f"Resultado guardado: {e1_name} {g1} : {g2} {e2_name}."

            # save and refresh
            self.torneo.guardar_datos()
            win.destroy()
            self.load_phase(self.current_phase)

            # mostrar mensaje solo si hubo empate y se aplicó alargue/penales
            if p.fase in self.phases_order and g1 == g2:
                messagebox.showinfo("Desempate", msg)
            else:
                # si fue victoria normal, no mostrar ventana extra
                print(f"Resultado guardado: {msg}")

        ttk.Button(frm, text="Guardar", command=save).pack(pady=8)

    def save_phase(self):
        # nothing extra needed: partidos ya guardados al editar. Save JSON and export excel
        self.torneo.guardar_datos()
        # export current phase to excel
        rows = []
        for mid, p in self.torneo.calendario.items():
            if p.fase != self.current_phase: continue
            e1 = self.torneo.equipos.get(p.id_equipo1).pais if p.id_equipo1 in self.torneo.equipos else p.id_equipo1
            e2 = self.torneo.equipos.get(p.id_equipo2).pais if p.id_equipo2 in self.torneo.equipos else p.id_equipo2
            # include extra info if present
            extra = ""
            if hasattr(p, 'alargue'):
                extra += f" Alargue {p.alargue.get('goles_et1',0)}-{p.alargue.get('goles_et2',0)}"
            if hasattr(p, 'penales'):
                extra += f" Penales {p.penales.get('p1',0)}-{p.penales.get('p2',0)}"
            rows.append({'ID': mid, 'Fase': p.fase, 'Equipo1': e1, 'G1': p.goles_e1, 'G2': p.goles_e2, 'Equipo2': e2, 'Extra': extra})
        out = os.path.join(os.path.dirname(__file__), f"Resultados_{self.current_phase}.xlsx")
        try:
            pd.DataFrame(rows).to_excel(out, index=False)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar: {e}")
            return
        messagebox.showinfo("Guardado", f"Fase {self.current_phase} guardada y exportada.")

    def next_phase(self):
        idx = self.phases_order.index(self.current_phase)
        if idx < len(self.phases_order) - 1:
            # confirm
            if not messagebox.askyesno("Confirmar", f"¿Desea avanzar a la siguiente fase ({self.phases_order[idx+1]})?"):
                return
            # compute winners from current phase to produce next phase matches (simple pairing sequential)
            winners = []
            for mid, p in list(self.torneo.calendario.items()):
                if p.fase != self.current_phase: continue
                if p.goles_e1 is None or p.goles_e2 is None:
                    messagebox.showwarning("Faltan resultados", "Hay partidos sin resultado. Complete antes de avanzar.")
                    return
                # For elimination matches, penales or alargue must have resolved winner and goles reflect final state
                if p.goles_e1 > p.goles_e2:
                    winners.append(p.id_equipo1)
                elif p.goles_e2 > p.goles_e1:
                    winners.append(p.id_equipo2)
                else:
                    # As a safety fallback: if still tied (no debería suceder) preguntar al usuario
                    messagebox.showwarning("Empate detectado", f"Empate detectado en {mid}. Debe resolverse antes de continuar.")
                    return
            # pair winners sequentially
            next_phase = self.phases_order[idx + 1]
            pairs = []
            i = 0
            while i + 1 < len(winners):
                pairs.append((winners[i], winners[i + 1])); i += 2
            # create Partido for next phase
            for a, b in pairs:
                pp = Partido(a, b, fecha="", hora="", fase=next_phase)
                self.torneo.agregar_partido(pp)
            self.current_phase = next_phase
            self.torneo.guardar_datos()
            self.load_phase(self.current_phase)
        else:
            messagebox.showinfo("Info", "Ya estás en la última fase.")