# FrotaCheck

Sistema de gestão de ativos e conformidade veicular para transportadoras. Substitui a vistoria de frota em papel por checklists digitais auditáveis, com validação de GPS, evidências fotográficas, bloqueio automático de veículos com avaria crítica e alertas por e-mail para os gestores.

## Sobre o projeto

O FrotaCheck foi criado para transportadoras que precisam eliminar falhas operacionais, reduzir custos com manutenção não planejada e garantir segurança jurídica através de vistorias digitais rastreáveis — quem fez, quando, onde (GPS) e o que encontrou.

O fluxo central do sistema:

1. O motorista preenche um checklist de 28 itens de vistoria antes de rodar com o veículo, confirmando cada item explicitamente como **OK** ou **Avaria** (nenhum item fica pré-marcado, evitando que a inspeção seja finalizada sem revisão real).
2. O envio só é aceito com localização GPS confirmada e todos os itens revisados.
3. Qualquer avaria gera automaticamente uma **Ocorrência** rastreável, vinculada ao checklist e ao veículo.
4. Se a avaria envolver um item crítico de segurança (freio, pneu, farol, bateria, vazamento, etc.), o veículo é **bloqueado para despacho automaticamente** e os gestores recebem um e-mail de alerta.
5. O gestor acompanha as ocorrências em aberto (priorizadas por tempo de espera e gravidade) e, ao resolver a última ocorrência crítica de um veículo, ele é **desbloqueado automaticamente**.

## Funcionalidades

- **Checklist digital de vistoria** — 28 itens agrupados por categoria (iluminação, mecânica, externa/segurança, interna), com confirmação explícita item a item.
- **Validação de GPS obrigatória**, no cliente e no servidor — o envio é recusado sem localização confirmada.
- **Evidências fotográficas** de avaria, com descrição obrigatória e conversão automática para WebP.
- **Ocorrências de avaria** com fluxo de status (Aguardando → Em Reparo → Resolvida), sinal de gravidade (item crítico), sinal de atraso (dias em aberto) e resolução rápida sem sair da lista.
- **Bloqueio automático de veículo** por avaria crítica, com desbloqueio automático ao resolver a última ocorrência crítica pendente — decisões manuais do gestor nunca são sobrescritas pelo sistema.
- **Alertas por e-mail** aos gestores quando um checklist registra avaria, com assunto diferenciado por gravidade.
- **Gestão de frota**: veículos (documentos, FIPE, revisão por KM, foto), funcionários (CNH com controle de vencimento), ordens de manutenção e abastecimentos.
- **Etiquetas QR Code** por veículo para inspeção rápida.
- **Dashboard e relatórios**: conformidade da frota, exportação de checklists em CSV, indicadores de custo e consumo.
- **Controle de acesso por papel** — Motoristas (vistorias e abastecimentos próprios) e Gestores/Admin (gestão completa, relatórios, permissões).
- **Proteção contra força bruta de login** (django-axes) e demais práticas de segurança (uploads validados, downloads autenticados, proteção contra IDOR).

## Tecnologias utilizadas

- **Backend**: Python 3 & [Django 6.0.2](https://www.djangoproject.com/)
- **Frontend**: Tailwind CSS (via CDN) + Font Awesome 6, tema claro/escuro do sistema
- **Banco de dados**: PostgreSQL
- **Autenticação e segurança**: django-axes (rate limiting de login)
- **Geolocalização**: HTML5 Geolocation API, validada também no servidor
- **Imagens**: Pillow (conversão automática de fotos de avaria para WebP)
- **QR Code**: biblioteca `qrcode`

## Pré-requisitos

- Python 3.12+
- pip
- PostgreSQL 14+ rodando localmente (ou acessível via rede)

## Instalação

```bash
# Clone o repositório
git clone <url-do-repositorio>
cd FROTACHECK

# Crie e ative o ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/macOS

# Instale as dependências
pip install -r requirements.txt
```

### Banco de dados

Crie o banco e um usuário dedicado (via `psql` ou outra ferramenta), antes da primeira migration:

```sql
CREATE USER frotacheck WITH PASSWORD 'sua-senha' CREATEDB;
CREATE DATABASE frotacheck OWNER frotacheck ENCODING 'UTF8';
```

`CREATEDB` é necessário para que `manage.py test` consiga criar/destruir o banco de testes automaticamente.

```bash
python manage.py migrate
```

### Variáveis de ambiente

`DJANGO_SECRET_KEY` é **obrigatória** — a aplicação recusa subir sem ela quando `DEBUG=False` (padrão do projeto). As variáveis de conexão com o banco (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) têm valores padrão pensados para um Postgres local chamado `frotacheck`, mas devem ser configuradas explicitamente em qualquer outro ambiente. Não há loader de `.env`; exporte as variáveis manualmente no shell ou use um script local (veja `.env.example` para a lista completa, incluindo banco de dados e e-mail).

```bash
export DJANGO_SECRET_KEY="sua-chave-secreta-longa-e-aleatoria"   # Linux/macOS
$env:DJANGO_SECRET_KEY = "sua-chave-secreta-longa-e-aleatoria"   # Windows PowerShell
```

## Como rodar

```bash
python manage.py runserver
```

Acesse `http://127.0.0.1:8000/`.

### Popular com dados de demonstração

```bash
python manage.py popular_fixtures
```

Cria um usuário gestor (`gestor` / `demo1234`), 4 motoristas, 5 veículos, checklists, ocorrências, ordens de manutenção e abastecimentos de exemplo. Recusa rodar se `DEBUG=False`.

## Testes

```bash
python manage.py test frota
```

Para rodar um teste específico:

```bash
python manage.py test frota.tests.NomeDaClasse.test_metodo
```

## Estrutura do projeto

Projeto Django único (`core/`) com um único app (`frota/`) concentrando toda a lógica de domínio:

```
core/               configurações do projeto (settings, urls raiz)
frota/
├── models.py        Usuario, Funcionario, Veiculo, Checklist, FotoAvaria,
│                     OcorrenciaAvaria, OrdemManutencao, Abastecimento
├── views.py          regras de negócio e permissões
├── forms.py          formulários e validações
├── utils.py          constantes e regras de checklist/avaria (fonte única
│                     de verdade dos itens de vistoria e itens críticos)
├── context_processors.py   alertas globais (CNH, documentos, ocorrências)
├── templates/        templates organizados por domínio
└── tests.py          suíte de testes (regressões de segurança e negócio)
```

## Licença

Projeto privado, desenvolvido sob encomenda. Todos os direitos reservados.
