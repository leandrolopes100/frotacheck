from django import forms
from django.forms import inlineformset_factory
from .models import Checklist, Usuario, Funcionario, FotoAvaria, Veiculo

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
            'observacoes': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': 'Descreva detalhes sobre o estado do veículo...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Aplica classes Tailwind automaticamente em campos que não são checkbox
        for name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'w-full rounded-2xl border-slate-200 bg-slate-50 focus:border-blue-500 focus:ring-blue-500'
                })


# --------------------------------------------------------------------------------------------------
# --- FOTO AVARIA FORMS --------------------------------------------------------------------------------

FotoAvariaFormSet = inlineformset_factory(
    Checklist, 
    FotoAvaria,
    fields=('descricao', 'imagem'),
    extra=1,
    can_delete=True,
    widgets={
        'descricao': forms.TextInput(attrs={
            'class':'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-white shadow-sm focus:ring-blue-500',
            'placeholder': 'Ex: Risco na porta lateral'
        }),
        'imagem': forms.FileInput(attrs={
            'class': 'block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:bg-blue-50 file:text-blue-700'
        })
    }
)

# --------------------------------------------------------------------------------------------------
# --- FUNCIONÁRIO FORMS --------------------------------------------------------------------------------

class NovoFuncionarioForm(forms.ModelForm):
    username = forms.CharField(
        label="Usuário (Login)", 
        widget=forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'})
    )
    password = forms.CharField(
        label="Senha Inicial", 
        widget=forms.PasswordInput(attrs={'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'})
    )
    email = forms.EmailField(
        label="E-mail", 
        widget=forms.EmailInput(attrs={'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'})
    )

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
            'validade_cnh': forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'nome_completo': forms.TextInput(attrs={'placeholder': 'Ex: João', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'cpf': forms.TextInput(attrs={'placeholder': '000.000.000-00', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'numero_cnh': forms.TextInput(attrs={'placeholder': '06966757801','class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'cargo': forms.Select(attrs={'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'cnh_impressa': forms.FileInput(attrs={'class': 'mt-1 block w-full text-sm text-slate-500 file:rounded-xl file:border-0 file:bg-blue-50 file:px-4 file:py-2'})
        }



# --------------------------------------------------------------------------------------------------
# --- VEÍCULO FORMS --------------------------------------------------------------------------------

class VeiculoForm(forms.ModelForm):
    class Meta:
        model = Veiculo
        fields = ['placa', 'marca', 'modelo', 'ano', 'renavam', 'documento_impresso', 'fipe', 'foto']
        widgets = {
            'placa': forms.TextInput(attrs={'placeholder': 'ABC1D23', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'marca': forms.TextInput(attrs={'placeholder': 'Ex: Toyota', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'modelo': forms.TextInput(attrs={'placeholder': 'Ex: Hilux', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'ano': forms.TextInput(attrs={'placeholder': '2024', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'renavam': forms.TextInput(attrs={'placeholder': '18976898765','class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'fipe': forms.TextInput(attrs={'placeholder': 'Valor de mercado', 'class': 'mt-1 block w-full rounded-xl border-slate-300 p-3 border bg-slate-50/50'}),
            'foto': forms.FileInput(attrs={'class': 'mt-1 block w-full text-sm text-slate-500 file:rounded-xl file:border-0 file:bg-blue-50 file:px-4 file:py-2'}),
            'documento_impresso': forms.FileInput(attrs={'class': 'mt-1 block w-full text-sm text-slate-500 file:rounded-xl file:border-0 file:bg-blue-50 file:px-4 file:py-2'}),
        }

   
    def clean_renavam(self):
        renavam = self.cleaned_data.get("renavam")
        if renavam:
            # Remove espaços se houver
            renavam = renavam.strip()
            if len(renavam) not in [9, 11]:
                raise forms.ValidationError("Renavam deve conter 9 ou 11 dígitos.")
        return renavam
    
    def clean_placa(self):
        placa = self.cleaned_data.get("placa")
        if placa:
            # Converte para maiúsculo automaticamente e remove espaços
            placa = placa.strip().upper()
            if len(placa) != 7:
                raise forms.ValidationError("A placa deve conter exatamente 7 caracteres.")
        return placa