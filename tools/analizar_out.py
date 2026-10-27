#!/usr/bin/env python3
"""Post-proceso de out.mat del modelo DMC_FCSMPC_IM_Physical_v6_3.

Contrasta el hallazgo 1 (subfluxado) contra datos de simulacion, sin MATLAB.

Uso:  python3 tools/analizar_out.py out.mat [t_ini t_fin]

OJO con como se genera out.mat. El modelo tiene activado "single simulation
output", asi que sim() devuelve UN solo Simulink.SimulationOutput y
save('out.mat') guarda un unico objeto MCOS que scipy NO puede leer
(scipy.io.whosmat tira TypeError en shape_from_header). Hay que
desempaquetarlo primero:

    matlab -batch "addpath('tools'); desempaquetar_out('<ruta>/out.mat')"

Ventana por defecto 1.0 a 2.0 s: es la unica de regimen limpio, porque la
fuente programable mete un escalon de frecuencia 50->65 Hz entre 2 y 4 s
y el modelo corre hasta StopTime=3. Ademas w_ref rampa de 0 a 95 rad/s
durante el primer segundo (w_ramp_time = 1.0 en chart_40).

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
KP_W, TS_CTRL = 20.0, 2e-4
VENTANA = (1.0, 2.0)

# columna -> nombre, segun el cableado de los Mux verificado en system_root.xml
COLUMNAS = {
    'speed_log':    ['w_ref', 'wm'],
    'torque_log':   ['Te', 'Tm'],
    'currents_log': ['ia', 'ib', 'ic'],
    'iref_log':     ['ia_ref', 'ib_ref', 'ic_ref'],
    'psi_log':      ['psi_r_abs'],
    # Agregadas para medir directamente la funcion de costo del MPC.
    # Solo existen en las variantes del barrido de lambda_sw; si faltan,
    # el script avisa y sigue.
    'gmin_log':     ['g_min'],
    'iqcmd_log':    ['iq_cmd'],
    'iqref_log':    ['iq_ref'],
    # Flujo rotorico REAL, del bus de medicion de la maquina. A diferencia de
    # psi_log (que sale del estimador), este no pasa por ningun modelo del
    # control. OJO: con ReferenceFrame = Rotor las componentes estan en el
    # marco del rotor, asi que el MODULO es directo pero el angulo absoluto
    # requiere rotar por theta_r.
    'phir_log':     ['phir_q', 'phir_d'],
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
        if 'ans' in presentes:
            sys.exit(
                "\nEl .mat trae un solo 'ans': es el Simulink.SimulationOutput sin\n"
                "desempaquetar, y scipy no puede leer objetos MCOS. Correr primero:\n"
                "  matlab -batch \"addpath('tools'); desempaquetar_out('<ruta>/out.mat')\"")
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
    kr = Lm / Lr
    psi = medias.get('psi_r_abs')
    wm = medias.get('wm')
    Te = medias.get('Te')

    # --- flujo ---
    print("\n--- flujo rotorico ---")
    if psi is not None:
        print(f"psi_r medido       = {psi:.4f} Wb   "
              f"({100*psi/psi_nom:.1f} % del nominal {psi_nom:.4f} Wb)")
        print(f"Lm*id_ref          = {Lm*ID_REF:.4f} Wb   (id_ref={ID_REF} A; esa igualdad")
        print(f"                     vale solo si el eje d esta alineado con el flujo real)")
        print(f"desvio             = {100*(psi-Lm*ID_REF)/(Lm*ID_REF):+.1f} %")
        print(f"id necesario       = {psi_nom/Lm:.2f} A para flujo nominal")
        print(f"Te_max con este psi= {1.5*p*kr*psi*IQ_MAX:.2f} N.m  (con iq={IQ_MAX} A)")

    # --- amplitudes de corriente ---
    amp_ref = amp_med = None
    print("\n--- corriente: referencia contra medida ---")
    if 'iref_log' in datos:
        amp_ref = amplitud_abc(ventana(*datos['iref_log'], a, b)[1])
        print(f"|i_ref| medio      = {amp_ref.mean():7.2f} A pico "
              f"(min {amp_ref.min():.2f}  max {amp_ref.max():.2f})")
    if 'currents_log' in datos:
        amp_med = amplitud_abc(ventana(*datos['currents_log'], a, b)[1])
        print(f"|i|     medio      = {amp_med.mean():7.2f} A pico "
              f"(min {amp_med.min():.2f}  max {amp_med.max():.2f})")

    # --- saturacion ---
    # El limitador real del lazo es iq_max sobre iq_cmd dentro de chart_40,
    # no la amplitud de |i_ref|. Se miden los dos.
    print("\n--- saturacion del lazo de velocidad ---")
    if 'speed_log' in datos:
        t, SP = ventana(*datos['speed_log'], a, b)
        iq_cmd = KP_W * (SP[:, 0] - SP[:, 1])
        frac = float((np.abs(iq_cmd) >= IQ_MAX * 0.999).mean())
        print(f"iq_cmd = Kp_w*(w_ref-wm): medio {iq_cmd.mean():.2f} A, "
              f"max {np.abs(iq_cmd).max():.2f} A   (iq_max = {IQ_MAX} A)")
        print(f"fraccion saturada  = {100*frac:.1f} % de la ventana")
        print("  -> " + ("saturacion permanente: el lazo perdio autoridad" if frac > 0.95
                         else "sin saturacion: el error de velocidad es la caida"
                              " proporcional de un lazo P sin integrador"))
    if amp_ref is not None:
        techo = math.hypot(ID_REF, IQ_MAX)
        fr = float((amp_ref >= techo * 0.995).mean())
        print(f"|i_ref| en el techo sqrt(id^2+iq_max^2)={techo:.2f} A: "
              f"{100*fr:.1f} % del tiempo")

    # --- reconciliacion de iq por tres caminos ---
    # Los tres NO tienen por que coincidir: 1 y 2 viven en el marco del control
    # (eje d = flujo estimado), 3 vive en el marco del flujo real. La diferencia
    # entre 2 y 3 es justamente la desalineacion.
    print("\n--- iq por tres caminos independientes ---")
    iq_cmd_m = KP_W * (W_REF - wm) if wm is not None else None
    iq_de_ref = (math.sqrt(max(amp_ref.mean()**2 - ID_REF**2, 0.0))
                 if amp_ref is not None else None)
    iq_act = Te / (1.5 * p * kr * psi) if (Te is not None and psi) else None
    if iq_cmd_m is not None:
        print(f"1) iq_cmd  = Kp_w*(w_ref-wm)         = {iq_cmd_m:7.2f} A  (lo que pide el lazo)")
    if iq_de_ref is not None:
        print(f"2) iq_ref  = sqrt(|i_ref|^2-id_ref^2)= {iq_de_ref:7.2f} A  (lo que lleva la referencia)")
    if iq_act is not None:
        print(f"3) iq_real = Te/(1.5 p kr psi_r)     = {iq_act:7.2f} A  (lo que entrega la maquina)")
    if iq_cmd_m and iq_de_ref:
        d = 100 * abs(iq_de_ref - iq_cmd_m) / iq_cmd_m
        print(f"   1 contra 2: {d:5.2f} %  -> " +
              ("coherente, la cadena de referencia es la del codigo" if d < 2
               else "NO coherente: revisar id_ref, Kp_w o el filtro alpha_iq"))
    if iq_de_ref and iq_act:
        d = 100 * abs(iq_de_ref - iq_act) / iq_de_ref
        print(f"   2 contra 3: {d:5.2f} %  -> " +
              ("alineacion buena" if d < 3
               else "el vector corriente NO esta alineado con el flujo real"))

    # --- cierre del vector ---
    if psi and iq_act is not None:
        id_act = psi / Lm
        mod = math.hypot(id_act, iq_act)
        print("\n--- componentes reales en el marco del flujo ---")
        print(f"id_real = psi_r/Lm                 = {id_act:7.2f} A  "
              f"(contra id_ref = {ID_REF} A)")
        print(f"iq_real = Te/(1.5 p kr psi_r)      = {iq_act:7.2f} A")
        print(f"sqrt(id_real^2+iq_real^2)          = {mod:7.2f} A")
        if amp_med is not None:
            e = 100 * abs(mod - amp_med.mean()) / amp_med.mean()
            print(f"|i| medido                         = {amp_med.mean():7.2f} A  "
                  f"-> cierra al {e:.1f} %")
            print("  (la media de |i| queda algo por encima del modulo del vector medio:")
            print("   el rizado del FCS-MPC infla la media de un modulo)")
        if iq_de_ref:
            ang_ref = math.degrees(math.atan2(iq_de_ref, ID_REF))
            ang_act = math.degrees(math.atan2(iq_act, id_act))
            print(f"angulo del vector: referencia {ang_ref:.2f} deg, real {ang_act:.2f} deg"
                  f"  -> desalineacion {ang_ref-ang_act:+.2f} deg")
            tau_r = Lr / Rr
            w_slip = Lm * iq_act / (tau_r * psi)
            w_e = p * wm + w_slip
            print(f"w_slip = {w_slip:.2f} rad/s,  w_e = {w_e:.2f} rad/s "
                  f"({w_e/(2*math.pi):.2f} Hz)")
            print(f"un paso Ts_ctrl={TS_CTRL*1e6:.0f} us a esa w_e son "
                  f"{math.degrees(w_e*TS_CTRL):.2f} deg de rotacion")

    # --- balance de par ---
    print("\n--- balance de par ---")
    if wm is not None:
        Tl = 5 + 0.0054 * wm**2 + F * wm
        print(f"wm medido          = {wm:.2f} rad/s   (w_ref = {W_REF})")
        print(f"error de velocidad = {W_REF-wm:.2f} rad/s  ({100*(W_REF-wm)/W_REF:.1f} %)")
        print(f"carga a esa wm     = {Tl:.2f} N.m   (Tm + F*wm)")
        print(f"carga a w_ref={W_REF:.0f}      = {5+0.0054*W_REF**2+F*W_REF:.2f} N.m")
    for k, txt in (('Te', 'Te medido'), ('Tm', 'Tm medido')):
        if k in medias:
            t, Y = ventana(*datos['torque_log'], a, b)
            j = COLUMNAS['torque_log'].index(k)
            print(f"{txt:<19}= {medias[k]:.2f} N.m  (rizado {Y[:,j].max()-Y[:,j].min():.2f})")
    if Te is not None and wm is not None and 'Tm' in medias:
        print(f"Te - (Tm+F*wm)     = {Te-(medias['Tm']+F*wm):+.2f} N.m  "
              "(tiene que dar ~0 en regimen)")

    # --- contraste con la prediccion analitica de CLAUDE.md ---
    print("\n--- prediccion analitica (CLAUDE.md, hallazgo 1) ---")
    Te_pred = 1.5 * p * kr * (Lm * ID_REF) * IQ_MAX
    w_pred = (-F + math.sqrt(F*F + 4*0.0054*(Te_pred-5))) / (2*0.0054)
    print(f"psi_r = {Lm*ID_REF:.4f} Wb | Te_max = {Te_pred:.2f} N.m | w_eq = {w_pred:.2f} rad/s")
    if wm is not None:
        d = wm - w_pred
        print(f"wm medido - wm predicho = {d:+.2f} rad/s ({100*abs(d)/w_pred:.1f} %)")
        if abs(d) < 3:
            print("  -> prediccion CONFIRMADA")
        else:
            print("  -> prediccion NO confirmada. La cuenta supone psi_r = Lm*id_ref,")
            print("     es decir alineacion perfecta; arriba esta medido el desvio.")

    print(f"\nsigma = {SIGMA:.4f}   Ls = {Ls*1e3:.3f} mH   Lr = {Lr*1e3:.3f} mH")


if __name__ == '__main__':
    main()
