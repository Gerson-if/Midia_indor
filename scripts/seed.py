"""
Popula o banco de dados com conteúdo inicial de demonstração para uma
página (tenant) específica, a partir de um modelo por tipo de negócio
(TEMPLATES). Idempotente: pode ser executado múltiplas vezes sem
duplicar registros (serviços/galeria/depoimentos/parceiros só são
criados se a página ainda não tiver nenhum).

Uso:
    flask seed-demo --tenant-slug=default --template=barbearia
"""
from app.extensions import db
from app.models import GalleryItem, Partner, Service, SiteSettings, Testimonial

# Mesmos textos usados como default das colunas em app/models/content.py
# (SiteSettings.services_heading etc.) -- servem de "assinatura" para
# saber se um campo ainda está no valor de fábrica (seguro sobrescrever)
# ou se o admin já personalizou (não mexer).
_FACTORY_HEADINGS = {
    "services_heading": "Por que anunciar conosco?",
    "services_subtitle": "Gerenciamento inteligente e telas nos pontos mais estratégicos da cidade.",
    "gallery_heading": "Nossos Pontos",
    "gallery_subtitle": "Confira os locais onde sua marca será exibida.",
    "testimonials_heading": "Marcas que confiam",
    "contact_heading": "Pronto para anunciar?",
}

TEMPLATE_CHOICES = [
    ("midia_indoor", "Mídia Indoor / Publicidade em telas"),
    ("barbearia", "Barbearia"),
    ("salao_beleza", "Salão de Beleza / Cabeleireiro(a)"),
    ("portfolio", "Portfólio pessoal / Divulgar meu trabalho"),
    ("empresa", "Empresa (genérico)"),
    ("none", "Não popular (página em branco)"),
]

TEMPLATES = {
    "midia_indoor": {
        "hero_title": "Sua marca no centro das atenções.",
        "hero_subtitle": "Telas digitais em pontos estratégicos com conteúdo que muda em tempo real.",
        "hero_cta_primary_label": "Anuncie Conosco",
        "hero_cta_secondary_label": "Conhecer Locais",
        "company_description": "Rede de mídia indoor digital estratégica para sua marca.",
        "services_heading": _FACTORY_HEADINGS["services_heading"],
        "services_subtitle": _FACTORY_HEADINGS["services_subtitle"],
        "gallery_heading": _FACTORY_HEADINGS["gallery_heading"],
        "gallery_subtitle": _FACTORY_HEADINGS["gallery_subtitle"],
        "testimonials_heading": _FACTORY_HEADINGS["testimonials_heading"],
        "contact_heading": _FACTORY_HEADINGS["contact_heading"],
        "services": [
            ("Mídia em Elevadores", "Telas verticais de alto impacto em prédios comerciais e residenciais."),
            ("Gestão em Tempo Real", "Substitua anúncios remotamente, sem custo extra de instalação."),
            ("Cobertura Premium", "Selecione bairros e perfis de público por região da cidade."),
            ("Produção Inclusa", "Nossa equipe cria ou adapta as artes da sua campanha."),
        ],
        "gallery": [
            ("Torre Horizonte", "Elevadores"),
            ("Vitalis Centro", "Academias"),
            ("Bem Estar Diagnósticos", "Clínicas"),
            ("Alameda Jardins", "Condomínios"),
        ],
        "testimonials": [
            ("Marcela Duarte", "Vitalis Academia", "Aumentamos a procura por planos anuais depois de 2 meses."),
            ("Rafael Nunes", "Clínica Bem Estar", "Fácil de trocar a arte quando lançamos uma promoção nova."),
        ],
        "partners": ["Grupo Horizonte", "Vitalis Academia", "Clínica Bem Estar", "Condomínio Alameda"],
    },
    "barbearia": {
        "hero_title": "Estilo e precisão em cada corte.",
        "hero_subtitle": "Cortes modernos, barba terapêutica e um ambiente pensado para você.",
        "hero_cta_primary_label": "Agendar Horário",
        "hero_cta_secondary_label": "Ver o Espaço",
        "company_description": "Barbearia com atendimento personalizado, produtos de qualidade e ambiente exclusivo.",
        "services_heading": "Nossos Serviços",
        "services_subtitle": "Cuidado completo, do corte à barba.",
        "gallery_heading": "Nosso Espaço",
        "gallery_subtitle": "Conheça o ambiente da barbearia.",
        "testimonials_heading": "Quem já passou por aqui",
        "contact_heading": "Bora marcar seu horário?",
        "services": [
            ("Corte Masculino", "Cortes clássicos e modernos, sempre na régua."),
            ("Barba Terapia", "Toalha quente, navalha e hidratação completa."),
            ("Combo Corte + Barba", "O pacote completo com desconto especial."),
            ("Sobrancelha", "Design e acabamento para completar o visual."),
        ],
        "gallery": [
            ("Área de Corte", "Ambiente"),
            ("Estação de Barba", "Ambiente"),
            ("Recepção", "Ambiente"),
            ("Produtos", "Ambiente"),
        ],
        "testimonials": [
            ("Lucas Almeida", "Cliente", "Melhor barba terapia da região, sempre saio renovado."),
            ("Diego Ferreira", "Cliente", "Atendimento show, virei cliente fiel."),
        ],
        "partners": ["Truss Professional", "American Crew", "QOD Barber Shop", "Menu Barber"],
    },
    "salao_beleza": {
        "hero_title": "Sua beleza, nossa especialidade.",
        "hero_subtitle": "Cortes, coloração e tratamentos capilares para realçar o seu melhor visual.",
        "hero_cta_primary_label": "Agendar Horário",
        "hero_cta_secondary_label": "Ver Trabalhos",
        "company_description": "Salão de beleza especializado em cabelo, com profissionais experientes e produtos de alta qualidade.",
        "services_heading": "Nossos Serviços",
        "services_subtitle": "Cuidado completo para o seu cabelo.",
        "gallery_heading": "Nossos Trabalhos",
        "gallery_subtitle": "Alguns resultados que já entregamos.",
        "testimonials_heading": "Quem confia no nosso trabalho",
        "contact_heading": "Vamos cuidar do seu cabelo?",
        "services": [
            ("Corte Feminino", "Cortes personalizados para todos os estilos."),
            ("Coloração", "Técnicas modernas de coloração e mechas."),
            ("Escova e Finalização", "Escova modelada com produtos profissionais."),
            ("Tratamento Capilar", "Hidratação, reconstrução e nutrição."),
        ],
        "gallery": [
            ("Coloração", "Trabalhos"),
            ("Corte + Escova", "Trabalhos"),
            ("Mechas", "Trabalhos"),
            ("Tratamento", "Trabalhos"),
        ],
        "testimonials": [
            ("Fernanda Costa", "Cliente", "Amei o resultado da coloração, super indico!"),
            ("Juliana Marques", "Cliente", "Atendimento impecável e cabelo renovado."),
        ],
        "partners": ["Kérastase", "Wella Professionals", "L'Oréal Professionnel", "Truss"],
    },
    "portfolio": {
        "hero_title": "Meu trabalho fala por mim.",
        "hero_subtitle": "Confira meus projetos e vamos conversar sobre a sua próxima ideia.",
        "hero_cta_primary_label": "Fale Comigo",
        "hero_cta_secondary_label": "Ver Portfólio",
        "company_description": "Profissional dedicado a transformar ideias em resultados, projeto após projeto.",
        "services_heading": "O Que Eu Faço",
        "services_subtitle": "Serviços e habilidades que ofereço.",
        "gallery_heading": "Portfólio",
        "gallery_subtitle": "Alguns dos meus trabalhos recentes.",
        "testimonials_heading": "O que dizem sobre meu trabalho",
        "contact_heading": "Vamos trabalhar juntos?",
        "services": [
            ("Design Gráfico", "Identidade visual e peças para redes sociais."),
            ("Fotografia", "Ensaios e cobertura de eventos."),
            ("Edição de Vídeo", "Vídeos com storytelling e cortes dinâmicos."),
            ("Consultoria", "Orientação personalizada para o seu projeto."),
        ],
        "gallery": [
            ("Projeto 1", "Design"),
            ("Projeto 2", "Fotografia"),
            ("Projeto 3", "Vídeo"),
            ("Projeto 4", "Design"),
        ],
        "testimonials": [
            ("Marina Souza", "Cliente", "Entrega rápida e um resultado acima do esperado."),
            ("Pedro Lima", "Cliente", "Profissionalismo do início ao fim do projeto."),
        ],
        "partners": ["Cliente A", "Cliente B", "Cliente C", "Cliente D"],
    },
    "empresa": {
        "hero_title": "Soluções que fazem a diferença.",
        "hero_subtitle": "Ajudamos empresas a crescer com atendimento próximo e resultados consistentes.",
        "hero_cta_primary_label": "Fale Conosco",
        "hero_cta_secondary_label": "Nossos Serviços",
        "company_description": "Empresa comprometida em entregar qualidade e resultado em cada projeto.",
        "services_heading": "Nossos Serviços",
        "services_subtitle": "Soluções pensadas para o seu negócio.",
        "gallery_heading": "Nossos Projetos",
        "gallery_subtitle": "Alguns resultados que já entregamos.",
        "testimonials_heading": "Empresas que confiam",
        "contact_heading": "Vamos conversar sobre o seu projeto?",
        "services": [
            ("Consultoria Especializada", "Diagnóstico e plano de ação sob medida."),
            ("Atendimento Personalizado", "Suporte próximo em todas as etapas."),
            ("Soluções Sob Medida", "Projetos adaptados à realidade do seu negócio."),
            ("Suporte Contínuo", "Acompanhamento mesmo depois da entrega."),
        ],
        "gallery": [
            ("Projeto A", "Cases"),
            ("Projeto B", "Cases"),
            ("Projeto C", "Cases"),
            ("Projeto D", "Cases"),
        ],
        "testimonials": [
            ("Carlos Mendes", "Diretor Comercial", "Parceria que trouxe resultado real para nosso time."),
            ("Beatriz Rocha", "Gerente de Operações", "Atendimento ágil e solução sob medida."),
        ],
        "partners": ["Empresa Parceira A", "Empresa Parceira B", "Empresa Parceira C", "Empresa Parceira D"],
    },
}


def run_seed(tenant_id: int, template: str = "midia_indoor"):
    data = TEMPLATES.get(template, TEMPLATES["midia_indoor"])
    settings = SiteSettings.get_solo(tenant_id=tenant_id)

    if not settings.hero_title:
        settings.hero_title = data["hero_title"]
        settings.hero_subtitle = data["hero_subtitle"]
        settings.hero_cta_primary_label = data["hero_cta_primary_label"]
        settings.hero_cta_secondary_label = data["hero_cta_secondary_label"]
        settings.company_description = data["company_description"]

    # Títulos de seção são NOT NULL (sempre têm o texto de fábrica desde a
    # criação da página) -- só trocamos se ainda estiverem exatamente no
    # valor de fábrica, para não sobrescrever uma personalização já feita
    # pelo admin caso "seed-demo"/este template seja aplicado depois.
    for field, factory_value in _FACTORY_HEADINGS.items():
        if getattr(settings, field) == factory_value:
            setattr(settings, field, data[field])

    if not settings.privacy_content:
        settings.privacy_content = SiteSettings._default_privacy_content()

    if not settings.terms_content:
        settings.terms_content = SiteSettings._default_terms_content()

    if Service.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                Service(tenant_id=tenant_id, title=title, description=description, display_order=i)
                for i, (title, description) in enumerate(data["services"], start=1)
            ]
        )

    if GalleryItem.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                GalleryItem(tenant_id=tenant_id, title=title, category=category, display_order=i)
                for i, (title, category) in enumerate(data["gallery"], start=1)
            ]
        )

    if Testimonial.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                Testimonial(tenant_id=tenant_id, name=name, company_name=company_name, text=text, display_order=i)
                for i, (name, company_name, text) in enumerate(data["testimonials"], start=1)
            ]
        )

    if Partner.query.filter_by(tenant_id=tenant_id).count() == 0:
        db.session.add_all(
            [
                Partner(tenant_id=tenant_id, name=name, display_order=i)
                for i, name in enumerate(data["partners"], start=1)
            ]
        )

    db.session.commit()


def replace_template_content(tenant_id: int, template: str) -> None:
    """
    Troca o modelo de conteúdo de uma página que JÁ existe -- ação
    explícita do super admin, diferente de run_seed() (que só preenche
    o que ainda está vazio/no valor de fábrica). Aqui os títulos de
    seção sempre são trocados, e os serviços/galeria/depoimentos/
    parceiros atuais são substituídos pelos do novo modelo (perde o que
    já estava lá nessas 4 listas -- por isso é uma ação com confirmação
    no painel, não algo que roda sozinho). Hero/textos legais só são
    preenchidos se ainda estiverem vazios, para não apagar o que o
    cliente já personalizou de verdade.
    """
    data = TEMPLATES.get(template, TEMPLATES["midia_indoor"])
    settings = SiteSettings.get_solo(tenant_id=tenant_id)

    for field in _FACTORY_HEADINGS:
        setattr(settings, field, data[field])

    if not settings.hero_title:
        settings.hero_title = data["hero_title"]
        settings.hero_subtitle = data["hero_subtitle"]
        settings.hero_cta_primary_label = data["hero_cta_primary_label"]
        settings.hero_cta_secondary_label = data["hero_cta_secondary_label"]
        settings.company_description = data["company_description"]

    Service.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    GalleryItem.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    Testimonial.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)
    Partner.query.filter_by(tenant_id=tenant_id).delete(synchronize_session=False)

    db.session.add_all(
        [
            Service(tenant_id=tenant_id, title=title, description=description, display_order=i)
            for i, (title, description) in enumerate(data["services"], start=1)
        ]
    )
    db.session.add_all(
        [
            GalleryItem(tenant_id=tenant_id, title=title, category=category, display_order=i)
            for i, (title, category) in enumerate(data["gallery"], start=1)
        ]
    )
    db.session.add_all(
        [
            Testimonial(tenant_id=tenant_id, name=name, company_name=company_name, text=text, display_order=i)
            for i, (name, company_name, text) in enumerate(data["testimonials"], start=1)
        ]
    )
    db.session.add_all(
        [
            Partner(tenant_id=tenant_id, name=name, display_order=i)
            for i, name in enumerate(data["partners"], start=1)
        ]
    )

    db.session.commit()
