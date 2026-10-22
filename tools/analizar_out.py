#!/usr/bin/env python3
"""Post-proceso de out.mat del modelo DMC_FCSMPC_IM_Physical_v6_3.

Verifica el hallazgo 1 (subfluxado) contra datos de simulacion, sin MATLAB.

Uso:  python3 tools/analizar_out.py out.mat [t_ini t_fin]

Ventana por defecto 1.0 a 2.0 s: es la unica de regimen limpio, porque la
fuente programable mete un escalon de frecuencia 50->65 Hz entre 2 y 4 s
y el modelo corre hasta StopTime=3.

Variables que escribe el v6.3 (bloques To Workspace, 'Structure With Time'):

    speed_log     [w_ref, wm]              torque_log    [Te, Tm]
    currents_log  [ia, ib, ic]             iref_log      [ia_ref, ib_ref, ic_ref]
    psi_log       psi_r_abs                gates_log     9 compuertas
    isource_log / vsource_log / idmc_log / ic_log   medidas trifasicas
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
ID_REF, IQ_MAX, W_REF = 10.0, 50.0, 95.0
VENTANA = (1.0, 2.0)

# columna -> nombre, segun el cableado de los Mux verificado en system_root.xml
COLUMNAS = {
    'speed_log':    ['w_ref', 'wm'],
    'torque_log':   ['Te', 'Tm'],
    'currents_log': ['ia', 'ib', 'ic'],
    'iref_log':     ['ia_ref', 'ib_ref', 'ic_ref'],
    'psi_log':      ['psi_r_abs'],
}


def _desenvolver(x):
    """Saca capas de ndarray de un solo elemento hasta llegar al dato util."""
    while isinstance(x, np.ndarray) and x.size == 1 and (
            x.dtype == object or x.dtype.names is not None):
        x = x.flat[0]
    return x


def leer(mat, nombre):
    """Devuelve (t, Y) de un To Workspace en formato 'Structure With Time'."""
    if nombre not in mat:
        return None
    s = _desenvolver(mat[nombre])
    try:
        t = np.asarray(_desenvolver(s['time']), float).squeeze()
        sig = _desenvolver(s['signals'])
        Y = np.asarray(_desenvolver(sig['values']), float)
    except Exception as e:
        print(f"  AVISO: no se pudo leer {nombre} ({type(e).__name__}: {e})")
        return None
    if Y.ndim == 1:
        Y = Y.reshape(-1, 1)
    if Y.shape[0] != t.size and Y.shape[-1] == t.size:
        Y = Y.T
    return t, Y


def ventana(t, Y, a, b):
    m = (t >= a) & (t <= b)
    return (t[m], Y[m]) if m.any() else (t, Y)


def amplitud_abc(Y):
    """Amplitud pico del fasor, via Clarke invariante en amplitud."""
    ia, ib, ic = Y[:, 0], Y[:, 1], Y[:, 2]
    al = (2.0 / 3.0) * (ia - 0.5 * ib - 0.5 * ic)
    be = (ib - ic) / math.sqrt(3.0)
    return np.hypot(al, be)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ruta = sys.argv[1]
    a, b = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) >= 4 else VENTANA

    mat = loadmat(ruta, squeeze_me=False, struct_as_record=True)
    presentes = [k for k in mat if not k.startswith('__')]
    print(f"=== {ruta} ===")
    print(f"Variables en el archivo ({len(presentes)}): {', '.join(sorted(presentes))}")

    datos = {}
    for nombre in COLUMNAS:
        r = leer(mat, nombre)
        if r:
            datos[nombre] = r
    faltan = [k for k in COLUMNAS if k not in datos]
    if faltan:
        print(f"AVISO: faltan {', '.join(faltan)}")
    if not datos:
        sys.exit("\nNinguna variable esperada. Confirmar que se guardo el workspace "
                 "tras simular DMC_FCSMPC_IM_Physical_v6_3_STABLE.")

    t0 = next(iter(datos.values()))[0]
    print(f"\nSimulacion: {t0[0]:.3f} a {t0[-1]:.3f} s, {t0.size} muestras "
          f"(paso medio {np.diff(t0).mean()*1e6:.1f} us)")
    print(f"Ventana de regimen: {a} a {b} s\n")

    # --- tabla de senales ---
    print(f"{'senal':<12}{'media':>12}{'min':>12}{'max':>12}{'final':>12}")
    medias = {}
    for nombre, etiquetas in COLUMNAS.items():
        if nombre not in datos:
            continue
        t, Y = datos[nombre]
        tv, Yv = ventana(t, Y, a, b)
        for j, et in enumerate(etiquetas):
            if j >= Yv.shape[1]:
                continue
            col = Yv[:, j]
            medias[et] = float(col.mean())
            print(f"{et:<12}{col.mean():>12.4f}{col.min():>12.4f}"
                  f"{col.max():>12.4f}{Y[-1, j]:>12.4f}")

    psi_nom = (380 / math.sqrt(3)) * math.sqrt(2) / (2 * math.pi * 50)

    # --- hallazgo 1 ---
    print("\n--- hallazgo 1: subfluxado ---")
    psi = medias.get('psi_r_abs')
    if psi is not None:
        print(f"psi_r medido       = {psi:.4f} Wb   ({100*psi/psi_nom:.1f} % del nominal {psi_nom:.4f} Wb)")
        print(f"psi_r predicho     = {Lm*ID_REF:.4f} Wb   (Lm*id_ref con id_ref={ID_REF} A)")
        print(f"error de prediccion= {100*abs(psi-Lm*ID_REF)/(Lm*ID_REF):.1f} %")
        print(f"id_ref necesario   = {psi_nom/Lm:.2f} A para flujo nominal")
        print(f"Te_max con este psi= {1.5*p*(Lm/Lr)*psi*IQ_MAX:.2f} N.m  (con iq={IQ_MAX} A)")

    if 'iref_log' in datos:
        tv, Yv = ventana(*datos['iref_log'], a, b)
        amp = amplitud_abc(Yv)
        amp_sat = math.hypot(ID_REF, IQ_MAX)
        frac = float((amp >= amp_sat * 0.995).mean())
        print(f"\n|i_ref| medido     = {amp.mean():.2f} A pico   "
              f"(saturacion teorica = sqrt(id^2+iq_max^2) = {amp_sat:.2f} A)")
        print(f"fraccion saturada  = {100*frac:.1f} % de la ventana")
        if frac > 0.95:
            print("  -> saturacion permanente: el lazo de velocidad perdio autoridad")
        iq_est = math.sqrt(max(amp.mean()**2 - ID_REF**2, 0.0))
        print(f"iq estimado        = {iq_est:.2f} A  (de |i_ref| y id_ref)")

    if psi is not None and 'Te' in medias:
        iq_te = medias['Te'] / (1.5 * p * (Lm / Lr) * psi)
        print(f"iq segun Te y psi  = {iq_te:.2f} A")

    # --- balance de par y velocidad ---
    print("\n--- balance de par ---")
    if 'wm' in medias:
        wm = medias['wm']
        Tl = 5 + 0.0054 * wm**2 + F * wm
        print(f"wm medido          = {wm:.2f} rad/s   (w_ref = {W_REF})")
        print(f"error de velocidad = {W_REF-wm:.2f} rad/s  ({100*(W_REF-wm)/W_REF:.1f} %)")
        print(f"carga a esa wm     = {Tl:.2f} N.m   (Tm + F*wm)")
    for k, txt in (('Te', 'Te medido'), ('Tm', 'Tm medido')):
        if k in medias:
            t, Y = ventana(*datos['torque_log'], a, b)
            j = COLUMNAS['torque_log'].index(k)
            print(f"{txt:<19}= {medias[k]:.2f} N.m  (rizado {Y[:,j].max()-Y[:,j].min():.2f})")

    # --- contraste con la prediccion analitica ---
    print("\n--- prediccion analitica (CLAUDE.md, hallazgo 1) ---")
    Te_pred = 1.5 * p * (Lm / Lr) * (Lm * ID_REF) * IQ_MAX
    w_pred = (-F + math.sqrt(F*F + 4*0.0054*(Te_pred-5))) / (2*0.0054)
    print(f"psi_r = {Lm*ID_REF:.4f} Wb | Te_max = {Te_pred:.2f} N.m | w_eq = {w_pred:.2f} rad/s")
    if 'wm' in medias:
        d = medias['wm'] - w_pred
        print(f"wm medido - wm predicho = {d:+.2f} rad/s ({100*abs(d)/w_pred:.1f} %)")
        print("  -> " + ("prediccion CONFIRMADA" if abs(d) < 3
                         else "discrepancia: revisar las hipotesis del calculo"))

    print(f"\nsigma = {SIGMA:.4f}   Ls = {Ls*1e3:.3f} mH   Lr = {Lr*1e3:.3f} mH")


if __name__ == '__main__':
    main()
