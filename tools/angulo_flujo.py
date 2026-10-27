#!/usr/bin/env python3
"""Angulo absoluto del flujo rotorico REAL y descomposicion de la desalineacion.

Necesita en cada barrido_L*.mat:
  phir_log  = [phir_q, phir_d]       flujo rotorico del bus, marco rotor
  marco_log = [thetam, is_q, is_d]   angulo mecanico y corriente de estator,
                                     en el mismo marco que phir

Convencion de Park de la maquina de SPS, con theta = p*thetam (marco rotor):
  x_q = (2/3)*sum x_k*cos(theta - phi_k) = X*cos(theta - gamma)
  x_d = (2/3)*sum x_k*sin(theta - phi_k) = X*sin(theta - gamma)
=> angulo en marco estacionario: gamma = theta - atan2(x_d, x_q).
No se supone: se verifica con is_q/is_d contra ia/ib/ic, que se loguean por
separado. Si no cierra, el script corta.

Descomposicion, en el marco del flujo real, con nominal = atan2(iq_ref, id_ref):
  desalineacion = ang(i(k)) - ang(psi) - nominal
                = [ang(iref(k)) - ang(psi) - nominal]     error de orientacion
                                                          de la referencia
                + [ang(i(k+1)) - ang(iref(k))]            error de seguimiento
                + [ang(i(k)) - ang(i(k+1))]               un paso de rotacion
                                                          (ref de k apunta a k+1)
El primer termino, en T0, es el error de angulo del estimador; en T1 incluye
ademas el adelanto. Angulos positivos = adelantado respecto del flujo real.

Uso:  python tools/angulo_flujo.py [carpeta]
"""
import sys, os, glob, math
import numpy as np
from scipy.io import loadmat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comparar_barrido import serie  # noqa: E402

P, ID_REF, TS = 2, 10.0, 2e-4
LM, LR, RR = 0.0354, 0.040873, 0.6258
TAU_R = LR / RR
VENTANA = (1.0, 2.0)
ORDEN = ['L100_T0', 'L10_T0', 'L1_T0', 'L0_T0', 'L100_T1', 'L0_T1']


def cx(Y):
    return ((2/3) * (Y[:, 0] - 0.5*Y[:, 1] - 0.5*Y[:, 2])
            + 1j * (Y[:, 1] - Y[:, 2]) / math.sqrt(3))


def ang_medio(z):
    """angulo medio, en grados, de una serie de fasores relativos"""
    return math.degrees(np.angle(np.mean(z / np.abs(z))))


def analizar(ruta, sufijo=''):
    m = loadmat(ruta, squeeze_me=False, struct_as_record=True)
    v = os.path.basename(ruta)[8:-4 - len(sufijo)]
    sr = [serie(m, n) for n in ('phir_log', 'marco_log', 'currents_log', 'iref_log', 'iqref_log')]
    if any(s is None for s in sr[:4]):
        print(f"{v}: falta phir_log o marco_log, salteo")
        return None
    (t, PH), (tm, MA), (ti, I), (tr, R) = sr[:4]
    n = min(len(t), len(tm), len(ti), len(tr))
    if not (np.allclose(t[:n], tm[:n]) and np.allclose(t[:n], ti[:n]) and np.allclose(t[:n], tr[:n])):
        sys.exit(f"{v}: las bases de tiempo de los logs no coinciden")
    mk = (t[:n] >= VENTANA[0]) & (t[:n] <= VENTANA[1])
    th = P * MA[:n, 0][mk]
    rot = np.exp(1j * th)                      # gamma = theta - atan2(d, q)

    i_s = cx(I[:n][mk])
    i_bus = rot * np.exp(-1j * np.arctan2(MA[:n, 2][mk], MA[:n, 1][mk])) * np.hypot(MA[:n, 1][mk], MA[:n, 2][mk])
    chk = ang_medio(i_bus * np.conj(i_s))
    chk_mod = 100 * abs(np.abs(i_bus).mean() / np.abs(i_s).mean() - 1)

    psi = rot * np.exp(-1j * np.arctan2(PH[:n, 1][mk], PH[:n, 0][mk])) * np.hypot(PH[:n, 0][mk], PH[:n, 1][mk])
    iref = cx(R[:n][mk])

    if sr[4] is not None:
        iq_ref = sr[4][1][:n, 0][mk].mean()
    else:
        iq_ref = math.sqrt(max(np.abs(iref).mean()**2 - ID_REF**2, 0))
    nominal = math.degrees(math.atan2(iq_ref, ID_REF))

    # En t = k*Ts, floor(t/Ts) da k-1 por redondeo en el 57 % de los pasos: la
    # MATLAB Function recien se actualiza 1 us despues y el log toma la iref
    # del paso ANTERIOR, mientras el flujo del bus ya es el de k. Eso sesga
    # orient y seguim en ~0,57 pasos (~1,5 grados) en sentidos opuestos. Los
    # terminos que involucran iref se miden solo en las muestras limpias.
    tk = t[:n][mk]
    limpio = np.floor(tk / TS) == np.round(tk / TS)
    a_i = ang_medio(i_s * np.conj(psi))
    a_ref = ang_medio((iref * np.conj(psi))[limpio])
    seg = ang_medio((i_s[1:] * np.conj(iref[:-1]))[limpio[:-1]])
    paso = ang_medio(i_s[:-1] * np.conj(i_s[1:]))
    # Error de angulo del estimador en el MISMO instante. iref(k) se arma con
    # theta_est(k+1), porque el estimador integra hasta k+1 antes del atan2,
    # y T1 suma otro paso: hay que descontarlos.
    x = math.radians(abs(ang_medio(psi[1:] * np.conj(psi[:-1]))))   # rotacion por paso
    adel = 1 if v.endswith('T1') else 0
    E_med = -(a_ref - nominal) + math.degrees((1 + adel) * x)
    # Prediccion de Euler explicito en regimen: psi[k+1] = psi[k](1 - Ts/tr + j wr Ts)
    # + Ts Lm/tr i[k], contra el modelo continuo, con w_e y wm medidos.
    we = x / TS
    sp = serie(m, 'speed_log')
    wr = P * sp[1][:n, 1][mk].mean()
    Dc = 1 / TAU_R + 1j * (we - wr)
    if sufijo == '_EX':
        # discretizacion exacta con ZOH sobre i (tools/estimador_exacto.py)
        A = -1 / TAU_R + 1j * wr
        Phi = np.exp(A * TS)
        De = (np.exp(1j * x) - Phi) * A / (Phi - 1)
    else:
        De = (np.exp(1j * x) - 1) / TS + 1 / TAU_R - 1j * wr
    E_eul = math.degrees(np.angle(De) - np.angle(Dc))
    ps = serie(m, 'psi_log')
    mag_med = ps[1][:n, 0][mk].mean() / np.abs(psi).mean() if ps else float('nan')
    return dict(limpio=limpio.mean(), E_med=E_med, E_eul=E_eul, mag_med=mag_med, mag_eul=abs(Dc) / abs(De),
                we=we, var=v, chk=chk, chk_mod=chk_mod, psi=np.abs(psi).mean(),
                nominal=nominal, a_i=a_i, a_ref=a_ref,
                desal=nominal - a_i, orient=a_ref - nominal, seg=seg, paso=paso)


def main():
    sufijo = next((x.split('=', 1)[1] for x in sys.argv[1:] if x.startswith('--sufijo=')), '')
    resto = [x for x in sys.argv[1:] if not x.startswith('--sufijo=')]
    carpeta = resto[0] if resto else '.'
    rutas = [x for x in glob.glob(os.path.join(carpeta, 'barrido_L*.mat'))
             if os.path.basename(x)[8:-4] in [o + sufijo for o in ORDEN]]
    rutas.sort(key=lambda x: ORDEN.index(os.path.basename(x)[8:-4 - len(sufijo)]))
    res = [r for r in (analizar(x, sufijo) for x in rutas) if r]
    print(f"Estimador: {'EXACTO (ZOH)' if sufijo == '_EX' else 'Euler explicito'}\n")
    if not res:
        sys.exit("sin datos con phir_log y marco_log")

    print("--- verificacion de la convencion de Park (is_q/is_d del bus contra ia/ib/ic) ---")
    for r in res:
        print(f"  {r['var']:<8} angulo {r['chk']:+7.3f} deg   modulo {r['chk_mod']:5.2f} %")
    if max(abs(r['chk']) for r in res) > 1.0:
        print("\nPARAR: la rotacion por p*thetam no reproduce las corrientes medidas.")
        print("El angulo absoluto del flujo no es confiable; quedarse con el modulo.")
        return

    print("\n--- angulos en el marco del flujo REAL, grados ---")
    print(f"  {'celda':<8}{'|psi|':>8}{'nominal':>9}{'i real':>8}{'desal':>8}"
          f"{'orient ref':>12}{'seguim':>8}{'1 paso':>8}{'suma':>8}")
    for r in res:
        s = r['orient'] + r['seg'] + r['paso']
        print(f"  {r['var']:<8}{r['psi']:8.4f}{r['nominal']:9.2f}{r['a_i']:8.2f}{r['desal']:8.2f}"
              f"{r['orient']:12.2f}{r['seg']:8.2f}{r['paso']:8.2f}{-s:8.2f}")
    print("\n  desal  = nominal - angulo real de i respecto del flujo real (>0: i atrasada)")
    print("  orient = angulo de iref respecto del flujo real, menos nominal (<0: ref atrasada)")
    print("  seguim = ang(i(k+1)) - ang(iref(k)): error de seguimiento del MPC")
    print("  1 paso = ang(i(k)) - ang(i(k+1)): la ref de k apunta a k+1")
    print("  suma   = -(orient + seguim + 1 paso); tiene que dar desal")

    print("\n--- error del estimador contra el flujo real, mismo instante ---")
    print(f"  {'celda':<8}{'w_e':>8}{'E medido':>10}{'E pred':>9}{'resto':>8}"
          f"{'|est|/|real|':>14}{'pred':>8}")
    for r in res:
        print(f"  {r['var']:<8}{r['we']:8.1f}{r['E_med']:10.2f}{r['E_eul']:9.2f}"
              f"{r['E_med']-r['E_eul']:8.2f}{r['mag_med']:14.4f}{r['mag_eul']:8.4f}")
    print("  E > 0: el estimado atrasa al real. 'E pred' es lo que predice, en")
    print("  regimen, la discretizacion en uso (Euler, o ZOH exacta con --sufijo=_EX).")


if __name__ == '__main__':
    main()
