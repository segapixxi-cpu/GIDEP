function barrido_lambda(cuales)
% Corre el experimento factorial que separa dos hipotesis sobre por que
% psi_r medido (0.5509 Wb) supera a Lm*id_ref (0.354 Wb).
%
%   H1  lambda_sw = 100 penaliza tanto la conmutacion que el MPC deja de
%       seguir la referencia; ese error de seguimiento mete corriente de mas
%       en el eje de magnetizacion.        Se prueba bajando lambda_sw.
%
%   H2  theta_psi se calcula sin adelantar un paso, asi que la referencia se
%       genera con el angulo que el flujo tenia en k y no con el de k+1.
%       Se prueba con la variante T1, que agrega el adelanto.
%
% Las dos pueden ser ciertas, una sola, o ninguna. Por eso el diseno es
% factorial: hace falta la celda con LAS DOS corregidas para poder concluir
% que no queda nada por explicar.
%
%      lambda_sw \ adelanto |   no (T0)      si (T1)
%      ---------------------+---------------------------
%      100  (como esta)     |   L100_T0      L100_T1     <- H2 sola
%      0    (sin penaliz.)  |   L0_T0        L0_T1       <- H1 sola / ambas
%
% L10_T0 y L1_T0 completan la tendencia de lambda_sw, son secundarias.
%
% Uso, desde la carpeta del proyecto:
%     matlab -batch "addpath('tools'); barrido_lambda"              % las seis
%     matlab -batch "addpath('tools'); barrido_lambda({'L100_T0','L0_T1'})"
%
% Salta las corridas ya hechas, asi que se puede cortar y relanzar.
% Deja barrido_<variante>.mat. Omite dos cosas pesadas:
%   tout      : vector de tiempo del solver, 3e6 puntos sin decimar, 24 MB
%               inutiles. Cada To Workspace ya trae su propio .time.
%   gates_log : 9 columnas. Deja en su lugar Nsw por paso de control, que es
%               lo unico que hace falta para contar conmutaciones.
% Asi cada archivo queda en unos 2.6 MB en vez de 17.7.

if nargin < 1 || isempty(cuales)
    % el 2x2 primero: es lo que decide. La tendencia despues.
    cuales = {'L100_T0', 'L0_T0', 'L100_T1', 'L0_T1', 'L10_T0', 'L1_T0'};
end

for k = 1:numel(cuales)
    v = cuales{k};
    modelo  = sprintf('DMC_FCSMPC_IM_Physical_v6_3_%s', v);
    destino = sprintf('barrido_%s.mat', v);

    if exist(destino, 'file')
        fprintf('[%d/%d] %s ya existe, salteo\n', k, numel(cuales), destino);
        continue
    end
    if ~exist([modelo '.slx'], 'file')
        fprintf('[%d/%d] FALTA %s.slx, salteo\n', k, numel(cuales), modelo);
        continue
    end

    partes = split(v, '_');
    lam = str2double(extractAfter(partes{1}, 'L'));
    adel = strcmp(partes{2}, 'T1');

    fprintf('[%d/%d] %s  (lambda_sw = %g, adelanto de theta = %d) ...\n', ...
            k, numel(cuales), modelo, lam, adel);
    t0 = tic;
    so = sim(modelo);
    fprintf('        listo en %.0f s\n', toc(t0));

    R = struct();
    R.lambda_sw = lam;
    R.adelanto  = double(adel);
    R.variante  = v;
    R.modelo    = modelo;

    nombres = so.who;
    for j = 1:numel(nombres)
        n = nombres{j};
        if strcmp(n, 'gates_log') || strcmp(n, 'tout'); continue; end
        x = so.get(n);
        if isstruct(x) || isnumeric(x); R.(n) = x; end
    end

    % Nsw por paso: cuantas salidas (a,b,c) cambian de fuente.
    % gates_log = [SAa SAb SAc SBa SBb SBc SCa SCb SCc], Sxy = entrada x -> salida y.
    if any(strcmp(nombres, 'gates_log'))
        g = so.get('gates_log');
        G = squeeze(g.signals.values);
        if size(G,1) ~= numel(g.time); G = G.'; end
        [~, sa] = max(G(:, [1 4 7]), [], 2);
        [~, sb] = max(G(:, [2 5 8]), [], 2);
        [~, sc] = max(G(:, [3 6 9]), [], 2);
        R.Nsw = int8(sum(diff([sa sb sc], 1, 1) ~= 0, 2));
        R.tsw = g.time(2:end);
    end

    save(destino, '-struct', 'R', '-v7');
    d = dir(destino);
    fprintf('        guardado %s (%.1f MB)\n', destino, d.bytes/1e6);
end

fprintf('\nAnalizar con:\n    python tools/comparar_barrido.py\n');
end
