import csv
import json
from datetime import timedelta
from io import BytesIO

import qrcode
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.mail import send_mail
from django.db import transaction
from django.core.cache import cache
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from .forms import (
    AbastecimentoForm, ChecklistForm, NovoFuncionarioForm,
    OcorrenciaUpdateForm, OrdemManutencaoForm, VeiculoForm,
)
from .models import (
    Abastecimento, Checklist, FotoAvaria, Funcionario,
    OcorrenciaAvaria, OrdemManutencao, Usuario, Veiculo,
)
from .utils import (
    CAMPO_LABELS, CAMPOS_AVARIA, criar_ocorrencia_para_checklist,
    get_filtro_avaria, get_filtro_ok, get_itens_com_falha, tem_avaria_critica,
)


# ── MIXINS ────────────────────────────────────────────────────────────────────

class GestorRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_patrao

    def handle_no_permission(self):
        messages.error(self.request, "Acesso Negado: Apenas gestores podem realizar esta operação.")
        return redirect('checklist_list')


FotoAvariaFormSet = inlineformset_factory(
    Checklist, FotoAvaria,
    fields=('descricao', 'imagem'),
    extra=1, can_delete=True,
)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _enviar_email_avaria_critica(checklist):
    """Envia e-mail aos gestores quando itens críticos falham. Falha silenciosamente."""
    if not getattr(django_settings, 'EMAIL_HOST_USER', ''):
        return

    if not tem_avaria_critica(checklist):
        return

    chave_cache = f'email_avaria_critica_{checklist.pk}'
    if cache.get(chave_cache):
        return  # e-mail já enviado para este checklist nas últimas 2h
    cache.set(chave_cache, True, 60 * 60 * 2)

    gestores_emails = list(
        Usuario.objects.filter(is_patrao=True)
        .exclude(email='').values_list('email', flat=True)
    )
    if not gestores_emails:
        return

    itens = get_itens_com_falha(checklist)
    from .utils import ITENS_CRITICOS
    itens_criticos_falhos = [
        CAMPO_LABELS.get(c, c) for c in ITENS_CRITICOS
        if not getattr(checklist, c, True)
    ]

    corpo = (
        f"ALERTA DE SEGURANÇA — FrotaCheck\n\n"
        f"Veículo : {checklist.veiculo.marca} {checklist.veiculo.modelo} ({checklist.veiculo.placa})\n"
        f"Motorista: {checklist.motorista.nome_completo if checklist.motorista else 'N/A'}\n"
        f"Data    : {checklist.data_realizada.strftime('%d/%m/%Y %H:%M')}\n"
        f"KM      : {checklist.km_atual}\n\n"
        f"Itens CRÍTICOS com falha:\n"
        + "\n".join(f"  • {i}" for i in itens_criticos_falhos)
        + f"\n\nTodos os itens com falha:\n"
        + "\n".join(f"  • {i}" for i in itens)
        + f"\n\nObservações: {checklist.observacoes or 'Nenhuma'}\n\n"
        f"Acesse o sistema para acompanhar a ocorrência."
    )

    try:
        send_mail(
            subject=f"[ALERTA] Avaria crítica — {checklist.veiculo.placa}",
            message=corpo,
            from_email=getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'FrotaCheck'),
            recipient_list=gestores_emails,
            fail_silently=True,
        )
    except Exception:
        pass


# ── CHECKLIST VIEWS ───────────────────────────────────────────────────────────

class CheckListBaseView:
    model = Checklist
    form_class = ChecklistForm
    success_url = reverse_lazy('checklist_list')


class QrCodeMixin:
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

    def _qs_usuario(self):
        user = self.request.user
        qs = Checklist.objects.select_related('veiculo', 'motorista')
        if not (user.is_superuser or user.is_patrao):
            qs = qs.filter(motorista__usuario=user)
        return qs

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

        # Dados para gráficos
        qs_chart = self._qs_usuario()
        hoje = timezone.now().date()
        labels, data_ok, data_avarias = [], [], []
        for i in range(6, -1, -1):
            dia = hoje - timedelta(days=i)
            dia_qs = qs_chart.filter(data_realizada__date=dia)
            qtd_avarias = dia_qs.filter(get_filtro_avaria()).distinct().count()
            labels.append(dia.strftime('%d/%m'))
            data_avarias.append(qtd_avarias)
            data_ok.append(dia_qs.count() - qtd_avarias)

        context['chart_labels'] = json.dumps(labels)
        context['chart_ok'] = json.dumps(data_ok)
        context['chart_avarias'] = json.dumps(data_avarias)

        top_veiculos = (
            qs_chart.filter(get_filtro_avaria())
            .values('veiculo__modelo', 'veiculo__placa')
            .annotate(total=Count('id'))
            .order_by('-total')[:5]
        )
        context['top_veiculos_labels'] = json.dumps([
            f"{v['veiculo__modelo']} ({v['veiculo__placa']})" for v in top_veiculos
        ])
        context['top_veiculos_data'] = json.dumps([v['total'] for v in top_veiculos])

        # Alertas de CNH (gestores)
        if self.request.user.is_patrao or self.request.user.is_superuser:
            limite = hoje + timedelta(days=30)
            context['cnh_expiradas'] = Funcionario.objects.filter(validade_cnh__lt=hoje).count()
            context['cnh_vencendo'] = Funcionario.objects.filter(
                validade_cnh__gte=hoje, validade_cnh__lte=limite,
            ).count()

            # Alertas de documentos de veículos
            context['docs_vencidos'] = Veiculo.objects.filter(ativo=True).filter(
                Q(vencimento_crlv__lt=hoje) | Q(vencimento_seguro__lt=hoje)
            ).count()
            context['docs_vencendo'] = Veiculo.objects.filter(ativo=True).filter(
                Q(vencimento_crlv__gte=hoje, vencimento_crlv__lte=limite) |
                Q(vencimento_seguro__gte=hoje, vencimento_seguro__lte=limite)
            ).count()

            # Alerta de combustível crítico — 1 query via Subquery (sem N+1)
            ultimo_nivel_sq = Subquery(
                Checklist.objects.filter(veiculo=OuterRef('pk'))
                .order_by('-data_realizada')
                .values('nivel_combustivel')[:1]
            )
            context['combustivel_critico'] = (
                Veiculo.objects.filter(ativo=True)
                .annotate(ultimo_nivel=ultimo_nivel_sq)
                .filter(ultimo_nivel='Reserva')
                .count()
            )

            # Veículos sem inspeção hoje
            inspecionados_hoje_ids = set(
                Checklist.objects.filter(data_realizada__date=hoje)
                .values_list('veiculo_id', flat=True)
            )
            total_ativos = Veiculo.objects.filter(ativo=True).count()
            context['veiculos_sem_inspecao_hoje'] = max(
                0,
                total_ativos - Veiculo.objects.filter(
                    ativo=True, id__in=inspecionados_hoje_ids
                ).count()
            )

        return context

    def get_queryset(self):
        user = self.request.user
        queryset = Checklist.objects.select_related('veiculo', 'motorista').order_by('-data_realizada')

        termo = self.request.GET.get('veiculo')
        motorista = self.request.GET.get('motorista')
        status = self.request.GET.get('status')
        tipo = self.request.GET.get('tipo')

        if termo:
            queryset = queryset.filter(
                Q(veiculo__modelo__icontains=termo) | Q(veiculo__placa__icontains=termo)
            )
        if motorista:
            queryset = queryset.filter(motorista__nome_completo__icontains=motorista)
        if status == 'avaria':
            queryset = queryset.filter(get_filtro_avaria())
        elif status == 'ok':
            queryset = queryset.filter(**get_filtro_ok())
        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if user.is_superuser or user.is_patrao:
            return queryset
        return queryset.filter(motorista__usuario=user)


class ChecklistCreateView(LoginRequiredMixin, QrCodeMixin, CheckListBaseView, CreateView):
    template_name = 'frota/checklist_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'fotos' not in context:
            if self.request.POST:
                context['fotos'] = FotoAvariaFormSet(self.request.POST, self.request.FILES, prefix='fotos')
            else:
                context['fotos'] = FotoAvariaFormSet(prefix='fotos')
        return context

    def form_valid(self, form):
        fotos = FotoAvariaFormSet(self.request.POST, self.request.FILES, prefix='fotos')

        if not hasattr(self.request.user, 'perfil_funcionario'):
            form.add_error(None, "Seu usuário não possui um perfil de Funcionário vinculado.")
            return self.form_invalid(form)

        # Verifica bloqueio do veículo
        veiculo = form.cleaned_data.get('veiculo')
        if veiculo and veiculo.bloqueado:
            motivo = veiculo.motivo_bloqueio or 'Verifique com o gestor.'
            form.add_error('veiculo', f'Veículo {veiculo.placa} bloqueado para despacho: {motivo}')
            return self.form_invalid(form)

        form.instance.motorista = self.request.user.perfil_funcionario

        if fotos.is_valid():
            with transaction.atomic():
                self.object = form.save()
                fotos.instance = self.object
                fotos.save()
                if self.object.tem_avaria:
                    criar_ocorrencia_para_checklist(self.object)

            # E-mail fora da transação (falha silenciosa)
            if self.object.tem_avaria:
                _enviar_email_avaria_critica(self.object)

            return redirect(self.success_url)

        return self.render_to_response(self.get_context_data(form=form, fotos=fotos))


class CheckListDetailView(LoginRequiredMixin, CheckListBaseView, DetailView):
    template_name = 'frota/checklist_detail.html'


class CheckListUpdateView(LoginRequiredMixin, GestorRequiredMixin, UpdateView):
    model = Checklist
    form_class = ChecklistForm
    template_name = 'frota/checklist_update.html'
    success_url = reverse_lazy('checklist_list')


class CheckListDeleteView(LoginRequiredMixin, GestorRequiredMixin, DeleteView):
    model = Checklist
    template_name = 'frota/checklist_delete.html'
    success_url = reverse_lazy('checklist_list')


class ChecklistExportCSVView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        queryset = Checklist.objects.select_related('veiculo', 'motorista').order_by('-data_realizada')
        if not (user.is_superuser or user.is_patrao):
            queryset = queryset.filter(motorista__usuario=user)

        nome = f"checklists_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="{nome}"'
        writer = csv.writer(response)
        writer.writerow(['Data', 'Tipo', 'Motorista', 'Veículo', 'Placa', 'KM', 'Combustível', 'Status', 'Observações'])
        for c in queryset:
            writer.writerow([
                c.data_realizada.strftime('%d/%m/%Y %H:%M'),
                c.get_tipo_display(),
                c.motorista.nome_completo if c.motorista else '-',
                c.veiculo.modelo, c.veiculo.placa, c.km_atual,
                c.nivel_combustivel,
                'Avaria' if c.tem_avaria else 'Conforme',
                c.observacoes or '',
            ])
        return response


# ── CONFORMIDADE DA FROTA ─────────────────────────────────────────────────────

class ConformidadeFrotaView(LoginRequiredMixin, GestorRequiredMixin, View):
    template_name = 'frota/conformidade.html'

    def get(self, request):
        from django.shortcuts import render
        hoje = timezone.now().date()

        # 1ª query: veículos anotados com ID do último checklist e qtd de ocorrências abertas
        ultima_id_sq = Subquery(
            Checklist.objects.filter(veiculo=OuterRef('pk'))
            .order_by('-data_realizada')
            .values('id')[:1]
        )
        veiculos_ativos = (
            Veiculo.objects.filter(ativo=True)
            .annotate(
                ultima_checklist_id=ultima_id_sq,
                n_ocorrencias_abertas=Count(
                    'ocorrencias',
                    filter=~Q(ocorrencias__status='resolvida'),
                    distinct=True,
                ),
            )
            .order_by('modelo')
        )

        # 2ª query: busca todos os últimos checklists de uma vez
        ids_ultima = [v.ultima_checklist_id for v in veiculos_ativos if v.ultima_checklist_id]
        checklists_map = {
            c.id: c for c in
            Checklist.objects.filter(id__in=ids_ultima).select_related('motorista')
        }

        # Montagem sem queries adicionais
        situacao = []
        for v in veiculos_ativos:
            ultima = checklists_map.get(v.ultima_checklist_id)
            situacao.append({
                'veiculo': v,
                'ultima_inspecao': ultima,
                'inspecionado_hoje': ultima is not None and ultima.data_realizada.date() == hoje,
                'ocorrencias_abertas': v.n_ocorrencias_abertas,
            })

        total = len(situacao)
        inspecionados = sum(1 for s in situacao if s['inspecionado_hoje'])
        context = {
            'situacao': situacao,
            'hoje': hoje,
            'total_veiculos': total,
            'inspecionados_hoje': inspecionados,
            'pendentes_hoje': total - inspecionados,
            'conformidade_pct': round(inspecionados / total * 100) if total else 0,
        }
        return render(request, self.template_name, context)


# ── OCORRÊNCIAS DE AVARIA ─────────────────────────────────────────────────────

class OcorrenciaListView(LoginRequiredMixin, GestorRequiredMixin, ListView):
    model = OcorrenciaAvaria
    template_name = 'frota/ocorrencias_list.html'
    context_object_name = 'ocorrencias'
    paginate_by = 12

    def get_queryset(self):
        qs = OcorrenciaAvaria.objects.select_related('veiculo', 'checklist', 'resolvida_por')
        status = self.request.GET.get('status')
        veiculo = self.request.GET.get('veiculo')
        if status:
            qs = qs.filter(status=status)
        if veiculo:
            qs = qs.filter(Q(veiculo__placa__icontains=veiculo) | Q(veiculo__modelo__icontains=veiculo))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contagens = OcorrenciaAvaria.objects.aggregate(
            aguardando=Count('id', filter=Q(status='aguardando')),
            em_reparo=Count('id', filter=Q(status='em_reparo')),
            resolvidas=Count('id', filter=Q(status='resolvida')),
        )
        context['total_aguardando'] = contagens['aguardando']
        context['total_em_reparo'] = contagens['em_reparo']
        context['total_resolvidas'] = contagens['resolvidas']
        return context


class OcorrenciaUpdateView(LoginRequiredMixin, GestorRequiredMixin, UpdateView):
    model = OcorrenciaAvaria
    form_class = OcorrenciaUpdateForm
    template_name = 'frota/ocorrencia_update.html'
    success_url = reverse_lazy('ocorrencias_list')

    def form_valid(self, form):
        obj = form.save(commit=False)
        if obj.status == 'resolvida' and not obj.resolvida_por:
            obj.resolvida_por = self.request.user
        obj.save()
        messages.success(self.request, f"Ocorrência do veículo {obj.veiculo.placa} atualizada.")
        return redirect(self.success_url)


# ── VEÍCULO VIEWS ─────────────────────────────────────────────────────────────

class VeiculoBaseView:
    model = Veiculo
    form_class = VeiculoForm
    success_url = reverse_lazy('veiculos_list')


class QRCodeGeneratorView(LoginRequiredMixin, View):
    def get(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk)
        path = reverse('checklist_add')
        url = request.build_absolute_uri(f"{path}?veiculo_id={veiculo.id}")
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return HttpResponse(buf.getvalue(), content_type="image/png")


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
                Q(placa__icontains=busca) | Q(marca__icontains=busca) | Q(modelo__icontains=busca)
            )
        return queryset.order_by('-ativo', '-id')


class VeiculoCreateView(LoginRequiredMixin, GestorRequiredMixin, VeiculoBaseView, CreateView):
    template_name = 'veiculo/veiculo_form.html'


class VeiculoDetailView(LoginRequiredMixin, VeiculoBaseView, DetailView):
    model = Veiculo
    template_name = 'veiculo/veiculo_detail.html'
    context_object_name = 'veiculo'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        limite_doc = hoje + timedelta(days=30)

        # Histórico de KM
        km_hist = list(
            Checklist.objects.filter(veiculo=self.object)
            .order_by('data_realizada').values('data_realizada', 'km_atual')[:20]
        )
        context['km_labels'] = json.dumps([c['data_realizada'].strftime('%d/%m') for c in km_hist])
        context['km_data'] = json.dumps([c['km_atual'] for c in km_hist])
        context['tem_km_historico'] = len(km_hist) >= 2

        # Alerta de revisão por KM
        if self.object.km_proxima_revisao and km_hist:
            ultimo_km = km_hist[-1]['km_atual']
            context['alerta_km_revisao'] = ultimo_km >= (self.object.km_proxima_revisao - 500)
            context['ultimo_km'] = ultimo_km
        else:
            context['alerta_km_revisao'] = False

        # Alertas de documentos
        v = self.object
        context['crlv_vencido'] = v.vencimento_crlv and v.vencimento_crlv < hoje
        context['crlv_vencendo'] = v.vencimento_crlv and hoje <= v.vencimento_crlv <= limite_doc and not context['crlv_vencido']
        context['seguro_vencido'] = v.vencimento_seguro and v.vencimento_seguro < hoje
        context['seguro_vencendo'] = v.vencimento_seguro and hoje <= v.vencimento_seguro <= limite_doc and not context['seguro_vencido']

        # Ocorrências abertas — queryset reutilizado (evita query duplicada)
        oc_qs = OcorrenciaAvaria.objects.filter(veiculo=self.object).exclude(status='resolvida')
        context['ocorrencias_abertas'] = oc_qs.order_by('-criada_em')[:5]
        context['total_ocorrencias_abertas'] = oc_qs.count()

        # Últimas 5 inspeções
        context['ultimas_inspecoes'] = (
            Checklist.objects.filter(veiculo=self.object)
            .select_related('motorista')
            .order_by('-data_realizada')[:5]
        )

        # Último abastecimento
        context['ultimo_abastecimento'] = (
            Abastecimento.objects.filter(veiculo=self.object).first()
        )

        return context


class VeiculoUpdateView(LoginRequiredMixin, GestorRequiredMixin, UpdateView):
    model = Veiculo
    form_class = VeiculoForm
    template_name = 'veiculo/veiculo_form.html'
    success_url = reverse_lazy('veiculos_list')


class VeiculoDeleteView(LoginRequiredMixin, GestorRequiredMixin, DeleteView):
    model = Veiculo
    template_name = 'veiculo/veiculo_delete.html'
    context_object_name = 'veiculo'
    success_url = reverse_lazy('veiculos_list')


class VeiculoAlternarStatusView(LoginRequiredMixin, GestorRequiredMixin, View):
    def post(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk)
        veiculo.ativo = not veiculo.ativo
        veiculo.save()
        status = "ativado" if veiculo.ativo else "desativado"
        messages.success(request, f"Veículo {veiculo.placa} {status} com sucesso.")
        return redirect('veiculos_list')


class VeiculoBloqueioView(LoginRequiredMixin, GestorRequiredMixin, View):
    def post(self, request, pk):
        veiculo = get_object_or_404(Veiculo, pk=pk)
        action = request.POST.get('action')
        if action == 'bloquear':
            veiculo.bloqueado = True
            veiculo.motivo_bloqueio = request.POST.get('motivo', '').strip()
            veiculo.save()
            messages.warning(request, f"Veículo {veiculo.placa} bloqueado para despacho.")
        elif action == 'liberar':
            veiculo.bloqueado = False
            veiculo.motivo_bloqueio = ''
            veiculo.save()
            messages.success(request, f"Veículo {veiculo.placa} liberado para despacho.")
        return redirect('veiculo_detail', pk=pk)


# ── MANUTENÇÃO ────────────────────────────────────────────────────────────────

class OrdemManutencaoListView(LoginRequiredMixin, GestorRequiredMixin, ListView):
    model = OrdemManutencao
    template_name = 'manutencao/ordem_list.html'
    context_object_name = 'ordens'
    paginate_by = 10

    def get_queryset(self):
        qs = OrdemManutencao.objects.select_related('veiculo', 'ocorrencia')
        status = self.request.GET.get('status')
        veiculo = self.request.GET.get('veiculo')
        if status:
            qs = qs.filter(status=status)
        if veiculo:
            qs = qs.filter(Q(veiculo__placa__icontains=veiculo) | Q(veiculo__modelo__icontains=veiculo))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_abertas'] = OrdemManutencao.objects.filter(status='aberta').count()
        context['total_andamento'] = OrdemManutencao.objects.filter(status='em_andamento').count()
        custo = OrdemManutencao.objects.filter(status='concluida').aggregate(t=Sum('custo'))['t']
        context['custo_total'] = custo or 0
        return context


class OrdemManutencaoCreateView(LoginRequiredMixin, GestorRequiredMixin, CreateView):
    model = OrdemManutencao
    form_class = OrdemManutencaoForm
    template_name = 'manutencao/ordem_form.html'
    success_url = reverse_lazy('ordem_manutencao_list')

    def form_valid(self, form):
        form.instance.criada_por = self.request.user
        messages.success(self.request, "Ordem de manutenção criada com sucesso.")
        return super().form_valid(form)


class OrdemManutencaoUpdateView(LoginRequiredMixin, GestorRequiredMixin, UpdateView):
    model = OrdemManutencao
    form_class = OrdemManutencaoForm
    template_name = 'manutencao/ordem_form.html'
    success_url = reverse_lazy('ordem_manutencao_list')

    def form_valid(self, form):
        messages.success(self.request, "Ordem de manutenção atualizada.")
        return super().form_valid(form)


# ── ABASTECIMENTO ─────────────────────────────────────────────────────────────

class AbastecimentoListView(LoginRequiredMixin, ListView):
    model = Abastecimento
    template_name = 'veiculo/abastecimento_list.html'
    context_object_name = 'abastecimentos'
    paginate_by = 15

    def get_queryset(self):
        user = self.request.user
        qs = Abastecimento.objects.select_related('veiculo', 'motorista')
        if not (user.is_superuser or user.is_patrao):
            qs = qs.filter(motorista__usuario=user)
        veiculo = self.request.GET.get('veiculo')
        if veiculo:
            qs = qs.filter(Q(veiculo__placa__icontains=veiculo) | Q(veiculo__modelo__icontains=veiculo))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        totais = qs.aggregate(litros=Sum('litros'), valor=Sum('valor_total'))
        context['total_litros'] = totais['litros'] or 0
        context['total_valor'] = totais['valor'] or 0
        return context


class AbastecimentoCreateView(LoginRequiredMixin, CreateView):
    model = Abastecimento
    form_class = AbastecimentoForm
    template_name = 'veiculo/abastecimento_form.html'
    success_url = reverse_lazy('abastecimento_list')

    def form_valid(self, form):
        form.instance.registrado_por = self.request.user
        messages.success(self.request, "Abastecimento registrado com sucesso.")
        return super().form_valid(form)


# ── FUNCIONÁRIO VIEWS ─────────────────────────────────────────────────────────

class FuncionarioBaseView:
    model = Funcionario
    form_class = NovoFuncionarioForm
    success_url = reverse_lazy('funcionario_list')


class FuncionarioListView(LoginRequiredMixin, GestorRequiredMixin, FuncionarioBaseView, ListView):
    template_name = 'funcionario/funcionario_list.html'
    context_object_name = 'funcionarios'
    paginate_by = 9

    def get_queryset(self):
        queryset = super().get_queryset()
        busca = self.request.GET.get('busca')
        if busca:
            queryset = queryset.filter(nome_completo__icontains=busca)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        context['hoje'] = hoje
        context['limite_alerta_cnh'] = hoje + timedelta(days=30)
        return context


class FuncionarioCreateView(LoginRequiredMixin, GestorRequiredMixin, CreateView):
    model = Funcionario
    form_class = NovoFuncionarioForm
    template_name = 'funcionario/funcionario_form.html'
    success_url = reverse_lazy('funcionario_list')

    def form_valid(self, form):
        try:
            with transaction.atomic():
                cargo = form.cleaned_data.get('cargo', 'Motorista')
                is_gestor = cargo == 'Gestor'
                user = Usuario.objects.create_user(
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password'],
                    email=form.cleaned_data.get('email', ''),
                    is_motorista=not is_gestor,
                    is_patrao=is_gestor,
                )
                funcionario = form.save(commit=False)
                funcionario.usuario = user
                funcionario.cadastrado_por = self.request.user
                funcionario.save()
            messages.success(self.request, "Funcionário cadastrado com sucesso.")
            return redirect(self.success_url)
        except Exception:
            form.add_error(None, "Erro ao cadastrar. Verifique se o login já existe.")
            return self.form_invalid(form)


class FuncionarioUpdateView(LoginRequiredMixin, GestorRequiredMixin, FuncionarioBaseView, UpdateView):
    template_name = 'funcionario/funcionario_update.html'


class FuncionarioDeleteView(LoginRequiredMixin, GestorRequiredMixin, FuncionarioBaseView, DeleteView):
    template_name = 'funcionario/funcionario_delete.html'
