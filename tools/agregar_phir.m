function agregar_phir(cuales)
% Agrega el flujo rotorico REAL de la maquina a las variantes del barrido.
%
% El Bus Selector1 extraia solo wm, is_c, is_b, is_a y Te. Se le agregan, al
% final para no mover los puertos 1 a 5 ya cableados:
%
%   6  Rotor measurements.Rotor flux phir_q (V s)   -> phir_log, columna 1
%   7  Rotor measurements.Rotor flux phir_d (V s)   -> phir_log, columna 2
%   8  Mechanical.Rotor angle thetam (rad)          -> marco_log, columna 1
%   9  Stator measurements.Stator current  is_q (A) -> marco_log, columna 2
%  10  Stator measurements.Stator current is_d (A)  -> marco_log, columna 3
%
% Los nombres son los que devuelve get_param(...,'InputSignals') en R2021a,
% incluidos los dobles espacios de "Rotor current  iq" y "Stator current  is_q".
%
% marco_log existe para el angulo absoluto: con ReferenceFrame = Rotor las
% componentes dq estan en marco rotor y hay que rotarlas por p*thetam. is_q e
% is_d estan en el mismo marco, y como ia/ib/ic ya se loguean, permiten
% verificar la convencion de Park con datos en vez de suponerla.
%
% Uso, desde la carpeta del proyecto:
%     matlab -batch "addpath('tools'); agregar_phir"
% Es idempotente: si la variante ya tiene phir_log, la saltea.

if nargin < 1 || isempty(cuales)
    cuales = {'L100_T0', 'L0_T0', 'L100_T1', 'L0_T1', 'L10_T0', 'L1_T0'};
end

nuevas = {'Rotor measurements.Rotor flux phir_q (V s)', ...
          'Rotor measurements.Rotor flux phir_d (V s)', ...
          'Mechanical.Rotor angle thetam (rad)', ...
          'Stator measurements.Stator current  is_q (A)', ...
          'Stator measurements.Stator current is_d (A)'};

for k = 1:numel(cuales)
    m = sprintf('DMC_FCSMPC_IM_Physical_v6_3_%s', cuales{k});
    load_system(m);
    if ~isempty(find_system(m, 'SearchDepth', 1, 'BlockType', 'ToWorkspace', ...
                            'VariableName', 'phir_log'))
        fprintf('%s ya tiene phir_log, salteo\n', m);
        close_system(m, 0);
        continue
    end

    bs = [m '/Bus Selector1'];
    salidas = get_param(bs, 'OutputSignals');
    if numel(strsplit(salidas, ',')) ~= 5
        error('%s: Bus Selector1 no tiene las 5 salidas esperadas: %s', m, salidas);
    end
    set_param(bs, 'OutputSignals', strjoin([{salidas}, nuevas], ','));

    pos = get_param(bs, 'Position');
    x0 = pos(3) + 150;
    y0 = pos(4) + 60;

    add_block('simulink/Signal Routing/Mux', [m '/Mux_phir'], ...
              'Inputs', '2', 'Position', [x0, y0, x0+5, y0+40]);
    add_block('simulink/Signal Routing/Mux', [m '/Mux_marco'], ...
              'Inputs', '3', 'Position', [x0, y0+70, x0+5, y0+130]);
    tw = {'Decimation', '200', 'MaxDataPoints', 'inf', ...
          'SaveFormat', 'Structure With Time', 'SampleTime', '-1', ...
          'BackgroundColor', 'orange'};
    add_block('simulink/Sinks/To Workspace', [m '/To Workspace phir'], ...
              'VariableName', 'phir_log', tw{:}, ...
              'Position', [x0+60, y0+5, x0+150, y0+35]);
    add_block('simulink/Sinks/To Workspace', [m '/To Workspace marco'], ...
              'VariableName', 'marco_log', tw{:}, ...
              'Position', [x0+60, y0+85, x0+150, y0+115]);

    add_line(m, 'Bus Selector1/6', 'Mux_phir/1', 'autorouting', 'on');
    add_line(m, 'Bus Selector1/7', 'Mux_phir/2', 'autorouting', 'on');
    add_line(m, 'Bus Selector1/8', 'Mux_marco/1', 'autorouting', 'on');
    add_line(m, 'Bus Selector1/9', 'Mux_marco/2', 'autorouting', 'on');
    add_line(m, 'Bus Selector1/10', 'Mux_marco/3', 'autorouting', 'on');
    add_line(m, 'Mux_phir/1', 'To Workspace phir/1', 'autorouting', 'on');
    add_line(m, 'Mux_marco/1', 'To Workspace marco/1', 'autorouting', 'on');

    % compilar antes de guardar: si un nombre del bus estuviera mal, falla aca
    set_param(m, 'SimulationCommand', 'update');
    save_system(m);
    close_system(m, 0);
    fprintf('%s: phir_log y marco_log agregados\n', m);
end
end
