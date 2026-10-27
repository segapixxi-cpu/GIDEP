#!/usr/bin/env python3
"""Compara las corridas del experimento factorial lambda_sw x adelanto.

El hecho a explicar: psi_r medido da 0.5509 Wb, muy por encima de los
Lm*id_ref = 0.354 Wb que pide el control. Hay dos hipotesis sobre la causa,
y NO son excluyentes: pueden ser las dos, una sola, o ninguna.

  H1  lambda_sw = 100 penaliza tanto la conmutacion que el MPC deja de seguir
      la referencia de corriente; ese error mete corriente de mas en el eje
      de magnetizacion.                        Se prueba bajando lambda_sw.

  H2  theta_psi no se adelanta un paso, asi que la referencia se genera con
      el angulo que el flujo tenia en k y no con el que tendra en k+1, que es
      cuando se compara.                       Se prueba con la variante T1.

Por eso el diseno es factorial. La celda con LAS DOS corregidas (L0_T1) es la
que permite decir si queda algo sin explicar:

     lambda_sw \ adelanto |   no (T0)      si (T1)
     ---------------------+---------------------------
     100 (como esta)      |   L100_T0      L100_T1
     0   (sin penaliz.)   |   L0_T0        L0_T1

Lecturas posibles de la celda L0_T1:
  psi_r cerca de 0.354  -> entre las dos explican el fenomeno; las celdas
                           individuales dicen cuanto aporta cada una.
  psi_r lejos de 0.354  -> falta una causa que no esta en ninguna hipotesis.

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
    r['adel'] = float(np.asarray(mat['adelanto']).flat[0]) if 'adelanto' in mat else 0.0
    # el nombre puede venir envuelto en varias capas de ndarray de objetos
    v = mat.get('variante')
    while isinstance(v, np.ndarray) and v.size >= 1:
        v = v.flat[0]
    r['var'] = str(v) if isinstance(v, str) else r['archivo'][8:-4]

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
    ph = serie(mat, 'phir_log')
    if ph and ph[1].shape[1] >= 2:
        # modulo del flujo rotorico real: invariante al marco, asi que no
        # importa el orden de las columnas ni que esten en marco rotor
        r['phir'] = float(np.hypot(ph[1][mk, 0], ph[1][mk, 1]).mean())

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

    # Tercera via, independiente del estimador Y del bus: resolver
    #   Te = 1.5*p*kr*Lm*id*iq  y  |i_s|^2 = id^2+iq^2
    # con el valor eficaz de las corrientes. Sirve de control cruzado.
    if im and 'Te' in r:
        I = im[1][mk]
        Ipk = math.sqrt(2.0/3.0 * np.mean(I[:,0]**2 + I[:,1]**2 + I[:,2]**2))
        K = 1.5 * p * KR * Lm
        prod, S = r['Te'] / K, Ipk**2
        disc = S*S - 4*prod*prod
        if disc > 0:
            idv = math.sqrt((S - math.sqrt(disc)) / 2)
            r['psi_ded'] = Lm * idv
    return r


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else '.'
    a, b = VENTANA
    ORDEN = ['L100_T0', 'L10_T0', 'L1_T0', 'L0_T0', 'L100_T1', 'L0_T1']
    rutas = glob.glob(os.path.join(carpeta, 'barrido_L*.mat'))
    def pos(x):
        n = os.path.basename(x)[8:-4]
        return ORDEN.index(n) if n in ORDEN else 99
    rutas.sort(key=pos)
    if not rutas:
        sys.exit(f"No encontre barrido_L*.mat en {carpeta}. "
                 f"Correr antes: matlab -batch \"addpath('tools'); barrido_lambda\"")

    res = [x for x in (analizar(r, a, b) for r in rutas) if x]
    print(f"=== BARRIDO DE lambda_sw, ventana {a}-{b} s ===\n")

    filas = [
        ('lambda_sw',        'lambda',  '{:8.0f}'),
        ('adelanto theta',   'adel',    '{:8.0f}'),
        ('psi_r est [Wb]',   'psi',     '{:8.4f}'),
        ('psi_r REAL [Wb]',  'phir',    '{:8.4f}'),
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
    print(' ' * w + ''.join(f"{r['var']:>10}" for r in res))
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

    # ---- control cruzado de las tres fuentes de flujo ----
    print("\n--- de donde sale el flujo, y si las fuentes concuerdan ---")
    print(f"  {'celda':<10}{'estimador':>11}{'deducido':>11}{'bus maquina':>13}{'veredicto':>28}")
    confiable = None
    for r in res:
        e, d, b = r.get('psi'), r.get('psi_ded'), r.get('phir')
        def f(x): return f"{x:11.4f}" if x is not None else ' ' * 11
        nota = ''
        if b is not None and d is not None:
            dif_bd = 100 * abs(b - d) / d
            dif_be = 100 * abs(b - e) / e if e else None
            if dif_bd < 12:
                nota = 'bus y deducido concuerdan'
                if confiable is None: confiable = True
                if dif_be is not None and dif_be > 12:
                    nota = f'EL ESTIMADOR SE DESVIA {dif_be:.0f} %'
            else:
                nota = f'bus vs deducido: {dif_bd:.0f} % <-- SOSPECHOSO'
                confiable = False
        elif d is not None and e:
            nota = f'sin bus; est vs ded {100*abs(e-d)/d:.0f} %'
        print(f"  {r['var']:<10}{f(e)}{f(d)}{f(b):>13}{nota:>28}")
    if confiable is False:
        print("\n  PARAR ACA. El flujo del bus no concuerda con el deducido de Te e |i_s|.")
        print("  Antes de interpretar nada, revisar que phir_log sea lo que creemos:")
        print("    - orden de las columnas y nombres de las senales del bus,")
        print("    - unidades (Wb contra V*s), y si hay algun factor de escala,")
        print("    - ReferenceFrame = Rotor: el MODULO es invariante al marco, asi que")
        print("      si el modulo no cierra, el problema no es el marco.")
        print("  Si la lectura resulta correcta, entonces falla el otro lado: el deducido")
        print("  supone regimen permanente y los parametros de la chapa. Revisar que la")
        print("  ventana este realmente en regimen antes de dudar del bus.")
        print("  Un veredicto calculado sobre una lectura mala se parece a un resultado.")
        return

    print("\n--- veredicto ---")
    por = {r['var']: r for r in res}
    base, h1, h2, ambas = (por.get('L100_T0'), por.get('L0_T0'),
                           por.get('L100_T1'), por.get('L0_T1'))

    def psi(r):
        # si esta el flujo real de la maquina se usa ese; si no, el estimado
        if not r: return None
        return r.get('phir', r.get('psi'))

    usa_real = any('phir' in r for r in res)
    print("Flujo usado para el veredicto: " +
          ("REAL, del bus de la maquina (phir_log)" if usa_real
           else "ESTIMADO (psi_log). Ojo: sale del mismo modelo que usa el control."))

    falta = [n for n, r in (('L100_T0', base), ('L0_T0', h1),
                            ('L100_T1', h2), ('L0_T1', ambas)) if psi(r) is None]
    if falta:
        print("Faltan corridas del factorial: " + ", ".join(falta))
        print("Sin las cuatro celdas no se puede separar una hipotesis de la otra,")
        print("ni detectar si queda algo sin explicar. Correr:")
        print('    matlab -batch "addpath(\'tools\'); barrido_lambda"')
        return

    p0, pH1, pH2, pA = psi(base), psi(h1), psi(h2), psi(ambas)
    exceso = p0 - PSI_PRED
    print(f"exceso a explicar: psi_r({p0:.4f}) - Lm*id_ref({PSI_PRED:.4f}) = {exceso:+.4f} Wb\n")

    MIN_EXCESO = 0.02
    if abs(exceso) < MIN_EXCESO:
        print(f"NO HAY NADA QUE EXPLICAR: el flujo ya esta a menos de {MIN_EXCESO} Wb de")
        print("Lm*id_ref. El control hace lo que dice hacer.")
        print("Si esto aparecio recien al medir el flujo del bus en vez del estimado,")
        print("entonces el problema nunca estuvo en el control: estaba en el estimador,")
        print("y lo que hay que revisar es por que psi_log se desvia tanto.")
        return
    if exceso < 0:
        print("EL FLUJO QUEDA POR DEBAJO de Lm*id_ref, no por encima. Se invirtio el")
        print("signo del fenomeno respecto de lo que veniamos discutiendo.")
        print("Las dos hipotesis estaban pensadas para explicar un EXCESO de flujo:")
        print("ninguna aplica. Revisar primero la lectura del flujo y el punto de")
        print("operacion antes de buscar causas.")
        return
    print(f"  {'celda':<10}{'psi_r':>9}{'exceso':>9}{'explica':>10}")
    for n, r in (('L100_T0', base), ('L0_T0', h1), ('L100_T1', h2), ('L0_T1', ambas)):
        e = psi(r) - PSI_PRED
        cuanto = '' if n == 'L100_T0' else f"{100*(1-e/exceso):9.0f} %"
        print(f"  {n:<10}{psi(r):9.4f}{e:+9.4f}{cuanto:>10}")

    tol = 0.02
    q1 = 1 - (pH1 - PSI_PRED) / exceso if exceso else 0     # cuanto explica H1 sola
    q2 = 1 - (pH2 - PSI_PRED) / exceso if exceso else 0     # cuanto explica H2 sola
    qA = 1 - (pA - PSI_PRED) / exceso if exceso else 0      # cuanto explican juntas
    print()
    for nom, q, desc in (('H1 (lambda_sw)', q1, 'seguimiento degradado por la penalizacion'),
                         ('H2 (adelanto)',  q2, 'referencia generada con el angulo de k')):
        q = max(min(q, 2.0), -2.0)
        if q > 0.8:   v = "explica casi todo"
        elif q > 0.3: v = "aporta una parte"
        elif q > 0.05:v = "aporta poco"
        elif q < -0.05: v = "EMPEORA: mueve el flujo en sentido contrario"
        else:         v = "no explica nada"
        print(f"  {nom:<16} {100*q:6.0f} %  -> {v}   ({desc})")

    print()
    if abs(pA - PSI_PRED) < tol:
        print(f"Las dos juntas dejan psi_r en {pA:.4f} Wb, a menos de {tol} de Lm*id_ref.")
        print("No queda nada por explicar: el fenomeno esta cubierto por H1 y H2.")
        if q1 + q2 > 1.3:
            print("Se solapan: los aportes individuales suman mas que el efecto conjunto,")
            print("asi que las dos actuan sobre el mismo mecanismo.")
    else:
        print(f"ATENCION: con las dos corregidas psi_r queda en {pA:.4f} Wb, todavia")
        print(f"a {pA-PSI_PRED:+.4f} Wb de Lm*id_ref = {PSI_PRED:.4f}.")
        print("NINGUNA de las dos hipotesis, ni su suma, explica el fenomeno completo.")
        print("Hay una tercera causa. Candidatas a revisar antes de seguir:")
        print("  - el estimador usa Euler explicito con Ts=200 us: a w_e~222 rad/s eso es")
        print("    2.5 grados por paso y amplifica el modulo (|1+jwTs| > 1).")
        print("  - el MPC excluye los tres estados cero (7, 17, 27): sin vector nulo, la")
        print("    unica forma de 'no hacer nada' es repetir estado.")
        print("  - el modelo de prediccion del MPC contra la planta Simscape real.")

    wA = ambas.get('wm')
    if wA is not None:
        print(f"\nvelocidad con las dos corregidas: {wA:.2f} rad/s "
              f"(predicho por el hallazgo 1: {W_PRED:.2f}, referencia: {W_REF})")
        if abs(wA - W_PRED) < 3:
            print("El hallazgo 1 (subfluxado) queda vigente: estaba enmascarado.")
        elif wA > W_PRED + 3:
            print("El motor sigue llegando mas alto que lo predicho: el hallazgo 1 tampoco")
            print("se confirma con el control corregido. Revisar el balance de par.")


if __name__ == '__main__':
    main()
