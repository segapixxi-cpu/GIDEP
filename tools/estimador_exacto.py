#!/usr/bin/env python3
"""Crea las variantes *_EX: el estimador de flujo con discretizacion exacta.

El modelo de corriente en alfa-beta, en complejo, es
    dpsi/dt = A*psi + (Lm/tau_r)*i,     A = -1/tau_r + j*omega_r
Con i y omega_r constantes en el paso (ZOH), la solucion exacta es
    psi(k+1) = Phi*psi(k) + G*Lm*i(k)
    Phi = exp(A*Ts),   G = (Phi - 1)/(A*tau_r)
en lugar de Euler explicito, psi(k+1) = psi(k) + Ts*dpsi(k).

Se reemplaza en los DOS estimadores, que son copias: MATLAB Function8
(chart_40, el que usa el control) y MATLAB Function9 (chart_61, el que
escribe psi_log). Si se cambiara solo el primero, psi_log seguiria
mostrando el de Euler.

Prediccion en regimen, con el punto de operacion de L100_T0: el error de
Euler (-6,69 grados, +4,1 %) baja a -1,29 grados y 0,0 %. Lo que queda es
medio paso: la corriente gira w_e*Ts = 2,6 grados dentro del paso y ZOH
la toma quieta.

Uso:  python tools/estimador_exacto.py
Deja DMC_FCSMPC_IM_Physical_v6_3_<variante>_EX.slx al lado de cada variante.
"""
import os, sys, zipfile

VARIANTES = ['L100_T0', 'L0_T0', 'L100_T1', 'L0_T1', 'L10_T0', 'L1_T0']
CHARTS = ['simulink/stateflow/chart_40.xml', 'simulink/stateflow/chart_61.xml']

EULER = """    dpsi_a = (-psi_a + Lm*i_alpha)/tau_r - omega_r*psi_b;
    dpsi_b = (-psi_b + Lm*i_beta )/tau_r + omega_r*psi_a;

    psi_a_next = psi_a + Ts_ctrl*dpsi_a;
    psi_b_next = psi_b + Ts_ctrl*dpsi_b;"""

EXACTO = """    % Discretizacion exacta (ZOH sobre i), no Euler explicito:
    %   psi(k+1) = Phi*psi(k) + G*Lm*i(k)
    %   Phi = exp(A*Ts),  G = (Phi-1)/(A*tau_r),  A = -1/tau_r + j*omega_r
    ea = exp(-Ts_ctrl/tau_r);
    Phi_re = ea*cos(omega_r*Ts_ctrl);
    Phi_im = ea*sin(omega_r*Ts_ctrl);
    den_A = (1.0/tau_r)^2 + omega_r^2;
    G_re = (-(Phi_re - 1.0)/tau_r + Phi_im*omega_r)/(den_A*tau_r);
    G_im = (-Phi_im/tau_r - (Phi_re - 1.0)*omega_r)/(den_A*tau_r);

    psi_a_next = Phi_re*psi_a - Phi_im*psi_b + Lm*(G_re*i_alpha - G_im*i_beta);
    psi_b_next = Phi_im*psi_a + Phi_re*psi_b + Lm*(G_im*i_alpha + G_re*i_beta);"""


def main():
    for v in VARIANTES:
        src = f'DMC_FCSMPC_IM_Physical_v6_3_{v}.slx'
        dst = f'DMC_FCSMPC_IM_Physical_v6_3_{v}_EX.slx'
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst + '.tmp', 'w') as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename in CHARTS:
                    txt = data.decode('utf-8')
                    if txt.count(EULER) != 1:
                        sys.exit(f'{src}: {item.filename} no tiene el bloque de Euler esperado')
                    data = txt.replace(EULER, EXACTO).encode('utf-8')
                zout.writestr(item, data)
        os.replace(dst + '.tmp', dst)
        print(f'{dst}: estimador exacto en chart_40 y chart_61')


if __name__ == '__main__':
    main()
