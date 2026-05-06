from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import (
    Usuario, Funcionario, Veiculo, Checklist, FotoAvaria,
    OcorrenciaAvaria, OrdemManutencao, Abastecimento,
)

# --- INLINES ---
class FotoAvariaInline(admin.TabularInline):
    model = FotoAvaria
    extra = 1
    readonly_fields = ('miniatura',)

    def miniatura(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" style="width: 100px; height: auto; border-radius: 8px;" />', obj.imagem.url)
        return "Sem imagem"

# --- CONFIGURAÇÕES DO ADMIN ---

@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'usuario', 'cargo', 'cadastrado_por')
    exclude = ('cadastrado_por',) 

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.cadastrado_por = request.user
        super().save_model(request, obj, form, change)

    def has_module_permission(self, request):
        return request.user.is_authenticated and (request.user.is_patrao or request.user.is_superuser)

@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ('nome_checklist', 'veiculo', 'motorista', 'data_realizada')
    list_filter = ('veiculo', 'motorista', 'data_realizada')
    # Removi o 'exclude' para que o Admin possa corrigir checklists sem motorista manualmente
    inlines = [FotoAvariaInline]

    def save_model(self, request, obj, form, change):
        """ Garante que o motorista seja preenchido se estiver vazio """
        if not obj.motorista:
            try:
                # Tenta o vínculo pelo related_name ou busca direta
                if hasattr(request.user, 'perfil_funcionario'):
                    obj.motorista = request.user.perfil_funcionario
                else:
                    obj.motorista = Funcionario.objects.get(usuario=request.user)
            except Exception:
                # Se for um Admin/Patrão que não é motorista, o campo continua editável no formulário
                pass
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        """ Filtra a visualização no Admin: Motorista só vê o dele, Patrão vê tudo """
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, 'is_patrao', False):
            return qs
        return qs.filter(motorista__usuario=request.user)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, 'is_patrao', False):
            return True
        if obj and obj.motorista and obj.motorista.usuario == request.user:
            return False # Bloqueia edição após salvar (segurança de dados)
        return False

@admin.register(Veiculo)
class VeiculoAdmin(admin.ModelAdmin):
    list_display = ('placa', 'modelo', 'exibir_foto')
    
    def exibir_foto(self, obj):
        if obj.foto:
            return format_html('<img src="{}" style="width: 50px; border-radius: 5px;" />', obj.foto.url)
        return "Sem foto"

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_patrao', 'is_motorista', 'is_staff')

    fieldsets = UserAdmin.fieldsets + (
        ('Permissões Frota Check', {'fields': ('is_patrao', 'is_motorista')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Permissões Frota Check', {'fields': ('is_patrao', 'is_motorista')}),
    )

    def has_module_permission(self, request):
        return request.user.is_authenticated and (request.user.is_patrao or request.user.is_superuser)


@admin.register(OcorrenciaAvaria)
class OcorrenciaAvariaAdmin(admin.ModelAdmin):
    list_display = ('veiculo', 'status', 'descricao', 'criada_em', 'resolvida_por')
    list_filter = ('status', 'veiculo')
    readonly_fields = ('criada_em', 'atualizada_em')


@admin.register(OrdemManutencao)
class OrdemManutencaoAdmin(admin.ModelAdmin):
    list_display = ('pk', 'veiculo', 'status', 'responsavel', 'data_agendada', 'custo')
    list_filter = ('status', 'veiculo')
    readonly_fields = ('criada_em', 'atualizada_em')


@admin.register(Abastecimento)
class AbastecimentoAdmin(admin.ModelAdmin):
    list_display = ('veiculo', 'data', 'litros', 'valor_total', 'tipo_combustivel', 'motorista')
    list_filter = ('veiculo', 'tipo_combustivel')