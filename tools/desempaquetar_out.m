function desempaquetar_out(archivo)
% Desempaqueta el Simulink.SimulationOutput que deja sim() cuando el modelo
% esta configurado con "single simulation output" y reescribe el .mat con las
% variables de los To Workspace como structs planos, legibles por scipy.
%
%   desempaquetar_out('C:\...\out.mat')
%
% Sin esto, save() guarda un unico objeto MCOS que scipy.io.loadmat no puede
% leer (TypeError en shape_from_header).
if nargin < 1 || isempty(archivo); archivo = fullfile(pwd, 'out.mat'); end
S = load(archivo);
f = fieldnames(S);
so = [];
for k = 1:numel(f)
    if isa(S.(f{k}), 'Simulink.SimulationOutput'); so = S.(f{k}); break; end
end
if isempty(so)
    fprintf('Ya esta desempaquetado: %s\n', strjoin(f', ', '));
    return
end
nombres = so.who;
fprintf('Variables dentro del SimulationOutput (%d):\n', numel(nombres));
limpio = struct();
for k = 1:numel(nombres)
    n = nombres{k};
    v = so.get(n);
    fprintf('  %-14s %s\n', n, class(v));
    if isstruct(v) || isnumeric(v); limpio.(n) = v; end
end
save(archivo, '-struct', 'limpio', '-v7');
d = dir(archivo);
fprintf('reescrito: %.1f MB, %d variables\n', d.bytes/1e6, numel(fieldnames(limpio)));
end
