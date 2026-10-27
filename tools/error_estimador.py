#!/usr/bin/env python3
"""Cuantifica el error sistematico del estimador de flujo discreto.

El estimador (identico en chart_40 y chart_61) integra con Euler explicito:

    psi(k+1) = psi(k) + Ts*[ (-psi(k) + Lm*i(k))/tau_r + j*omega_r*psi(k) ]

Con Ts = 200 us y w_e del orden de 227 rad/s, w_e*Ts = 2.6 grados por paso.
Eso NO es despreciable, y hace que el punto fijo discreto difiera del
continuo exacto. En regimen, con i y psi girando a w_e:

    discreto: psi = (Ts*Lm/tau_r)*i / (exp(j*w_e*Ts) - 1 + Ts/tau_r - j*w_r*Ts)
    continuo: psi = Lm*i / (1 + j*w_sl*tau_r)

La diferencia entre los dos es error del estimador, no del control: aparece
aunque el MPC siguiera su referencia perfectamente.

Uso:  python3 tools/error_estimador.py [wm] [psi] [iq]
      sin argumentos usa el punto de operacion medido en L100_T0.
"""
import sys, math, cmath

Lm, Lr, Rr, p = 0.0354, 0.040873, 0.6258, 2
TAU_R = Lr / Rr


def analizar(wm, psi_real, iq, Ts=2e-4, verbose=True):
    idd = psi_real / Lm
    w_sl = Lm * iq / (TAU_R * psi_real)
    w_r = p * wm
    w_e = w_r + w_sl
    I = complex(idd, iq)
    cont = Lm * I / (1 + 1j * w_sl * TAU_R)
    disc = (Ts * Lm / TAU_R) * I / (cmath.exp(1j * w_e * Ts) - 1 + Ts / TAU_R - 1j * w_r * Ts)
    amp = 100 * (abs(disc) / abs(cont) - 1)
    des = math.degrees(cmath.phase(disc) - cmath.phase(cont))
    if verbose:
        print(f"  w_r = {w_r:7.2f}   w_sl = {w_sl:6.2f}   w_e = {w_e:7.2f} rad/s"
              f"   (w_e*Ts = {math.degrees(w_e*Ts):.2f} grados por paso)")
        print(f"  |psi| continuo exacto  = {abs(cont):.4f} Wb")
        print(f"  |psi| discreto (Euler) = {abs(disc):.4f} Wb")
        print(f"  el estimador amplifica {amp:+.2f} %  y desfasa {des:+.2f} grados")
    return amp, des


def main():
    if len(sys.argv) >= 4:
        wm, psi, iq = map(float, sys.argv[1:4])
    else:
        wm, psi, iq = 92.957, 0.5159, 38.89
        print("(punto de operacion de L100_T0, con el flujo deducido de Te e |i_s|)\n")
    print("=== error del estimador a Ts = 200 us ===")
    amp, des = analizar(wm, psi, iq)

    print("\n=== como escala con Ts ===")
    print(f"{'Ts [us]':>9}{'amplificacion [%]':>20}{'desfase [grados]':>19}")
    for ts in (200e-6, 100e-6, 50e-6, 20e-6, 10e-6):
        a, d = analizar(wm, psi, iq, ts, verbose=False)
        print(f"{ts*1e6:>9.0f}{a:>20.2f}{d:>19.2f}")

    print("\nLectura. El error escala casi lineal con Ts, asi que es testeable:")
    print("bajar Ts_ctrl y ver si el residuo se achica en la misma proporcion.")
    print("Si no se achica, el estimador no es la causa y hay que buscar en otro lado.")
    print("\nOJO con sobreinterpretar el signo del desfase antes de tener el flujo")
    print("del bus: el angulo 'medido' hasta ahora sale de proyectar la corriente")
    print("sobre el flujo ESTIMADO, que es justamente lo que esta en duda.")


if __name__ == '__main__':
    main()
