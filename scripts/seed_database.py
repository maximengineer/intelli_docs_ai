import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.documents.service import get_document_service


def main() -> None:
    service = get_document_service()
    for path in sorted((ROOT / "data" / "sample_documents").glob("*.txt")):
        document = service.upload(path.name, path.read_bytes())
        print(f"{document.document_id} {document.filename} {document.status}")


if __name__ == "__main__":
    main()
