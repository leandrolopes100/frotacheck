# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FrotaCheck — sistema de gestão de ativos e conformidade veicular para transportadoras: checklists digitais de vistoria (com validação de GPS e evidências fotográficas), controle de ocorrências de avaria, ordens de manutenção, abastecimento e cadastro de funcionários/veículos. Django 6.0.2, Tailwind CSS via CDN, SQLite (dev; Postgres planejado para produção, ver README.md).

## Commands

Venv Windows em `venv/` (usa `Scripts/python.exe`, não `bin/`).

- Instalar dependências: `venv/Scripts/python.exe -m pip install -r requirements.txt`
- Rodar servidor de dev: `DJANGO_SECRET_KEY=<valor> venv/Scripts/python.exe manage.py runserver`
- Rodar todos os testes: `DJANGO_SECRET_KEY=<valor> venv/Scripts/python.exe manage.py test frota`
- Rodar um teste específico: `... manage.py test frota.tests.NomeDaClasse.test_metodo`
- Gerar migrations: `... manage.py makemigrations frota`
- Aplicar migrations: `... manage.py migrate`
- System check: `... manage.py check` (use `--deploy` para ver avisos de prontidão para produção)
- Popular banco com dados de demonstração (recusa rodar se `DEBUG=False`): `... manage.py popular_fixtures` — cria usuário `gestor`/`demo1234`, 4 motoristas (`demo1234`), 5 veículos, checklists, ocorrências, ordens de manutenção e abastecimentos

`DJANGO_SECRET_KEY` é **obrigatória**: `core/settings.py` levanta `ImproperlyConfigured` se ela não estiver definida e `DEBUG=False` (que é o padrão do arquivo). Não há loader de `.env` no projeto — `.env.example` só documenta o nome da variável; exporte-a manualmente no shell.

## Architecture

Projeto Django único (`core/`) com um único app (`frota/`) que concentra toda a lógica de domínio — `models.py`, `views.py`, `forms.py`, `admin.py`, `urls.py` são um arquivo por responsabilidade, não divididos por feature.

### Modelo de autenticação e permissões

- `Usuario` (custom `AUTH_USER_MODEL = 'frota.Usuario'`) estende `AbstractUser` com dois flags: `is_patrao` (gestor/admin) e `is_motorista`.
- `Funcionario` é um perfil `OneToOneField` ligado a `Usuario` (`related_name='perfil_funcionario'`), com CPF/CNH/cargo. Views que precisam "o registro do motorista logado" usam `request.user.perfil_funcionario`.
- `GestorRequiredMixin` (definido em `frota/views.py`) é o gate padrão para views só-de-gestor — sempre combinado com `LoginRequiredMixin`. Usuário sem permissão é redirecionado para `checklist_list` com mensagem, não recebe 403.
- Views de lista/detalhe usadas por motoristas (checklists, abastecimentos) filtram queryset por `motorista__usuario=request.user` a menos que `user.is_superuser or user.is_patrao`; as views de criação correspondentes forçam `motorista = request.user.perfil_funcionario` no servidor para não-gestores, em vez de confiar em campo de formulário submetido.
- Documentos sensíveis enviados (CNH, CRLV do veículo) **não** são linkados direto via `MEDIA_URL` — passam por views autenticadas dedicadas (`FuncionarioCnhDownloadView`, `VeiculoDocumentoDownloadView`) usando `FileResponse`.

### Lógica de domínio do checklist/avaria

- `frota/utils.py` é a fonte única de verdade para os ~26 campos booleanos de inspeção do `Checklist` (`CAMPOS_AVARIA`, `CAMPO_LABELS`, `ITENS_CRITICOS`). Qualquer campo `False` conta como "avaria" (`get_filtro_avaria()` / `Checklist.tem_avaria`). Novos campos de inspeção entram ali, não direto em views/templates.
- Criar um `Checklist` com alguma avaria cria automaticamente uma `OcorrenciaAvaria` via `criar_ocorrencia_para_checklist()`; se a avaria estiver em `ITENS_CRITICOS`, `_enviar_email_avaria_critica()` (em `views.py`) envia e-mail a todos os usuários `is_patrao=True`, com deduplicação via cache por 2h por checklist.
- GPS (`latitude`/`longitude`) é capturado no cliente em `checklist_form.html` e também **validado no servidor** em `ChecklistForm.clean()` — não depender só da checagem via JavaScript.
- `FotoAvaria.save()` converte automaticamente as imagens enviadas para WebP (máx. 1920×1080) — não duplicar essa lógica em outro lugar.

### Padrões de query a reaproveitar

Várias views evitam N+1 deliberadamente com `Subquery`/`OuterRef` (ex.: "último checklist por veículo" em `ConformidadeFrotaView`, "último nível de combustível por veículo" em `ChecklistListView`) em vez de laço em Python — seguir esse padrão para necessidades parecidas de "último registro relacionado", em vez de query por objeto.

### Configuração sensível em `core/settings.py`

- `SECRET_KEY`: sem fallback inseguro quando `DEBUG=False` (ver Commands acima).
- Configurações de HTTPS/cookies seguros (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS) ficam atrás de `DJANGO_HTTPS_ENABLED=True` — desligadas por padrão porque hoje a aplicação roda em rede local sem TLS na frente.
- `django-axes` cuida do rate limiting de login (5 tentativas falhas → bloqueio de 1h por IP+usuário, persistido no banco). É desativado automaticamente durante `manage.py test` (`AXES_ENABLED = 'test' not in sys.argv`), pois `Client.login()` não passa um `request` e `AxesStandaloneBackend` exige um — testes que precisam exercitar o bloqueio de verdade usam `@override_settings(AXES_ENABLED=True, ...)` e fazem POST direto na view de login em vez de `client.login()`.
- Uploads de CNH/documento do veículo são restritos a `pdf/jpg/jpeg/png` via `FileExtensionValidator` (`DOCUMENTO_EXTENSOES_PERMITIDAS` em `models.py`).

### Testes

`frota/tests.py` usa `TestCase` puro. Helper útil: `_criar_motorista(username, is_patrao=False)` cria um par `Usuario`+`Funcionario` com CPF válido gerado (`_gerar_cpf_valido()` — `Funcionario.cpf` tem `unique=True`, então testes não podem reusar um CPF hardcoded entre motoristas diferentes). Testes que mexem em `FileField` usam `@override_settings(MEDIA_ROOT=<tempdir>)` e limpam em `tearDownClass`.

### Templates

Organizados por domínio em `frota/templates/`: `frota/` (checklists, ocorrências, conformidade), `veiculo/`, `funcionario/`, `manutencao/`, `registration/` (login). Tailwind é carregado via `cdn.tailwindcss.com` (não é build de produção), mais Font Awesome e Google Fonts via CDN — Font Awesome tem hash SRI fixado em `base.html`; Google Fonts e o script do Tailwind CDN não suportam SRI (conteúdo dinâmico por requisição).
