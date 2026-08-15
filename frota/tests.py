import itertools
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ChecklistForm
from .models import Abastecimento, Checklist, Funcionario, OcorrenciaAvaria, Veiculo
from .utils import CAMPOS_AVARIA
from .views import _enviar_email_avaria

Usuario = get_user_model()

_cpf_counter = itertools.count(100000001)


def _gerar_cpf_valido():
    """Gera um CPF com dígitos verificadores válidos (mesmo algoritmo de
    frota.forms._validar_cpf), único a cada chamada — evita colisão com a
    constraint unique=True de Funcionario.cpf nos testes."""
    base = str(next(_cpf_counter)).zfill(9)[-9:]

    def dv(digitos, peso_inicial):
        soma = sum(int(d) * p for d, p in zip(digitos, range(peso_inicial, 1, -1)))
        resto = soma % 11
        return '0' if resto < 2 else str(11 - resto)

    d1 = dv(base, 10)
    d2 = dv(base + d1, 11)
    return base + d1 + d2


def _criar_motorista(username, is_patrao=False):
    usuario = Usuario.objects.create_user(
        username=username, password='senha-teste-123',
        is_motorista=not is_patrao, is_patrao=is_patrao,
    )
    Funcionario.objects.create(
        usuario=usuario, nome_completo=f'Funcionario {username}',
        cpf=_gerar_cpf_valido(),
        numero_cnh='12345678900', validade_cnh=date(2030, 1, 1),
        cargo='Gestor' if is_patrao else 'Motorista',
    )
    return usuario


class FuncionarioCreateViewPermissionTests(TestCase):
    """Regressão: motorista comum não pode se autopromover a gestor
    criando um novo Usuario com cargo='Gestor' (era possível pois a view
    só exigia login, sem checar is_patrao)."""

    def setUp(self):
        self.motorista = _criar_motorista('motorista1')
        self.gestor = _criar_motorista('gestor1', is_patrao=True)
        self.dados_novo_funcionario = {
            'username': 'novo.usuario', 'password': 'outra-senha-123',
            'email': 'novo@exemplo.com', 'nome_completo': 'Fulano de Tal',
            'cpf': '39053344705', 'numero_cnh': '98765432100',
            'validade_cnh': '2030-01-01', 'cargo': 'Gestor',
        }

    def test_motorista_nao_pode_criar_funcionario(self):
        self.client.login(username='motorista1', password='senha-teste-123')
        response = self.client.post(reverse('funcionario_add'), self.dados_novo_funcionario)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Usuario.objects.filter(username='novo.usuario').exists())

    def test_gestor_pode_criar_funcionario(self):
        self.client.login(username='gestor1', password='senha-teste-123')
        response = self.client.post(reverse('funcionario_add'), self.dados_novo_funcionario)
        self.assertRedirects(response, reverse('funcionario_list'))
        novo_usuario = Usuario.objects.get(username='novo.usuario')
        self.assertTrue(novo_usuario.is_patrao)


class ChecklistFormGPSTests(TestCase):
    """Regressão: o formulário de checklist deve exigir latitude/longitude
    no servidor — antes a checagem era só via JavaScript no navegador."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='ABC1D23', marca='Ford', modelo='Cargo',
            ano=2020, renavam='12345678901',
        )

    def _dados_base(self):
        return {
            'veiculo': self.veiculo.pk, 'nome_checklist': 'Checklist Teste',
            'km_atual': 1000, 'nivel_combustivel': 'Cheio', 'tipo': 'geral',
        }

    def test_form_invalido_sem_gps(self):
        form = ChecklistForm(data=self._dados_base())
        self.assertFalse(form.is_valid())

    def test_form_invalido_com_gps_parcial(self):
        dados = self._dados_base()
        dados['latitude'] = -23.55
        form = ChecklistForm(data=dados)
        self.assertFalse(form.is_valid())

    def test_form_valido_com_gps_completo(self):
        dados = self._dados_base()
        dados['latitude'] = -23.55
        dados['longitude'] = -46.63
        form = ChecklistForm(data=dados)
        self.assertTrue(form.is_valid(), form.errors)


class DocumentoUploadValidationTests(TestCase):
    """Regressão: uploads de CNH/documento do veículo devem aceitar
    apenas pdf/jpg/jpeg/png — antes qualquer extensão era aceita."""

    def test_cnh_com_extensao_invalida_e_rejeitada(self):
        usuario = Usuario.objects.create_user(username='motorista2', password='x', is_motorista=True)
        arquivo_malicioso = SimpleUploadedFile(
            'cnh.html', b'<script>alert(1)</script>', content_type='text/html',
        )
        funcionario = Funcionario(
            usuario=usuario, nome_completo='Fulano de Tal', cpf='39053344705',
            numero_cnh='12345678900', validade_cnh=date(2030, 1, 1),
            cnh_impressa=arquivo_malicioso,
        )
        with self.assertRaises(Exception):
            funcionario.full_clean()

    def test_cnh_com_extensao_valida_e_aceita(self):
        usuario = Usuario.objects.create_user(username='motorista3', password='x', is_motorista=True)
        arquivo_valido = SimpleUploadedFile(
            'cnh.pdf', b'%PDF-1.4 conteudo de teste', content_type='application/pdf',
        )
        funcionario = Funcionario(
            usuario=usuario, nome_completo='Fulano de Tal', cpf='39053344705',
            numero_cnh='12345678900', validade_cnh=date(2030, 1, 1),
            cnh_impressa=arquivo_valido,
        )
        funcionario.full_clean()


class ChecklistDetailIDORTests(TestCase):
    """Regressão: um motorista não pode ver o detalhe de checklist de
    outro motorista trocando o pk na URL (CheckListDetailView não
    filtrava por usuário)."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='XYZ9A87', marca='Ford', modelo='Cargo',
            ano=2021, renavam='98765432100',
        )
        self.motorista_a = _criar_motorista('motoristaA')
        self.motorista_b = _criar_motorista('motoristaB')
        self.gestor = _criar_motorista('gestor2', is_patrao=True)
        self.checklist_a = Checklist.objects.create(
            veiculo=self.veiculo,
            motorista=Funcionario.objects.get(usuario=self.motorista_a),
            km_atual=1000, latitude=-23.55, longitude=-46.63,
        )

    def test_motorista_nao_acessa_checklist_de_outro(self):
        self.client.login(username='motoristaB', password='senha-teste-123')
        response = self.client.get(reverse('checklist_detail', args=[self.checklist_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_motorista_acessa_proprio_checklist(self):
        self.client.login(username='motoristaA', password='senha-teste-123')
        response = self.client.get(reverse('checklist_detail', args=[self.checklist_a.pk]))
        self.assertEqual(response.status_code, 200)

    def test_gestor_acessa_qualquer_checklist(self):
        self.client.login(username='gestor2', password='senha-teste-123')
        response = self.client.get(reverse('checklist_detail', args=[self.checklist_a.pk]))
        self.assertEqual(response.status_code, 200)


_MEDIA_ROOT_TESTE = tempfile.mkdtemp(prefix='frotacheck_test_media_')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT_TESTE)
class DocumentoDownloadViewTests(TestCase):
    """Regressão: CNH/documento do veículo não devem mais ser acessíveis
    via link direto de mídia sem autenticação/permissão — agora passam
    por uma view que checa login e, no caso da CNH, propriedade do
    registro."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT_TESTE, ignore_errors=True)

    def setUp(self):
        self.motorista_a = _criar_motorista('motoristaC')
        self.motorista_b = _criar_motorista('motoristaD')
        self.gestor = _criar_motorista('gestor3', is_patrao=True)
        self.funcionario_a = Funcionario.objects.get(usuario=self.motorista_a)
        self.funcionario_a.cnh_impressa = SimpleUploadedFile(
            'cnh.pdf', b'%PDF-1.4 conteudo de teste', content_type='application/pdf',
        )
        self.funcionario_a.save()

    def test_download_cnh_exige_login(self):
        response = self.client.get(reverse('funcionario_cnh_download', args=[self.funcionario_a.pk]))
        self.assertEqual(response.status_code, 302)

    def test_motorista_nao_baixa_cnh_de_outro(self):
        self.client.login(username='motoristaD', password='senha-teste-123')
        response = self.client.get(reverse('funcionario_cnh_download', args=[self.funcionario_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_motorista_baixa_propria_cnh(self):
        self.client.login(username='motoristaC', password='senha-teste-123')
        response = self.client.get(reverse('funcionario_cnh_download', args=[self.funcionario_a.pk]))
        self.assertEqual(response.status_code, 200)

    def test_gestor_baixa_cnh_de_qualquer_funcionario(self):
        self.client.login(username='gestor3', password='senha-teste-123')
        response = self.client.get(reverse('funcionario_cnh_download', args=[self.funcionario_a.pk]))
        self.assertEqual(response.status_code, 200)

    def test_download_documento_veiculo_exige_login(self):
        veiculo = Veiculo.objects.create(
            placa='DOC1A23', marca='Ford', modelo='Cargo', ano=2021, renavam='11223344556',
        )
        response = self.client.get(reverse('veiculo_documento_download', args=[veiculo.pk]))
        self.assertEqual(response.status_code, 302)


class AbastecimentoIDORTests(TestCase):
    """Regressão: um motorista não pode registrar abastecimento em nome
    de outro motorista adulterando o campo 'motorista' do formulário
    (AbastecimentoCreateView não forçava o motorista logado)."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='FUE1L23', marca='Ford', modelo='Cargo',
            ano=2020, renavam='55667788990',
        )
        self.motorista_a = _criar_motorista('motoristaE')
        self.motorista_b = _criar_motorista('motoristaF')

    def test_motorista_nao_atribui_abastecimento_a_outro(self):
        self.client.login(username='motoristaE', password='senha-teste-123')
        funcionario_b = Funcionario.objects.get(usuario=self.motorista_b)
        response = self.client.post(reverse('abastecimento_add'), {
            'veiculo': self.veiculo.pk, 'motorista': funcionario_b.pk,
            'data': '2026-01-10T10:00', 'km_atual': 1000,
            'litros': '50.00', 'valor_total': '300.00', 'tipo_combustivel': 'diesel',
        })
        self.assertEqual(response.status_code, 302)
        abastecimento = Abastecimento.objects.get()
        self.assertEqual(abastecimento.motorista, Funcionario.objects.get(usuario=self.motorista_a))


class ChartJSONScriptXSSTests(TestCase):
    """Regressão: dados injetados em <script> do dashboard usavam |safe
    sobre json.dumps simples — uma string de veículo contendo
    '</script>' quebrava o contexto do script. Agora usam o filtro
    json_script, que escapa corretamente."""

    def test_nome_malicioso_de_veiculo_nao_quebra_script(self):
        veiculo = Veiculo.objects.create(
            placa='XSS1A23', marca='Ford',
            modelo='Cargo</script><script>alert(1)</script>',
            ano=2020, renavam='99887766554',
        )
        motorista = _criar_motorista('motoristaG')
        gestor = _criar_motorista('gestorX', is_patrao=True)
        Checklist.objects.create(
            veiculo=veiculo, motorista=Funcionario.objects.get(usuario=motorista),
            km_atual=1000, latitude=-23.55, longitude=-46.63, farol=False,
        )
        self.client.login(username='gestorX', password='senha-teste-123')
        response = self.client.get(reverse('checklist_list'))
        self.assertEqual(response.status_code, 200)
        conteudo = response.content.decode()
        self.assertNotIn('</script><script>alert(1)</script>', conteudo)
        self.assertIn('id="top-veiculos-labels-data"', conteudo)


@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=3, AXES_COOLOFF_TIME=1)
class LoginBruteForceProtectionTests(TestCase):
    """Regressão: o login não tinha nenhuma proteção contra força bruta
    de senha. django-axes agora bloqueia após AXES_FAILURE_LIMIT
    tentativas com senha errada, mesmo que a senha correta seja
    enviada depois."""

    def setUp(self):
        self.motorista = _criar_motorista('motoristaH')

    def test_bloqueia_apos_tentativas_repetidas_de_senha_errada(self):
        login_url = reverse('login')
        for _ in range(3):
            self.client.post(login_url, {'username': 'motoristaH', 'password': 'senha-errada'})

        response = self.client.post(login_url, {'username': 'motoristaH', 'password': 'senha-teste-123'})
        self.assertEqual(response.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)


class ChecklistExportCSVStreamingTests(TestCase):
    """Regressão: a exportação de CSV carregava a queryset inteira em
    memória via HttpResponse. Agora usa StreamingHttpResponse, gerando
    linha por linha."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='CSV1A23', marca='Ford', modelo='Cargo',
            ano=2021, renavam='11122233344',
        )
        self.gestor = _criar_motorista('gestor4', is_patrao=True)
        Checklist.objects.create(
            veiculo=self.veiculo, km_atual=1000,
            latitude=-23.55, longitude=-46.63,
        )

    def test_export_e_streaming_e_contem_cabecalho_e_linha(self):
        from django.http import StreamingHttpResponse

        self.client.login(username='gestor4', password='senha-teste-123')
        response = self.client.get(reverse('checklist_export_csv'))
        self.assertIsInstance(response, StreamingHttpResponse)
        conteudo = b''.join(response.streaming_content).decode('utf-8-sig')
        self.assertIn('Data,Tipo,Motorista,Veículo,Placa,KM', conteudo)
        self.assertIn('CSV1A23', conteudo)


@override_settings(EMAIL_HOST_USER='remetente@exemplo.com')
class ChecklistAvariaEmailTests(TestCase):
    """Regressão: o e-mail de avaria só disparava para os 10 itens
    marcados como críticos — qualquer um dos outros 18 itens falhando
    criava a Ocorrência mas não avisava ninguém por e-mail."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # o dedup por checklist.pk usa cache real, não isolado entre testes
        self.veiculo = Veiculo.objects.create(
            placa='EML1A23', marca='Ford', modelo='Cargo',
            ano=2022, renavam='55566677788',
        )
        self.motorista = _criar_motorista('motorista_email')
        self.gestor = _criar_motorista('gestor_email', is_patrao=True)
        self.gestor.email = 'gestor@exemplo.com'
        self.gestor.save()

    def _dados_base(self, campos_ok=()):
        dados = {
            'veiculo': self.veiculo.pk, 'nome_checklist': 'Checklist Email',
            'km_atual': 5000, 'nivel_combustivel': 'Cheio', 'tipo': 'geral',
            'latitude': -23.55, 'longitude': -46.63,
            'itens_tocados': ','.join(CAMPOS_AVARIA),
            'fotos-TOTAL_FORMS': '0', 'fotos-INITIAL_FORMS': '0',
            'fotos-MIN_NUM_FORMS': '0', 'fotos-MAX_NUM_FORMS': '1000',
        }
        for campo in campos_ok:
            dados[campo] = 'on'
        return dados

    def test_email_enviado_para_avaria_nao_critica(self):
        campos_ok = [c for c in CAMPOS_AVARIA if c != 'carga']
        self.client.login(username='motorista_email', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(campos_ok))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('gestor@exemplo.com', mail.outbox[0].to)
        self.assertTrue(mail.outbox[0].subject.startswith('[Aviso]'))

    def test_email_com_item_critico_usa_assunto_de_alerta(self):
        campos_ok = [c for c in CAMPOS_AVARIA if c != 'farol']
        self.client.login(username='motorista_email', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(campos_ok))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].subject.startswith('[ALERTA]'))

    def test_email_nao_enviado_sem_avaria(self):
        self.client.login(username='motorista_email', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(CAMPOS_AVARIA))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_HOST_USER='')
    def test_email_nao_enviado_sem_configuracao_smtp(self):
        self.client.login(username='motorista_email', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(()))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_dedup_nao_reenvia_para_o_mesmo_checklist(self):
        checklist = Checklist.objects.create(
            veiculo=self.veiculo, motorista=self.motorista.perfil_funcionario,
            km_atual=1000, latitude=-23.55, longitude=-46.63,
        )
        _enviar_email_avaria(checklist)
        _enviar_email_avaria(checklist)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(EMAIL_HOST_USER='remetente@exemplo.com')
class VeiculoAutoBloqueioTests(TestCase):
    """Regressão: item crítico de segurança reprovado no checklist não
    bloqueava o veículo — ele continuava liberado para despacho até um
    gestor notar e bloquear manualmente."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.veiculo = Veiculo.objects.create(
            placa='BLK1A23', marca='Scania', modelo='R450',
            ano=2022, renavam='66677788899',
        )
        self.motorista = _criar_motorista('motorista_bloqueio')
        self.gestor = _criar_motorista('gestor_bloqueio', is_patrao=True)
        self.gestor.email = 'gestor@exemplo.com'
        self.gestor.save()

    def _dados_base(self, campos_ok=()):
        dados = {
            'veiculo': self.veiculo.pk, 'nome_checklist': 'Checklist Bloqueio',
            'km_atual': 3000, 'nivel_combustivel': 'Cheio', 'tipo': 'geral',
            'latitude': -23.55, 'longitude': -46.63,
            'itens_tocados': ','.join(CAMPOS_AVARIA),
            'fotos-TOTAL_FORMS': '0', 'fotos-INITIAL_FORMS': '0',
            'fotos-MIN_NUM_FORMS': '0', 'fotos-MAX_NUM_FORMS': '1000',
        }
        for campo in campos_ok:
            dados[campo] = 'on'
        return dados

    def test_item_critico_falho_bloqueia_veiculo_automaticamente(self):
        campos_ok = [c for c in CAMPOS_AVARIA if c != 'farol']
        self.client.login(username='motorista_bloqueio', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(campos_ok))
        self.assertEqual(response.status_code, 302)

        self.veiculo.refresh_from_db()
        self.assertTrue(self.veiculo.bloqueado)
        self.assertTrue(self.veiculo.bloqueio_automatico)
        self.assertIn('Faróis', self.veiculo.motivo_bloqueio)

    def test_apenas_item_nao_critico_falho_nao_bloqueia(self):
        campos_ok = [c for c in CAMPOS_AVARIA if c != 'carga']
        self.client.login(username='motorista_bloqueio', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(campos_ok))
        self.assertEqual(response.status_code, 302)

        self.veiculo.refresh_from_db()
        self.assertFalse(self.veiculo.bloqueado)
        self.assertFalse(self.veiculo.bloqueio_automatico)

    def test_veiculo_bloqueado_rejeita_novo_checklist(self):
        self.veiculo.bloqueado = True
        self.veiculo.motivo_bloqueio = 'Teste manual'
        self.veiculo.save()

        self.client.login(username='motorista_bloqueio', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(CAMPOS_AVARIA))
        self.assertEqual(response.status_code, 200)  # form_invalid, não redireciona
        self.assertFalse(Checklist.objects.filter(veiculo=self.veiculo).exists())


class OcorrenciaListViewFiltroPadraoTests(TestCase):
    """Regressão: a lista abria mostrando abertas e resolvidas juntas,
    ordenadas da mais recente pra mais antiga — uma ocorrência esquecida
    há semanas ficava enterrada nas últimas páginas."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='LST1A23', marca='Ford', modelo='Cargo',
            ano=2021, renavam='55566677788',
        )
        self.gestor = _criar_motorista('gestor_lista', is_patrao=True)

        def criar_oc(dias_atras, status):
            dados = {c: True for c in CAMPOS_AVARIA}
            dados['farol'] = False
            checklist = Checklist.objects.create(
                veiculo=self.veiculo, km_atual=1000,
                latitude=-23.55, longitude=-46.63, **dados,
            )
            oc = OcorrenciaAvaria.objects.create(
                checklist=checklist, veiculo=self.veiculo, descricao='Faróis', status=status,
            )
            OcorrenciaAvaria.objects.filter(pk=oc.pk).update(
                criada_em=timezone.now() - timedelta(days=dias_atras)
            )
            return oc

        self.antiga_aberta = criar_oc(10, 'aguardando')
        self.recente_aberta = criar_oc(1, 'em_reparo')
        self.antiga_resolvida = criar_oc(20, 'resolvida')

    def test_sem_filtro_esconde_resolvidas_e_ordena_mais_antiga_primeiro(self):
        self.client.login(username='gestor_lista', password='senha-teste-123')
        response = self.client.get(reverse('ocorrencias_list'))
        ocorrencias = list(response.context['ocorrencias'])
        self.assertNotIn(self.antiga_resolvida, ocorrencias)
        self.assertEqual(ocorrencias[0], self.antiga_aberta)
        self.assertEqual(ocorrencias[1], self.recente_aberta)
        self.assertTrue(response.context['filtro_padrao_ativo'])

    def test_status_vazio_explicito_mostra_tudo(self):
        self.client.login(username='gestor_lista', password='senha-teste-123')
        response = self.client.get(reverse('ocorrencias_list'), {'status': ''})
        ocorrencias = list(response.context['ocorrencias'])
        self.assertIn(self.antiga_resolvida, ocorrencias)
        self.assertFalse(response.context['filtro_padrao_ativo'])

    def test_filtro_explicito_aguardando_mantem_ordenacao_mais_antiga_primeiro(self):
        self.client.login(username='gestor_lista', password='senha-teste-123')
        response = self.client.get(reverse('ocorrencias_list'), {'status': 'aguardando'})
        ocorrencias = list(response.context['ocorrencias'])
        self.assertEqual(ocorrencias, [self.antiga_aberta])

    def test_filtro_resolvida_mostra_so_resolvidas(self):
        self.client.login(username='gestor_lista', password='senha-teste-123')
        response = self.client.get(reverse('ocorrencias_list'), {'status': 'resolvida'})
        ocorrencias = list(response.context['ocorrencias'])
        self.assertEqual(ocorrencias, [self.antiga_resolvida])

    def test_kpi_atrasadas_conta_apenas_abertas_alem_do_limite(self):
        self.client.login(username='gestor_lista', password='senha-teste-123')
        response = self.client.get(reverse('ocorrencias_list'))
        # antiga_aberta (10 dias, aguardando) conta; recente_aberta (1 dia) não;
        # antiga_resolvida (20 dias, mas resolvida) não conta.
        self.assertEqual(response.context['total_atrasadas'], 1)


class OcorrenciaAvariaPropriedadesTests(TestCase):
    """Regressão: a lista de ocorrências não tinha nenhum sinal de há
    quanto tempo uma ocorrência está aberta nem de gravidade — tudo
    parecia igual, o que contribuía pra elas ficarem esquecidas."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='PRP1A23', marca='Ford', modelo='Cargo',
            ano=2021, renavam='44455566677',
        )

    def _criar_checklist(self, **campos_falhos):
        dados = {c: True for c in CAMPOS_AVARIA}
        dados.update(campos_falhos)
        return Checklist.objects.create(
            veiculo=self.veiculo, km_atual=1000,
            latitude=-23.55, longitude=-46.63, **dados,
        )

    def test_dias_em_aberto_conta_a_partir_da_criacao(self):
        checklist = self._criar_checklist(farol=False)
        oc = OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo, descricao='Faróis', status='aguardando',
        )
        OcorrenciaAvaria.objects.filter(pk=oc.pk).update(criada_em=timezone.now() - timedelta(days=5))
        oc.refresh_from_db()
        self.assertEqual(oc.dias_em_aberto, 5)

    def test_ocorrencia_resolvida_congela_contagem_na_data_de_resolucao(self):
        checklist = self._criar_checklist(farol=False)
        oc = OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo, descricao='Faróis', status='resolvida',
        )
        agora = timezone.now()
        OcorrenciaAvaria.objects.filter(pk=oc.pk).update(
            criada_em=agora - timedelta(days=20), atualizada_em=agora - timedelta(days=18),
        )
        oc.refresh_from_db()
        self.assertEqual(oc.dias_em_aberto, 2)  # congelado em 2, não continua contando até "agora"

    def test_atrasada_true_apos_limite_de_dias(self):
        from frota.utils import OCORRENCIA_DIAS_ALERTA
        checklist = self._criar_checklist(farol=False)
        oc = OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo, descricao='Faróis', status='aguardando',
        )
        OcorrenciaAvaria.objects.filter(pk=oc.pk).update(
            criada_em=timezone.now() - timedelta(days=OCORRENCIA_DIAS_ALERTA)
        )
        oc.refresh_from_db()
        self.assertTrue(oc.atrasada)

    def test_atrasada_false_quando_recente_ou_resolvida(self):
        checklist = self._criar_checklist(farol=False)
        recente = OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo, descricao='Faróis', status='aguardando',
        )
        self.assertFalse(recente.atrasada)

        checklist2 = self._criar_checklist(farol=False)
        antiga_resolvida = OcorrenciaAvaria.objects.create(
            checklist=checklist2, veiculo=self.veiculo, descricao='Faróis', status='resolvida',
        )
        OcorrenciaAvaria.objects.filter(pk=antiga_resolvida.pk).update(
            criada_em=timezone.now() - timedelta(days=30)
        )
        antiga_resolvida.refresh_from_db()
        self.assertFalse(antiga_resolvida.atrasada)  # resolvida nunca é "atrasada"

    def test_critica_true_para_item_de_seguranca(self):
        checklist = self._criar_checklist(pneus=False)
        oc = OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo, descricao='Pneus', status='aguardando',
        )
        self.assertTrue(oc.critica)

    def test_critica_false_para_item_nao_critico(self):
        checklist = self._criar_checklist(carga=False)
        oc = OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo, descricao='Carga', status='aguardando',
        )
        self.assertFalse(oc.critica)


class OcorrenciaResolucaoDesbloqueioTests(TestCase):
    """Regressão: resolver a Ocorrência de avaria não desbloqueava o
    veículo — eram duas ações manuais e desconectadas. Agora, resolver a
    última ocorrência crítica em aberto desbloqueia sozinho, mas só quando
    o bloqueio foi automático (nunca sobrescreve uma decisão manual)."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='RES1A23', marca='Volvo', modelo='VM',
            ano=2021, renavam='77788899900',
        )
        self.motorista = _criar_motorista('motorista_resolucao')
        self.gestor = _criar_motorista('gestor_resolucao', is_patrao=True)

    def _criar_checklist_com_falha(self, **campos_falhos):
        dados = {c: True for c in CAMPOS_AVARIA}
        dados.update(campos_falhos)
        return Checklist.objects.create(
            veiculo=self.veiculo, motorista=self.motorista.perfil_funcionario,
            km_atual=1000, latitude=-23.55, longitude=-46.63,
            **dados,
        )

    def _criar_ocorrencia(self, checklist):
        from .models import OcorrenciaAvaria
        return OcorrenciaAvaria.objects.create(
            checklist=checklist, veiculo=self.veiculo,
            descricao='Item de teste', status='aguardando',
        )

    def _bloquear_automaticamente(self, checklist):
        self.veiculo.bloqueado = True
        self.veiculo.bloqueio_automatico = True
        self.veiculo.motivo_bloqueio = f'Bloqueio automático — checklist #{checklist.pk}'
        self.veiculo.save()

    def _resolver(self, ocorrencia):
        self.client.login(username='gestor_resolucao', password='senha-teste-123')
        return self.client.post(
            reverse('ocorrencia_update', args=[ocorrencia.pk]),
            {'status': 'resolvida', 'nota_resolucao': 'Reparo concluído em oficina.'},
        )

    def test_formulario_inline_da_lista_exige_nota_de_resolucao(self):
        """O mini-formulário inline (list de ocorrências) envia exatamente
        {status, nota_resolucao} — confirma que a exigência de nota
        continua valendo mesmo por esse caminho mais curto."""
        checklist = self._criar_checklist_com_falha(farol=False)
        ocorrencia = self._criar_ocorrencia(checklist)
        self.client.login(username='gestor_resolucao', password='senha-teste-123')
        response = self.client.post(
            reverse('ocorrencia_update', args=[ocorrencia.pk]),
            {'status': 'resolvida', 'nota_resolucao': ''},
        )
        self.assertEqual(response.status_code, 200)  # form_invalid, não redireciona
        ocorrencia.refresh_from_db()
        self.assertEqual(ocorrencia.status, 'aguardando')

    def test_resolver_unica_ocorrencia_critica_desbloqueia(self):
        checklist = self._criar_checklist_com_falha(farol=False)
        ocorrencia = self._criar_ocorrencia(checklist)
        self._bloquear_automaticamente(checklist)

        self._resolver(ocorrencia)

        self.veiculo.refresh_from_db()
        self.assertFalse(self.veiculo.bloqueado)
        self.assertFalse(self.veiculo.bloqueio_automatico)

    def test_resolver_uma_de_duas_ocorrencias_criticas_mantem_bloqueado(self):
        checklist1 = self._criar_checklist_com_falha(farol=False)
        checklist2 = self._criar_checklist_com_falha(pneus=False)
        ocorrencia1 = self._criar_ocorrencia(checklist1)
        ocorrencia2 = self._criar_ocorrencia(checklist2)
        self._bloquear_automaticamente(checklist1)

        self._resolver(ocorrencia1)
        self.veiculo.refresh_from_db()
        self.assertTrue(self.veiculo.bloqueado)  # ocorrencia2 ainda aberta

        self._resolver(ocorrencia2)
        self.veiculo.refresh_from_db()
        self.assertFalse(self.veiculo.bloqueado)

    def test_resolver_ocorrencia_nao_critica_com_critica_aberta_mantem_bloqueado(self):
        checklist_critico = self._criar_checklist_com_falha(freio_mao=False)
        checklist_leve = self._criar_checklist_com_falha(carga=False)
        ocorrencia_critica = self._criar_ocorrencia(checklist_critico)
        ocorrencia_leve = self._criar_ocorrencia(checklist_leve)
        self._bloquear_automaticamente(checklist_critico)

        self._resolver(ocorrencia_leve)

        self.veiculo.refresh_from_db()
        self.assertTrue(self.veiculo.bloqueado)

    def test_bloqueio_manual_nao_e_desfeito_por_resolucao_automatica(self):
        checklist = self._criar_checklist_com_falha(bateria=False)
        ocorrencia = self._criar_ocorrencia(checklist)
        # Gestor bloqueia manualmente (bloqueio_automatico=False)
        self.veiculo.bloqueado = True
        self.veiculo.bloqueio_automatico = False
        self.veiculo.motivo_bloqueio = 'Aguardando troca de pneu agendada'
        self.veiculo.save()

        self._resolver(ocorrencia)

        self.veiculo.refresh_from_db()
        self.assertTrue(self.veiculo.bloqueado)
        self.assertEqual(self.veiculo.motivo_bloqueio, 'Aguardando troca de pneu agendada')

    def test_liberar_manual_limpa_bloqueio_automatico(self):
        checklist = self._criar_checklist_com_falha(vazamentos=False)
        self._bloquear_automaticamente(checklist)

        self.client.login(username='gestor_resolucao', password='senha-teste-123')
        self.client.post(
            reverse('veiculo_bloqueio', args=[self.veiculo.pk]),
            {'action': 'liberar'},
        )

        self.veiculo.refresh_from_db()
        self.assertFalse(self.veiculo.bloqueado)
        self.assertFalse(self.veiculo.bloqueio_automatico)


class ChecklistTouchedItemsValidationTests(TestCase):
    """Regressão: o checklist podia ser enviado sem que o motorista tivesse
    revisado nenhum dos 28 itens — só o GPS travava o envio. Como todo
    campo nasce False (= avaria), itens nunca tocados viravam avaria
    automática. Agora o servidor exige que todos os itens constem em
    itens_tocados antes de aceitar o envio (a tela de edição não é afetada
    — usa ChecklistForm, não ChecklistCreateForm)."""

    def setUp(self):
        self.veiculo = Veiculo.objects.create(
            placa='TCH1A23', marca='Iveco', modelo='Daily',
            ano=2023, renavam='88899900011',
        )
        self.motorista = _criar_motorista('motorista_tocados')

    def _dados_base(self, itens_tocados=None):
        dados = {
            'veiculo': self.veiculo.pk, 'nome_checklist': 'Checklist Revisão',
            'km_atual': 2000, 'nivel_combustivel': 'Cheio', 'tipo': 'geral',
            'latitude': -23.55, 'longitude': -46.63,
            'fotos-TOTAL_FORMS': '0', 'fotos-INITIAL_FORMS': '0',
            'fotos-MIN_NUM_FORMS': '0', 'fotos-MAX_NUM_FORMS': '1000',
        }
        if itens_tocados is not None:
            dados['itens_tocados'] = itens_tocados
        return dados

    def test_envio_sem_itens_tocados_e_rejeitado(self):
        self.client.login(username='motorista_tocados', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base())
        self.assertEqual(response.status_code, 200)  # form_invalid
        self.assertIn('Revise todos os itens', str(response.context['form'].errors))
        self.assertFalse(Checklist.objects.filter(veiculo=self.veiculo).exists())

    def test_envio_com_itens_parciais_e_rejeitado_nomeando_faltantes(self):
        parcial = ','.join(CAMPOS_AVARIA[:5])
        self.client.login(username='motorista_tocados', password='senha-teste-123')
        response = self.client.post(reverse('checklist_add'), self._dados_base(parcial))
        self.assertEqual(response.status_code, 200)
        erros = str(response.context['form'].errors)
        self.assertIn('Revise todos os itens', erros)

    def test_envio_com_todos_os_itens_tocados_e_aceito(self):
        self.client.login(username='motorista_tocados', password='senha-teste-123')
        response = self.client.post(
            reverse('checklist_add'), self._dados_base(','.join(CAMPOS_AVARIA))
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Checklist.objects.filter(veiculo=self.veiculo).exists())

    def test_edicao_de_checklist_nao_exige_itens_tocados(self):
        gestor = _criar_motorista('gestor_tocados', is_patrao=True)
        checklist = Checklist.objects.create(
            veiculo=self.veiculo, motorista=self.motorista.perfil_funcionario,
            km_atual=2500, latitude=-23.55, longitude=-46.63,
            **{c: True for c in CAMPOS_AVARIA},
        )
        self.client.login(username='gestor_tocados', password='senha-teste-123')
        response = self.client.post(
            reverse('checklist_update', args=[checklist.pk]),
            {
                'veiculo': self.veiculo.pk, 'nome_checklist': 'Editado',
                'km_atual': 2600, 'nivel_combustivel': 'Cheio', 'tipo': 'geral',
                'latitude': -23.55, 'longitude': -46.63,
                'fotos-TOTAL_FORMS': '0', 'fotos-INITIAL_FORMS': '0',
                'fotos-MIN_NUM_FORMS': '0', 'fotos-MAX_NUM_FORMS': '1000',
                **{c: 'on' for c in CAMPOS_AVARIA},
            },
        )
        self.assertEqual(response.status_code, 302)
        checklist.refresh_from_db()
        self.assertEqual(checklist.km_atual, 2600)


class SessionConfigTests(TestCase):
    """Regressão: a sessão expirava em ~28 min e fechava ao trocar de app
    (ex.: abrir a câmera pra foto de avaria), com risco real de perder um
    checklist em preenchimento. Agora dura 8h, renovando a cada requisição."""

    def test_sessao_dura_8_horas_e_nao_expira_ao_fechar_navegador(self):
        from django.conf import settings
        self.assertEqual(settings.SESSION_COOKIE_AGE, 28800)
        self.assertFalse(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
