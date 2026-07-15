"""
Extra Construtora — Ledger de Verdade (Golden Path C).

Registro proprietário de:
- Oportunidades avaliadas
- Decisões (participar/não participar)
- Propostas apresentadas
- Resultados (vencida/perdida)
- Contratos ativos
- Contratos encerrados
- Atestados e capacidades

Formato: JSON file em data/extra_ledger.json
CLI-first, single-user, sem banco de dados.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date

LEDGER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "extra_ledger.json"
)


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


def _load() -> dict:
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH) as f:
            return json.load(f)
    return {
        "version": 1,
        "cliente": "Extra Construtora",
        "created_at": date.today().isoformat(),
        "oportunidades": [],
        "propostas": [],
        "contratos": [],
        "atestados": [],
        "capacidades": [],
        "notas": [],
    }


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Commands — Oportunidades
# ---------------------------------------------------------------------------


def cmd_oportunidade_add(args: argparse.Namespace) -> None:
    """Registra uma oportunidade avaliada."""
    data = _load()
    opp = {
        "id": len(data["oportunidades"]) + 1,
        "data_avaliacao": date.today().isoformat(),
        "orgao": args.orgao,
        "edital": args.edital,
        "objeto": args.objeto,
        "valor_estimado": args.valor,
        "decisao": args.decisao,  # participar / nao_participar / reavaliar
        "motivo": args.motivo or "",
        "confianca": args.confianca or "media",
        "pncp_id": args.pncp_id or "",
        "notas": args.notas or "",
    }
    data["oportunidades"].append(opp)
    _save(data)
    print(f"Oportunidade #{opp['id']} registrada: {args.decisao}")


def cmd_oportunidade_list(args: argparse.Namespace) -> None:
    """Lista oportunidades avaliadas."""
    data = _load()
    opps = data["oportunidades"]
    if args.decisao:
        opps = [o for o in opps if o["decisao"] == args.decisao]
    if not opps:
        print("Nenhuma oportunidade registrada.")
        return
    print(f"\n=== OPORTUNIDADES AVALIADAS ({len(opps)}) ===")
    for o in opps[-args.limit:]:
        icon = {"participar": "✅", "nao_participar": "❌", "reavaliar": "🔍"}
        print(f"  #{o['id']} {icon.get(o['decisao'], '?')} {o['orgao'][:40]}")
        print(f"       {o['objeto'][:60]} — R$ {o.get('valor_estimado', 0):,.2f}")
        print(f"       {o['data_avaliacao']} | {o['decisao']} | {o.get('motivo', '')[:50]}")


# ---------------------------------------------------------------------------
# Commands — Propostas
# ---------------------------------------------------------------------------


def cmd_proposta_add(args: argparse.Namespace) -> None:
    """Registra uma proposta apresentada."""
    data = _load()
    prop = {
        "id": len(data["propostas"]) + 1,
        "data_envio": args.data or date.today().isoformat(),
        "oportunidade_id": args.opp_id or None,
        "orgao": args.orgao,
        "edital": args.edital,
        "objeto": args.objeto,
        "valor_proposta": args.valor,
        "prazo_execucao_dias": args.prazo or None,
        "status": "enviada",  # enviada / habilitada / vencedora / perdedora
        "resultado_data": None,
        "resultado_valor": None,
        "motivo_perda": "",
        "notas": args.notas or "",
    }
    data["propostas"].append(prop)
    _save(data)
    print(f"Proposta #{prop['id']} registrada: R$ {args.valor:,.2f}")


def cmd_proposta_resultado(args: argparse.Namespace) -> None:
    """Registra o resultado de uma proposta."""
    data = _load()
    for p in data["propostas"]:
        if p["id"] == args.id:
            p["status"] = args.resultado  # vencedora / perdedora / habilitada
            p["resultado_data"] = date.today().isoformat()
            p["resultado_valor"] = args.valor_homologado or p["valor_proposta"]
            p["motivo_perda"] = args.motivo or ""
            if args.contrato_id:
                p["contrato_vinculo"] = args.contrato_id
            _save(data)
            print(f"Proposta #{args.id} → {args.resultado}")
            return
    print(f"Proposta #{args.id} não encontrada.")


def cmd_proposta_list(args: argparse.Namespace) -> None:
    """Lista propostas."""
    data = _load()
    props = data["propostas"]
    if args.status:
        props = [p for p in props if p["status"] == args.status]
    if not props:
        print("Nenhuma proposta registrada.")
        return

    total = sum(p.get("valor_proposta", 0) for p in props)
    vencidas = [p for p in props if p["status"] == "vencedora"]
    win_rate = len(vencidas) / len(props) * 100 if props else 0

    print(f"\n=== PROPOSTAS ({len(props)}) ===")
    print(f"Valor total proposto: R$ {total:,.2f}")
    print(f"Win rate: {win_rate:.0f}% ({len(vencidas)}/{len(props)})")
    print()
    for p in props[-args.limit:]:
        icon = {"vencedora": "🏆", "perdedora": "❌", "enviada": "📤", "habilitada": "✅"}
        print(f"  #{p['id']} {icon.get(p['status'], '?')} {p['orgao'][:40]}")
        print(f"       R$ {p.get('valor_proposta', 0):,.2f} | {p['status']} | {p.get('data_envio', '?')}")
        if p.get("motivo_perda"):
            print(f"       Perda: {p['motivo_perda'][:60]}")


# ---------------------------------------------------------------------------
# Commands — Contratos
# ---------------------------------------------------------------------------


def cmd_contrato_add(args: argparse.Namespace) -> None:
    """Registra um contrato da Extra (ativo ou histórico)."""
    data = _load()
    contrato = {
        "id": len(data["contratos"]) + 1,
        "orgao": args.orgao,
        "numero_contrato": args.numero or "",
        "objeto": args.objeto,
        "valor": args.valor,
        "data_inicio": args.inicio or date.today().isoformat(),
        "data_fim": args.fim or "",
        "status": args.status or "ativo",  # ativo / encerrado / suspenso / aditado
        "responsavel": args.responsavel or "",
        "proposta_id": args.proposta_id or None,
        "obrigacoes": [],
        "marcos": [],
        "aditivos": [],
        "medicoes": [],
        "notas": args.notas or "",
    }
    data["contratos"].append(contrato)
    _save(data)
    print(f"Contrato #{contrato['id']} registrado: R$ {args.valor:,.2f} — {args.status}")


def cmd_contrato_list(args: argparse.Namespace) -> None:
    """Lista contratos da Extra."""
    data = _load()
    contratos = data["contratos"]
    if args.status:
        contratos = [c for c in contratos if c["status"] == args.status]
    if not contratos:
        print("Nenhum contrato registrado.")
        print("Use: python scripts/extra_ledger/cli.py contrato add ...")
        return

    ativos = [c for c in data["contratos"] if c["status"] == "ativo"]
    total_valor = sum(c.get("valor", 0) for c in data["contratos"])
    total_ativos = sum(c.get("valor", 0) for c in ativos)

    print(f"\n=== CONTRATOS DA EXTRA ({len(contratos)}) ===")
    print(f"Valor total: R$ {total_valor:,.2f}")
    print(f"Ativos: {len(ativos)} — R$ {total_ativos:,.2f}")
    print()
    for c in contratos[-args.limit:]:
        icon = {"ativo": "🟢", "encerrado": "⚫", "suspenso": "🟡", "aditado": "🔵"}
        print(f"  #{c['id']} {icon.get(c['status'], '?')} {c['orgao'][:40]}")
        print(f"       {c['objeto'][:60]}")
        print(f"       R$ {c.get('valor', 0):,.2f} | {c['data_inicio']} → {c['data_fim']} | {c['status']}")


def cmd_contrato_evento(args: argparse.Namespace) -> None:
    """Adiciona evento a um contrato (marco, aditivo, medição, ocorrência)."""
    data = _load()
    for c in data["contratos"]:
        if c["id"] == args.id:
            evento = {
                "data": date.today().isoformat(),
                "tipo": args.tipo,  # marco / aditivo / medicao / ocorrencia / comunicacao
                "descricao": args.descricao,
                "valor": args.valor_evento or None,
            }
            if args.tipo == "aditivo":
                c.setdefault("aditivos", []).append(evento)
            elif args.tipo == "medicao":
                c.setdefault("medicoes", []).append(evento)
            elif args.tipo == "marco":
                c.setdefault("marcos", []).append(evento)
            else:
                c.setdefault("ocorrencias", []).append(evento)
            _save(data)
            print(f"Evento adicionado ao contrato #{args.id}: {args.tipo}")
            return
    print(f"Contrato #{args.id} não encontrado.")


# ---------------------------------------------------------------------------
# Commands — Dashboard
# ---------------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Visão consolidada da verdade da Extra."""
    data = _load()

    opps = data["oportunidades"]
    props = data["propostas"]
    contratos = data["contratos"]

    participar = [o for o in opps if o["decisao"] == "participar"]
    vencidas = [p for p in props if p["status"] == "vencedora"]
    ativos = [c for c in contratos if c["status"] == "ativo"]
    total_proposto = sum(p.get("valor_proposta", 0) for p in props)
    total_contratado = sum(c.get("valor", 0) for c in contratos)
    win_rate = len(vencidas) / len(props) * 100 if props else 0

    print("\n=== EXTRA CONSTRUTORA — LEDGER ===")
    print(f"Data: {date.today().strftime('%d/%m/%Y')}")
    print()
    print("--- OPORTUNIDADES ---")
    print(f"Avaliadas:    {len(opps)}")
    print(f"Participar:   {len(participar)}")
    print(f"Não partic.:  {len([o for o in opps if o['decisao'] == 'nao_participar'])}")
    print(f"Reavaliar:    {len([o for o in opps if o['decisao'] == 'reavaliar'])}")
    print()
    print("--- PROPOSTAS ---")
    print(f"Enviadas:     {len(props)}")
    print(f"Vencidas:     {len(vencidas)}")
    print(f"Win rate:     {win_rate:.0f}%")
    print(f"Valor prop.:  R$ {total_proposto:,.2f}")
    print()
    print("--- CONTRATOS ---")
    print(f"Total:        {len(contratos)}")
    print(f"Ativos:       {len(ativos)}")
    print(f"Valor total:  R$ {total_contratado:,.2f}")
    print(f"Valor ativos: R$ {sum(c.get('valor',0) for c in ativos):,.2f}")
    print()
    print("--- CAPACIDADES ---")
    print(f"Atestados:    {len(data['atestados'])}")
    print(f"Capacidades:  {len(data['capacidades'])}")
    print()
    if not opps and not props and not contratos:
        print("⚠️  Ledger vazio. Registre a primeira oportunidade:")
        print("  python scripts/extra_ledger/cli.py oportunidade add ...")
    elif not contratos:
        print("⚠️  Sem contratos registrados. Se há contratos ativos, cadastre-os:")
        print("  python scripts/extra_ledger/cli.py contrato add ...")


def cmd_capacidade_add(args: argparse.Namespace) -> None:
    """Registra capacidade técnica ou atestado."""
    data = _load()
    cap = {
        "id": len(data["capacidades"]) + 1,
        "tipo": args.tipo,  # atestado / capacidade_tecnica / equipe / equipamento
        "descricao": args.descricao,
        "orgao_emissor": args.orgao or "",
        "data_emissao": args.data_emissao or date.today().isoformat(),
        "validade": args.validade or "",
        "categoria": args.categoria or "",
    }
    data["capacidades"].append(cap)
    _save(data)
    print(f"Capacidade #{cap['id']} registrada: {args.tipo}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extra Ledger — Verdade proprietária da Extra Construtora",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/extra_ledger/cli.py dashboard
  python scripts/extra_ledger/cli.py oportunidade add --orgao "PMF" --edital "001/2026" \\
      --objeto "Reforma predial" --valor 500000 --decisao participar
  python scripts/extra_ledger/cli.py proposta add --orgao "PMF" --edital "001/2026" \\
      --objeto "Reforma predial" --valor 485000
  python scripts/extra_ledger/cli.py contrato add --orgao "PMF" --numero "CT-001/2026" \\
      --objeto "Reforma Escola X" --valor 485000 --status ativo
""",
    )
    sub = parser.add_subparsers(dest="command")

    # dashboard
    sub.add_parser("dashboard", help="Visão consolidada do ledger")

    # oportunidade
    opp = sub.add_parser("oportunidade", help="Gerenciar oportunidades")
    opp_sub = opp.add_subparsers(dest="subcommand")
    opp_add = opp_sub.add_parser("add", help="Registrar oportunidade avaliada")
    opp_add.add_argument("--orgao", required=True)
    opp_add.add_argument("--edital", default="")
    opp_add.add_argument("--objeto", required=True)
    opp_add.add_argument("--valor", type=float, default=0)
    opp_add.add_argument("--decisao", required=True, choices=["participar", "nao_participar", "reavaliar"])
    opp_add.add_argument("--motivo", default="")
    opp_add.add_argument("--confianca", default="media")
    opp_add.add_argument("--pncp-id", default="")
    opp_add.add_argument("--notas", default="")
    opp_list = opp_sub.add_parser("list", help="Listar oportunidades")
    opp_list.add_argument("--decisao", default="")
    opp_list.add_argument("--limit", type=int, default=20)

    # proposta
    prop = sub.add_parser("proposta", help="Gerenciar propostas")
    prop_sub = prop.add_subparsers(dest="subcommand")
    prop_add = prop_sub.add_parser("add", help="Registrar proposta")
    prop_add.add_argument("--orgao", required=True)
    prop_add.add_argument("--edital", default="")
    prop_add.add_argument("--objeto", required=True)
    prop_add.add_argument("--valor", type=float, required=True)
    prop_add.add_argument("--prazo", type=int, default=None)
    prop_add.add_argument("--opp-id", type=int, default=None)
    prop_add.add_argument("--data", default=None)
    prop_add.add_argument("--notas", default="")
    prop_res = prop_sub.add_parser("resultado", help="Registrar resultado")
    prop_res.add_argument("--id", type=int, required=True)
    prop_res.add_argument("--resultado", required=True, choices=["vencedora", "perdedora", "habilitada"])
    prop_res.add_argument("--valor-homologado", type=float, default=None)
    prop_res.add_argument("--motivo", default="")
    prop_res.add_argument("--contrato-id", type=int, default=None)
    prop_list = prop_sub.add_parser("list", help="Listar propostas")
    prop_list.add_argument("--status", default="")
    prop_list.add_argument("--limit", type=int, default=20)

    # contrato
    cont = sub.add_parser("contrato", help="Gerenciar contratos próprios")
    cont_sub = cont.add_subparsers(dest="subcommand")
    cont_add = cont_sub.add_parser("add", help="Registrar contrato")
    cont_add.add_argument("--orgao", required=True)
    cont_add.add_argument("--numero", default="")
    cont_add.add_argument("--objeto", required=True)
    cont_add.add_argument("--valor", type=float, required=True)
    cont_add.add_argument("--inicio", default=None)
    cont_add.add_argument("--fim", default="")
    cont_add.add_argument("--status", default="ativo", choices=["ativo", "encerrado", "suspenso", "aditado"])
    cont_add.add_argument("--responsavel", default="")
    cont_add.add_argument("--proposta-id", type=int, default=None)
    cont_add.add_argument("--notas", default="")
    cont_list = cont_sub.add_parser("list", help="Listar contratos")
    cont_list.add_argument("--status", default="")
    cont_list.add_argument("--limit", type=int, default=20)
    cont_evt = cont_sub.add_parser("evento", help="Registrar evento em contrato")
    cont_evt.add_argument("--id", type=int, required=True)
    cont_evt.add_argument("--tipo", required=True, choices=["marco", "aditivo", "medicao", "ocorrencia", "comunicacao"])
    cont_evt.add_argument("--descricao", required=True)
    cont_evt.add_argument("--valor-evento", type=float, default=None)

    # capacidade
    cap = sub.add_parser("capacidade", help="Gerenciar atestados e capacidades")
    cap_sub = cap.add_subparsers(dest="subcommand")
    cap_add = cap_sub.add_parser("add", help="Registrar capacidade")
    cap_add.add_argument("--tipo", required=True, choices=["atestado", "capacidade_tecnica", "equipe", "equipamento"])
    cap_add.add_argument("--descricao", required=True)
    cap_add.add_argument("--orgao", default="")
    cap_add.add_argument("--data-emissao", default=None)
    cap_add.add_argument("--validade", default="")
    cap_add.add_argument("--categoria", default="")
    _ = cap_sub.add_parser("list", help="Listar capacidades")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "oportunidade":
        if args.subcommand == "add":
            cmd_oportunidade_add(args)
        elif args.subcommand == "list":
            cmd_oportunidade_list(args)
        else:
            parser.print_help()
    elif args.command == "proposta":
        if args.subcommand == "add":
            cmd_proposta_add(args)
        elif args.subcommand == "resultado":
            cmd_proposta_resultado(args)
        elif args.subcommand == "list":
            cmd_proposta_list(args)
        else:
            parser.print_help()
    elif args.command == "contrato":
        if args.subcommand == "add":
            cmd_contrato_add(args)
        elif args.subcommand == "list":
            cmd_contrato_list(args)
        elif args.subcommand == "evento":
            cmd_contrato_evento(args)
        else:
            parser.print_help()
    elif args.command == "capacidade":
        if args.subcommand == "add":
            cmd_capacidade_add(args)
        elif args.subcommand == "list":
            data = _load()
            for c in data["capacidades"]:
                print(f"  #{c['id']} [{c['tipo']}] {c['descricao'][:60]}")
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
