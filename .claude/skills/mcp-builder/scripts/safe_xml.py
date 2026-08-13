"""Hardened XML parsing for MCP evaluation fixtures."""

from pathlib import Path

from lxml import etree


def parse_xml_safely(file_path: Path) -> etree._ElementTree:
    """Parse local XML without resolving entities or fetching network resources."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.parse(str(file_path), parser)
