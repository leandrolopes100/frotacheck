from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
import os

# --- USUÁRIOS ---
class Usuario(AbstractUser):
    is_patrao = models.BooleanField(default=False, verbose_name="É Gestor/Admin")
    is_motorista = models.BooleanField(default=False, verbose_name="É Motorista/Funcionário")

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

# --------------------------------------------------------------------------------------------------
# --- FUNCIONÁRIO MODELS --------------------------------------------------------------------------------

class Funcionario(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil_funcionario')
    nome_completo = models.CharField(max_length=200, null=True, verbose_name="Nome do Funcionário")
    cadastrado_por = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='funcionarios_criados',
        verbose_name="Gestor Responsável",
        db_index=True
    )
    CARGO_CHOICES = (('Motorista', 'Motorista'), ('Gestor', 'Gestor'))
    cpf = models.CharField(max_length=14, unique=True, db_index=True)
    numero_cnh = models.CharField(max_length=20, verbose_name="Número CNH")
    validade_cnh = models.DateField(verbose_name="Validade da CNH")
    cnh_impressa = models.FileField(upload_to='funcionarios/cnh/', null=True, blank=True, verbose_name="CNH Digital/Scanner")
    cargo = models.CharField(max_length=100, choices=CARGO_CHOICES, default="Motorista")

    def __str__(self):
        return f"{self.nome_completo} ({self.usuario.username})"

# --------------------------------------------------------------------------------------------------
# --- VEÍCULO MODELS --------------------------------------------------------------------------------

class Veiculo(models.Model):
    placa = models.CharField(max_length=7, unique=True, db_index=True)
    marca = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100, db_index=True)
    ano = models.IntegerField()
    renavam = models.CharField(max_length=11, unique=True)
    documento_impresso = models.FileField(upload_to='veiculos/docs/%Y/%m/', null=True, blank=True)
    fipe = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Valor FIPE", blank=True, null=True, default=0)
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    foto = models.ImageField(upload_to='veiculos/fotos/%Y/%m/', null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = "Veículo"

    def __str__(self):
        return f"{self.modelo} - {self.placa}"

# --------------------------------------------------------------------------------------------------
# --- CHECKLIST MODELS --------------------------------------------------------------------------------

class Checklist(models.Model):
    COMBUSTIVEL_CHOICES = (
        ('Reserva', 'Reserva'), ('1/4', '1/4'), ('1/2', '1/2'), ('3/4', '3/4'), ('Cheio', 'Cheio'),
    )
    
    nome_checklist = models.CharField(max_length=100, null=True, blank=False, verbose_name="Título do Checklist")
    veiculo = models.ForeignKey(Veiculo, on_delete=models.CASCADE)
    motorista = models.ForeignKey(Funcionario, on_delete=models.CASCADE, null=True, blank=True)
    data_realizada = models.DateTimeField(default=timezone.now)
    km_atual = models.PositiveIntegerField(verbose_name="KM Atual")
    nivel_combustivel = models.CharField(max_length=10, choices=COMBUSTIVEL_CHOICES, default='Cheio')
    
    # Coordenadas e tempo
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
    
    observacoes = models.TextField(blank=True, null=True)

    def get_campos_agrupados(self):
        return {
            "Iluminação": [("Faróis", self.farol), ("Lanterna", self.lanterna), ("Ré/Freio", self.re_freio), ("Piscas", self.piscas)],
            "Mecânica": [("Pneus", self.pneus), ("Amortecedor", self.amortecedor), ("Bateria", self.bateria), ("Óleo", self.oleo), ("Arrefecimento", self.arrefecimento_radiador), ("Vazamentos", self.vazamentos)],
            "Externa/Segurança": [("Limpadores", self.limpadores), ("Vidros", self.vidros), ("Retrovisores", self.retrovisor), ("Estepe", self.estepe), ("Macaco", self.macaco), ("Chave de Roda", self.chave_roda), ("Lataria", self.lataria)],
            "Interna": [("Buzina", self.buzina), ("Luz Interna", self.iluminacao_interna), ("Bancos", self.bancos), ("Tapetes", self.tapetes), ("Freio de Mão", self.freio_mao), ("Ar Condicionado", self.ar_condicionado), ("Som", self.som), ("Teto", self.teto),
                        ("Tacógrafo", self.tacografo), ("Carga", self.carga)]
        }

    @property
    def tem_avaria(self):
        # Pega todos os campos booleanos do modelo automaticamente
        campos = [getattr(self, field.name) for field in self._meta.fields if isinstance(field, models.BooleanField)]
        return False in campos

    def __str__(self):
        return f"{self.nome_checklist} - {self.veiculo.placa}"
    
# --------------------------------------------------------------------------------------------------
# --- FOTO AVARIA MODELS --------------------------------------------------------------------------------

class FotoAvaria(models.Model):
    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name='fotos_avarias')
    descricao = models.CharField(max_length=255, verbose_name="Descrição da Avaria")
    imagem = models.ImageField(upload_to='checklists/avarias/%Y/%m/%m/')

    def save(self, *args, **kwargs):
        if self.imagem and not self.imagem.name.endswith('.webp'):
            img = Image.open(self.imagem)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            max_size = (1920, 1080)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            output = BytesIO()
            img.save(output, format='WEBP', quality=75, optimize=True)
            output.seek(0)
            name = os.path.splitext(self.imagem.name)[0]
            self.imagem.save(f"{name}.webp", ContentFile(output.read()), save=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Foto de Avaria"
        verbose_name_plural = "Fotos de Avarias"