#!/bin/bash
# ============================================================================
# UFW Rules for PostgreSQL Hardening — Extra Consultoria
# ============================================================================
#
# Restringe acesso a porta 54399 do PostgreSQL apenas a fontes confiaveis.
#
# Uso:
#   sudo ./ufw-rules.sh [apply|status|remove]
#
# Seguranca:
#   - Bloqueia porta 54399 para qualquer origem nao autorizada
#   - Libera apenas IPs explicitamente configurados em TRUSTED_IPS
#   - Nao afeta outras portas ou servicos
#   - Mantem sessao SSH ativa (porta 22) para evitar lockout
#
# Technical Debt: TD-SEC-02 (MEDIUM)
# Story: TD-5.4 — Hardening de Seguranca
# ============================================================================

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

# Porta PostgreSQL customizada (diferente do default 5432)
PG_PORT=54399

# IPs confiaveis que podem acessar o banco
# Formato: "IP1 IP2 ..." (espacos como separadores)
TRUSTED_IPS="${TRUSTED_IPS:-}"

# Nome da regra UFW para identificacao
RULE_COMMENT="extra-postgresql-${PG_PORT}"

# ============================================================================
# Functions
# ============================================================================

usage() {
    echo "Uso: $0 [apply|status|remove]"
    echo ""
    echo "Comandos:"
    echo "  apply   — Aplica as regras de firewall (padrao)"
    echo "  status  — Mostra o estado atual das regras"
    echo "  remove  — Remove as regras de firewall do PostgreSQL"
    echo ""
    echo "Variaveis de ambiente:"
    echo "  TRUSTED_IPS  — Lista de IPs autorizados (obrigatorio para apply)"
    echo ""
    echo "Exemplo:"
    echo "  TRUSTED_IPS='192.168.1.100 10.0.0.50' sudo ./ufw-rules.sh apply"
    exit 1
}

check_prerequisites() {
    if [[ $EUID -ne 0 ]]; then
        echo "ERRO: Este script deve ser executado como root (sudo)."
        exit 1
    fi

    if ! command -v ufw &>/dev/null; then
        echo "ERRO: UFW nao encontrado. Instale com: apt install ufw"
        exit 1
    fi

    if ! ufw status | grep -q "Status: active"; then
        echo "AVISO: UFW nao esta ativo."
        echo "Ative com: ufw --force enable"
        echo "Continuando mesmo assim..."
    fi
}

apply_rules() {
    if [[ -z "$TRUSTED_IPS" ]]; then
        echo "ERRO: TRUSTED_IPS nao definido."
        echo "Defina os IPs autorizados:"
        echo "  TRUSTED_IPS='IP1 IP2 ...' sudo $0 apply"
        echo ""
        echo "Para acesso apenas localhost, use:"
        echo "  TRUSTED_IPS='127.0.0.1' sudo $0 apply"
        exit 1
    fi

    echo "=== Aplicando regras UFW para PostgreSQL porta ${PG_PORT} ==="
    echo ""

    # Remove regras existentes para esta porta (evitar duplicatas)
    echo "[1/4] Removendo regras anteriores para porta ${PG_PORT}..."
    while ufw status numbered | grep -q "${PG_PORT}"; do
        RULE_NUM=$(ufw status numbered | grep "${PG_PORT}" | head -1 | sed 's/^\[//' | sed 's/\].*//' | tr -d ' ')
        if [[ -n "$RULE_NUM" ]]; then
            ufw --force delete "$RULE_NUM" 2>/dev/null || true
        fi
    done

    # Libera IPs confiaveis
    echo "[2/4] Liberando IPs autorizados..."
    IP_COUNT=0
    for ip in $TRUSTED_IPS; do
        ip_trimmed=$(echo "$ip" | xargs)
        if [[ -n "$ip_trimmed" ]]; then
            ufw allow from "$ip_trimmed" to any port "$PG_PORT" comment "${RULE_COMMENT}-trusted"
            echo "  + Liberado: $ip_trimmed"
            IP_COUNT=$((IP_COUNT + 1))
        fi
    done

    if [[ $IP_COUNT -eq 0 ]]; then
        echo "  AVISO: Nenhum IP valido configurado em TRUSTED_IPS"
    fi

    # Bloqueia qualquer outra origem para esta porta
    echo "[3/4] Bloqueando outras origens..."
    ufw deny "$PG_PORT" comment "${RULE_COMMENT}-deny"

    # Verifica regras
    echo "[4/4] Verificando regras aplicadas..."
    echo ""
    ufw status | grep "${PG_PORT}" || echo "  Nenhuma regra encontrada para porta ${PG_PORT}"

    echo ""
    echo "=== Aplicacao concluida ==="
    echo "Porta ${PG_PORT} bloqueada para origens nao autorizadas."
    echo ""
    echo "Para verificar: ufw status | grep ${PG_PORT}"
    echo "Para testar de um IP externo: nc -zv <SERVER_IP> ${PG_PORT}"
}

show_status() {
    echo "=== Status das regras UFW para PostgreSQL porta ${PG_PORT} ==="
    echo ""
    ufw status | grep "${PG_PORT}" || echo "Nenhuma regra encontrada para porta ${PG_PORT}."
    echo ""
    echo "=== Status geral do UFW ==="
    ufw status verbose
}

remove_rules() {
    echo "=== Removendo regras UFW para PostgreSQL porta ${PG_PORT} ==="
    echo ""

    local removed=0
    while ufw status numbered | grep -q "${PG_PORT}"; do
        RULE_NUM=$(ufw status numbered | grep "${PG_PORT}" | head -1 | sed 's/^\[//' | sed 's/\].*//' | tr -d ' ')
        if [[ -n "$RULE_NUM" ]]; then
            ufw --force delete "$RULE_NUM" 2>/dev/null || true
            removed=$((removed + 1))
        fi
    done

    echo "Removidas ${removed} regras para porta ${PG_PORT}."
    echo "AVISO: A porta ${PG_PORT} agora esta acessivel a todas as origens (se nao houver outras regras)."
}

# ============================================================================
# Main
# ============================================================================

check_prerequisites

case "${1:-apply}" in
    apply)
        apply_rules
        ;;
    status)
        show_status
        ;;
    remove)
        remove_rules
        ;;
    *)
        usage
        ;;
esac
