# Story: EXTRA-002 off-site joint backup/restore

**Status:** InProgress  
**Branch:** `feat/extra-002-offsite-backup`  
**Base:** `origin/main` @ `5e33bb951f70bd74d90c8a97405c932e7705a4de`  
**DECISION-ID:** `PREAPPROVED-EXTRA-002-2026-08-17`

## Goal

Fechar o ponto único de perda da VPS: CAS SHA-256 + backup cifrado conjunto de PostgreSQL + blobs + manifests + restore isolado com hash idêntico. Sem `VPS_OPERATIONAL`.

## Scope IN

- Rebase do PR #412
- Destino NFS já provisionado (Storagespace)
- store/get/head + réplica off-site + job fail-closed
- Pacote cifrado + transporte + restore isolado
- Política 24h / 8h / 14+8+12 / trimestral
- Prova para #271 e #277

## Scope OUT

- Compra de plano, WAL/PITR, restore em produção, purge de backups antigos
- Enable do timer em produção antes do merge
- Declaração `VPS_OPERATIONAL`

## DoD

Restore isolado com hash byte-a-byte; segredos fora de logs; job `failed` em falha de blob/backup; recorrência off até a prova.
