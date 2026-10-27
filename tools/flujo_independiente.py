#!/usr/bin/env python3
"""Estima el flujo rotorico SIN usar el estimador del modelo.

Por que hace falta. psi_log viene de MATLAB Function9, que es una copia exacta
del estimador interno del MPC: mismas ecuaciones, mismo Euler explicito, mismo
Ts. O sea que psi_log es "lo que el control cree", no lo que la maquina tiene.
Antes de discutir por que el flujo supera a Lm*id_ref, hay que descartar que
el exceso sea un error del estimador.

Este script lo estima por otro camino, usando solo dos cantidades que salen de
la maquina Simscape y no pasan por ningun estimador:

    Te      del Bus Selector de la maquina
    i_s     de las corrientes de fase medidas

En regimen permanente, con el modelo de la maquina de induccion orientado a
flujo rotorico, valen a la vez:

    Te      = 1.5 * p * (Lm/Lr) * Lm * id * iq        (par electromagnetico)
    |i_s|^2 = id^2 + iq^2                             (modulo de la corriente)

Son dos ecuaciones con dos incognitas. Tienen dos soluciones; la fisica es la
de iq > id, porque el motor esta cargado. De ahi sale psi_r = Lm * id.

Limitaciones, para no sobrevender el resultado:
  - supone regimen permanente y los mismos parametros que usa la planta,
  - el rizado del FCS-MPC mete error: para el modulo del fasor hay que usar
    el valor eficaz de las tres fases, NO la media del modulo instantaneo,
    que queda inflada.

Uso:  python3 tools/flujo_independiente.py <archivo.mat> [t_ini t_fin]
      sirve con out.mat y con los barrido_*.mat
"""
import sys, math
import numpy as np
from scipy.io import loadmat

Lm, Lr, Rr, p = 0.0354, 0.040873, 0.6258, 2
KR, TAU_R = Lm / Lr, Lr / Rr
ID_REF = 10.0
VENTANA = (1.0, 2.0)


def _des(x):
    while isinstance(x, np.ndarray) and x.size == 1 and (
            x.dtype == object or x.dtype.names is not None):
        x = x.flat[0]
    return x


def serie(mat, nombre):
    if nombre not in mat:
        return None
    s = _des(mat[nombre])
    try:
        t = np.asarray(_des(s['time']), float).squeeze()
        Y = np.asarray(_des(_des(s['signals'])['values']), float)
    except Exception:
        return None
    if Y.ndim == 1:
        Y = Y.reshape(-1, 1)
    if Y.shape[0] != t.size and Y.shape[-1] == t.size:
        Y = Y.T
    return t, Y


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ruta = sys.argv[1]
    a, b = (float(sys.argv[2]), float(sys.argv[3])) if len(sys.argv) >= 4 else VENTANA
    mat = loadmat(ruta, squeeze_me=False, struct_as_record=True)

    tq, cu = serie(mat, 'torque_log'), serie(mat, 'currents_log')
    if not tq or not cu:
        sys.exit("Faltan torque_log o currents_log en " + ruta)
    t = tq[0]
    mk = (t >= a) & (t <= b)
    Te = tq[1][mk, 0].mean()
    I = cu[1][mk]

    # Amplitud del fasor via valor eficaz de las tres fases. La media del
    # modulo instantaneo queda inflada por el rizado de conmutacion.
    Ipk = math.sqrt(2.0 / 3.0 * np.mean(I[:, 0] ** 2 + I[:, 1] ** 2 + I[:, 2] ** 2))

    K = 1.5 * p * KR * Lm
    prod, S = Te / K, Ipk ** 2
    disc = S * S - 4 * prod * prod
    print(f"=== {ruta}, ventana {a}-{b} s ===")
    print(f"  Te   (de la maquina)        = {Te:9.4f} N.m")
    print(f"  |i_s| pico (valor eficaz)   = {Ipk:9.4f} A")
    if disc <= 0:
        print("\n  Sin solucion real: el par pedido no es alcanzable con esa corriente.")
        print("  Probablemente la ventana no esta en regimen permanente.")
        return
    idv = math.sqrt((S - math.sqrt(disc)) / 2)
    iqv = prod / idv
    psi_real = Lm * idv
    print(f"\n  id deducido                 = {idv:9.2f} A   (el control pide {ID_REF})")
    print(f"  iq deducido                 = {iqv:9.2f} A")
    print(f"  psi_r = Lm*id               = {psi_real:9.4f} Wb")
    print(f"  Lm*id_ref                   = {Lm*ID_REF:9.4f} Wb")

    ps = serie(mat, 'psi_log')
    if ps:
        psi_est = ps[1][mk, 0].mean()
        d = 100 * (psi_est - psi_real) / psi_real
        print(f"\n  psi_r del estimador         = {psi_est:9.4f} Wb   ({d:+.1f} % contra el deducido)")
        if abs(d) < 15:
            print("  -> las dos coinciden razonablemente: el exceso de flujo es REAL,")
            print("     no un artefacto del estimador.")
        else:
            print("  -> discrepan bastante: el estimador podria estar aportando parte")
            print("     del exceso. Revisarlo antes de atribuir el flujo al control.")

    sp = serie(mat, 'speed_log')
    if sp and psi_real > 0:
        wm = sp[1][mk, 1].mean()
        w_sl = Lm * iqv / (TAU_R * psi_real)
        w_e = p * wm + w_sl
        print(f"\n  w_slip = {w_sl:6.2f} rad/s,  w_e = {w_e:7.2f} rad/s ({w_e/(2*math.pi):.2f} Hz)")
        print(f"  un paso de 200 us a esa w_e son {math.degrees(w_e*2e-4):.2f} grados:")
        print(f"  esa es la cota de lo que puede explicar la falta de adelanto de theta_psi.")


if __name__ == '__main__':
    main()
