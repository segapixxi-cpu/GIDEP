# Por qué el motor no llega a la velocidad de referencia

**Modelo:** `DMC_FCSMPC_IM_Physical_v6_3_STABLE.slx`
**Autor:** Eduardo Landoni
**Para:** quien se esté metiendo con este modelo por primera vez

Este apunte explica, desde cero, por qué el motor de este modelo se queda
en unos 86,6 rad/s cuando le pedimos 95. La conclusión es que está
**subfluxado**. Lo que sigue es el razonamiento completo, para que puedas
seguirlo y, sobre todo, para que puedas discutirlo.

---

## 1. De dónde sale el par en un motor de inducción

1. Un motor de inducción hace fuerza por la interacción de dos cosas: un
   **campo magnético** (el flujo, `psi_r`) y una **corriente** que circula
   perpendicular a ese campo. Si falta cualquiera de las dos, no hay par.

2. La cuenta es casi tan simple como suena:

   ```
   Te = 1,5 · p · (Lm/Lr) · psi_r · iq
   ```

   donde `psi_r` es el flujo y `iq` la corriente que produce par. `p`, `Lm`
   y `Lr` son constantes del motor: no las podés cambiar.

3. La analogía que uso para explicarlo: **el flujo es el largo de la palanca
   y la corriente es la fuerza que hacés**. Si la palanca es corta, por más
   fuerza que metas, el torque es poco.

---

## 2. Cómo se controla cada una por separado

4. El truco del control vectorial, que es lo que hace nuestro FCS-MPC, es
   partir la corriente del estator en dos partes independientes.

5. **`id`** es la corriente que **magnetiza**, la que arma el flujo:
   `psi_r = Lm · id`. Es la que fabrica la palanca.

6. **`iq`** es la corriente que **produce par**. Es la fuerza sobre la palanca.

7. En el modelo esos dos valores son `id_ref` e `iq_ref`, y viven en
   `chart_40.xml`, dentro del `.slx`.

---

## 3. Acá está el problema

8. El control tiene `id_ref = 10 A`. Con `Lm = 0,0354 H`:

   ```
   psi_r = 0,0354 · 10 = 0,354 Wb
   ```

9. ¿Cuánto debería ser? El flujo nominal lo fija la chapa del motor,
   380 V a 50 Hz:

   ```
   psi_nominal = (380/√3) · √2 / (2π · 50) = 0,988 Wb
   ```

10. O sea: estamos trabajando con el **36 % del flujo** que el motor puede
    tener. La palanca está a poco más de un tercio de su largo. Para llegar
    al flujo nominal harían falta `id ≈ 27,9 A`, casi tres veces más.

11. A eso se le dice **motor subfluxado**.

---

## 4. Qué pasa cuando la carga pide más par

12. Con ese flujo chico, el par máximo que el motor puede dar es el que sale
    cuando `iq` llega a su tope, que en el control es `iq_max = 50 A`:

    ```
    Te_max = 1,5 · 2 · (0,0354/0,040873) · 0,354 · 50 = 45,99 N·m
    ```

13. Ahora mirá lo que le pedimos. La carga es un ventilador, que crece con
    el cuadrado de la velocidad:

    ```
    Tm = 5 + 0,0054 · wm²
    ```

14. A la velocidad que queremos, 95 rad/s:

    ```
    Tm = 5 + 0,0054 · 95² = 53,73 N·m
    ```

    Más la fricción viscosa del propio motor (`F · wm = 0,005879 · 95 = 0,56`),
    total **54,29 N·m**.

15. Y acá está todo el asunto: **el motor puede dar 46 N·m y la carga pide
    54 N·m**. No alcanza. No hay vuelta.

---

## 5. Por qué se queda justo en 86,6 rad/s

16. El motor acelera mientras el par que entrega sea mayor que el que pide
    la carga. Como la carga crece con la velocidad al cuadrado, en algún
    punto las dos curvas se cruzan. Ese cruce es donde se queda.

17. Planteás la igualdad y resolvés la cuadrática:

    ```
    0,0054 · w² + 0,005879 · w + 5 = 45,99   →   w = 86,58 rad/s
    ```

18. Ese es el estancamiento. El lazo de velocidad ve que falta velocidad,
    pide más `iq`, pero `iq` ya está clavado en su tope de 50 A. **Satura y
    se queda ahí para siempre.** No es una oscilación ni un transitorio
    largo: es el equilibrio del sistema.

> **Detalle fino, que vale la pena.** Ese 86,58 solo cierra si incluís la
> fricción viscosa `F = 0,005879` que está en el parámetro `Mechanical` de
> la máquina. Si la ignorás te da 87,12. Son medio rad/s, pero la diferencia
> entre un modelo que cierra y uno que "casi" cierra suele estar justo ahí.

---

## 6. Por qué NO es culpa del convertidor matricial

19. Un convertidor matricial tiene una limitación conocida: solo puede
    entregar hasta el **86,6 %** de la tensión de entrada. Es tentador
    echarle la culpa a eso. Pero la cuenta dice que no.

20. Si corrigiéramos el flujo y lleváramos el motor a 95 rad/s con `psi`
    nominal, haría falta:

    ```
    id = 27,9 A    iq = 21,2 A    w_slip = 11,6 rad/s    w_e = 201,6 rad/s (32,1 Hz)
    tensión requerida ≈ 273 V de línea rms
    ```

    Y el convertidor nos da `0,866 · 380 = 329 V`.

21. **Sobra un 17 % de tensión.** El cuello de botella no es el convertidor:
    es el flujo que nosotros mismos fijamos bajo.

---

## 7. La corrección propuesta

22. Subir `id_ref` de 10 A a algo entre **25 y 28 A**. Eso lleva el flujo
    cerca del nominal, alarga la palanca, y con eso el mismo `iq` de 50 A
    daría del orden de 128 N·m, muy por encima de los 54 que pide la carga.

23. **Pero no lo tocamos todavía**, y esta es la parte importante del método:
    el cálculo cierra en el papel, pero el papel siempre asume cosas. Antes
    de cambiar un parámetro hay que ver los datos de la simulación real y
    confirmar que la máquina se comporta como predijo la cuenta. Si cambiás
    primero y mirás después, nunca sabés si entendiste el problema o le
    pegaste de casualidad.

---

## 8. Qué aporta la versión 6.3

24. La v6.1 no guardaba los datos en ningún lado: se podía simular, pero no
    había manera de leer los números después. La v6.3 agrega **nueve bloques
    `To Workspace`**, que escriben las señales a la memoria de MATLAB para
    poder analizarlas. Esa era exactamente la pieza que faltaba.

25. La v6.3 **no cambió el control**: `id_ref` sigue en 10 A, y las cuatro
    MATLAB Function tienen el código idéntico, línea por línea. Lo único que
    cambió en el código del MPC es `lambda_sw = 100.0` escrito ahora como
    `100`, que es el mismo número. Lo que se agregó es instrumentación.

---

## 9. Dos arreglos que se le hicieron a la v6.3

26. **Decimación.** Esos bloques guardaban una muestra cada microsegundo, sin
    límite: 3 millones de puntos por señal, del orden de **1 GB de memoria**.
    Se les puso `Decimation = 200`, o sea guardar uno de cada 200: quedan
    15.000 puntos por señal, unos 5 MB, y para ver velocidad y par sobra.
    Es como filmar a 1000 cuadros por segundo algo que alcanza con ver a 5.

27. **Falta el flujo.** Entre las nueve señales no estaba `psi_r`, que es
    justamente lo que estamos discutiendo. Se agregó un décimo `To Workspace`
    llamado `psi_log`, que toma `psi_r_abs` de `MATLAB Function9`, para
    **medirlo directamente en vez de inferirlo**.

---

## 10. Cómo verificarlo vos mismo

28. Abrí el modelo y simulá. Después, desde la carpeta del proyecto:

    ```
    python3 tools/analizar_out.py out.mat
    ```

29. El script lee el `.mat` sin necesidad de MATLAB y te contesta cuatro cosas:

    | Qué mira | Qué esperamos ver |
    |---|---|
    | `psi_r` medido | ≈ 0,354 Wb, el 36 % del nominal |
    | `wm` de régimen | ≈ 86,6 rad/s, contra los 95 pedidos |
    | `\|i_ref\|` | clavado en 50,99 A el 100 % del tiempo |
    | `Te` contra la carga | ≈ 46 N·m contra 54,29 pedidos |

30. El script calcula `iq` **por dos caminos independientes**: uno desde la
    amplitud de las corrientes de referencia, otro desde `Te` y `psi_r`
    medidos. Si los dos dan lo mismo, el modelo es internamente consistente
    y podemos confiar en la medición. Si dan distinto, hay algo que no
    entendimos y conviene frenar antes de seguir.

31. **Importante: analizá solo entre 1 y 2 segundos.** La fuente programable
    tiene activo un escalón de frecuencia de 50 a 65 Hz a partir de t = 2 s,
    y el modelo corre hasta t = 3 s. Esa es la única ventana de régimen
    permanente limpio.

---

## 11. Una trampa del modelo que te va a morder

32. Varios scopes tienen el rótulo equivocado, heredado de versiones viejas.
    Si mirás el que dice `psi` creyendo que ves flujo, vas a sacar conclusiones
    sobre otra cosa:

    | Scope | Qué muestra **realmente** |
    |---|---|
    | `psi` | `w_ref` e `iq_cmd`. **No es flujo** |
    | `psi r abs` | `iq_ref`. **No es flujo** |
    | `psi t abs` | `psi_r_abs`. **Este sí es el flujo** |

33. Moraleja general, que vale para cualquier modelo que heredes: **el rótulo
    no es el dato**. Antes de creerle a un gráfico, rastreá de dónde viene la
    señal. En este caso eso se hace leyendo las líneas en
    `simulink/systems/system_root.xml` dentro del `.slx`.
