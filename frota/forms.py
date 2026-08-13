from django import forms
from django.forms import inlineformset_factory
from .models import (
    Checklist, Usuario, Funcionario, FotoAvaria, Veiculo,
    OcorrenciaAvaria, OrdemManutencao, Abastecimento,
)


# ── Validadores de documentos brasileiros ─────────────────────────────────────

def _validar_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i, peso_base in enumerate([10, 11]):
        soma = sum(int(cpf[j]) * (peso_base - j) for j in range(peso_base - 1))
        if int(cpf[peso_base - 1]) != (soma * 10 % 11) % 10:
            return False
    return True


def _validar_renavam(renavam: str) -> bool:
    renavam = renavam.strip()
    if not renavam.isdigit():
        return False
    if len(renavam) == 9:
        renavam = '00' + renavam
    if len(renavam) != 11:
        return False
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(renavam[i]) * pesos[i] for i in range(10))
    resto = soma % 11
    digito = 0 if resto < 2 else 11 - resto
    return digito == int(renavam[10])

_INPUT = 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50 text-sm font-semibold focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 outline-none transition'
_SELECT = _INPUT
_FILE = 'mt-1 block w-full text-sm text-slate-500 file:rounded-xl file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-blue-700 file:font-semibold'


# ── CHECKLIST ─────────────────────────────────────────────────────────────────

class ChecklistForm(forms.ModelForm):
    class Meta:
        model = Checklist
        exclude = ['motorista', 'data_realizada']
        widgets = {
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
            'nome_checklist': forms.TextInput(attrs={'placeholder': 'Ex: Check-in Segunda-feira'}),
            'km_atual': forms.NumberInput(attrs={'placeholder': '000000'}),
            'nivel_combustivel': forms.Select(),
            'tipo': forms.Select(),
            'observacoes': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Descreva detalhes sobre o estado do veículo...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': _INPUT})

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('latitude') is None or cleaned_data.get('longitude') is None:
            raise forms.ValidationError(
                "Não foi possível confirmar sua localização. Permita o acesso ao "
                "GPS e tente novamente — o envio do checklist exige localização confirmada."
            )
        return cleaned_data


# ── FOTO AVARIA ───────────────────────────────────────────────────────────────

FotoAvariaFormSet = inlineformset_factory(
    Checklist, FotoAvaria,
    fields=('descricao', 'imagem'),
    extra=1, can_delete=True,
    widgets={
        'descricao': forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-white shadow-sm focus:ring-blue-500',
            'placeholder': 'Ex: Risco na porta lateral',
        }),
        'imagem': forms.FileInput(attrs={'class': _FILE}),
    },
)


# ── FUNCIONÁRIO ───────────────────────────────────────────────────────────────

class NovoFuncionarioForm(forms.ModelForm):
    username = forms.CharField(label="Usuário (Login)", widget=forms.TextInput(attrs={'class': _INPUT}))
    password = forms.CharField(label="Senha Inicial", widget=forms.PasswordInput(attrs={'class': _INPUT}))
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={'class': _INPUT}))

    def clean_nome_completo(self):
        nome = self.cleaned_data.get("nome_completo")
        if len(nome) < 5:
            raise forms.ValidationError("O nome deve ter pelo menos 5 caracteres.")
        return nome

    def clean_cpf(self):
        cpf = self.cleaned_data.get("cpf")
        if cpf:
            if not cpf.isdigit():
                raise forms.ValidationError("CPF deve conter apenas números.")
            if len(cpf) != 11:
                raise forms.ValidationError("CPF deve conter 11 dígitos.")
            if not _validar_cpf(cpf):
                raise forms.ValidationError("CPF inválido. Verifique os dígitos verificadores.")
        return cpf

    def clean_numero_cnh(self):
        numero_cnh = self.cleaned_data.get("numero_cnh")
        if numero_cnh:
            if not numero_cnh.isdigit():
                raise forms.ValidationError("Registro CNH deve conter apenas números.")
            if len(numero_cnh) != 11:
                raise forms.ValidationError("Registro CNH deve conter 11 dígitos.")
        return numero_cnh

    class Meta:
        model = Funcionario
        fields = ['nome_completo', 'cpf', 'numero_cnh', 'validade_cnh', 'cnh_impressa', 'cargo']
        widgets = {
            'validade_cnh': forms.DateInput(attrs={'type': 'date', 'class': _INPUT}),
            'nome_completo': forms.TextInput(attrs={'placeholder': 'Ex: João Silva', 'class': _INPUT}),
            'cpf': forms.TextInput(attrs={'placeholder': '00000000000', 'class': _INPUT}),
            'numero_cnh': forms.TextInput(attrs={'placeholder': '06966757801', 'class': _INPUT}),
            'cargo': forms.Select(attrs={'class': _SELECT}),
            'cnh_impressa': forms.FileInput(attrs={'class': _FILE}),
        }


# ── VEÍCULO ───────────────────────────────────────────────────────────────────

class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = [
            'placa', 'marca', 'modelo', 'ano', 'renavam',
            'documento_impresso', 'fipe', 'foto',
            'vencimento_crlv', 'vencimento_seguro', 'km_proxima_revisao',
        ]
        widgets = {
            'placa': forms.TextInput(attrs={'placeholder': 'ABC1D23', 'class': _INPUT}),
            'marca': forms.TextInput(attrs={'placeholder': 'Ex: Toyota', 'class': _INPUT}),
            'modelo': forms.TextInput(attrs={'placeholder': 'Ex: Hilux', 'class': _INPUT}),
            'ano': forms.TextInput(attrs={'placeholder': '2024', 'class': _INPUT}),
            'renavam': forms.TextInput(attrs={'placeholder': '18976898765', 'class': _INPUT}),
            'fipe': forms.TextInput(attrs={'placeholder': 'Valor de mercado', 'class': _INPUT}),
            'foto': forms.FileInput(attrs={'class': _FILE}),
            'documento_impresso': forms.FileInput(attrs={'class': _FILE}),
            'vencimento_crlv': forms.DateInput(attrs={'type': 'date', 'class': _INPUT}),
            'vencimento_seguro': forms.DateInput(attrs={'type': 'date', 'class': _INPUT}),
            'km_proxima_revisao': forms.NumberInput(attrs={'placeholder': 'Ex: 150000', 'class': _INPUT}),
        }

    def clean_renavam(self):
        renavam = self.cleaned_data.get("renavam")
        if renavam:
            renavam = renavam.strip()
            if not renavam.isdigit():
                raise forms.ValidationError("RENAVAM deve conter apenas números.")
            if len(renavam) not in [9, 11]:
                raise forms.ValidationError("RENAVAM deve conter 9 ou 11 dígitos.")
            if not _validar_renavam(renavam):
                raise forms.ValidationError("RENAVAM inválido. Verifique o dígito verificador.")
        return renavam

    def clean_placa(self):
        placa = self.cleaned_data.get("placa")
        if placa:
            placa = placa.strip().upper()
            if len(placa) != 7:
                raise forms.ValidationError("A placa deve conter exatamente 7 caracteres.")
        return placa


# ── OCORRÊNCIA DE AVARIA ──────────────────────────────────────────────────────

class OcorrenciaUpdateForm(forms.ModelForm):
    class Meta:
        model = OcorrenciaAvaria
        fields = ['status', 'nota_resolucao']
        widgets = {
            'status': forms.Select(attrs={'class': _SELECT}),
            'nota_resolucao': forms.Textarea(attrs={
                'rows': 3,
                'class': _INPUT,
                'placeholder': 'Descreva o que foi feito para resolver...',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('status') == 'resolvida' and not cleaned.get('nota_resolucao', '').strip():
            self.add_error('nota_resolucao', 'Informe o que foi feito para resolver a ocorrência.')
        return cleaned


# ── ORDEM DE MANUTENÇÃO ───────────────────────────────────────────────────────

class OrdemManutencaoForm(forms.ModelForm):
    class Meta:
        model = OrdemManutencao
        fields = ['veiculo', 'ocorrencia', 'descricao', 'responsavel', 'status', 'data_agendada', 'custo']
        widgets = {
            'veiculo': forms.Select(attrs={'class': _SELECT}),
            'ocorrencia': forms.Select(attrs={'class': _SELECT}),
            'descricao': forms.Textarea(attrs={
                'rows': 3, 'class': _INPUT,
                'placeholder': 'Descreva o serviço a ser realizado...',
            }),
            'responsavel': forms.TextInput(attrs={
                'class': _INPUT, 'placeholder': 'Nome da oficina ou mecânico responsável',
            }),
            'status': forms.Select(attrs={'class': _SELECT}),
            'data_agendada': forms.DateInput(attrs={'type': 'date', 'class': _INPUT}),
            'custo': forms.NumberInput(attrs={'class': _INPUT, 'placeholder': '0.00', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Só mostra ocorrências não resolvidas no dropdown
        self.fields['ocorrencia'].queryset = OcorrenciaAvaria.objects.exclude(
            status='resolvida'
        ).select_related('veiculo').order_by('-criada_em')
        self.fields['ocorrencia'].required = False
        self.fields['ocorrencia'].empty_label = "— Nenhuma (opcional) —"
        self.fields['custo'].required = False


# ── ABASTECIMENTO ─────────────────────────────────────────────────────────────

class AbastecimentoForm(forms.ModelForm):
    class Meta:
        model = Abastecimento
        fields = ['veiculo', 'motorista', 'data', 'km_atual', 'litros', 'valor_total', 'tipo_combustivel']
        widgets = {
            'veiculo': forms.Select(attrs={'class': _SELECT}),
            'motorista': forms.Select(attrs={'class': _SELECT}),
            'data': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': _INPUT}),
            'km_atual': forms.NumberInput(attrs={'class': _INPUT, 'placeholder': '000000'}),
            'litros': forms.NumberInput(attrs={'class': _INPUT, 'placeholder': '0.00', 'step': '0.01'}),
            'valor_total': forms.NumberInput(attrs={'class': _INPUT, 'placeholder': '0.00', 'step': '0.01'}),
            'tipo_combustivel': forms.Select(attrs={'class': _SELECT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motorista'].required = False
        self.fields['motorista'].empty_label = "— Selecionar motorista (opcional) —"

    def clean(self):
        cleaned_data = super().clean()
        litros = cleaned_data.get('litros')
        valor = cleaned_data.get('valor_total')
        if litros is not None and litros <= 0:
            self.add_error('litros', 'Litros deve ser maior que zero.')
        if valor is not None and valor <= 0:
            self.add_error('valor_total', 'Valor deve ser maior que zero.')
        return cleaned_data
