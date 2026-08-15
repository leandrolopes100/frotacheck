from django.db.models import Q

CAMPOS_AVARIA = [
    'farol', 'lanterna', 're_freio', 'piscas',
    'pneus', 'amortecedor', 'bateria', 'oleo',
    'arrefecimento_radiador', 'vazamentos',
    'limpadores', 'vidros', 'retrovisor', 'estepe',
    'macaco', 'chave_roda', 'lataria', 'buzina',
    'iluminacao_interna', 'bancos', 'tapetes',
    'freio_mao', 'ar_condicionado', 'som', 'teto',
    'tacografo', 'carga', 'tablet_cigame',
]

CAMPO_LABELS = {
    'farol': 'Faróis', 'lanterna': 'Lanterna', 're_freio': 'Ré/Freio', 'piscas': 'Piscas',
    'pneus': 'Pneus', 'amortecedor': 'Amortecedor', 'bateria': 'Bateria', 'oleo': 'Óleo',
    'arrefecimento_radiador': 'Arrefecimento', 'vazamentos': 'Vazamentos',
    'limpadores': 'Limpadores', 'vidros': 'Vidros', 'retrovisor': 'Retrovisores',
    'estepe': 'Estepe', 'macaco': 'Macaco', 'chave_roda': 'Chave de Roda', 'lataria': 'Lataria',
    'buzina': 'Buzina', 'iluminacao_interna': 'Luz Interna', 'bancos': 'Bancos',
    'tapetes': 'Tapetes', 'freio_mao': 'Freio de Mão', 'ar_condicionado': 'Ar Condicionado',
    'som': 'Som', 'teto': 'Teto', 'tacografo': 'Tacógrafo', 'carga': 'Carga',
    'tablet_cigame': 'Tablet Entregas CIGAME',
}

# Itens que representam risco direto à segurança
ITENS_CRITICOS = [
    'farol', 'lanterna', 're_freio', 'piscas',
    'pneus', 'amortecedor', 'bateria',
    'freio_mao', 'vazamentos', 'arrefecimento_radiador',
]

# Dias em aberto a partir dos quais uma OcorrenciaAvaria é sinalizada como atrasada
OCORRENCIA_DIAS_ALERTA = 3


def get_filtro_avaria():
    q = Q()
    for campo in CAMPOS_AVARIA:
        q |= Q(**{campo: False})
    return q


def get_filtro_ok():
    return {campo: True for campo in CAMPOS_AVARIA}


def get_itens_com_falha(checklist):
    """Retorna lista de labels dos itens com falha."""
    return [
        CAMPO_LABELS.get(campo, campo)
        for campo in CAMPOS_AVARIA
        if not getattr(checklist, campo, True)
    ]


def criar_ocorrencia_para_checklist(checklist):
    """Cria um registro OcorrenciaAvaria para um checklist com avarias."""
    from .models import OcorrenciaAvaria
    itens = get_itens_com_falha(checklist)
    if not itens:
        return None
    return OcorrenciaAvaria.objects.create(
        checklist=checklist,
        veiculo=checklist.veiculo,
        descricao=', '.join(itens),
        status='aguardando',
    )


def gerar_motivo_bloqueio_automatico(checklist):
    """Monta o texto de motivo_bloqueio para o bloqueio automático por
    avaria crítica, citando o checklist de origem e os itens reprovados."""
    itens = [CAMPO_LABELS.get(c, c) for c in ITENS_CRITICOS if not getattr(checklist, c, True)]
    return (
        f"Bloqueio automático — item(ns) crítico(s) reprovado(s) no checklist #{checklist.pk} "
        f"({checklist.data_realizada.strftime('%d/%m/%Y %H:%M')}): " + ", ".join(itens)
    )


def veiculo_tem_ocorrencia_critica_aberta(veiculo, excluir_pk=None):
    """True se o veículo tem alguma OcorrenciaAvaria não resolvida cujo
    checklist de origem reprovou algum item crítico de segurança."""
    from .models import OcorrenciaAvaria
    q_critico = Q()
    for campo in ITENS_CRITICOS:
        q_critico |= Q(**{f'checklist__{campo}': False})
    qs = OcorrenciaAvaria.objects.filter(veiculo=veiculo).exclude(status='resolvida').filter(q_critico)
    if excluir_pk:
        qs = qs.exclude(pk=excluir_pk)
    return qs.exists()
