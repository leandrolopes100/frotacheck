from django.urls import reverse_lazy, reverse
from django.contrib import messages

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
from .utils import get_filtro_avaria, get_filtro_ok

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
        qs_base = self.object_list
        total = qs_base.count()

        avarias_qs = qs_base.filter(get_filtro_avaria()).distinct() 
        total_avarias = avarias_qs.count()
        total_ok = total - total_avarias

        context['total_checklists'] = total
        context['total_avarias'] = total_avarias
        context['total_ok'] = total_ok
        context['saude_frota'] = round((total_ok / total * 100), 1) if total > 0 else 0

        checklist_com_avaria = qs_base.filter(get_filtro_avaria()).first()
        if checklist_com_avaria:
            context['alerta_critico'] = True
            context['ultimo_veiculo_avaria'] = checklist_com_avaria.veiculo.placa

        return context

    def get_queryset(self):
        user = self.request.user
        queryset = Checklist.objects.select_related('veiculo', 'motorista').order_by('-data_realizada')

        termo_busca = self.request.GET.get('veiculo')
        motorista = self.request.GET.get('motorista')
        status = self.request.GET.get('status')

        if termo_busca:
            queryset = queryset.filter(
                Q(veiculo__modelo__icontains=termo_busca) |
                Q(veiculo__placa__icontains=termo_busca)
            )

        if motorista:
            queryset = queryset.filter(motorista__nome_completo__icontains=motorista)

        if status == 'avaria':
            queryset = queryset.filter(get_filtro_avaria())     
        elif status == 'ok':
            queryset = queryset.filter(**get_filtro_ok())   

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
  