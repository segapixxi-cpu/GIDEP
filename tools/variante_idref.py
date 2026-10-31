#!/usr/bin/env python3
"""Crea variantes con otro id_ref_final, a partir de una familia existente.

id_ref_final vive solo en MATLAB Function8 (chart_40); los demas charts no
lo usan. Se cambia esa linea y nada mas.

Uso:  python tools/variante_idref.py <sufijo_origen> <sufijo_destino> <id_ref>
      python tools/variante_idref.py _EX _EX28 28
Deja DMC_FCSMPC_IM_Physical_v6_3_<variante><sufijo_destino>.slx.
"""
import os, re, sys, zipfile

VARIANTES = ['L100_T0', 'L0_T0', 'L100_T1', 'L0_T1', 'L10_T0', 'L1_T0']
CHART = 'simulink/stateflow/chart_40.xml'
LINEA = re.compile(r'(    id_ref_final = )[0-9.]+(;)')


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    origen, destino, id_ref = sys.argv[1], sys.argv[2], float(sys.argv[3])
    for v in VARIANTES:
        src = f'DMC_FCSMPC_IM_Physical_v6_3_{v}{origen}.slx'
        dst = f'DMC_FCSMPC_IM_Physical_v6_3_{v}{destino}.slx'
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst + '.tmp', 'w') as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == CHART:
                    txt, n = LINEA.subn(rf'\g<1>{id_ref:.1f}\g<2>', data.decode('utf-8'))
                    if n != 1:
                        sys.exit(f'{src}: no encontre una unica linea id_ref_final')
                    data = txt.encode('utf-8')
                zout.writestr(item, data)
        os.replace(dst + '.tmp', dst)
        print(f'{dst}: id_ref_final = {id_ref:.1f}')


if __name__ == '__main__':
    main()
