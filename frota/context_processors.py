from datetime import timedelta
from django.utils import timezone


def alertas_globais(request):
    if not request.user.is_authenticated:
        return {'alertas_cnh_total': 0, 'alertas_total_geral': 0}

    is_gestor = getattr(request.user, 'is_patrao', False) or request.user.is_superuser
    if not is_gestor:
        return {'alertas_cnh_total': 0, 'alertas_total_geral': 0}

    from .models import Funcionario, Veiculo, OcorrenciaAvaria
    hoje = timezone.now().date()
    limite = hoje + timedelta(days=30)

    # CNH vencendo/vencida
    cnh_total = Funcionario.objects.filter(validade_cnh__lte=limite).count()

    # Documentos de veículos vencendo/vencidos
    from django.db.models import Q
    docs_total = Veiculo.objects.filter(ativo=True).filter(
        Q(vencimento_crlv__isnull=False, vencimento_crlv__lte=limite) |
        Q(vencimento_seguro__isnull=False, vencimento_seguro__lte=limite)
    ).count()

    # Ocorrências de avaria abertas
    ocorrencias_abertas = OcorrenciaAvaria.objects.exclude(status='resolvida').count()

    total_geral = cnh_total + docs_total + ocorrencias_abertas

    return {
        'alertas_cnh_total': cnh_total,
        'alertas_docs_total': docs_total,
        'alertas_ocorrencias': ocorrencias_abertas,
        'alertas_total_geral': total_geral,
    }
