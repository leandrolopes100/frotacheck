from django.urls import reverse_lazy, reverse
from django.contrib import messages

import os
from io import BytesIO

import qrcode
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Q
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView, View
)


from .forms import ChecklistForm, NovoFuncionarioForm, VeiculoForm
from .models import Checklist, FotoAvaria, Funcionario, Usuario, Veiculo

class GestorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_patrao

    def handle_no_permission(self):
        messages.error(self.request, "Acesso Negado: Apenas gestores podem realizar esta operação.")
        return redirect('checklist_list') 

# --- FORMSETS ---

FotoAvariaFormSet = inlineformset_factory(
    Checklist, 
    FotoAvaria, 
    fields=('descricao', 'imagem'), 
    extra=1, 
    can_delete=True
)

# --------------------------------------------------------------------------------------------------
# --- CHECKLIST VIEWS --------------------------------------------------------------------------------
class CheckListBaseView():
    model = Checklist
    form_class = ChecklistForm
    success_url = reverse_lazy('checklist_list')

class QrCodeMixin(object): 
    def get_initial(self):
        initial = super().get_initial()
        veiculo_id = self.request.GET.get('veiculo_id')
        if veiculo_id:
            initial['veiculo'] = veiculo_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        veiculo_id = self.request.GET.get('veiculo_id')
        if veiculo_id:
            context['veiculo_qr'] = Veiculo.objects.filter(id=veiculo_id).first()
        return context

class ChecklistListView(LoginRequiredMixin, CheckListBaseView, ListView):
    template_name = 'frota/checklist_list.html'
    context_object_name = 'checklists'
    paginate_by = 8

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs_base = self.get_queryset()
        total = qs_base.count()
        context['total_checklists'] = total

        # Filtro de avarias (mesma lógica sua)
        avarias_qs = qs_base.filter(
            Q(farol=False) | Q(lanterna=False) | Q(re_freio=False) | Q(piscas=False) |
            Q(pneus=False) | Q(amortecedor=False) | Q(bateria=False) | Q(oleo=False) |
            Q(arrefecimento_radiador=False) | Q(vazamentos=False) | Q(limpadores=False) |
            Q(vidros=False) | Q(retrovisor=False) | Q(estepe=False) | Q(macaco=False) |
            Q(chave_roda=False) | Q(lataria=False) | Q(buzina=False) | 
            Q(iluminacao_interna=False) | Q(bancos=False) | Q(tapetes=False) | 
            Q(freio_mao=False) | Q(ar_condicionado=False) | Q(som=False) | Q(teto=False)
        ).distinct()

        context['total_avarias'] = avarias_qs.count()
        context['total_ok'] = total - context['total_avarias']
        context['saude_frota'] = round((context['total_ok'] / total * 100), 1) if total > 0 else 0
        
        ultimo_checklist = qs_base.first()
        if ultimo_checklist:
            context['alerta_critico'] = ultimo_checklist.tem_avaria 
            context['ultimo_veiculo_avaria'] = ultimo_checklist.veiculo.placa
            
        return context

    def get_queryset(self):
        user = self.request.user
        queryset = Checklist.objects.select_related('veiculo', 'motorista').order_by('-data_realizada')

        motorista = self.request.GET.get('motorista')
        status = self.request.GET.get('status')
        termo_busca = self.request.GET.get('veiculo') 

        if termo_busca:
            queryset = queryset.filter(Q(veiculo__modelo__icontains=termo_busca) | 
                                    Q(veiculo__placa__icontains=termo_busca))
            
        if motorista:
            queryset = queryset.filter(Q(motorista__nome_completo__icontains=motorista))

        if status == 'avaria':
            # Filtra onde QUALQUER um desses campos for False
            queryset = queryset.filter(
                Q(farol=False) | Q(lanterna=False) | Q(re_freio=False) | Q(piscas=False) |
                Q(pneus=False) | Q(amortecedor=False) | Q(bateria=False) | Q(oleo=False) |
                Q(arrefecimento_radiador=False) | Q(vazamentos=False) | Q(limpadores=False) |
                Q(vidros=False) | Q(retrovisor=False) | Q(estepe=False) | Q(macaco=False) |
                Q(chave_roda=False) | Q(lataria=False) | Q(buzina=False) | 
                Q(iluminacao_interna=False) | Q(bancos=False) | Q(tapetes=False) | 
                Q(freio_mao=False) | Q(ar_condicionado=False) | Q(som=False) | Q(teto=False)
            )
        elif status == 'ok':
            queryset = queryset.filter(
                farol=True, lanterna=True, re_freio=True, piscas=True,
                pneus=True, amortecedor=True, bateria=True, oleo=True,
                arrefecimento_radiador=True, vazamentos=True, limpadores=True,
                vidros=True, retrovisor=True, estepe=True, macaco=True,
                chave_roda=True, lataria=True, buzina=True, 
                iluminacao_interna=True, bancos=True, tapetes=True, 
                freio_mao=True, ar_condicionado=True, som=True, teto=True
            )
        
        if user.is_superuser or user.is_patrao:
            return queryset
        return queryset.filter(motorista__usuario=user)


class ChecklistCreateView(LoginRequiredMixin, QrCodeMixin, CheckListBaseView, CreateView):
    template_name = 'frota/checklist_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['fotos'] = FotoAvariaFormSet(self.request.POST, self.request.FILES, prefix='fotos')
        else:
            context['fotos'] = FotoAvariaFormSet(prefix='fotos')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        fotos = context['fotos']
        
        if not hasattr(self.request.user, 'perfil_funcionario'):
            form.add_error(None, "Seu usuário não possui um perfil de Funcionário vinculado.")
            return self.form_invalid(form)

        form.instance.motorista = self.request.user.perfil_funcionario

        if form.is_valid() and fotos.is_valid():
            with transaction.atomic():
                self.object = form.save()
                fotos.instance = self.object
                fotos.save()
            return redirect(self.success_url)
        
        return self.render_to_response(self.get_context_data(form=form, fotos=fotos))

class CheckListDetailView(LoginRequiredMixin, CheckListBaseView, DetailView):
    template_name = 'frota/checklist_detail.html'
    
    def get(self, request, pk):
        checklist = get_object_or_404(Checklist, pk=pk)
        context = { 'checklist': checklist}
        return render(request, self.template_name, context)
    
class CheckListUpdateView(LoginRequiredMixin, GestorRequiredMixin, UpdateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = 'frota/checklist_update.html'
    success_url = reverse_lazy('checklist_list')

    def test_func(self):
        return self.request.user.is_patrao

class CheckListDeleteView(LoginRequiredMixin, GestorRequiredMixin, DeleteView):
    model = Checklist
    template_name = 'frota/checklist_delete.html'
    success_url = reverse_lazy('checklist_list')
    
# --------------------------------------------------------------------------------------------------
# --- VEÍCULO VIEWS --------------------------------------------------------------------------------

class VeiculoBaseView():
    model = Veiculo
    form_class = VeiculoForm
    success_url = reverse_lazy('veiculos_list')

class QRCodeGeneratorView(LoginRequiredMixin, View):
    def get(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk)
        path_checklist = reverse('checklist_add') 
        url_destino = request.build_absolute_uri(f"{path_checklist}?veiculo_id={veiculo.id}")
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url_destino) 
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return HttpResponse(buffer.getvalue(), content_type="image/png")

class VeiculoEtiquetaListView(LoginRequiredMixin, ListView):
    model = Veiculo
    template_name = 'veiculo/etiquetas_list.html'
    context_object_name = 'veiculos'

    def get_queryset(self):
        return Veiculo.objects.all().order_by('modelo')

class VeiculoListView(LoginRequiredMixin, VeiculoBaseView, ListView):
    model = Veiculo
    template_name = 'veiculo/veiculo_list.html'
    context_object_name = 'veiculos'
    paginate_by = 9

    def get_queryset(self):
        queryset = Veiculo.objects.all()
        busca = self.request.GET.get('busca')

        if busca:
            queryset = queryset.filter(
                Q(placa__icontains=busca) |
                Q(marca__icontains=busca) |
                Q(modelo__icontains=busca)
            )

        return queryset.order_by('-ativo', '-id')

class VeiculoCreateView(LoginRequiredMixin, VeiculoBaseView, CreateView):
    template_name = 'veiculo/veiculo_form.html'

class VeiculoDetailView(LoginRequiredMixin, VeiculoBaseView, DetailView):
    model = Veiculo
    template_name = 'veiculo/veiculo_detail.html'
    context_object_name = 'veiculo'

class VeiculoUpdateView(LoginRequiredMixin, UpdateView):
        model = Veiculo
        form_class = VeiculoForm
        template_name = 'veiculo/veiculo_form.html'
        success_url = reverse_lazy('veiculos_list')
    
class VeiculoDeleteView(LoginRequiredMixin, DeleteView):
    model = Veiculo
    template_name = 'veiculo/veiculo_delete.html'
    context_object_name = 'veiculo'
    success_url = reverse_lazy('veiculos_list')

class VeiculoAlternarStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk)
        veiculo.ativo = not veiculo.ativo
        veiculo.save()
        return redirect('veiculos_list')
    
# -------------------------------------------------------------------------------------------------
# --- FUNCIONÁRIO VIEWS --------------------------------------------------------------------------------

class FuncionarioBaseView():
    model = Funcionario
    form_class = NovoFuncionarioForm
    success_url = reverse_lazy('funcionario_list')

class FuncionarioListView(LoginRequiredMixin, FuncionarioBaseView, ListView):
    template_name = 'funcionario/funcionario_list.html'
    context_object_name = 'funcionarios'  
    paginate_by = 9
    
    def get_queryset(self):
        queryset = super().get_queryset()
        busca = self.request.GET.get('busca')
        if busca:
            queryset = queryset.filter(nome_completo__icontains=busca)
        return queryset

class FuncionarioCreateView(LoginRequiredMixin, CreateView):
    model = Funcionario
    form_class = NovoFuncionarioForm
    template_name = 'funcionario/funcionario_form.html'
    success_url = reverse_lazy('funcionario_list')

    def form_valid(self, form):
        try:
            with transaction.atomic():
                user = Usuario.objects.create_user(
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password'],
                    email=form.cleaned_data.get('email', ''),
                    is_motorista=True)

                funcionario = form.save(commit=False)
                funcionario.usuario = user
                funcionario.cadastrado_por = self.request.user
                funcionario.save()

            messages.success(self.request, "Funcionário cadastrado com sucesso.")
            return redirect(self.success_url)

        except Exception as e:
            form.add_error(None, "Erro ao cadastrar funcionário. Tente novamente.")
            return self.form_invalid(form)

class FuncionarioUpdateView(LoginRequiredMixin, FuncionarioBaseView, UpdateView):
    template_name = 'funcionario/funcionario_update.html'

class FuncionarioDeleteView(LoginRequiredMixin, FuncionarioBaseView, DeleteView):
    template_name = 'funcionario/funcionario_delete.html'
  