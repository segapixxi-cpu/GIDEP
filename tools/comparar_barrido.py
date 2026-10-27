#!/usr/bin/env python3
"""Compara las corridas del barrido de lambda_sw.

Pregunta que responde: lambda_sw = 100 penaliza tanto la conmutacion que el
MPC deja de seguir la referencia de corriente, y ese error de seguimiento mete
corriente de mas en el eje de magnetizacion, subiendo psi_r por encima de
Lm*id_ref = 0.354 Wb. Si la hipotesis es correcta, al bajar lambda_sw deberia:

  1. subir la frecuencia de conmutacion,
  2. bajar el error |i_ref - i|,
  3. bajar psi_r hacia 0.354 Wb,
  4. y recien ahi aparecer el estancamiento de velocidad en ~86.6 rad/s
     que predice el hallazgo 1.

Uso:  python3 tools/comparar_barrido.py [carpeta]
Lee barrido_L*.mat generados por tools/barrido_lambda.m
"""
import sys, glob, os, math
import numpy as np
from scipy.io import loadmat

Lm, Lr, Rr, p, F = 0.0354, 0.040873, 0.6258, 2, 0.005879
KR = Lm / Lr
ID_REF, IQ_MAX, W_REF = 10.0, 50.0, 95.0
TS_CTRL = 2e-4
VENTANA = (1.0, 2.0)
PSI_NOM = (380 / math.sqrt(3)) * math.sqrt(2) / (2 * math.pi * 50)
PSI_PRED = Lm * ID_REF
W_PRED = (-F + math.sqrt(F * F + 4 * 0.0054 * (1.5 * p * KR * PSI_PRED * IQ_MAX - 5))) / (2 * 0.0054)


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


def amp_abc(Y):
    al = (2 / 3) * (Y[:, 0] - 0.5 * Y[:, 1] - 0.5 * Y[:, 2])
    be = (Y[:, 1] - Y[:, 2]) / math.sqrt(3)
    return al, be


def analizar(ruta, a, b):
    mat = loadmat(ruta, squeeze_me=False, struct_as_record=True)
    r = {'archivo': os.path.basename(ruta)}
    r['lambda'] = float(np.asarray(mat['lambda_sw']).flat[0]) if 'lambda_sw' in mat else float('nan')

    sp = serie(mat, 'speed_log')
    if sp is None:
        return None
    t, SP = sp
    mk = (t >= a) & (t <= b)
    r['n'] = int(mk.sum())
    r['w_ref'] = SP[mk, 0].mean()
    r['wm'] = SP[mk, 1].mean()

    tq = serie(mat, 'torque_log')
    if tq: r['Te'], r['Tm'] = tq[1][mk, 0].mean(), tq[1][mk, 1].mean()
    ps = serie(mat, 'psi_log')
    if ps: r['psi'] = ps[1][mk, 0].mean()

    ir, im = serie(mat, 'iref_log'), serie(mat, 'currents_log')
    if ir and im:
        ra, rb = amp_abc(ir[1][mk]); ma, mb = amp_abc(im[1][mk])
        r['err'] = float(np.hypot(ra - ma, rb - mb).mean())
        r['Ji'] = float((np.hypot(ra - ma, rb - mb) ** 2).mean())
        r['i_ref'] = float(np.hypot(ra, rb).mean())
        r['i'] = float(np.hypot(ma, mb).mean())

    gm = serie(mat, 'gmin_log')
    if gm: r['g_min'] = gm[1][mk, 0].mean()
    ic = serie(mat, 'iqcmd_log')
    if ic:
        v = ic[1][mk, 0]
        r['iq_cmd'] = v.mean()
        r['sat'] = float((np.abs(v) >= IQ_MAX * 0.999).mean())

    if 'Nsw' in mat and 'tsw' in mat:
        ts = np.asarray(mat['tsw'], float).squeeze()
        ns = np.asarray(mat['Nsw'], float).squeeze()
        k = (ts >= a) & (ts <= b)
        r['Nsw'] = float(ns[k].mean())
        r['quieto'] = float((ns[k] == 0).mean())
        r['f_sw'] = float(ns[k].sum() / (b - a) / 3)   # por salida

    if 'psi' in r and 'Te' in r and r['psi'] > 0:
        r['id'] = r['psi'] / Lm
        r['iq'] = r['Te'] / (1.5 * p * KR * r['psi'])
    return r


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else '.'
    a, b = VENTANA
    rutas = sorted(glob.glob(os.path.join(carpeta, 'barrido_L*.mat')),
                   key=lambda x: -float(os.path.basename(x)[9:-4] or 0))
    if not rutas:
        sys.exit(f"No encontre barrido_L*.mat en {carpeta}. "
                 f"Correr antes: matlab -batch \"addpath('tools'); barrido_lambda\"")

    res = [x for x in (analizar(r, a, b) for r in rutas) if x]
    print(f"=== BARRIDO DE lambda_sw, ventana {a}-{b} s ===\n")

    filas = [
        ('lambda_sw',        'lambda',  '{:8.0f}'),
        ('psi_r [Wb]',       'psi',     '{:8.4f}'),
        ('  % del nominal',  None,      None),
        ('wm [rad/s]',       'wm',      '{:8.2f}'),
        ('Te [N.m]',         'Te',      '{:8.2f}'),
        ('|i_ref| [A]',      'i_ref',   '{:8.2f}'),
        ('|i| [A]',          'i',       '{:8.2f}'),
        ('|i_ref - i| [A]',  'err',     '{:8.2f}'),
        ('g_min',            'g_min',   '{:8.1f}'),
        ('iq_cmd [A]',       'iq_cmd',  '{:8.2f}'),
        ('  saturado [%]',   'sat',     None),
        ('Nsw medio',        'Nsw',     '{:8.3f}'),
        ('  sin conmutar[%]','quieto',  None),
        ('f_sw/salida [Hz]', 'f_sw',    '{:8.0f}'),
        ('id real [A]',      'id',      '{:8.2f}'),
        ('iq real [A]',      'iq',      '{:8.2f}'),
    ]
    w = 20
    print(' ' * w + ''.join(f"{r['archivo'][8:-4]:>10}" for r in res))
    print('-' * (w + 10 * len(res)))
    for etiq, key, fmt in filas:
        if key is None:
            if 'nominal' in etiq:
                vals = [f"{100*r['psi']/PSI_NOM:8.1f}" if 'psi' in r else ' ' * 8 for r in res]
            else:
                continue
        elif fmt is None:
            vals = [f"{100*r[key]:8.1f}" if key in r else ' ' * 8 for r in res]
        else:
            vals = [fmt.format(r[key]) if key in r else ' ' * 8 for r in res]
        print(f"{etiq:<{w}}" + ''.join(f"{v:>10}" for v in vals))

    print(f"\nReferencias:  psi nominal = {PSI_NOM:.4f} Wb | "
          f"Lm*id_ref = {PSI_PRED:.4f} Wb | w_eq predicho = {W_PRED:.2f} rad/s | w_ref = {W_REF}")

    print("\n--- veredicto ---")
    r100 = next((r for r in res if r.get('lambda') == 100), None)
    r0 = next((r for r in res if r.get('lambda') == 0), None)
    if r100 and r0 and 'psi' in r100 and 'psi' in r0:
        print(f"psi_r: {r100['psi']:.4f} Wb con lambda=100  ->  {r0['psi']:.4f} Wb con lambda=0 "
              f"(Lm*id_ref = {PSI_PRED:.4f})")
        print(f"wm   : {r100['wm']:.2f} rad/s  ->  {r0['wm']:.2f} rad/s "
              f"(predicho sin error de seguimiento: {W_PRED:.2f})")
        if 'err' in r100 and 'err' in r0:
            print(f"error de seguimiento: {r100['err']:.2f} A  ->  {r0['err']:.2f} A")
        baja_psi = r0['psi'] < r100['psi'] - 0.02
        baja_w = r0['wm'] < r100['wm'] - 1.0
        cerca = abs(r0['psi'] - PSI_PRED) < abs(r100['psi'] - PSI_PRED)
        print()
        if baja_psi and cerca:
            print("HIPOTESIS CONFIRMADA: al quitar la penalizacion de conmutacion el flujo cae")
            print("hacia Lm*id_ref. El flujo de mas venia del error de seguimiento, no de una")
            print("desalineacion del marco de referencia.")
            if baja_w:
                print("Y la velocidad cae, con lo que el hallazgo 1 (subfluxado) queda vigente:")
                print("estaba enmascarado por el mal seguimiento del MPC.")
            else:
                print("Pero la velocidad NO cae: revisar, porque entonces el par alcanza igual.")
        else:
            print("HIPOTESIS NO CONFIRMADA: el flujo no se mueve hacia Lm*id_ref al bajar lambda_sw.")
            print("La causa del flujo extra es otra. Revisar la orientacion del marco (theta_psi).")


if __name__ == '__main__':
    main()
