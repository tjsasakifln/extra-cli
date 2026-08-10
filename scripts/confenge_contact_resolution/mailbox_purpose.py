"""Deterministic mailbox-purpose classification for commercial send gates.

mailbox_purpose describes the *function of an email local-part*, not a person role.
Never invent a person_role from an address. Ownership and purpose are independent:
vagas@company.com may be COMPANY_OWNED yet EMAIL_SEND_READY=false.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Positive / usable for CONFENGE cold email (ordered by commercial preference).
PURPOSE_CONTRATOS = "CONTRATOS"
PURPOSE_LICITACOES = "LICITACOES"
PURPOSE_ENGENHARIA = "ENGENHARIA"
PURPOSE_ORCAMENTO = "ORCAMENTO"
PURPOSE_COMERCIAL = "COMERCIAL"
PURPOSE_DIRETORIA = "DIRETORIA"
PURPOSE_FINANCEIRO = "FINANCEIRO"
PURPOSE_GENERIC_CONTACT = "GENERIC_CONTACT"

# Blocked from commercial autorun.
PURPOSE_HR_RECRUITING = "HR_RECRUITING"
PURPOSE_SUPPORT_SAC = "SUPPORT_SAC"
PURPOSE_PRIVACY_DPO = "PRIVACY_DPO"
PURPOSE_NOREPLY = "NOREPLY"
PURPOSE_UNKNOWN = "UNKNOWN"

ALL_PURPOSES = frozenset(
    {
        PURPOSE_CONTRATOS,
        PURPOSE_LICITACOES,
        PURPOSE_ENGENHARIA,
        PURPOSE_ORCAMENTO,
        PURPOSE_COMERCIAL,
        PURPOSE_DIRETORIA,
        PURPOSE_FINANCEIRO,
        PURPOSE_GENERIC_CONTACT,
        PURPOSE_HR_RECRUITING,
        PURPOSE_SUPPORT_SAC,
        PURPOSE_PRIVACY_DPO,
        PURPOSE_NOREPLY,
        PURPOSE_UNKNOWN,
    }
)

# Blocked local-parts and aliases (commercial autorun).
_BLOCKED_HR = frozenset(
    {
        "vagas",
        "rh",
        "curriculo",
        "currículos",
        "curriculos",
        "carreiras",
        "careers",
        "jobs",
        "job",
        "trabalheconosco",
        "trabalhe-conosco",
        "recrutamento",
        "selecao",
        "seleção",
        "people",
        "talent",
        "talents",
        "hr",
        "humanresources",
    }
)
_BLOCKED_SUPPORT = frozenset(
    {
        "suporte",
        "support",
        "sac",
        "helpdesk",
        "help",
        "ticket",
        "tickets",
        "ouvidoria",
        "reclamacao",
        "reclamação",
        "reclamacoes",
        "reclamações",
        # Retail / e-commerce inboxes are not commercial B2G outreach targets
        # (skeptic: eshop@barranova.com for BARRA NOVA ENGENHARIA).
        "eshop",
        "e-shop",
        "webshop",
        "loja",
        "lojaonline",
        "ecommerce",
        "e-commerce",
        "store",
        "shop",
    }
)
_BLOCKED_PRIVACY = frozenset(
    {
        "privacidade",
        "privacy",
        "dpo",
        "lgpd",
        "gdpr",
        "dataprotection",
        "protecaodedados",
        "proteção-de-dados",
    }
)
_BLOCKED_NOREPLY = frozenset(
    {
        "noreply",
        "no-reply",
        "no_reply",
        "donotreply",
        "do-not-reply",
        "mailer-daemon",
        "mailerdaemon",
        "bounce",
        "bounces",
        "postmaster",
        "daemon",
    }
)

# Preferential functional mailboxes for CONFENGE services.
_CONTRATOS = frozenset({"contratos", "contrato", "contract", "contracts", "aditivos", "aditivo"})
_LICITACOES = frozenset(
    {
        "licitacao",
        "licitacoes",
        "licitações",
        "licitações",
        "licitacoes",
        "pregao",
        "pregão",
        "editais",
        "edital",
        "pncp",
        "compras",
        "bidding",
        "bid",
    }
)
_ENGENHARIA = frozenset(
    {
        "engenharia",
        "engineering",
        "obras",
        "obra",
        "tecnico",
        "técnico",
        "tecnicos",
        "técnicos",
        "projetos",
        "projeto",
    }
)
_ORCAMENTO = frozenset(
    {
        "orcamento",
        "orçamento",
        "orcamentos",
        "orçamentos",
        "medicao",
        "medição",
        "medicoes",
        "medições",
        "bdi",
        "custos",
        "custo",
        "pricing",
    }
)
_COMERCIAL = frozenset(
    {
        "comercial",
        "vendas",
        "sales",
        "negocio",
        "negócio",
        "negocios",
        "negócios",
        "business",
        "parcerias",
        "partnership",
    }
)
_DIRETORIA = frozenset(
    {
        "diretoria",
        "diretor",
        "diretores",
        "presidencia",
        "presidência",
        "ceo",
        "c-level",
        "board",
        "gerencia",
        "gerência",
        "gestao",
        "gestão",
    }
)
_FINANCEIRO = frozenset(
    {
        "financeiro",
        "finance",
        "fiscal",
        "contas",
        "billing",
        "cobranca",
        "cobrança",
        "nf",
        "nfe",
        "faturamento",
    }
)
_GENERIC = frozenset(
    {
        "contato",
        "contact",
        "contatos",
        "atendimento",
        "info",
        "informacoes",
        "informações",
        "geral",
        "general",
        "office",
        "escritorio",
        "escritório",
        "admin",
        "adm",
        "administrativo",
        "secretaria",
        "secretariado",
        "recepcao",
        "recepção",
        "mail",
        "email",
        "empresa",
    }
)

# Preference rank for picking among several valid addresses (lower = better for CONFENGE).
PURPOSE_RANK: dict[str, int] = {
    PURPOSE_CONTRATOS: 10,
    PURPOSE_LICITACOES: 20,
    PURPOSE_ENGENHARIA: 30,
    PURPOSE_ORCAMENTO: 40,
    PURPOSE_COMERCIAL: 50,
    PURPOSE_DIRETORIA: 60,
    PURPOSE_FINANCEIRO: 70,
    PURPOSE_GENERIC_CONTACT: 80,
    PURPOSE_UNKNOWN: 90,
    PURPOSE_HR_RECRUITING: 900,
    PURPOSE_SUPPORT_SAC: 910,
    PURPOSE_PRIVACY_DPO: 920,
    PURPOSE_NOREPLY: 930,
}

BLOCKED_PURPOSES = frozenset(
    {
        PURPOSE_HR_RECRUITING,
        PURPOSE_SUPPORT_SAC,
        PURPOSE_PRIVACY_DPO,
        PURPOSE_NOREPLY,
    }
)

# Allowed for commercial autorun when other gates pass.
SEND_ALLOWED_PURPOSES = frozenset(
    {
        PURPOSE_CONTRATOS,
        PURPOSE_LICITACOES,
        PURPOSE_ENGENHARIA,
        PURPOSE_ORCAMENTO,
        PURPOSE_COMERCIAL,
        PURPOSE_DIRETORIA,
        PURPOSE_FINANCEIRO,
        PURPOSE_GENERIC_CONTACT,
        PURPOSE_UNKNOWN,  # unknown is not blocked; other gates still apply
    }
)

_LOCAL_CLEAN_RE = re.compile(r"[^a-z0-9+\-_.]")


def extract_local_part(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    local = email.split("@", 1)[0].strip().lower()
    # strip plus-tags: comercial+x → comercial
    if "+" in local:
        local = local.split("+", 1)[0]
    return local


def normalize_local_token(local: str) -> str:
    """Collapse separators so trabalhe.conosco / trabalhe_conosco match aliases."""
    s = (local or "").lower().strip()
    s = _LOCAL_CLEAN_RE.sub("", s)
    s = s.replace(".", "").replace("_", "").replace("-", "")
    return s


@dataclass(frozen=True)
class MailboxPurposeResult:
    purpose: str
    local_part: str
    send_blocked: bool
    block_reason: str | None
    rank: int

    def as_dict(self) -> dict:
        return {
            "mailbox_purpose": self.purpose,
            "local_part": self.local_part,
            "send_blocked": self.send_blocked,
            "block_reason": self.block_reason,
            "rank": self.rank,
        }


def classify_mailbox_purpose(email: str | None) -> MailboxPurposeResult:
    """Classify functional mailbox purpose from the email local-part only."""
    local = extract_local_part(email)
    if not local:
        return MailboxPurposeResult(
            purpose=PURPOSE_UNKNOWN,
            local_part="",
            send_blocked=False,
            block_reason=None,
            rank=PURPOSE_RANK[PURPOSE_UNKNOWN],
        )

    token = normalize_local_token(local)
    # Also match first segment before common separators for multi-word locals.
    head = re.split(r"[._\-]", local)[0]

    def _match(bucket: frozenset[str]) -> bool:
        if local in bucket or head in bucket:
            return True
        # Compact forms: trabalheconosco, noreply, etc.
        for alias in bucket:
            a = normalize_local_token(alias)
            if a and (token == a or token.startswith(a) or a in token):
                return True
        return False

    if _match(_BLOCKED_NOREPLY):
        purpose = PURPOSE_NOREPLY
    elif _match(_BLOCKED_HR):
        purpose = PURPOSE_HR_RECRUITING
    elif _match(_BLOCKED_PRIVACY):
        purpose = PURPOSE_PRIVACY_DPO
    elif _match(_BLOCKED_SUPPORT):
        purpose = PURPOSE_SUPPORT_SAC
    elif _match(_CONTRATOS):
        purpose = PURPOSE_CONTRATOS
    elif _match(_LICITACOES):
        purpose = PURPOSE_LICITACOES
    elif _match(_ENGENHARIA):
        purpose = PURPOSE_ENGENHARIA
    elif _match(_ORCAMENTO):
        purpose = PURPOSE_ORCAMENTO
    elif _match(_COMERCIAL):
        purpose = PURPOSE_COMERCIAL
    elif _match(_DIRETORIA):
        purpose = PURPOSE_DIRETORIA
    elif _match(_FINANCEIRO):
        purpose = PURPOSE_FINANCEIRO
    elif _match(_GENERIC):
        purpose = PURPOSE_GENERIC_CONTACT
    else:
        purpose = PURPOSE_UNKNOWN

    blocked = purpose in BLOCKED_PURPOSES
    reason = f"mailbox_purpose_blocked:{purpose}" if blocked else None
    return MailboxPurposeResult(
        purpose=purpose,
        local_part=local,
        send_blocked=blocked,
        block_reason=reason,
        rank=PURPOSE_RANK.get(purpose, 99),
    )


def is_mailbox_send_allowed(email: str | None) -> bool:
    return not classify_mailbox_purpose(email).send_blocked


def purpose_preference_rank(email: str | None) -> int:
    return classify_mailbox_purpose(email).rank
