from datetime import timedelta
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

_VAZIO = {'alertas_cnh_total': 0, 'alertas_docs_total': 0, 'alertas_ocorrencias': 0, 'alertas_total_geral': 0}


def alertas_globais(request):
    if not request.user.is_authenticated:
        return _VAZIO

    is_gestor = getattr(request.user, 'is_patrao', False) or request.user.is_superuser
    if not is_gestor:
        return _VAZIO

    chave = f'alertas_globais_u{request.user.pk}'
    resultado = cache.get(chave)
    if resultado is not None:
        return resultado

    from .models import Funcionario, Veiculo, OcorrenciaAvaria
    hoje = timezone.now().date()
    limite = hoje + timedelta(days=30)

    cnh_total = Funcionario.objects.filter(validade_cnh__lte=limite).count()

    docs_total = Veiculo.objects.filter(ativo=True).filter(
        Q(vencimento_crlv__isnull=False, vencimento_crlv__lte=limite) |
        Q(vencimento_seguro__isnull=False, vencimento_seguro__lte=limite)
    ).count()

    ocorrencias_abertas = OcorrenciaAvaria.objects.exclude(status='resolvida').count()

    resultado = {
        'alertas_cnh_total': cnh_total,
        'alertas_docs_total': docs_total,
        'alertas_ocorrencias': ocorrencias_abertas,
        'alertas_total_geral': cnh_total + docs_total + ocorrencias_abertas,
    }
    cache.set(chave, resultado, 60)  # TTL: 60 segundos
    return resultado
