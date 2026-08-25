from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.core.models import DocumentChunk, ChunkMetadata
from src.core.logging import logger


VALID_PRODUCT_LINES = frozenset({"Standard", "Pro", "All"})


class MarkdownCorpusParser:
    def __init__(self, corpus_dir: Path, manifest_path: Optional[Path] = None):
        self.corpus_dir = Path(corpus_dir)
        self.manifest_path = Path(manifest_path) if manifest_path else self.corpus_dir / "manifest.json"
        self.manifest_loaded: bool = False
        self.manifest_version: Optional[str] = None
        self.manifest_source_ids: set[str] = set()
        self.manifest_meta: Dict[str, Dict[str, Any]] = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Dict[str, Any]]:
        if not self.manifest_path.exists():
            logger.warning(f"Manifest not found at {self.manifest_path}")
            return {}
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = {}
            for doc in data.get("documents", []):
                meta[doc.get("id")] = doc
                meta[doc.get("path")] = doc
                if doc.get("id"):
                    self.manifest_source_ids.add(doc["id"])
            self.manifest_version = data.get("version")
            self.manifest_loaded = True
            return meta
        except Exception as e:
            logger.error(f"Error reading manifest: {e}")
            return {}

    def _get_document_product_line(self, source_id: str) -> str:
        """Product line comes from the manifest — the single source of truth.

        A document without a manifest entry (or without a product_line field)
        is classified "All" with a WARNING; we never guess from filenames or
        content heuristics.
        """
        manifest_entry = self.manifest_meta.get(source_id)
        if manifest_entry is None:
            logger.warning(
                f"Document '{source_id}' has no manifest entry; defaulting product_line to 'All'. "
                f"Add it to {self.manifest_path.name} with an explicit product_line."
            )
            return "All"

        product_line = manifest_entry.get("product_line")
        if product_line is None:
            logger.warning(
                f"Manifest entry '{source_id}' has no product_line field; defaulting to 'All'."
            )
            return "All"
        if product_line not in VALID_PRODUCT_LINES:
            logger.warning(
                f"Manifest entry '{source_id}' has invalid product_line '{product_line}' "
                f"(expected one of {sorted(VALID_PRODUCT_LINES)}); defaulting to 'All'."
            )
            return "All"
        return product_line

    def _is_archived_doc(self, source_id: str, title: str, text: str) -> bool:
        if source_id == "firmware-archive" or "archive" in source_id.lower():
            return True
        if "superseded" in title.lower() or "superseded" in text.lower()[:100]:
            return True
        return False

    def parse_file(self, file_path: Path) -> List[DocumentChunk]:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        doc_id = file_path.stem
        manifest_entry = self.manifest_meta.get(doc_id, self.manifest_meta.get(file_path.name, {}))
        source_id = manifest_entry.get("id", doc_id)
        doc_title = manifest_entry.get("title", doc_id.replace("-", " ").title())
        doc_version = manifest_entry.get("version")
        effective_date = manifest_entry.get("effective_date")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        doc_product_line = self._get_document_product_line(source_id)

        lines = content.splitlines()
        chunks: List[DocumentChunk] = []

        header_stack: List[tuple[int, str]] = []
        current_section_lines: List[str] = []
        current_locator = doc_title

        def flush_chunk():
            nonlocal current_section_lines, current_locator, header_stack
            body = "\n".join(current_section_lines).strip()
            if not body:
                return

            header_path = [h[1] for h in header_stack]
            is_archived = self._is_archived_doc(source_id, current_locator, body)

            hash_input = f"{source_id}:{current_locator}:{body}".encode("utf-8")
            chunk_hash = hashlib.sha256(hash_input).hexdigest()
            chunk_id = f"{source_id}_{chunk_hash[:12]}"

            chunk_meta = ChunkMetadata(
                chunk_id=chunk_id,
                source_id=source_id,
                doc_title=doc_title,
                locator=current_locator,
                product_line=doc_product_line,
                is_archived=is_archived,
                effective_date=effective_date,
                version=doc_version,
                header_path=header_path,
                sha256=chunk_hash,
            )
            chunks.append(DocumentChunk(text=body, metadata=chunk_meta))
            current_section_lines = []

        header_re = re.compile(r"^(#{1,6})\s+(.*)$")

        for line in lines:
            m = header_re.match(line)
            if m:
                flush_chunk()
                level = len(m.group(1))
                h_text = m.group(2).strip()

                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()

                header_stack.append((level, h_text))
                current_locator = h_text
                current_section_lines.append(line)
            else:
                current_section_lines.append(line)

        flush_chunk()
        return chunks

    def parse_all(self) -> List[DocumentChunk]:
        all_chunks: List[DocumentChunk] = []
        for md_file in sorted(self.corpus_dir.glob("*.md")):
            all_chunks.extend(self.parse_file(md_file))
        logger.info(f"Parsed {len(all_chunks)} chunks from {len(list(self.corpus_dir.glob('*.md')))} files in {self.corpus_dir}")
        return all_chunks
