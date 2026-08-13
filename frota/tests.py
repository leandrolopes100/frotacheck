from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import ChecklistForm
from .models import Funcionario, Veiculo

Usuario = get_user_model()


def _criar_motorista(username, is_patrao=False):
    usuario = Usuario.objects.create_user(
        username=username, password='senha-teste-123',
        is_motorista=not is_patrao, is_patrao=is_patrao,
    )
    Funcionario.objects.create(
        usuario=usuario, nome_completo=f'Funcionario {username}',
        cpf='52998224725' if not is_patrao else '11144477735',
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
