from django.core.validators import FileExtensionValidator
from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
import os

DOCUMENTO_EXTENSOES_PERMITIDAS = ['pdf', 'jpg', 'jpeg', 'png']


# ── USUÁRIOS ──────────────────────────────────────────────────────────────────

class Usuario(AbstractUser):
    is_patrao = models.BooleanField(default=False, verbose_name="É Gestor/Admin")
    is_motorista = models.BooleanField(default=False, verbose_name="É Motorista/Funcionário")

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"


# ── FUNCIONÁRIO ───────────────────────────────────────────────────────────────

class Funcionario(models.Model):
    CARGO_CHOICES = (('Motorista', 'Motorista'), ('Gestor', 'Gestor'))

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='perfil_funcionario',
    )
    nome_completo = models.CharField(max_length=200, null=True, verbose_name="Nome do Funcionário")
    cadastrado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='funcionarios_criados', verbose_name="Gestor Responsável", db_index=True,
    )
    cpf = models.CharField(max_length=14, unique=True, db_index=True)
    numero_cnh = models.CharField(max_length=20, verbose_name="Número CNH")
    validade_cnh = models.DateField(verbose_name="Validade da CNH", db_index=True)
    cnh_impressa = models.FileField(
        upload_to='funcionarios/cnh/', null=True, blank=True,
        verbose_name="CNH Digital/Scanner",
        validators=[FileExtensionValidator(DOCUMENTO_EXTENSOES_PERMITIDAS)],
    )
    cargo = models.CharField(max_length=100, choices=CARGO_CHOICES, default="Motorista")

    def __str__(self):
        return f"{self.nome_completo} ({self.usuario.username})"


# ── VEÍCULO ───────────────────────────────────────────────────────────────────

class Veiculo(models.Model):
    placa = models.CharField(max_length=7, unique=True, db_index=True)
    marca = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100, db_index=True)
    ano = models.IntegerField()
    renavam = models.CharField(max_length=11, unique=True)
    documento_impresso = models.FileField(
        upload_to='veiculos/docs/%Y/%m/', null=True, blank=True,
        validators=[FileExtensionValidator(DOCUMENTO_EXTENSOES_PERMITIDAS)],
    )
    fipe = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Valor FIPE",
        blank=True, null=True, default=0,
    )
    ativo = models.BooleanField(default=True, verbose_name="Ativo", db_index=True)
    foto = models.ImageField(upload_to='veiculos/fotos/%Y/%m/', null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # Controle de documentos
    vencimento_crlv = models.DateField(null=True, blank=True, verbose_name="Vencimento CRLV", db_index=True)
    vencimento_seguro = models.DateField(null=True, blank=True, verbose_name="Vencimento Seguro", db_index=True)

    # Revisão por KM
    km_proxima_revisao = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="KM da Próxima Revisão",
    )

    # Bloqueio para despacho
    bloqueado = models.BooleanField(default=False, verbose_name="Bloqueado para Despacho")
    motivo_bloqueio = models.TextField(blank=True, null=True, verbose_name="Motivo do Bloqueio")
    bloqueio_automatico = models.BooleanField(
        default=False, verbose_name="Bloqueio Automático (Avaria Crítica)",
    )

    class Meta:
        ordering = ['-criado_em']
        verbose_name = "Veículo"

    def __str__(self):
        return f"{self.modelo} - {self.placa}"

    @property
    def documentacao_vencida(self):
        hoje = timezone.now().date()
        return bool(
            (self.vencimento_crlv and self.vencimento_crlv < hoje) or
            (self.vencimento_seguro and self.vencimento_seguro < hoje)
        )

    @property
    def documentacao_vencendo(self):
        if self.documentacao_vencida:
            return False
        hoje = timezone.now().date()
        limite = hoje + timedelta(days=30)
        return bool(
            (self.vencimento_crlv and hoje <= self.vencimento_crlv <= limite) or
            (self.vencimento_seguro and hoje <= self.vencimento_seguro <= limite)
        )


# ── CHECKLIST ─────────────────────────────────────────────────────────────────

class Checklist(models.Model):
    COMBUSTIVEL_CHOICES = (
        ('Reserva', 'Reserva'), ('1/4', '1/4'), ('1/2', '1/2'),
        ('3/4', '3/4'), ('Cheio', 'Cheio'),
    )
    TIPO_CHOICES = (
        ('pre_viagem', 'Pré-Viagem'),
        ('pos_viagem', 'Pós-Viagem'),
        ('geral', 'Geral'),
    )

    nome_checklist = models.CharField(
        max_length=100, blank=False, verbose_name="Título do Checklist",
    )
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE)
    motorista = models.ForeignKey(Funcionario, on_delete=models.CASCADE, null=True, blank=True)
    data_realizada = models.DateTimeField(default=timezone.now, db_index=True)
    km_atual = models.PositiveIntegerField(verbose_name="KM Atual")
    nivel_combustivel = models.CharField(max_length=10, choices=COMBUSTIVEL_CHOICES, default='Cheio', db_index=True)
    tipo = models.CharField(
        max_length=20, choices=TIPO_CHOICES, default='geral', verbose_name="Tipo de Inspeção",
    )

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Iluminação
    farol = models.BooleanField(default=False, verbose_name="Faróis OK?")
    lanterna = models.BooleanField(default=False, verbose_name="Lanterna OK?")
    re_freio = models.BooleanField(default=False, verbose_name="Ré/Freio OK?")
    piscas = models.BooleanField(default=False, verbose_name="Piscas OK?")
    # Mecânica
    pneus = models.BooleanField(default=False, verbose_name="Pneus OK?")
    amortecedor = models.BooleanField(default=False, verbose_name="Amortecedor OK?")
    bateria = models.BooleanField(default=False, verbose_name="Bateria OK?")
    oleo = models.BooleanField(default=False, verbose_name="Óleo OK?")
    arrefecimento_radiador = models.BooleanField(default=False, verbose_name="Arrefecimento OK?")
    vazamentos = models.BooleanField(default=False, verbose_name="Livre de Vazamentos?")
    # Externa/Segurança
    limpadores = models.BooleanField(default=False, verbose_name="Limpadores OK?")
    vidros = models.BooleanField(default=False, verbose_name="Vidros OK?")
    retrovisor = models.BooleanField(default=False, verbose_name="Retrovisores OK?")
    estepe = models.BooleanField(default=False, verbose_name="Estepe OK?")
    macaco = models.BooleanField(default=False, verbose_name="Macaco OK?")
    chave_roda = models.BooleanField(default=False, verbose_name="Chave de Roda OK?")
    lataria = models.BooleanField(default=False, verbose_name="Lataria OK?")
    # Interna
    buzina = models.BooleanField(default=False, verbose_name="Buzina OK?")
    iluminacao_interna = models.BooleanField(default=False, verbose_name="Luz Interna OK?")
    bancos = models.BooleanField(default=False, verbose_name="Bancos OK?")
    tapetes = models.BooleanField(default=False, verbose_name="Tapetes OK?")
    freio_mao = models.BooleanField(default=False, verbose_name="Freio de Mão OK?")
    ar_condicionado = models.BooleanField(default=False, verbose_name="Ar Condicionado OK?")
    som = models.BooleanField(default=False, verbose_name="Som OK?")
    teto = models.BooleanField(default=False, verbose_name="Teto OK?")
    tacografo = models.BooleanField(default=False, verbose_name="Tacógrafo Ok?")
    carga = models.BooleanField(default=False, verbose_name="Carga Ok?")
    tablet_cigame = models.BooleanField(default=False, verbose_name="Tablet Entregas CIGAME Ok?")

    observacoes = models.TextField(blank=True, null=True)

    def get_campos_agrupados(self):
        return {
            "Iluminação": [
                ("Faróis", self.farol), ("Lanterna", self.lanterna),
                ("Ré/Freio", self.re_freio), ("Piscas", self.piscas),
            ],
            "Mecânica": [
                ("Pneus", self.pneus), ("Amortecedor", self.amortecedor),
                ("Bateria", self.bateria), ("Óleo", self.oleo),
                ("Arrefecimento", self.arrefecimento_radiador), ("Vazamentos", self.vazamentos),
            ],
            "Externa/Segurança": [
                ("Limpadores", self.limpadores), ("Vidros", self.vidros),
                ("Retrovisores", self.retrovisor), ("Estepe", self.estepe),
                ("Macaco", self.macaco), ("Chave de Roda", self.chave_roda),
                ("Lataria", self.lataria),
            ],
            "Interna": [
                ("Buzina", self.buzina), ("Luz Interna", self.iluminacao_interna),
                ("Bancos", self.bancos), ("Tapetes", self.tapetes),
                ("Freio de Mão", self.freio_mao), ("Ar Condicionado", self.ar_condicionado),
                ("Som", self.som), ("Teto", self.teto),
                ("Tacógrafo", self.tacografo), ("Carga", self.carga),
                ("Tablet Entregas CIGAME", self.tablet_cigame),
            ],
        }

    @property
    def tem_avaria(self):
        from .utils import CAMPOS_AVARIA
        return any(not getattr(self, campo) for campo in CAMPOS_AVARIA)

    @property
    def tem_item_critico_reprovado(self):
        from .utils import ITENS_CRITICOS
        return any(not getattr(self, campo) for campo in ITENS_CRITICOS)

    def __str__(self):
        return f"{self.nome_checklist} - {self.veiculo.placa}"


# ── FOTO DE AVARIA ────────────────────────────────────────────────────────────

class FotoAvaria(models.Model):
    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name='fotos_avarias')
    descricao = models.CharField(max_length=255, verbose_name="Descrição da Avaria")
    imagem = models.ImageField(upload_to='checklists/avarias/%Y/%m/%d/')

    def save(self, *args, **kwargs):
        if self.imagem and not self.imagem.name.endswith('.webp'):
            img = Image.open(self.imagem)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
            output = BytesIO()
            img.save(output, format='WEBP', quality=75, optimize=True)
            output.seek(0)
            name = os.path.splitext(self.imagem.name)[0]
            self.imagem.save(f"{name}.webp", ContentFile(output.read()), save=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Foto de Avaria"
        verbose_name_plural = "Fotos de Avarias"


# ── OCORRÊNCIA DE AVARIA ──────────────────────────────────────────────────────

class OcorrenciaAvaria(models.Model):
    STATUS_CHOICES = [
        ('aguardando', 'Aguardando Reparo'),
        ('em_reparo', 'Em Reparo'),
        ('resolvida', 'Resolvida'),
    ]

    checklist = models.ForeignKey(
        Checklist, on_delete=models.CASCADE, related_name='ocorrencias',
    )
    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.CASCADE, related_name='ocorrencias',
    )
    descricao = models.TextField(verbose_name="Itens com Falha")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aguardando', db_index=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    resolvida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ocorrencias_resolvidas',
    )
    nota_resolucao = models.TextField(blank=True, null=True, verbose_name="Nota de Resolução")

    class Meta:
        ordering = ['-criada_em']
        verbose_name = "Ocorrência de Avaria"
        verbose_name_plural = "Ocorrências de Avarias"
        indexes = [
            models.Index(fields=['veiculo', 'status']),
        ]

    def __str__(self):
        return f"{self.veiculo.placa} — {self.get_status_display()} ({self.criada_em.strftime('%d/%m/%Y')})"

    @property
    def dias_em_aberto(self):
        fim = self.atualizada_em if self.status == 'resolvida' else timezone.now()
        return (fim - self.criada_em).days

    @property
    def atrasada(self):
        from .utils import OCORRENCIA_DIAS_ALERTA
        return self.status != 'resolvida' and self.dias_em_aberto >= OCORRENCIA_DIAS_ALERTA

    @property
    def critica(self):
        return self.checklist.tem_item_critico_reprovado


# ── ORDEM DE MANUTENÇÃO ───────────────────────────────────────────────────────

class OrdemManutencao(models.Model):
    STATUS_CHOICES = [
        ('aberta', 'Aberta'),
        ('agendada', 'Agendada'),
        ('em_andamento', 'Em Andamento'),
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
    ]

    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name='ordens_manutencao',
    )
    ocorrencia = models.ForeignKey(
        OcorrenciaAvaria, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ordens',
        verbose_name="Ocorrência vinculada",
    )
    descricao = models.TextField(verbose_name="Descrição do Serviço")
    responsavel = models.CharField(
        max_length=200, blank=True, verbose_name="Responsável / Oficina",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aberta')
    data_agendada = models.DateField(null=True, blank=True, verbose_name="Data Agendada")
    data_conclusao = models.DateField(null=True, blank=True, verbose_name="Data de Conclusão")
    custo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Custo (R$)",
    )
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ordens_criadas',
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-criada_em']
        verbose_name = "Ordem de Manutenção"
        verbose_name_plural = "Ordens de Manutenção"

    def __str__(self):
        return f"OS #{self.pk} — {self.veiculo.placa} ({self.get_status_display()})"


# ── ABASTECIMENTO ─────────────────────────────────────────────────────────────

class Abastecimento(models.Model):
    COMBUSTIVEL_CHOICES = [
        ('diesel', 'Diesel'), ('gasolina', 'Gasolina'),
        ('etanol', 'Etanol'), ('gnv', 'GNV'), ('flex', 'Flex'),
    ]

    veiculo = models.ForeignKey(
        Veiculo, on_delete=models.PROTECT, related_name='abastecimentos',
    )
    motorista = models.ForeignKey(
        Funcionario, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='abastecimentos',
    )
    data = models.DateTimeField(default=timezone.now, verbose_name="Data/Hora")
    km_atual = models.PositiveIntegerField(verbose_name="KM no Abastecimento")
    litros = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Litros Abastecidos")
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Total (R$)")
    tipo_combustivel = models.CharField(
        max_length=20, choices=COMBUSTIVEL_CHOICES, default='diesel',
        verbose_name="Tipo de Combustível",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='abastecimentos_registrados',
    )

    class Meta:
        ordering = ['-data']
        verbose_name = "Abastecimento"
        verbose_name_plural = "Abastecimentos"

    @property
    def valor_por_litro(self):
        if self.litros and self.litros > 0:
            return round(float(self.valor_total) / float(self.litros), 3)
        return None

    def __str__(self):
        return f"{self.veiculo.placa} — {self.litros}L em {self.data.strftime('%d/%m/%Y')}"
