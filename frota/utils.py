from django.db.models import Q

CAMPOS_AVARIA = [
    'farol', 'lanterna', 're_freio', 'piscas',
    'pneus', 'amortecedor', 'bateria', 'oleo',
    'arrefecimento_radiador', 'vazamentos',
    'limpadores', 'vidros', 'retrovisor', 'estepe',
    'macaco', 'chave_roda', 'lataria', 'buzina',
    'iluminacao_interna', 'bancos', 'tapetes',
    'freio_mao', 'ar_condicionado', 'som', 'teto',
    'tacografo', 'carga'
]

def get_filtro_avaria():
    q = Q()
    for campo in CAMPOS_AVARIA:
        q |= Q(**{campo: False})
    return q

def get_filtro_ok():
    return {campo: True for campo in CAMPOS_AVARIA}