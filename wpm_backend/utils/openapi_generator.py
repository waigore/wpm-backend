"""Utility to generate OpenAPI JSON specification from FastAPI app."""

import json
import logging
import os
import sys
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def generate_openapi_spec(app: FastAPI, output_path: str = "SPEC/openapi.json") -> None:
    """
    Generate OpenAPI 3.0 JSON specification from the FastAPI app instance.

    Args:
        app: FastAPI application instance
        output_path: Path to write the OpenAPI JSON file (default: "SPEC/openapi.json")
    """
    try:
        # Create SPEC directory if it doesn't exist
        spec_dir = os.path.dirname(output_path)
        if spec_dir:
            os.makedirs(spec_dir, exist_ok=True)

        # Generate OpenAPI schema
        openapi_schema = app.openapi()

        # Write to file
        with open(output_path, "w") as f:
            json.dump(openapi_schema, f, indent=2)

        logger.info(f"OpenAPI specification generated: {output_path}")
    except Exception as e:
        logger.error(f"Failed to generate OpenAPI specification: {e}", exc_info=True)
        raise


def main() -> None:
    """
    Entry point for the OpenAPI generation CLI command.

    Creates a FastAPI app instance and generates the OpenAPI specification file.
    """
    try:
        from wpm_backend.main import create_app

        # Create FastAPI app instance
        app = create_app()

        # Generate OpenAPI specification
        generate_openapi_spec(app)

        print(f"OpenAPI specification generated: SPEC/openapi.json")
    except Exception as e:
        print(f"Error: Failed to generate OpenAPI specification: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

