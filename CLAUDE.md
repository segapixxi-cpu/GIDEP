# DMC + FCS-MPC + Motor de inducción

Modelo Simulink de un convertidor matricial directo (DMC) 3x3 alimentando un motor
de inducción, con control predictivo de corriente de estados finitos (FCS-MPC).

- Archivo: `DMC_FCSMPC_IM_Physical_v6_1_STABLE.slx`
- MATLAB R2021a. Requiere Simulink + Simscape Specialized Power Systems.
- Autor: Eduardo Landoni. Revisión 1.69 al 07/08/2026.

```
matlab -batch "sim('DMC_FCSMPC_IM_Physical_v6_1_STABLE')"
```

## Estructura verificada en el archivo

| Elemento | Ref XML | Qué es |
|---|---|---|
| `MATLAB Function8` | `systems/system_272.xml`, `stateflow/chart_40.xml` | FCS-MPC. Entradas `t,vA,vB,vC,ia,ib,ic,wm`. Salidas `state_idx,g_min,w_ref_out,iq_cmd_out,iq_ref_out,ia_ref_out,ib_ref_out,ic_ref_out` |
| `MATLAB Function9` | `systems/system_287.xml`, `stateflow/chart_61.xml` | Estimador de flujo. 11 salidas, ninguna entra al MPC: monitoreo puro |
| `MATLAB Function1` | `systems/system_225.xml`, `stateflow/chart_25.xml` | Decodificador `state_idx` a 9 compuertas `SAa..SCc` |
| `MATLAB Function10` | `systems/system_298.xml`, `stateflow/chart_86.xml` | Clarke abc→alfa-beta, instrumentación |
| `DMC_Physical_IGBT_Matrix` | `systems/system_306.xml` | 18 IGBT/Diodo = 9 llaves bidireccionales |

Cadena física, con los valores leídos de `system_root.xml`:

| Bloque | Tipo | Valores |
|---|---|---|
| `Fuente de Tensión Trifásica` | Three-Phase Programmable Voltage Source | `PositiveSequence = [380 0 50]` |
| `Three-Phase Series RLC Branch2` | RL serie | R=13,4 mΩ, L=25,9 µH |
| `Three-Phase Parallel RLC Branch` | RL paralelo | R=10 Ω ∥ L=2,3 mH |
| `Three-Phase Series RLC Branch1` | C serie | C=10 µF |
| `Cable Marlew (R)` | R | R=52,5 mΩ |
| `Cable Marlew (L)` | RL paralelo | L=7,95 µH **∥ R=25 Ω** |
| `Asynchronous Machine SI Units1` | máquina | 18,45 kW / 380 V / 50 Hz |

## Parámetros clave, verificados

Motor (`NominalParameters=[1.845e4 380 50]`, `RotorType=Squirrel-cage`, `PolePairs=2`):

```
Rs = 0.5968    Lls = 0.0003495
Rr = 0.6258    Llr = 0.005473
Lm = 0.0354
Mechanical = [J=0.08  F=0.005879  p=2]      SimulateSaturation = off
```

Derivados: `Ls = 35.750 mH`, `Lr = 40.873 mH`, `sigma = 0.1424`.

Control (`stateflow/chart_40.xml`):

```
Ts_ctrl = 2e-4   lambda_sw = 100.0   Imax = 300.0
id_ref_final = 10.0   iq_max = 50.0   Kp_w = 20.0
alpha_iq = 0.05   w_ref_final = 95.0
```

Carga (`Add1` de tres entradas `+++`, `Saturation1` a [0, 100000]):
`Tm = 5 (Step3) + 0.0054*wm^2 (Gain1) + 0 (Step2)`. Sumado a `F*wm` de la máquina.

Solver (`configSet0.xml`): `StartTime=0`, `StopTime=4`, `FixedStep=1e-6`,
`SignalLogging=on`, `LoggingToFile=off`, `LoggingFileName=out.mat`, `SaveFormat=Dataset`.

## Hallazgos, por prioridad

### 1. BLOQUEANTE — subfluxado. CONFIRMADO analíticamente

`id_ref_final = 10.0` verificado en `chart_40.xml`. Con orientación a flujo rotórico:

```
psi_r = Lm*id                  = 0.354 Wb
psi nominal ~ (380/raiz3)*raiz2/(2*pi*50) = 0.988 Wb   ->  id_nom = 27.9 A
Te_max = 1.5*p*(Lm/Lr)*psi_r*iq_max                    = 45.99 N.m
Tm(95) = 5 + 0.0054*95^2 = 53.73, + F*95 = 0.56        = 54.29 N.m
```

Punto de equilibrio con `Te = Te_max` resolviendo `0.0054*w^2 + F*w + 5 = 45.99`:
**w_eq = 86.58 rad/s**, con `iq_ref` saturado en 50 A de forma permanente.
El valor de 86,6 rad/s solo cierra si se incluye la fricción viscosa `F = 0.005879`,
que está en `Mechanical` y no siempre se tiene en cuenta.

El límite de 0,866 del DMC no es lo que bloquea. A 95 rad/s con flujo nominal:
`id=27.9 A`, `iq=21.2 A`, `w_slip=11.6 rad/s`, `w_e=201.6 rad/s` (32,1 Hz),
tensión requerida **273 V de línea rms** contra **329 V** disponibles (0,866·380).
Margen del 17 %. La conclusión se sostiene: sobra tensión, falta flujo.

Corrección propuesta: `id_ref_final` de 10 a 25-28 A.
PENDIENTE: verificar con `out.mat` antes de tocar nada.

### 2. Fuente programable con variación de frecuencia ACTIVA. CONFIRMADO

```
VariationEntity = Frequency    VariationType = Step
VariationMagnitude = 0.3       VariationTiming = [2 4]
```

Escalón de +0,3 pu sobre 50 Hz, o sea 50→65 Hz, entre t=2 s y t=4 s. Con `StopTime=4`,
la única ventana de régimen permanente limpio es **1 s a 2 s**. Verificar si es intencional.

### 3. Filtro de entrada, margen fino

`f_res = 1/(2*pi*sqrt(L*C))` con L=2,3 mH y C=10 µF da **1049 Hz**; incluyendo los
25,9 µH de la fuente (L=2,3259 mH) da **1044 Hz**. Contra el espectro de banda ancha del
FCS-MPC con Ts=200 µs, que llega a 2,5 kHz. Opciones: bajar Ts, subir C a 30-40 µF,
o amortiguamiento activo en la función de costo. El reactor ya trae `R=10 Ω` en paralelo.

### 4. powergui en 60 Hz siendo la red de 50 Hz. CONFIRMADO

`frequency = 60` y `fundamental = 60` en el bloque `powergui`, con
`SimulationMode=Discrete`, `SampleTime=1e-6`. No afecta la simulación en el tiempo;
sí invalida FFT, THD y steady-state del powergui.

### 5. Asimetría Llr/Lls. CONFIRMADO

`Llr=5,473 mH` contra `Lls=0,3495 mH`: relación 15,7 a 1, atípica para jaula de ardilla.
Da `sigma = 0,1424` (lo normal sería 0,04-0,08). Planta y control usan los mismos
números, el modelo es autoconsistente, pero no representaría a un motor real.

### 6. Imax = 300 A en el MPC

6 veces la corriente nominal de pico. No protege nada.

### 7. Faltan para pasar a hardware

Circuito de clamp, conmutación en cuatro pasos, pérdidas de conmutación y tensión de
codo en los semiconductores, y capacidad del cable a tierra para evaluar onda reflejada.

### 8. NUEVO — `Cable Marlew (L)` no es una RL serie

Es un **Three-Phase Parallel RLC Branch** tipo RL: los 7,95 µH del cable están en
paralelo con **R = 25 Ω**, no en serie con los 52,5 mΩ. Es un amortiguador sobre la
inductancia del cable. La documentación previa lo describía como "cable 52,5 mΩ + 7,95 µH",
que omite esa resistencia.

## Trampas conocidas

Rótulos de scopes, rastreados línea por línea en `system_root.xml`:

| Scope | Qué muestra realmente |
|---|---|
| `psi` | `Mux4` = `w_ref_out` + `iq_cmd_out`. **NO es flujo** |
| `psi r abs` | `MATLAB Function8.iq_ref_out`. **NO es flujo** |
| `psi t abs` | `MATLAB Function9.psi_r_abs`. **Este sí es el módulo de flujo** |
| `psi alpha beta` | `Mux1` = `psi_r_alpha` + `psi_r_beta`. Correcto |
| `theta psi` | `MATLAB Function9.theta_psi`. Correcto |
| `gmin` | `MATLAB Function8.g_min`. Correcto |
| `Scope9` | `Mux3` = `pred_err_alpha/beta/abs` |
| `ip alpha` / `ip beta` | predicho (`Function9`) contra medido (`Function10`), superpuestos |
| `i_ref/i` | `Mux5` = `ia/ib/ic_ref_out` contra `From<ia/ib/ic>` |
| `vo alpha beta` | `Mux` = `vo_alpha` + `vo_beta` |
| `wm1` / `Te1` / `current1` | del `Bus Selector1` de la máquina |

Otras:

- `Cage1 = [0.4155 0.002066]` y `Cage2 = [0.4168 0.0003495]` están cargados pero
  INACTIVOS: `RotorType = Squirrel-cage`, no doble jaula. No es un desajuste con el MPC.
- `Pmec = 1.492e6` y `LoadFlowParameters = 1492000` son incoherentes con la chapa de
  18,45 kW, pero solo los usa la herramienta de Load Flow. Inofensivo.
- `Saturation` trae una tabla cargada pero `SimulateSaturation = off`.

## Cómo trabajar acá

- El `.slx` es un ZIP con XML adentro. Se puede inspeccionar y editar sin MATLAB:
  `unzip -q DMC_..._STABLE.slx -d /tmp/slx`. El grueso está en
  `simulink/systems/system_root.xml` y `simulink/stateflow/chart_*.xml`.
- Antes de afirmar rutas, nombres de bloque o parámetros: verificarlos en el archivo.
  No suponer.
- Para analizar un `out.mat` ya generado: `python3 tools/analizar_out.py out.mat`.
  No requiere MATLAB, solo `scipy`.
- Respuestas cortas, itemización numérica, sin viñetas. Español rioplatense.

## Entorno

Este repo se trabaja tanto desde Claude Code local como desde sesiones remotas.
En una sesión remota **no hay MATLAB**: se puede editar el `.slx` y analizar un
`out.mat` subido al repo, pero no correr la simulación. Para el ciclo completo
(editar, simular, analizar en una sola vuelta) hace falta Claude Code corriendo
en la misma máquina donde está instalado MATLAB, con `matlab` en el PATH.
