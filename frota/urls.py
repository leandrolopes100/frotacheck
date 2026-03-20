from django.urls import path
from .views import (ChecklistListView, ChecklistCreateView, FuncionarioCreateView, CheckListDetailView,
                    CheckListDeleteView, CheckListUpdateView, VeiculoAlternarStatusView, VeiculoListView, VeiculoDetailView,
                    VeiculoUpdateView, VeiculoCreateView, VeiculoDeleteView, FuncionarioListView, FuncionarioUpdateView,
                    FuncionarioDeleteView, VeiculoEtiquetaListView, QRCodeGeneratorView)

urlpatterns = [
    #Checklist
    path('meus-checklists/', ChecklistListView.as_view(), name='checklist_list'),
    path('novo/', ChecklistCreateView.as_view(), name='checklist_add'),
    path('detalhe/<int:pk>/', CheckListDetailView.as_view(), name='checklist_detail' ),
    path('excluir/<int:pk>/', CheckListDeleteView.as_view(), name='checklist_delete'),
    path('editar/<int:pk>/', CheckListUpdateView.as_view(), name='checklist_update'),

    #Veiculo
    path('veiculos/', VeiculoListView.as_view(), name='veiculos_list'),
    path('veiculo/novo', VeiculoCreateView.as_view(), name='veiculo_add'),
    path('veiculos/detalhe/<int:pk>/', VeiculoDetailView.as_view(), name='veiculo_detail'),
    path('veiculos/editar/<int:pk>/', VeiculoUpdateView.as_view(), name='veiculo_update' ),
    path('veiculos/excluir/<int:pk>/', VeiculoDeleteView.as_view(), name='veiculo_delete'),
    path('veiculos/<int:pk>/status/', VeiculoAlternarStatusView.as_view(), name='alternar_status'),
 # No seu urls.py
    path('veiculo/<int:pk>/qrcode/', QRCodeGeneratorView.as_view(), name='veiculo_qrcode'),
    path('gestao/etiquetas/', VeiculoEtiquetaListView.as_view(), name='etiquetas_list'),

    #Funcionario
    path('funcionarios/novo/', FuncionarioCreateView.as_view(), name='funcionario_add'),
    path('funcionarios/', FuncionarioListView.as_view(), name='funcionario_list'),
    path('funcionarios/editar/<int:pk>/', FuncionarioUpdateView.as_view(), name='funcionario_update'),
    path('funcionarios/delete/<int:pk>/', FuncionarioDeleteView.as_view(), name='funcionario_delete'),
]
