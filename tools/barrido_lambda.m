function barrido_lambda()
% Corre las cuatro variantes de lambda_sw y guarda un resumen compacto por
% corrida, para medir si lambda_sw es lo que degrada el seguimiento de
% corriente y, con eso, lo que sube el flujo por encima de Lm*id_ref.
%
% Uso, desde la carpeta del proyecto:
%     matlab -batch "addpath('tools'); barrido_lambda"
%
% Deja barrido_L<valor>.mat por cada corrida. Omite dos cosas pesadas:
%   tout      : vector de tiempo del solver, 3e6 puntos sin decimar, 24 MB.
%               No hace falta: cada To Workspace trae su propio .time.
%   gates_log : 9 columnas. En su lugar guarda Nsw por paso de control, que
%               es lo unico que hace falta para contar conmutaciones.
% Con eso cada archivo queda en unos pocos MB en vez de 20.

variantes = {'L100', 'L10', 'L1', 'L0'};
lambdas   = [100, 10, 1, 0];

for k = 1:numel(variantes)
    modelo = sprintf('DMC_FCSMPC_IM_Physical_v6_3_%s', variantes{k});
    destino = sprintf('barrido_%s.mat', variantes{k});

    if exist(destino, 'file')
        fprintf('[%d/%d] %s ya existe, salteo\n', k, numel(variantes), destino);
        continue
    end

    fprintf('[%d/%d] simulando %s (lambda_sw = %g) ...\n', ...
            k, numel(variantes), modelo, lambdas(k));
    t0 = tic;
    so = sim(modelo);
    fprintf('        listo en %.0f s\n', toc(t0));

    R = struct();
    R.lambda_sw = lambdas(k);
    R.modelo = modelo;

    nombres = so.who;
    for j = 1:numel(nombres)
        n = nombres{j};
        if strcmp(n, 'gates_log'); continue; end     % se procesa aparte
        if strcmp(n, 'tout');      continue; end     % 3e6 puntos sin decimar, 24 MB inutiles
        v = so.get(n);
        if isstruct(v) || isnumeric(v); R.(n) = v; end
    end

    % Nsw por paso: cuantas salidas (a,b,c) cambian de fuente.
    % gates_log = [SAa SAb SAc SBa SBb SBc SCa SCb SCc], Sxy = entrada x -> salida y.
    if any(strcmp(nombres, 'gates_log'))
        g = so.get('gates_log');
        G = squeeze(g.signals.values);
        if size(G,1) ~= numel(g.time); G = G.'; end
        [~, src_a] = max(G(:, [1 4 7]), [], 2);
        [~, src_b] = max(G(:, [2 5 8]), [], 2);
        [~, src_c] = max(G(:, [3 6 9]), [], 2);
        src = [src_a src_b src_c];
        R.Nsw  = int8(sum(diff(src, 1, 1) ~= 0, 2));
        R.tsw  = g.time(2:end);
    end

    save(destino, '-struct', 'R', '-v7');
    d = dir(destino);
    fprintf('        guardado %s (%.1f MB)\n', destino, d.bytes/1e6);
end

fprintf('\nBarrido completo. Analizar con:\n');
fprintf('    python tools/comparar_barrido.py\n');
end
