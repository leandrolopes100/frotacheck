from django.db.models import Q

CAMPOS_AVARIA = [
    'farol', 'lanterna', 're_freio', 'piscas',
    'pneus', 'amortecedor', 'bateria', 'oleo',
    'arrefecimento_radiador', 'vazamentos',
    'limpadores', 'vidros', 'retrovisor', 'estepe',
    'macaco', 'chave_roda', 'lataria', 'buzina',
    'iluminacao_interna', 'bancos', 'tapetes',
    'freio_mao', 'ar_condicionado', 'som', 'teto',
    'tacografo', 'carga',
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
}

# Itens que representam risco direto à segurança
ITENS_CRITICOS = [
    'farol', 'lanterna', 're_freio', 'piscas',
    'pneus', 'amortecedor', 'bateria',
    'freio_mao', 'vazamentos', 'arrefecimento_radiador',
]


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


def tem_avaria_critica(checklist):
    """True se algum item crítico de segurança falhou."""
    return any(not getattr(checklist, campo, True) for campo in ITENS_CRITICOS)


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
