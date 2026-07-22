"""Multi-key identity resolution — no first-wins on ambiguous cnpj8."""

from __future__ import annotations

from scripts.coverage.dual_capability_coverage import map_db_entities
from scripts.coverage.source_policy import identity_key
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse


def _ent(eid: str, name: str, mun: str, cnpj8: str = "00394494", ibge: str = "4205407") -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=1,
        razao_social=name,
        cnpj8=cnpj8,
        municipio=mun,
        codigo_ibge=ibge,
        natureza_juridica="Órgão Público do Poder Executivo Federal",
        latitude=None,
        longitude=None,
        distancia_km=None,
        radius_decision="included",
        within_radius=True,
        decision_method="test",
        identity_key=identity_key(cnpj8, mun, name),
        duplicate_root=True,
    )


class _FakeCur:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *a, **k):
        return None

    def fetchall(self):
        return self._rows

    def close(self):
        return None


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCur(self._rows)

    def rollback(self):
        return None


def test_ambiguous_cnpj8_resolved_by_identity_key_not_first_wins() -> None:
    entities = [
        _ent("e-mj", "MINISTERIO DA JUSTICA E SEGURANCA PUBLICA", "SANTA CATARINA", ibge="8105"),
        _ent("e-dpf", "SUPERINTENDENCIA REGIONAL DO DPF EM SANTA CATARINA", "FLORIANOPOLIS"),
        _ent("e-prf", "SUPERINTENDENCIA REG.POL.RODOV.FED. EM SANTA CATARINA", "FLORIANOPOLIS"),
        _ent("e-uni", "UNIVERSIDADE CORPORATIVA DA POLICIA RODOVIARIA FEDERAL", "FLORIANOPOLIS"),
    ]
    u = CanonicalUniverse(seed_path="t", seed_sha256="b" * 64, radius_km=200.0, entities=entities)
    rows = [
        (906, "00394494", "MINISTERIO DA JUSTICA E SEGURANCA PUBLICA", "SANTA CATARINA"),
        (2083, "00394494000309", "SUPERINTENDENCIA REGIONAL DO DPF EM SANTA CATARINA", "FLORIANOPOLIS"),
        (2084, "00394494012061", "SUPERINTENDENCIA REG.POL.RODOV.FED. EM SANTA CATARINA", "FLORIANOPOLIS"),
        (2085, "00394494015320", "UNIVERSIDADE CORPORATIVA DA POLICIA RODOVIARIA FEDERAL", "FLORIANOPOLIS"),
    ]
    metrics = map_db_entities(_FakeConn(rows), u)
    assert metrics.identity_unresolved_count == 0
    assert metrics.mapping_status != "identity_unresolved"
    assert metrics.db_entities_mapped == 4
    assert metrics.db_id_to_entity_id[906] == "e-mj"
    assert metrics.db_id_to_entity_id[2083] == "e-dpf"
    assert metrics.db_id_to_entity_id[2084] == "e-prf"
    assert metrics.db_id_to_entity_id[2085] == "e-uni"
    # Ambiguous root recorded for evidence without name, but not as entity unresolved
    assert "00394494" in metrics.ambiguous_cnpj8


def test_cnpj8_only_ambiguous_row_stays_unmapped() -> None:
    entities = [
        _ent("e1", "ALPHA", "CITY_A"),
        _ent("e2", "BETA", "CITY_B"),
    ]
    u = CanonicalUniverse(seed_path="t", seed_sha256="c" * 64, radius_km=200.0, entities=entities)
    # DB row has same root but no matching name/city → unmapped (not first-wins)
    rows = [(1, "00394494", "UNKNOWN ORG", "NOWHERE")]
    metrics = map_db_entities(_FakeConn(rows), u)
    assert metrics.db_entities_mapped == 0
    assert metrics.db_entities_unmapped == 1
    assert metrics.identity_unresolved_count == 0  # entities themselves are distinct
    assert 1 not in metrics.db_id_to_entity_id


def test_unique_cnpj8_still_maps() -> None:
    e = _ent("solo", "SOLO ORG", "TOWN", cnpj8="11223344")
    u = CanonicalUniverse(seed_path="t", seed_sha256="d" * 64, radius_km=200.0, entities=[e])
    rows = [(9, "11223344", "SOLO ORG", "TOWN")]
    metrics = map_db_entities(_FakeConn(rows), u)
    assert metrics.db_id_to_entity_id[9] == "solo"
    assert metrics.identity_unresolved_count == 0
