from django.urls import path
from .views import (
    # Checklist
    ChecklistListView, ChecklistCreateView, CheckListDetailView,
    CheckListDeleteView, CheckListUpdateView, ChecklistExportCSVView,
    ConformidadeFrotaView,
    # Ocorrências
    OcorrenciaListView, OcorrenciaUpdateView,
    # Veículo
    VeiculoAlternarStatusView, VeiculoListView, VeiculoDetailView,
    VeiculoUpdateView, VeiculoCreateView, VeiculoDeleteView,
    VeiculoEtiquetaListView, QRCodeGeneratorView, VeiculoBloqueioView,
    # Manutenção
    OrdemManutencaoListView, OrdemManutencaoCreateView, OrdemManutencaoUpdateView,
    # Abastecimento
    AbastecimentoListView, AbastecimentoCreateView,
    # Funcionário
    FuncionarioListView, FuncionarioCreateView, FuncionarioUpdateView,
    FuncionarioDeleteView,
)

urlpatterns = [
    # ── Checklist ──────────────────────────────────────────────────────────────
    path('meus-checklists/', ChecklistListView.as_view(), name='checklist_list'),
    path('novo/', ChecklistCreateView.as_view(), name='checklist_add'),
    path('detalhe/<int:pk>/', CheckListDetailView.as_view(), name='checklist_detail'),
    path('excluir/<int:pk>/', CheckListDeleteView.as_view(), name='checklist_delete'),
    path('editar/<int:pk>/', CheckListUpdateView.as_view(), name='checklist_update'),
    path('exportar/csv/', ChecklistExportCSVView.as_view(), name='checklist_export_csv'),
    path('conformidade/', ConformidadeFrotaView.as_view(), name='conformidade_frota'),

    # ── Ocorrências de Avaria ──────────────────────────────────────────────────
    path('ocorrencias/', OcorrenciaListView.as_view(), name='ocorrencias_list'),
    path('ocorrencias/<int:pk>/editar/', OcorrenciaUpdateView.as_view(), name='ocorrencia_update'),

    # ── Veículo ────────────────────────────────────────────────────────────────
    path('veiculos/', VeiculoListView.as_view(), name='veiculos_list'),
    path('veiculo/novo/', VeiculoCreateView.as_view(), name='veiculo_add'),
    path('veiculos/detalhe/<int:pk>/', VeiculoDetailView.as_view(), name='veiculo_detail'),
    path('veiculos/editar/<int:pk>/', VeiculoUpdateView.as_view(), name='veiculo_update'),
    path('veiculos/excluir/<int:pk>/', VeiculoDeleteView.as_view(), name='veiculo_delete'),
    path('veiculos/<int:pk>/status/', VeiculoAlternarStatusView.as_view(), name='alternar_status'),
    path('veiculos/<int:pk>/bloqueio/', VeiculoBloqueioView.as_view(), name='veiculo_bloqueio'),
    path('veiculo/<int:pk>/qrcode/', QRCodeGeneratorView.as_view(), name='veiculo_qrcode'),
    path('gestao/etiquetas/', VeiculoEtiquetaListView.as_view(), name='etiquetas_list'),

    # ── Manutenção ─────────────────────────────────────────────────────────────
    path('manutencao/', OrdemManutencaoListView.as_view(), name='ordem_manutencao_list'),
    path('manutencao/nova/', OrdemManutencaoCreateView.as_view(), name='ordem_manutencao_add'),
    path('manutencao/<int:pk>/editar/', OrdemManutencaoUpdateView.as_view(), name='ordem_manutencao_update'),

    # ── Abastecimento ──────────────────────────────────────────────────────────
    path('abastecimentos/', AbastecimentoListView.as_view(), name='abastecimento_list'),
    path('abastecimentos/novo/', AbastecimentoCreateView.as_view(), name='abastecimento_add'),

    # ── Funcionário ────────────────────────────────────────────────────────────
    path('funcionarios/novo/', FuncionarioCreateView.as_view(), name='funcionario_add'),
    path('funcionarios/', FuncionarioListView.as_view(), name='funcionario_list'),
    path('funcionarios/editar/<int:pk>/', FuncionarioUpdateView.as_view(), name='funcionario_update'),
    path('funcionarios/delete/<int:pk>/', FuncionarioDeleteView.as_view(), name='funcionario_delete'),
]
