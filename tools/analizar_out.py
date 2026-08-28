#!/usr/bin/env python3
"""Post-proceso de out.mat del modelo DMC_FCSMPC_IM_Physical_v6_1.

Verifica el hallazgo 1 (subfluxado) contra datos de simulacion, sin MATLAB.
Uso:  python3 tools/analizar_out.py out.mat [t_ini t_fin]
Por defecto la ventana de regimen es 1.0 a 2.0 s, que es la unica limpia:
la fuente programable mete un escalon de frecuencia 50->65 Hz entre 2 y 4 s.
"""
import sys, math
import numpy as np
from scipy.io import loadmat

# --- parametros del modelo, leidos del .slx ---
Lls, Llr, Lm = 0.0003495, 0.005473, 0.0354
Rs, Rr = 0.5968, 0.6258
J, F, p = 0.08, 0.005879, 2
Ls, Lr = Lls + Lm, Llr + Lm
SIGMA = 1 - Lm**2 / (Ls * Lr)
IQ_MAX, ID_REF, W_REF = 50.0, 10.0, 95.0
VENTANA = (1.0, 2.0)

SENALES = ['wm', 'Te', 'w_ref', 'iq_cmd', 'iq_ref', 'g_min', 'psi_r_abs', 'pred_err_abs']


def cosechar(obj, acc, prof=0):
    """Recorre el Dataset de Simulink y junta (nombre, t, y) de cada senal."""
    if prof > 12 or obj is None:
        return
    if isinstance(obj, np.ndarray):
        if obj.dtype.names:
            campos = obj.dtype.names
            if {'Values', 'Name'} <= set(campos) or {'Time', 'Data'} <= set(campos):
                reg = obj.flat[0] if obj.size else None
                if reg is not None:
                    nombre = None
                    if 'Name' in campos:
                        n = reg['Name']
                        nombre = str(np.asarray(n).flat[0]) if np.asarray(n).size else None
                    val = reg['Values'] if 'Values' in campos else reg
                    try:
                        v = val.flat[0] if isinstance(val, np.ndarray) and val.size else val
                        t = np.asarray(v['Time'], float).squeeze()
                        y = np.asarray(v['Data'], float).squeeze()
                        if t.size and y.size:
                            acc.append((nombre or 'sin_nombre', t, y))
                            return
                    except Exception:
                        pass
            for f in campos:
                for reg in obj.flat:
                    cosechar(reg[f], acc, prof + 1)
        elif obj.dtype == object:
            for reg in obj.flat:
                cosechar(reg, acc, prof + 1)


def ventana(t, y, a, b):
    m = (t >= a) & (t <= b)
    return (t[m], y[m]) if m.any() else (t, y)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ruta = sys.argv[1]
    a, b = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) >= 4 else VENTANA

    mat = loadmat(ruta, squeeze_me=False, struct_as_record=False)
    acc = []
    for k, v in mat.items():
        if not k.startswith('__'):
            cosechar(v, acc)
    # loadmat con struct_as_record=False devuelve mat_struct, no ndarray estructurado;
    # se reintenta en modo record si no se cosecho nada.
    if not acc:
        mat = loadmat(ruta, squeeze_me=False, struct_as_record=True)
        for k, v in mat.items():
            if not k.startswith('__'):
                cosechar(v, acc)
    if not acc:
        sys.exit(f"No se encontraron senales con time-series en {ruta}. "
                 f"Confirmar SaveFormat=Dataset y SignalLogging=on.")

    d = {}
    for nombre, t, y in acc:
        d.setdefault(nombre, (t, y))

    print(f"=== {ruta} ===")
    print(f"Senales halladas ({len(d)}): {', '.join(sorted(d))}")
    faltan = [s for s in SENALES if s not in d]
    if faltan:
        print(f"AVISO: faltan del set esperado: {', '.join(faltan)}")
    print(f"\nVentana de regimen: {a} s a {b} s")
    print(f"{'senal':<14}{'media':>12}{'min':>12}{'max':>12}{'final':>12}")
    for s in SENALES:
        if s not in d:
            continue
        t, y = ventana(*d[s], a, b)
        print(f"{s:<14}{y.mean():>12.4f}{y.min():>12.4f}{y.max():>12.4f}{d[s][1].flat[-1]:>12.4f}")

    print("\n--- hallazgo 1: subfluxado ---")
    if 'psi_r_abs' in d:
        _, psi = ventana(*d['psi_r_abs'], a, b)
        pm = float(psi.mean())
        psi_nom = (380 / math.sqrt(3)) * math.sqrt(2) / (2 * math.pi * 50)
        print(f"psi_r medido      = {pm:.4f} Wb   ({100*pm/psi_nom:.1f} % del nominal {psi_nom:.4f})")
        print(f"psi_r teorico     = {Lm*ID_REF:.4f} Wb  (Lm*id_ref, id_ref={ID_REF})")
        print(f"id_ref necesario  = {psi_nom/Lm:.2f} A para flujo nominal")
        te_max = 1.5 * p * (Lm / Lr) * pm * IQ_MAX
        print(f"Te_max con este psi = {te_max:.2f} N.m")
    if 'iq_ref' in d:
        _, iq = ventana(*d['iq_ref'], a, b)
        frac = float((np.abs(iq) >= IQ_MAX * 0.999).mean())
        print(f"iq_ref saturado   = {100*frac:.1f} % de la ventana (limite {IQ_MAX} A)")
        if frac > 0.95:
            print("  -> saturacion permanente: el lazo de velocidad no tiene autoridad")
    if 'wm' in d:
        _, w = ventana(*d['wm'], a, b)
        wm = float(w.mean())
        Tl = 5 + 0.0054 * wm**2 + F * wm
        print(f"wm medido         = {wm:.2f} rad/s   (w_ref = {W_REF})")
        print(f"error de velocidad= {W_REF - wm:.2f} rad/s ({100*(W_REF-wm)/W_REF:.1f} %)")
        print(f"Tm + F*wm a esa wm= {Tl:.2f} N.m")
    if 'Te' in d:
        _, te = ventana(*d['Te'], a, b)
        print(f"Te medido         = {te.mean():.2f} N.m  (rizado {te.max()-te.min():.2f})")
    if 'pred_err_abs' in d:
        _, e = ventana(*d['pred_err_abs'], a, b)
        print(f"\npred_err_abs      = {e.mean():.4f} A medio, {e.max():.4f} pico"
              f"   (si es alto, el modelo del MPC no sigue a la planta)")
    if 'g_min' in d:
        _, g = ventana(*d['g_min'], a, b)
        print(f"g_min             = {g.mean():.4f} medio, {g.max():.4f} pico")

    print(f"\nsigma = {SIGMA:.4f}   Ls = {Ls*1e3:.3f} mH   Lr = {Lr*1e3:.3f} mH")


if __name__ == '__main__':
    main()
