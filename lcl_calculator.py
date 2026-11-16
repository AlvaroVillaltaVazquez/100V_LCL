"""
============================================================
  Calculadora de Escalado — Limitador de Corriente LCL
============================================================
  Dependencias: reportlab  →  pip install reportlab
  Para generar .exe:
      pip install pyinstaller
      python -m PyInstaller --onefile --windowed --name "Calculadora_LCL" lcl_calculator.py
============================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import math
import os
import datetime
import shutil
import sys

# ── Ruta de la imagen (empaquetada con PyInstaller o local) ──
def resource_path(relative):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)

SCHEMATIC_PATH = resource_path("schematic.png")

# ── ReportLab (PDF) ──────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, HRFlowable, Image as RLImage)
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False


# ════════════════════════════════════════════════════════════
#   LÓGICA DE CÁLCULO
# ════════════════════════════════════════════════════════════

def sugerir_par_resistencias(ratio, R_base=10e3):
    """
    Dado R_up/R_down = ratio y R_down fija en R_base,
    devuelve (R_up, R_down) redondeando R_up a la serie E24.
    """
    E24 = [10,11,12,13,15,16,18,20,22,24,27,30,33,36,39,43,47,51,56,62,68,75,82,91]
    R_up_ideal = ratio * R_base
    # encontrar el valor E24 más cercano (en cualquier década)
    best = None
    best_err = float("inf")
    for decade in [1e3, 2.2e3, 4.7e3, 1e4, 2.2e4, 4.7e4, 1e5, 2.2e5]:
        for v in E24:
            val = v * decade / 10
            if val < 10e3:
                continue
            err = abs(val - R_up_ideal) / R_up_ideal
            if err < best_err:
                best_err = err
                best = val
    return best, R_base


def calcular(params: dict) -> dict:
    res = {}
    warns = []

    V_bus      = params["V_bus"]
    I_lim      = params["I_lim"]
    I_hys_sup  = params["I_hys_sup"]
    I_hys_inf  = params["I_hys_inf"]
    t_trip     = params["t_trip"]
    G          = params["G"]
    C_timer    = params["C_timer"]
    V_F        = params["V_F"]
    V_cc       = params["V_cc"]
    P_shunt_max  = params["P_shunt_max"]
    R_shunt_orig = params["R_shunt"]
    f_sw       = params["f_sw"]
    T_a        = params["T_a"]
    R_DS_ON    = params["R_DS_ON"]
    t_rise     = params["t_rise"]
    t_fall     = params["t_fall"]
    R_th_JC    = params["R_th_JC"]
    R_th_CS    = params["R_th_CS"]
    R_th_SA    = params["R_th_SA"]
    T_j_max    = params["T_j_max"]
    I_sat      = params["I_sat"]

    I_nom = (I_hys_sup + I_hys_inf) / 2.0
    res["I_nom"] = I_nom

    # ── 1. R_SHUNT ───────────────────────────────────────
    R_shunt = R_shunt_orig
    P_shunt = (I_nom ** 2) * R_shunt
    res["P_shunt_orig"] = P_shunt
    res["R_shunt_orig"] = R_shunt_orig

    if P_shunt > P_shunt_max:
        warns.append(
            f"⚠ P_shunt = {P_shunt*1e3:.1f} mW > límite {P_shunt_max*1e3:.0f} mW. "
            f"R_shunt ajustada automáticamente."
        )
        R_shunt = P_shunt_max / (I_nom ** 2)
        warns.append(
            f"   → R_shunt: {R_shunt_orig*1e3:.3f} mΩ  →  {R_shunt*1e3:.4f} mΩ"
        )
        P_shunt = P_shunt_max

    res["R_shunt"] = R_shunt
    res["P_shunt"] = P_shunt
    res["R_shunt_changed"] = (abs(R_shunt - R_shunt_orig) > 1e-12)

    # ── 2. TENSIONES DE SENSE ────────────────────────────
    V_TimON    = I_lim     * R_shunt * G
    V_superior = I_hys_sup * R_shunt * G
    V_inferior = I_hys_inf * R_shunt * G
    res["V_TimON"]    = V_TimON
    res["V_superior"] = V_superior
    res["V_inferior"] = V_inferior

    # ── 3. BLOQUE TEMPORIZADOR ───────────────────────────
    # Divisor R_up,timON / R_down,timON  →  VTimON = Vcc * R_down/(R_up+R_down)
    # → R_up/R_down = Vcc/VTimON - 1
    ratio_tim = V_cc / V_TimON - 1.0
    res["ratio_timON"] = ratio_tim          # R_up,timON / R_down,timON

    R_up_timON_sug, R_down_timON_sug = sugerir_par_resistencias(ratio_tim)
    V_TimON_real = V_cc * R_down_timON_sug / (R_up_timON_sug + R_down_timON_sug)
    res["R_up_timON"]   = R_up_timON_sug
    res["R_down_timON"] = R_down_timON_sug
    res["V_TimON_real"] = V_TimON_real

    # R_up,timer  →  τ = R_up,timer * C_timer
    #   τ = -t_trip / ln(1 - VTimON/(Vcc-VF))
    argln = 1.0 - V_TimON / (V_cc - V_F)
    if argln <= 0:
        warns.append(
            "⚠ V_TimON ≥ (Vcc − V_F): ecuación de τ sin solución. "
            "Revisa I_lim, R_shunt o G."
        )
        tau = float("nan")
        R_up_timer = float("nan")
    else:
        tau = -t_trip / math.log(argln)
        R_up_timer = tau / C_timer

    res["tau"]        = tau
    res["R_up_timer"] = R_up_timer

    # ── 4. BLOQUE HISTÉRESIS ─────────────────────────────
    # Vsuperior = Vcc * R_down,histSup / (R_up,histSup + R_down,histSup)
    # → R_up/R_down = Vcc/Vsup - 1
    delta_i = I_hys_sup - I_hys_inf
    res["delta_i"] = delta_i

    ratio_sup = V_cc / V_superior - 1.0
    ratio_inf = V_cc / V_inferior - 1.0
    res["ratio_histSup"] = ratio_sup
    res["ratio_histInf"] = ratio_inf

    R_up_hS, R_down_hS = sugerir_par_resistencias(ratio_sup)
    R_up_hI, R_down_hI = sugerir_par_resistencias(ratio_inf)
    V_sup_real = V_cc * R_down_hS / (R_up_hS + R_down_hS)
    V_inf_real = V_cc * R_down_hI / (R_up_hI + R_down_hI)

    res["R_up_histSup"]   = R_up_hS
    res["R_down_histSup"] = R_down_hS
    res["R_up_histInf"]   = R_up_hI
    res["R_down_histInf"] = R_down_hI
    res["V_sup_real"]     = V_sup_real
    res["V_inf_real"]     = V_inf_real

    # Error en corriente introducido por discretización
    I_hys_sup_real = V_sup_real / (R_shunt * G)
    I_hys_inf_real = V_inf_real / (R_shunt * G)
    res["I_hys_sup_real"] = I_hys_sup_real
    res["I_hys_inf_real"] = I_hys_inf_real

    err_sup_pct = abs(I_hys_sup_real - I_hys_sup) / I_hys_sup * 100
    err_inf_pct = abs(I_hys_inf_real - I_hys_inf) / I_hys_inf * 100
    res["err_sup_pct"] = err_sup_pct
    res["err_inf_pct"] = err_inf_pct
    if err_sup_pct > 3:
        warns.append(f"⚠ Error umbral superior con valores E24: {err_sup_pct:.1f} % — considera ajuste fino.")
    if err_inf_pct > 3:
        warns.append(f"⚠ Error umbral inferior con valores E24: {err_inf_pct:.1f} % — considera ajuste fino.")

    # ── 5. ESTRÉS TÉRMICO MOSFET ─────────────────────────
    duty  = 0.5
    I_rms = I_nom * math.sqrt(duty)
    P_cond = R_DS_ON * (I_rms ** 2)
    E_on   = 0.5 * V_bus * I_nom * t_rise
    E_off  = 0.5 * V_bus * I_nom * t_fall
    P_sw   = (E_on + E_off) * f_sw
    T_j    = T_a + (P_cond + P_sw) * (R_th_JC + R_th_CS + R_th_SA)

    res["I_rms"]   = I_rms
    res["P_cond"]  = P_cond
    res["P_sw"]    = P_sw
    res["T_j"]     = T_j
    res["T_j_max"] = T_j_max

    if T_j > T_j_max:
        warns.append(
            f"⚠ T_j = {T_j:.1f} °C > T_j,max = {T_j_max:.0f} °C. "
            f"Mejora disipador o reduce R_DS(ON)."
        )

    # ── 6. SATURACIÓN INDUCTANCIA ────────────────────────
    res["I_hys_sup"] = I_hys_sup
    res["I_sat"]     = I_sat
    margen_sat = I_sat - I_hys_sup
    res["margen_sat"] = margen_sat

    if margen_sat < 0:
        warns.append(
            f"⚠ I_hys,sup = {I_hys_sup:.2f} A > I_sat = {I_sat:.2f} A. "
            f"Riesgo de saturación del núcleo."
        )
    elif margen_sat < 0.1 * I_sat:
        warns.append(
            f"⚠ Margen saturación estrecho: I_sat − I_hys,sup = {margen_sat:.3f} A "
            f"(<10 % de I_sat). Verifica overshoot dinámico."
        )

    res["warnings"] = warns
    return res


# ════════════════════════════════════════════════════════════
#   EXPORTACIÓN A PDF
# ════════════════════════════════════════════════════════════

def exportar_pdf(params: dict, res: dict, filepath: str):
    if not REPORTLAB_OK:
        messagebox.showerror("Error", "reportlab no está instalado.\npip install reportlab")
        return

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    def sty(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    title_sty = sty("T", fontSize=15, spaceAfter=4,
                    textColor=colors.HexColor("#1a3a5c"), fontName="Helvetica-Bold")
    h2_sty    = sty("H2", fontSize=11, spaceBefore=10, spaceAfter=3,
                    textColor=colors.HexColor("#1a3a5c"), fontName="Helvetica-Bold")
    body_sty  = sty("B", fontSize=9, leading=13)
    warn_sty  = sty("W", fontSize=9, leading=13, textColor=colors.HexColor("#b85c00"))
    ok_sty    = sty("OK", fontSize=9, leading=13, textColor=colors.HexColor("#1a6e1a"))
    note_sty  = sty("N", fontSize=8, leading=11, textColor=colors.HexColor("#555577"))

    AZUL = colors.HexColor("#1a3a5c")
    GRIS = colors.HexColor("#eef2f7")
    GRID = colors.HexColor("#c0c8d8")

    def tbl(data, col_w=None):
        col_w = col_w or [9*cm, 7*cm]
        t = Table(data, colWidths=col_w)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), AZUL),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[GRIS, colors.white]),
            ("GRID",        (0,0), (-1,-1), 0.4, GRID),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING",(0,0), (-1,-1), 6),
            ("TOPPADDING",  (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ]))
        return t

    def kilo(v):
        if math.isnan(v): return "— error —"
        if v >= 1e6:   return f"{v/1e6:.3f} MΩ"
        if v >= 1e3:   return f"{v/1e3:.2f} kΩ"
        return f"{v:.1f} Ω"

    story = []

    # Cabecera
    story.append(Paragraph("Informe de Escalado — Limitador de Corriente LCL", title_sty))
    story.append(Paragraph(
        f"Generado: {datetime.datetime.now().strftime('%d/%m/%Y  %H:%M:%S')}", body_sty))
    story.append(HRFlowable(width="100%", thickness=1, color=AZUL, spaceAfter=8))

    # Esquemático
    if os.path.exists(SCHEMATIC_PATH):
        story.append(Paragraph("Esquemático de referencia", h2_sty))
        story.append(RLImage(SCHEMATIC_PATH, width=16*cm, height=8*cm))
        story.append(Spacer(1, 0.3*cm))

    # Parámetros de entrada
    story.append(Paragraph("Parámetros de entrada", h2_sty))
    entry_data = [
        ["Parámetro", "Valor"],
        ["V_bus",                  f"{params['V_bus']:.1f} V"],
        ["I_lim",                  f"{params['I_lim']:.2f} A"],
        ["I_hys,sup",              f"{params['I_hys_sup']:.2f} A"],
        ["I_hys,inf",              f"{params['I_hys_inf']:.2f} A"],
        ["Δi (banda histéresis)",  f"{res['delta_i']:.3f} A"],
        ["t_trip",                 f"{params['t_trip']*1e3:.3f} ms"],
        ["f_sw",                   f"{params['f_sw']*1e-3:.0f} kHz"],
        ["G",                      f"{params['G']:.1f} V/V"],
        ["C_timer",                f"{params['C_timer']*1e9:.0f} nF"],
        ["V_F",                    f"{params['V_F']:.2f} V"],
        ["V_cc",                   f"{params['V_cc']:.1f} V"],
        ["R_shunt (entrada)",      f"{params['R_shunt']*1e3:.3f} mΩ"],
        ["P_shunt,max",            f"{params['P_shunt_max']*1e3:.0f} mW"],
        ["I_sat",                  f"{params['I_sat']:.2f} A"],
    ]
    story.append(tbl(entry_data))
    story.append(Spacer(1, 0.3*cm))

    # 1 · R_shunt
    story.append(Paragraph("1 · Resistencia de sensado (R_shunt)", h2_sty))
    rs_data = [["Magnitud", "Valor"]]
    if res["R_shunt_changed"]:
        rs_data += [
            ["R_shunt introducida",    f"{params['R_shunt']*1e3:.3f} mΩ  ← excede P_max"],
            ["R_shunt ajustada ✦",     f"{res['R_shunt']*1e3:.4f} mΩ"],
        ]
    else:
        rs_data.append(["R_shunt",     f"{res['R_shunt']*1e3:.3f} mΩ  (sin cambios)"])
    rs_data.append(["P_shunt",         f"{res['P_shunt']*1e3:.1f} mW"])
    story.append(tbl(rs_data))

    # 2 · Temporizador
    story.append(Paragraph("2 · Bloque temporizador", h2_sty))
    story.append(Paragraph(
        "El divisor <b>R_up,timON / R_down,timON</b> fija VTimON = "
        "Vcc · R_down / (R_up + R_down).<br/>"
        "<b>R_up,timer</b> junto a C_timer determina el trip-off time: "
        "τ = R_up,timer · C_timer = −t_trip / ln(1 − VTimON/(Vcc−VF))",
        note_sty))
    story.append(Spacer(1, 0.15*cm))
    tim_data = [
        ["Magnitud", "Valor"],
        ["VTimON (teórico)",      f"{res['V_TimON']:.4f} V"],
        ["R_up,timON / R_down,timON (relación exacta)",
         f"{res['ratio_timON']:.4f}"],
        ["R_down,timON (ejemplo ≥10kΩ)",
         kilo(res["R_down_timON"])],
        ["R_up,timON (ejemplo E24)",
         kilo(res["R_up_timON"])],
        ["VTimON con valores E24",
         f"{res['V_TimON_real']:.4f} V"],
        ["τ_carga = R_up,timer · C_timer",
         f"{res['tau']*1e3:.3f} ms" if not math.isnan(res["tau"]) else "— error —"],
        ["R_up,timer (= τ / C_timer)",
         kilo(res["R_up_timer"]) if not math.isnan(res["R_up_timer"]) else "— error —"],
        ["C_timer (fijo)",
         f"{params['C_timer']*1e9:.0f} nF"],
    ]
    story.append(tbl(tim_data))

    # 3 · Histéresis
    story.append(Paragraph("3 · Bloque de histéresis", h2_sty))
    story.append(Paragraph(
        "Cada umbral usa su propio divisor desde Vcc: "
        "V_umbral = Vcc · R_down / (R_up + R_down).",
        note_sty))
    story.append(Spacer(1, 0.15*cm))
    hys_data = [
        ["Magnitud", "Umbral superior", "Umbral inferior"],
        ["V objetivo",
         f"{res['V_superior']:.4f} V", f"{res['V_inferior']:.4f} V"],
        ["R_up / R_down (relación exacta)",
         f"{res['ratio_histSup']:.4f}", f"{res['ratio_histInf']:.4f}"],
        ["R_down (ejemplo ≥10kΩ)",
         kilo(res["R_down_histSup"]), kilo(res["R_down_histInf"])],
        ["R_up (ejemplo E24)",
         kilo(res["R_up_histSup"]), kilo(res["R_up_histInf"])],
        ["V real con E24",
         f"{res['V_sup_real']:.4f} V", f"{res['V_inf_real']:.4f} V"],
        ["I_hys real con E24",
         f"{res['I_hys_sup_real']:.3f} A", f"{res['I_hys_inf_real']:.3f} A"],
        ["Error vs especificación",
         f"{res['err_sup_pct']:.2f} %", f"{res['err_inf_pct']:.2f} %"],
    ]
    story.append(tbl(hys_data, col_w=[7*cm, 4.5*cm, 4.5*cm]))

    # 4 · Térmico
    story.append(Paragraph("4 · Estrés térmico MOSFET", h2_sty))
    tj_ok = res["T_j"] <= res["T_j_max"]
    th_data = [
        ["Magnitud", "Valor"],
        ["I_rms",    f"{res['I_rms']:.3f} A"],
        ["P_cond",   f"{res['P_cond']:.3f} W"],
        ["P_sw",     f"{res['P_sw']:.3f} W"],
        ["P_total",  f"{(res['P_cond']+res['P_sw']):.3f} W"],
        ["T_j",      f"{res['T_j']:.1f} °C  {'✓ OK' if tj_ok else '✗ EXCEDIDO'}"],
    ]
    t_th = Table(th_data, colWidths=[9*cm, 7*cm])
    ts = TableStyle([
        ("BACKGROUND",  (0,0),(-1,0), AZUL),
        ("TEXTCOLOR",   (0,0),(-1,0), colors.white),
        ("FONTNAME",    (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0),(-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[GRIS, colors.white]),
        ("GRID",        (0,0),(-1,-1), 0.4, GRID),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",  (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("TEXTCOLOR",   (0,5),(-1,5),
         colors.HexColor("#1a6e1a") if tj_ok else colors.HexColor("#b80000")),
        ("FONTNAME",    (0,5),(-1,5), "Helvetica-Bold"),
    ])
    t_th.setStyle(ts)
    story.append(t_th)

    # 5 · Saturación
    story.append(Paragraph("5 · Margen de saturación inductancia", h2_sty))
    sat_ok = res["margen_sat"] >= 0
    sat_data = [
        ["Magnitud", "Valor"],
        ["I_hys,sup",               f"{res['I_hys_sup']:.3f} A"],
        ["I_sat",                   f"{res['I_sat']:.3f} A"],
        ["Margen (I_sat − I_hys,sup)",
         f"{res['margen_sat']:.3f} A  {'✓ OK' if sat_ok else '✗ SATURACIÓN'}"],
    ]
    t_sat = Table(sat_data, colWidths=[9*cm, 7*cm])
    ts2 = TableStyle([
        ("BACKGROUND",  (0,0),(-1,0), AZUL),
        ("TEXTCOLOR",   (0,0),(-1,0), colors.white),
        ("FONTNAME",    (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",    (0,0),(-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[GRIS, colors.white]),
        ("GRID",        (0,0),(-1,-1), 0.4, GRID),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",  (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("TEXTCOLOR",   (0,3),(-1,3),
         colors.HexColor("#1a6e1a") if sat_ok else colors.HexColor("#b80000")),
        ("FONTNAME",    (0,3),(-1,3), "Helvetica-Bold"),
    ])
    t_sat.setStyle(ts2)
    story.append(t_sat)

    # Advertencias
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRID, spaceAfter=4))
    story.append(Paragraph("Advertencias y validaciones", h2_sty))
    if res["warnings"]:
        for w in res["warnings"]:
            story.append(Paragraph(w, warn_sty))
    else:
        story.append(Paragraph("✓ Todos los parámetros dentro de especificación.", ok_sty))

    doc.build(story)


# ════════════════════════════════════════════════════════════
#   INTERFAZ GRÁFICA
# ════════════════════════════════════════════════════════════

AZUL   = "#1a3a5c"
AZUL_L = "#2c5f8a"
BLANCO = "#ffffff"
GRIS_F = "#f0f4f8"
GRIS_B = "#d0d8e4"
NARANJA= "#c96a00"
VERDE  = "#1a6e1a"
ROJO   = "#b80000"

def fmt_R(v):
    if math.isnan(v): return "— error —"
    if v >= 1e6:  return f"{v/1e6:.3f} MΩ"
    if v >= 1e3:  return f"{v/1e3:.2f} kΩ"
    return f"{v:.1f} Ω"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Calculadora LCL — Escalado de Diseño")
        self.configure(bg=AZUL)
        self.resizable(True, True)
        self.minsize(860, 660)
        self._build_ui()

    def _build_ui(self):
        # barra superior
        top = tk.Frame(self, bg=AZUL, padx=12, pady=8)
        top.pack(fill="x")
        tk.Label(top, text="⚡  Calculadora de Escalado · LCL",
                 bg=AZUL, fg=BLANCO,
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        # notebook (pestañas)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        self._tab_params(nb)
        self._tab_resultados(nb)
        self._tab_esquematico(nb)

    # ── Pestaña 1: Parámetros ────────────────────────────
    def _tab_params(self, nb):
        frame = tk.Frame(nb, bg=GRIS_F)
        nb.add(frame, text="  Parámetros  ")

        canvas = tk.Canvas(frame, bg=GRIS_F, highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=GRIS_F)
        iid = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(iid, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self.entries: dict[str, tk.StringVar] = {}

        sections = [
            ("ESPECIFICACIONES DE LA NUEVA CARGA", [
                ("V_bus",     "V_bus  (tensión de bus)",        "48",    "V"),
                ("I_lim",     "I_lim  (corriente limitación)",  "10",    "A"),
                ("I_hys_sup", "I_hys,sup  (umbral superior)",   "10.5",  "A"),
                ("I_hys_inf", "I_hys,inf  (umbral inferior)",   "9.5",   "A"),
                ("t_trip",    "t_trip  (tiempo de disparo)",    "5",     "ms"),
            ]),
            ("PARÁMETROS DE CONTROL  [defaults editables]", [
                ("G",        "G  (ganancia acond.)",            "25",    "V/V"),
                ("V_cc",     "V_cc  (alim. divisores)",         "5",     "V"),
                ("C_timer",  "C_timer",                         "100",   "nF"),
                ("V_F",      "V_F  (caída diodo)",              "0.32",  "V"),
                ("f_sw",     "f_sw  (frec. conmutación)",       "600",   "kHz"),
            ]),
            ("COMPONENTES DE POTENCIA", [
                ("R_shunt",     "R_shunt  (valor inicial)",     "5",     "mΩ"),
                ("P_shunt_max", "P_shunt,max  (encapsulado)",   "500",   "mW"),
                ("I_sat",       "I_sat  (núcleo magnético)",    "15",    "A"),
                ("R_DS_ON",     "R_DS(ON)  MOSFET",             "10",    "mΩ"),
                ("t_rise",      "t_rise",                       "50",    "ns"),
                ("t_fall",      "t_fall",                       "30",    "ns"),
            ]),
            ("MODELO TÉRMICO", [
                ("R_th_JC", "Rθ,JC  (junction→case)",          "1.2",   "°C/W"),
                ("R_th_CS", "Rθ,CS  (case→disipador)",         "0.5",   "°C/W"),
                ("R_th_SA", "Rθ,SA  (disipador→aire)",         "5.0",   "°C/W"),
                ("T_a",     "T_a  (ambiente)",                  "25",    "°C"),
                ("T_j_max", "T_j,max",                          "125",   "°C"),
            ]),
        ]

        for title, fields in sections:
            self._section(inner, title, fields)

        btn = tk.Frame(inner, bg=GRIS_F, pady=10)
        btn.pack(fill="x", padx=16)
        tk.Button(btn, text="▶  CALCULAR",
                  bg=AZUL, fg=BLANCO, activebackground=AZUL_L,
                  font=("Segoe UI", 11, "bold"), relief="flat",
                  padx=20, pady=8,
                  command=self._on_calcular).pack(side="left", padx=(0,10))
        tk.Button(btn, text="⬇  Exportar PDF",
                  bg=VERDE, fg=BLANCO,
                  font=("Segoe UI", 10), relief="flat",
                  padx=16, pady=8,
                  command=self._on_pdf).pack(side="left")

    def _section(self, parent, title, fields):
        lf = tk.LabelFrame(parent, text=f" {title} ", bg=GRIS_F,
                           fg=AZUL, font=("Segoe UI", 9, "bold"),
                           padx=10, pady=6)
        lf.pack(fill="x", padx=16, pady=(8,0))
        cols = 3
        for idx, (key, label, default, unit) in enumerate(fields):
            row = idx // cols
            col = (idx % cols) * 3
            tk.Label(lf, text=label+":", bg=GRIS_F, fg="#2a2a4a",
                     font=("Segoe UI", 9), anchor="e").grid(
                row=row, column=col, sticky="e", padx=(8,2), pady=3)
            var = tk.StringVar(value=default)
            self.entries[key] = var
            tk.Entry(lf, textvariable=var, width=10,
                     font=("Consolas", 9), relief="solid",
                     bg=BLANCO).grid(row=row, column=col+1, sticky="ew", padx=2)
            tk.Label(lf, text=unit, bg=GRIS_F, fg="#555577",
                     font=("Segoe UI", 8)).grid(
                row=row, column=col+2, sticky="w", padx=(2,12))

    # ── Pestaña 2: Resultados ────────────────────────────
    def _tab_resultados(self, nb):
        frame = tk.Frame(nb, bg=GRIS_F)
        nb.add(frame, text="  Resultados  ")

        self.res_text = tk.Text(
            frame, wrap="word", bg=BLANCO, fg="#1a1a2e",
            font=("Consolas", 9), relief="flat", state="disabled")
        vsb = ttk.Scrollbar(frame, orient="vertical",
                             command=self.res_text.yview)
        self.res_text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.res_text.pack(fill="both", expand=True, padx=8, pady=8)

        for tag, fg, bold in [
            ("titulo", AZUL,    True),
            ("ok",     VERDE,   False),
            ("warn",   NARANJA, False),
            ("error",  ROJO,    True),
            ("cambio", NARANJA, True),
            ("nota",   "#555577", False),
        ]:
            self.res_text.tag_config(
                tag, foreground=fg,
                font=("Consolas", 9, "bold" if bold else "normal"))

    # ── Pestaña 3: Esquemático ───────────────────────────
    def _tab_esquematico(self, nb):
        frame = tk.Frame(nb, bg=GRIS_F)
        nb.add(frame, text="  Esquemático  ")

        tk.Label(frame,
                 text="Esquemático de referencia — bloques Temporizador e Histéresis",
                 bg=GRIS_F, fg=AZUL, font=("Segoe UI", 10, "bold")).pack(pady=(12,6))

        if os.path.exists(SCHEMATIC_PATH):
            try:
                from PIL import Image as PILImage, ImageTk
                img = PILImage.open(SCHEMATIC_PATH)
                img.thumbnail((820, 500))
                self._photo = ImageTk.PhotoImage(img)
                tk.Label(frame, image=self._photo, bg=GRIS_F).pack(pady=4)
            except ImportError:
                tk.Label(frame,
                         text=f"[Instala Pillow para ver la imagen:\npip install Pillow]\n\n"
                              f"Archivo: {SCHEMATIC_PATH}",
                         bg=GRIS_F, fg=NARANJA,
                         font=("Segoe UI", 10), justify="center").pack(pady=40)
        else:
            tk.Label(frame,
                     text=f"Imagen no encontrada.\nColoca 'schematic.png' junto al script.",
                     bg=GRIS_F, fg=ROJO,
                     font=("Segoe UI", 10), justify="center").pack(pady=40)

        leyenda = (
            "R_up,timON / R_down,timON  →  divisor que fija VTimON\n"
            "R_up,timer + C_timer        →  red RC que determina t_trip\n"
            "R_up,histSup / R_down,histSup  →  divisor umbral superior de histéresis\n"
            "R_up,histInf / R_down,histInf  →  divisor umbral inferior de histéresis"
        )
        tk.Label(frame, text=leyenda, bg=GRIS_F, fg="#333355",
                 font=("Consolas", 8), justify="left",
                 relief="groove", padx=10, pady=6).pack(pady=(6,12), padx=16, fill="x")

    # ── Lectura de parámetros ────────────────────────────
    def _leer_params(self) -> dict:
        def g(k): return float(self.entries[k].get().replace(",","."))
        return {
            "V_bus":       g("V_bus"),
            "I_lim":       g("I_lim"),
            "I_hys_sup":   g("I_hys_sup"),
            "I_hys_inf":   g("I_hys_inf"),
            "t_trip":      g("t_trip")      * 1e-3,
            "G":           g("G"),
            "V_cc":        g("V_cc"),
            "C_timer":     g("C_timer")     * 1e-9,
            "V_F":         g("V_F"),
            "f_sw":        g("f_sw")        * 1e3,
            "R_shunt":     g("R_shunt")     * 1e-3,
            "P_shunt_max": g("P_shunt_max") * 1e-3,
            "I_sat":       g("I_sat"),
            "R_DS_ON":     g("R_DS_ON")     * 1e-3,
            "t_rise":      g("t_rise")      * 1e-9,
            "t_fall":      g("t_fall")      * 1e-9,
            "R_th_JC":     g("R_th_JC"),
            "R_th_CS":     g("R_th_CS"),
            "R_th_SA":     g("R_th_SA"),
            "T_a":         g("T_a"),
            "T_j_max":     g("T_j_max"),
        }

    # ── Mostrar resultados ───────────────────────────────
    def _mostrar(self, params, res):
        w = self.res_text
        w.configure(state="normal")
        w.delete("1.0", "end")

        def L(txt="", tag=""):  w.insert("end", txt+"\n", tag)
        def S(c="─", n=72):    L(c*n, "titulo")

        S("═"); L("  INFORME DE ESCALADO — LIMITADOR DE CORRIENTE LCL", "titulo")
        L(f"  {datetime.datetime.now().strftime('%d/%m/%Y  %H:%M')}", "titulo"); S("═")

        # 1 · R_shunt
        L(); L("【 1 · RESISTENCIA DE SENSADO — R_shunt 】", "titulo"); S()
        if res["R_shunt_changed"]:
            L(f"  R_shunt introducida  : {params['R_shunt']*1e3:.3f} mΩ", "warn")
            L(f"  P_shunt original     : {res['P_shunt_orig']*1e3:.1f} mW  "
              f"→ supera el límite ({params['P_shunt_max']*1e3:.0f} mW)", "warn")
            L(f"  R_shunt AJUSTADA     : {res['R_shunt']*1e3:.4f} mΩ  ← usar este valor", "cambio")
        else:
            L(f"  R_shunt              : {res['R_shunt']*1e3:.3f} mΩ  (sin cambios)", "ok")
        L(f"  P_shunt              : {res['P_shunt']*1e3:.1f} mW")

        # Tensiones de sense
        L(); L("【 2 · TENSIONES DE SENSE 】", "titulo"); S()
        L(f"  VTimON               : {res['V_TimON']:.4f} V")
        L(f"  Vsuperior            : {res['V_superior']:.4f} V")
        L(f"  Vinferior            : {res['V_inferior']:.4f} V")

        # Temporizador
        L(); L("【 3 · BLOQUE TEMPORIZADOR 】", "titulo"); S()
        L("  ── Divisor VTimON (R_up,timON / R_down,timON) ──", "nota")
        L(f"  VTimON = Vcc · R_down/(R_up+R_down)", "nota")
        L(f"  Relación exacta      : R_up,timON = {res['ratio_timON']:.4f} · R_down,timON")
        L(f"  Ejemplo ≥10kΩ        : R_down,timON = {fmt_R(res['R_down_timON'])}"
          f"  →  R_up,timON = {fmt_R(res['R_up_timON'])}")
        L(f"  VTimON real (E24)    : {res['V_TimON_real']:.4f} V")
        L()
        L("  ── Red RC (R_up,timer + C_timer) ──", "nota")
        L(f"  τ = R_up,timer · C_timer = {res['tau']*1e3:.3f} ms"
          if not math.isnan(res["tau"]) else "  τ: ERROR — ver advertencias", "error")
        L(f"  R_up,timer           : {fmt_R(res['R_up_timer'])}"
          if not math.isnan(res["R_up_timer"]) else "  R_up,timer: ERROR")
        L(f"  C_timer (fijo)       : {params['C_timer']*1e9:.0f} nF")

        # Histéresis
        L(); L("【 4 · BLOQUE DE HISTÉRESIS 】", "titulo"); S()
        L(f"  Δi (banda)           : {res['delta_i']:.3f} A")
        L()
        L("  ── Umbral SUPERIOR (R_up,histSup / R_down,histSup) ──", "nota")
        L(f"  Vsuperior objetivo   : {res['V_superior']:.4f} V")
        L(f"  Relación exacta      : R_up,histSup = {res['ratio_histSup']:.4f} · R_down,histSup")
        L(f"  Ejemplo ≥10kΩ        : R_down,histSup = {fmt_R(res['R_down_histSup'])}"
          f"  →  R_up,histSup = {fmt_R(res['R_up_histSup'])}")
        L(f"  Vsuperior real (E24) : {res['V_sup_real']:.4f} V  "
          f"→  I_hys,sup = {res['I_hys_sup_real']:.3f} A  "
          f"(error {res['err_sup_pct']:.2f} %)",
          "ok" if res["err_sup_pct"] < 3 else "warn")
        L()
        L("  ── Umbral INFERIOR (R_up,histInf / R_down,histInf) ──", "nota")
        L(f"  Vinferior objetivo   : {res['V_inferior']:.4f} V")
        L(f"  Relación exacta      : R_up,histInf = {res['ratio_histInf']:.4f} · R_down,histInf")
        L(f"  Ejemplo ≥10kΩ        : R_down,histInf = {fmt_R(res['R_down_histInf'])}"
          f"  →  R_up,histInf = {fmt_R(res['R_up_histInf'])}")
        L(f"  Vinferior real (E24) : {res['V_inf_real']:.4f} V  "
          f"→  I_hys,inf = {res['I_hys_inf_real']:.3f} A  "
          f"(error {res['err_inf_pct']:.2f} %)",
          "ok" if res["err_inf_pct"] < 3 else "warn")

        # Térmico
        L(); L("【 5 · ESTRÉS TÉRMICO MOSFET 】", "titulo"); S()
        L(f"  I_rms                : {res['I_rms']:.3f} A")
        L(f"  P_cond               : {res['P_cond']:.3f} W")
        L(f"  P_sw                 : {res['P_sw']:.3f} W")
        L(f"  P_total              : {(res['P_cond']+res['P_sw']):.3f} W")
        tj_ok = res["T_j"] <= res["T_j_max"]
        L(f"  T_j                  : {res['T_j']:.1f} °C  "
          f"({'✓ OK' if tj_ok else '✗ EXCEDIDO'})",
          "ok" if tj_ok else "error")

        # Saturación
        L(); L("【 6 · SATURACIÓN INDUCTANCIA 】", "titulo"); S()
        sat_ok = res["margen_sat"] >= 0
        L(f"  I_hys,sup            : {res['I_hys_sup']:.3f} A")
        L(f"  I_sat                : {res['I_sat']:.3f} A")
        L(f"  Margen               : {res['margen_sat']:.3f} A  "
          f"({'✓ OK' if sat_ok else '✗ SATURACIÓN'})",
          "ok" if sat_ok else "error")

        # Advertencias
        L(); S("═"); L("  ADVERTENCIAS", "titulo"); S("═")
        if res["warnings"]:
            for wt in res["warnings"]:
                L(f"  {wt}", "warn")
        else:
            L("  ✓ Todos los parámetros dentro de especificación.", "ok")

        w.configure(state="disabled")

    # ── Callbacks ────────────────────────────────────────
    def _on_calcular(self):
        try:
            params = self._leer_params()
        except ValueError as e:
            messagebox.showerror("Error de entrada", f"Valor no numérico:\n{e}")
            return
        try:
            res = calcular(params)
        except Exception as e:
            messagebox.showerror("Error de cálculo", str(e))
            return
        self._last_params = params
        self._last_res    = res
        self._mostrar(params, res)
        # cambiar a pestaña resultados
        self.nametowidget(self.winfo_children()[1]).select(1)

    def _on_pdf(self):
        if not hasattr(self, "_last_res") or self._last_res is None:
            messagebox.showinfo("Sin datos", "Primero pulsa CALCULAR.")
            return
        if not REPORTLAB_OK:
            messagebox.showerror("Error",
                                 "reportlab no instalado.\npip install reportlab")
            return
        fp = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF","*.pdf")],
            initialfile="informe_LCL.pdf", title="Guardar informe PDF")
        if not fp: return
        try:
            exportar_pdf(self._last_params, self._last_res, fp)
            messagebox.showinfo("PDF generado", f"Guardado en:\n{fp}")
            if os.name == "nt":
                os.startfile(fp)
        except Exception as e:
            messagebox.showerror("Error al generar PDF", str(e))

    _last_res    = None
    _last_params = None


# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    App().mainloop()

