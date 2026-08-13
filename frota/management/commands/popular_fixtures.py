import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from frota.models import (
    Usuario, Funcionario, Veiculo, Checklist, FotoAvaria,
    OcorrenciaAvaria, OrdemManutencao, Abastecimento,
)
from frota.utils import criar_ocorrencia_para_checklist


class Command(BaseCommand):
    help = "Popula o banco com dados de demonstração (usuários, veículos, checklists, ocorrências, manutenções e abastecimentos)."

    def handle(self, *args, **options):
        hoje = timezone.now()

        self.stdout.write("Criando usuários...")
        gestor, criado = Usuario.objects.get_or_create(
            username="gestor",
            defaults=dict(
                first_name="Carlos", last_name="Andrade",
                email="gestor@frotacheck.com.br",
                is_patrao=True, is_staff=True, is_superuser=True,
            ),
        )
        if criado:
            gestor.set_password("demo1234")
            gestor.save()

        motoristas_dados = [
            ("joao.silva", "João", "Silva", "111.111.111-11"),
            ("maria.souza", "Maria", "Souza", "222.222.222-22"),
            ("pedro.lima", "Pedro", "Lima", "333.333.333-33"),
            ("ana.costa", "Ana", "Costa", "444.444.444-44"),
        ]

        funcionarios = []
        for username, nome, sobrenome, cpf in motoristas_dados:
            usuario, criado = Usuario.objects.get_or_create(
                username=username,
                defaults=dict(
                    first_name=nome, last_name=sobrenome,
                    email=f"{username}@frotacheck.com.br",
                    is_motorista=True,
                ),
            )
            if criado:
                usuario.set_password("demo1234")
                usuario.save()

            funcionario, _ = Funcionario.objects.get_or_create(
                usuario=usuario,
                defaults=dict(
                    nome_completo=f"{nome} {sobrenome}",
                    cadastrado_por=gestor,
                    cpf=cpf,
                    numero_cnh=f"{random.randint(10**9, 10**10 - 1)}",
                    validade_cnh=(hoje + timedelta(days=random.randint(180, 900))).date(),
                    cargo="Motorista",
                ),
            )
            funcionarios.append(funcionario)

        self.stdout.write("Criando veículos...")
        veiculos_dados = [
            ("ABC1D23", "Volkswagen", "Delivery 9.170", 2020, "12345678901", 145000),
            ("DEF4E56", "Mercedes-Benz", "Accelo 815", 2021, "23456789012", 98000),
            ("GHI7F89", "Ford", "Cargo 1119", 2019, "34567890123", 210000),
            ("JKL0G12", "Iveco", "Daily 35S14", 2022, "45678901234", 65000),
            ("MNO3H45", "Volvo", "FH 460", 2018, "56789012345", 310000),
        ]

        veiculos = []
        for placa, marca, modelo, ano, renavam, fipe in veiculos_dados:
            veiculo, _ = Veiculo.objects.get_or_create(
                placa=placa,
                defaults=dict(
                    marca=marca, modelo=modelo, ano=ano, renavam=renavam,
                    fipe=fipe, ativo=True,
                    vencimento_crlv=(hoje + timedelta(days=random.randint(30, 400))).date(),
                    vencimento_seguro=(hoje + timedelta(days=random.randint(-30, 400))).date(),
                    km_proxima_revisao=random.randint(150000, 350000),
                ),
            )
            veiculos.append(veiculo)

        # Um veículo bloqueado para despacho, para demonstrar o alerta
        veiculo_bloqueado = veiculos[-1]
        veiculo_bloqueado.bloqueado = True
        veiculo_bloqueado.motivo_bloqueio = "Aguardando troca de pneus dianteiros."
        veiculo_bloqueado.save()

        self.stdout.write("Criando checklists...")
        campos_checklist_ok = {
            'farol': True, 'lanterna': True, 're_freio': True, 'piscas': True,
            'pneus': True, 'amortecedor': True, 'bateria': True, 'oleo': True,
            'arrefecimento_radiador': True, 'vazamentos': True,
            'limpadores': True, 'vidros': True, 'retrovisor': True, 'estepe': True,
            'macaco': True, 'chave_roda': True, 'lataria': True, 'buzina': True,
            'iluminacao_interna': True, 'bancos': True, 'tapetes': True,
            'freio_mao': True, 'ar_condicionado': True, 'som': True, 'teto': True,
            'tacografo': True, 'carga': True,
        }

        checklists_criados = []
        km_base = {v.placa: random.randint(50000, 150000) for v in veiculos}

        for dia in range(6, 0, -1):
            data_ref = hoje - timedelta(days=dia)
            for veiculo in veiculos:
                motorista = random.choice(funcionarios)
                km_base[veiculo.placa] += random.randint(80, 400)

                campos = dict(campos_checklist_ok)
                com_falha = random.random() < 0.3
                if com_falha:
                    campo_falho = random.choice(list(campos.keys()))
                    campos[campo_falho] = False

                checklist = Checklist.objects.create(
                    nome_checklist=f"Checklist Pré-Viagem {data_ref.strftime('%d/%m/%Y')}",
                    veiculo=veiculo,
                    motorista=motorista,
                    data_realizada=data_ref,
                    km_atual=km_base[veiculo.placa],
                    nivel_combustivel=random.choice(['1/4', '1/2', '3/4', 'Cheio']),
                    tipo='pre_viagem',
                    **campos,
                )
                checklists_criados.append(checklist)

                if com_falha:
                    criar_ocorrencia_para_checklist(checklist)

        self.stdout.write("Criando ordens de manutenção...")
        ocorrencias = list(OcorrenciaAvaria.objects.all())
        status_ordens = ['aberta', 'agendada', 'em_andamento', 'concluida']
        for i, ocorrencia in enumerate(ocorrencias):
            status = status_ordens[i % len(status_ordens)]
            ordem = OrdemManutencao.objects.create(
                veiculo=ocorrencia.veiculo,
                ocorrencia=ocorrencia,
                descricao=f"Reparo referente a: {ocorrencia.descricao}",
                responsavel=random.choice(["Oficina Central", "Auto Peças Bragança", "Oficina do Zé"]),
                status=status,
                data_agendada=(hoje + timedelta(days=random.randint(1, 15))).date() if status in ('agendada', 'em_andamento') else None,
                data_conclusao=(hoje - timedelta(days=random.randint(1, 5))).date() if status == 'concluida' else None,
                custo=round(random.uniform(150, 2500), 2) if status == 'concluida' else None,
                criada_por=gestor,
            )
            if status == 'concluida':
                ocorrencia.status = 'resolvida'
                ocorrencia.resolvida_por = gestor
                ocorrencia.nota_resolucao = "Serviço concluído e conferido."
                ocorrencia.save()
            elif status == 'em_andamento':
                ocorrencia.status = 'em_reparo'
                ocorrencia.save()

        # Ordem de manutenção preventiva avulsa (sem ocorrência vinculada)
        OrdemManutencao.objects.create(
            veiculo=veiculo_bloqueado,
            descricao="Troca de pneus dianteiros (desgaste identificado em inspeção).",
            responsavel="Borracharia Central",
            status='agendada',
            data_agendada=(hoje + timedelta(days=2)).date(),
            criada_por=gestor,
        )

        self.stdout.write("Criando abastecimentos...")
        for veiculo in veiculos:
            km_atual = km_base[veiculo.placa]
            for dia in range(15, 0, -3):
                km_atual += random.randint(200, 600)
                litros = round(random.uniform(80, 300), 2)
                preco_litro = round(random.uniform(5.8, 6.5), 2)
                Abastecimento.objects.create(
                    veiculo=veiculo,
                    motorista=random.choice(funcionarios),
                    data=hoje - timedelta(days=dia),
                    km_atual=km_atual,
                    litros=litros,
                    valor_total=round(litros * preco_litro, 2),
                    tipo_combustivel='diesel',
                    registrado_por=gestor,
                )

        self.stdout.write(self.style.SUCCESS(
            "\nDados de demonstração criados com sucesso!\n"
            f"  Usuários: {Usuario.objects.count()}\n"
            f"  Funcionários: {Funcionario.objects.count()}\n"
            f"  Veículos: {Veiculo.objects.count()}\n"
            f"  Checklists: {Checklist.objects.count()}\n"
            f"  Ocorrências de avaria: {OcorrenciaAvaria.objects.count()}\n"
            f"  Ordens de manutenção: {OrdemManutencao.objects.count()}\n"
            f"  Abastecimentos: {Abastecimento.objects.count()}\n\n"
            "Login do gestor -> usuário: gestor | senha: demo1234\n"
            "Login de motorista -> usuário: joao.silva | senha: demo1234"
        ))
