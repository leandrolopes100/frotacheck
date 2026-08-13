import itertools
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import ChecklistForm
from .models import Abastecimento, Checklist, Funcionario, Veiculo

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
